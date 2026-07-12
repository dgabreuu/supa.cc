import os
import re
import shutil
import stat
from typing import Callable, Optional, Sequence

from .auth import (ACCESS_TOKEN_PREFIX, AuthFailureCode, AuthResult, CommandResult,
                   contains_pat, is_access_token_body_character, normalize_exit_code)
from .models import Account
from .process import OutputSink, ProcessState, STREAM_SAMPLE_LIMIT, run_process

BinaryResolver = Callable[[str], Optional[str]]
AUTH_VALIDATION_TIMEOUT_SECONDS = 30
MINIMUM_VERSION = (2, 109, 1)
_SENSITIVE_ARGUMENTS = ("--token", "--access-token")
_VERSION_LINE = re.compile(r"^(?:supabase\s+version\s+)?(\d+)\.(\d+)\.(\d+)$", re.IGNORECASE)
_UNAUTHORIZED = re.compile(r"(?<!\d)401(?!\d)|\bunauthorized\b", re.IGNORECASE)
_MARKERS = {
    AuthFailureCode.TOKEN_MISSING: ("access token not provided", "access token is not provided", "missing access token", "supabase_access_token is not set"),
    AuthFailureCode.TOKEN_REJECTED: ("invalid access token",),
    AuthFailureCode.ENVIRONMENT_BLOCKED: ("eperm", "operation not permitted", "permission denied"),
    AuthFailureCode.NETWORK_FAILURE: ("connection refused", "connection reset", "could not resolve", "network is unreachable", "no such host", "temporary failure", "timed out", "timeout", "tls handshake"),
    AuthFailureCode.CLI_INCOMPATIBLE: ("unknown command", "unknown flag", "unrecognized command"),
    AuthFailureCode.PROFILE_MISMATCH: ("profile mismatch",),
    AuthFailureCode.API_AUTH_FAILED: ("authentication failed", "authentication error"),
}
_PRECEDENCE = (
    AuthFailureCode.TOKEN_REJECTED,
    AuthFailureCode.TOKEN_MISSING,
    AuthFailureCode.ENVIRONMENT_BLOCKED,
    AuthFailureCode.NETWORK_FAILURE,
    AuthFailureCode.CLI_INCOMPATIBLE,
    AuthFailureCode.PROFILE_MISMATCH,
    AuthFailureCode.API_AUTH_FAILED,
)
_MESSAGES = {
    AuthFailureCode.TOKEN_MISSING: "Token de acesso não foi fornecido à Supabase CLI.",
    AuthFailureCode.TOKEN_REJECTED: "O token foi rejeitado pela API da Supabase.",
    AuthFailureCode.ENVIRONMENT_BLOCKED: "O ambiente bloqueou a execução da Supabase CLI.",
    AuthFailureCode.NETWORK_FAILURE: "Não foi possível conectar à API da Supabase.",
    AuthFailureCode.CLI_INCOMPATIBLE: "A versão instalada da Supabase CLI não é compatível.",
    AuthFailureCode.PROFILE_MISMATCH: "O perfil da Supabase CLI não corresponde à conta selecionada.",
    AuthFailureCode.API_AUTH_FAILED: "A API da Supabase não pôde autenticar a conta.",
    AuthFailureCode.COMMAND_FAILED: "A Supabase CLI não pôde concluir o comando.",
}


class _StreamingPATRedactor:
    def __init__(self):
        self.pending, self.inside = "", False

    def feed(self, text, final=False):
        output = []
        for character in text:
            if self.inside and is_access_token_body_character(character):
                continue
            if self.inside:
                output.append("[REDACTED]")
                self.inside = False
            self.pending += character
            while self.pending and not ACCESS_TOKEN_PREFIX.startswith(self.pending):
                output.append(self.pending[0])
                self.pending = self.pending[1:]
            if self.pending == ACCESS_TOKEN_PREFIX:
                self.pending, self.inside = "", True
        if final:
            output.append("[REDACTED]" if self.inside else self.pending)
            self.pending, self.inside = "", False
        return "".join(output)


def _redact(text):
    redactor = _StreamingPATRedactor()
    return redactor.feed(text, final=True)


def _parse_version(stdout, stderr):
    for line in (stdout + "\n" + stderr).splitlines():
        match = _VERSION_LINE.fullmatch(line.strip())
        if match:
            return tuple(map(int, match.groups()))
    return None


class _FailureObserver:
    def __init__(self):
        self.tails, self.codes = {}, set()

    def feed(self, stream, text):
        normalized = self.tails.get(stream, "") + text.lower()
        if _UNAUTHORIZED.search(normalized):
            self.codes.add(AuthFailureCode.TOKEN_REJECTED)
        for code, markers in _MARKERS.items():
            if any(marker in normalized for marker in markers):
                self.codes.add(code)
        self.tails[stream] = normalized[-128:]

    def result(self):
        return next((code for code in _PRECEDENCE if code in self.codes), None)


def _contains_sensitive_argument(arguments: Sequence[str]) -> bool:
    for argument in arguments:
        lowered = argument.lower()
        if argument.startswith(ACCESS_TOKEN_PREFIX) or contains_pat(argument):
            return True
        if any(lowered == option or lowered.startswith(f"{option}=") for option in _SENSITIVE_ARGUMENTS):
            return True
    return False


class SupabaseCLI:
    def __init__(self, binary_resolver: Optional[BinaryResolver] = None,
                 validation_timeout_seconds: float = AUTH_VALIDATION_TIMEOUT_SECONDS):
        resolver = binary_resolver or shutil.which
        try:
            resolved = resolver("supabase")
        except OSError:
            resolved = None
        self.supabase_cli_invoked = os.path.abspath(resolved) if resolved else None
        self.supabase_cli = os.path.realpath(self.supabase_cli_invoked) if self.supabase_cli_invoked else None
        self.validation_timeout_seconds = validation_timeout_seconds

    def is_installed(self) -> bool:
        return self.supabase_cli is not None

    @staticmethod
    def _is_trusted(metadata):
        return (stat.S_ISREG(metadata.st_mode) and metadata.st_uid in {os.getuid(), 0}
                and bool(metadata.st_mode & stat.S_IXUSR)
                and not metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH))

    def _open_binary(self):
        if self.supabase_cli is None:
            return None, CommandResult.failure(AuthFailureCode.CLI_NOT_FOUND, "Supabase CLI não encontrada.")
        if os.name != "posix":
            return None, CommandResult.failure(AuthFailureCode.ENVIRONMENT_BLOCKED, _MESSAGES[AuthFailureCode.ENVIRONMENT_BLOCKED])
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(self.supabase_cli, flags)
        except FileNotFoundError:
            return None, CommandResult.failure(AuthFailureCode.CLI_NOT_FOUND, "Supabase CLI não encontrada.")
        except (PermissionError, OSError):
            return None, CommandResult.failure(AuthFailureCode.ENVIRONMENT_BLOCKED, _MESSAGES[AuthFailureCode.ENVIRONMENT_BLOCKED])
        try:
            opened = os.fstat(descriptor)
            current = os.stat(self.supabase_cli, follow_symlinks=False)
            if not self._is_trusted(opened) or not os.path.samestat(opened, current):
                raise PermissionError
            descriptor_root = "/proc/self/fd" if os.path.isdir("/proc/self/fd") else "/dev/fd"
            descriptor_path = f"{descriptor_root}/{descriptor}"
            if not os.path.exists(descriptor_root):
                raise PermissionError
            return (descriptor, descriptor_path), None
        except (FileNotFoundError, PermissionError, OSError):
            os.close(descriptor)
            return None, CommandResult.failure(AuthFailureCode.ENVIRONMENT_BLOCKED, _MESSAGES[AuthFailureCode.ENVIRONMENT_BLOCKED])

    def _run(self, arguments, env, stdout_sink=lambda _chunk: None, stderr_sink=lambda _chunk: None,
             sample_limit=STREAM_SAMPLE_LIMIT, timeout_seconds=None):
        opened, failure = self._open_binary()
        if failure is not None:
            return failure
        descriptor, descriptor_path = opened
        stdout_redactor, stderr_redactor = _StreamingPATRedactor(), _StreamingPATRedactor()
        observer = _FailureObserver()

        def publish(stream, redactor, sink, chunk):
            observer.feed(stream, chunk)
            sanitized = redactor.feed(chunk)
            if sanitized:
                sink(sanitized)

        try:
            process_result = run_process(
                [descriptor_path, *arguments], env,
                lambda chunk: publish("stdout", stdout_redactor, stdout_sink, chunk),
                lambda chunk: publish("stderr", stderr_redactor, stderr_sink, chunk),
                sample_limit, timeout_seconds, pass_fds=(descriptor,),
            )
            stdout_tail, stderr_tail = stdout_redactor.feed("", final=True), stderr_redactor.feed("", final=True)
            if stdout_tail:
                stdout_sink(stdout_tail)
            if stderr_tail:
                stderr_sink(stderr_tail)
            return self._command_result(process_result, observer.result())
        finally:
            os.close(descriptor)

    @staticmethod
    def _command_result(result, observed_code=None):
        if isinstance(result, CommandResult):
            return result
        stdout, stderr = _redact(result.stdout), _redact(result.stderr)
        if result.state is ProcessState.EXITED and result.exit_code == 0:
            return CommandResult.success(stdout=stdout, stderr=stderr)
        state_codes = {
            ProcessState.NOT_FOUND: AuthFailureCode.CLI_NOT_FOUND,
            ProcessState.PERMISSION_DENIED: AuthFailureCode.ENVIRONMENT_BLOCKED,
            ProcessState.INVALID_ARGUMENT: AuthFailureCode.UNSAFE_ARGUMENT,
            ProcessState.TIMED_OUT: AuthFailureCode.NETWORK_FAILURE,
        }
        code = state_codes.get(result.state)
        if code is None and result.state is ProcessState.EXITED:
            normalized = (result.stdout + "\n" + result.stderr).lower()
            found = {candidate for candidate, markers in _MARKERS.items()
                     if any(marker in normalized for marker in markers)}
            if _UNAUTHORIZED.search(normalized):
                found.add(AuthFailureCode.TOKEN_REJECTED)
            code = observed_code or next((candidate for candidate in _PRECEDENCE if candidate in found), AuthFailureCode.COMMAND_FAILED)
        code = code or AuthFailureCode.COMMAND_FAILED
        message = (_MESSAGES[AuthFailureCode.NETWORK_FAILURE] if result.state is ProcessState.TIMED_OUT
                   else _MESSAGES.get(code, _MESSAGES[AuthFailureCode.COMMAND_FAILED]))
        return CommandResult.failure(code, message, exit_code=normalize_exit_code(result.exit_code), stdout=stdout, stderr=stderr)

    def validate_access_token(self, account: Account) -> AuthResult:
        result = self.execute_authenticated(account, ["projects", "list"], timeout_seconds=self.validation_timeout_seconds)
        if result.ok:
            return AuthResult.success("Conta autenticada pela API da Supabase.")
        return AuthResult.failure(result.code, result.message, exit_code=result.exit_code)

    def login_with_access_token(self, account: Account, supabase_home=None, profile="supabase") -> AuthResult:
        if profile != "supabase":
            return self._native_profile_failure()
        return self._native_auth_result(self._execute_native(account, ["login"], supabase_home, profile),
                                         AuthFailureCode.NATIVE_LOGIN_FAILED, "Sessão nativa autenticada.")

    def verify_persisted_session(self, supabase_home=None, profile="supabase") -> AuthResult:
        if profile != "supabase":
            return self._native_profile_failure()
        return self._native_auth_result(self._execute_without_access_token(["projects", "list"], supabase_home, profile),
                                         AuthFailureCode.NATIVE_VERIFICATION_FAILED, "Sessão nativa verificada.")

    def logout_session(self, supabase_home=None, profile="supabase") -> AuthResult:
        if profile != "supabase":
            return self._native_profile_failure()
        return self._native_auth_result(self._execute_without_access_token(["logout", "--yes"], supabase_home, profile),
                                         AuthFailureCode.NATIVE_LOGOUT_FAILED, "Sessão nativa encerrada.")

    @staticmethod
    def _native_auth_result(result, fallback_code, success_message):
        if result.ok:
            return AuthResult.success(success_message)
        code = fallback_code if result.code is AuthFailureCode.COMMAND_FAILED else result.code
        return AuthResult.failure(code, result.message, exit_code=result.exit_code)

    @staticmethod
    def _native_profile_failure():
        return AuthResult.failure(
            AuthFailureCode.PROFILE_MISMATCH,
            _MESSAGES[AuthFailureCode.PROFILE_MISMATCH],
        )

    def _native_environment(self, supabase_home):
        env = os.environ.copy()
        env.pop("SUPABASE_ACCESS_TOKEN", None)
        if supabase_home is not None:
            env["SUPABASE_HOME"] = str(supabase_home)
        return env

    def _profile_arguments(self, arguments, profile):
        # A controlled empty home selects the official default on CLI builds
        # that do not expose an explicit profile flag.
        return list(arguments)

    def _execute_native(self, account, arguments, supabase_home, profile):
        if profile != "supabase":
            return self._native_profile_failure()
        argv, env, failure = self._prepare_authenticated_invocation(
            account, self._profile_arguments(arguments, profile)
        )
        if failure is not None:
            return failure
        if supabase_home is not None:
            env["SUPABASE_HOME"] = str(supabase_home)
        return self._run(argv, env, timeout_seconds=self.validation_timeout_seconds)

    def _execute_without_access_token(self, arguments, supabase_home=None, profile=None):
        if profile != "supabase":
            return self._native_profile_failure()
        env = self._native_environment(supabase_home)
        return self._run(self._profile_arguments(arguments, profile), env, timeout_seconds=self.validation_timeout_seconds)

    def _prepare_authenticated_invocation(self, account, arguments):
        command_arguments = [str(argument) for argument in arguments]
        if not command_arguments:
            return None, None, CommandResult.failure(AuthFailureCode.COMMAND_EMPTY, "Informe um comando da Supabase CLI para executar.")
        if _contains_sensitive_argument(command_arguments):
            return None, None, CommandResult.failure(AuthFailureCode.UNSAFE_ARGUMENT, "Argumentos que transportam token não são permitidos.")
        if not account.token:
            return None, None, CommandResult.failure(AuthFailureCode.TOKEN_MISSING, "Token de acesso não encontrado.")
        if not account.validate_token():
            return None, None, CommandResult.failure(AuthFailureCode.TOKEN_FORMAT_INVALID, "O token armazenado tem formato inválido.")
        env = os.environ.copy()
        env["SUPABASE_ACCESS_TOKEN"] = account.token
        return command_arguments, env, None

    def execute_authenticated(self, account: Account, arguments: Sequence[str], timeout_seconds: Optional[float] = None) -> CommandResult:
        return self._execute_authenticated_engine(account, arguments, lambda _chunk: None, lambda _chunk: None,
                                                  STREAM_SAMPLE_LIMIT, timeout_seconds)

    def execute_authenticated_streaming(self, account: Account, arguments: Sequence[str], stdout_sink: OutputSink,
                                        stderr_sink: OutputSink, sample_limit: int = STREAM_SAMPLE_LIMIT) -> CommandResult:
        return self._execute_authenticated_engine(account, arguments, stdout_sink, stderr_sink, sample_limit, None)

    def _execute_authenticated_engine(self, account, arguments, stdout_sink, stderr_sink, sample_limit, timeout_seconds):
        argv, env, failure = self._prepare_authenticated_invocation(account, arguments)
        if failure is not None:
            return failure
        return self._run(argv, env, stdout_sink, stderr_sink, sample_limit, timeout_seconds)

    def _version_command(self) -> CommandResult:
        env = os.environ.copy()
        env.pop("SUPABASE_ACCESS_TOKEN", None)
        return self._run(["--version"], env, timeout_seconds=self.validation_timeout_seconds)

    def detect_version(self):
        result = self._version_command()
        if not result.ok:
            return None
        return _parse_version(result.stdout, result.stderr)

    def preflight(self) -> AuthResult:
        result = self._version_command()
        if not result.ok:
            return AuthResult.failure(result.code, result.message, exit_code=result.exit_code)
        version = _parse_version(result.stdout, result.stderr)
        if version is None or version < MINIMUM_VERSION:
            return AuthResult.failure(AuthFailureCode.CLI_INCOMPATIBLE, "A versão instalada da Supabase CLI não é compatível.")
        return AuthResult.success("Supabase CLI compatível.")
