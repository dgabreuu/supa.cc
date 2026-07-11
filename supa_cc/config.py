import os
import codecs
import re
import signal
import shutil
import subprocess
import threading
import time
from typing import Callable, List, Optional, Sequence, Tuple

from .auth import (
    AuthFailureCode,
    ACCESS_TOKEN_PREFIX,
    AuthResult,
    CommandResult,
    contains_pat,
    is_access_token_body_character,
    normalize_exit_code,
    sanitize_sensitive_text,
)
from .models import Account


BinaryResolver = Callable[[str], Optional[str]]
OutputSink = Callable[[str], None]
AUTH_VALIDATION_TIMEOUT_SECONDS = 30
STREAM_SAMPLE_LIMIT = 8192
STREAM_SAMPLE_SEPARATOR = "\n...[truncated]...\n"

_TOKEN_MISSING_MARKERS = (
    "access token not provided",
    "access token is not provided",
    "missing access token",
    "supabase_access_token is not set",
)
_TOKEN_REJECTED_MARKERS = (
    "invalid access token",
)
_UNAUTHORIZED_RESPONSE_REGEX = re.compile(
    r"(?<!\d)401(?!\d)|\bunauthorized\b",
    re.IGNORECASE,
)
_NETWORK_MARKERS = (
    "connection refused",
    "connection reset",
    "could not resolve",
    "network is unreachable",
    "no such host",
    "temporary failure",
    "timed out",
    "timeout",
    "tls handshake",
)
_ENVIRONMENT_BLOCKED_MARKERS = (
    "eperm",
    "operation not permitted",
    "permission denied",
)
_CLI_INCOMPATIBLE_MARKERS = (
    "unknown command",
    "unknown flag",
    "unrecognized command",
)
_SENSITIVE_ARGUMENTS = ("--token", "--access-token")


def _contains_any(output: str, markers: tuple[str, ...]) -> bool:
    return any(marker in output for marker in markers)


def _classify_cli_failure(output: str) -> tuple[AuthFailureCode, str]:
    observer = _FailureObserver()
    observer.feed("combined", output)
    return observer.result()


def _failure_result(code: AuthFailureCode) -> tuple[AuthFailureCode, str]:
    if code is AuthFailureCode.TOKEN_MISSING:
        return (
            code,
            "Token de acesso não foi fornecido à Supabase CLI.",
        )
    if code is AuthFailureCode.TOKEN_REJECTED:
        return (
            code,
            "O token foi rejeitado pela API da Supabase.",
        )
    if code is AuthFailureCode.ENVIRONMENT_BLOCKED:
        return (
            code,
            "O ambiente bloqueou a execução da Supabase CLI.",
        )
    if code is AuthFailureCode.NETWORK_FAILURE:
        return (
            code,
            "Não foi possível conectar à API da Supabase.",
        )
    if code is AuthFailureCode.CLI_INCOMPATIBLE:
        return (
            code,
            "A versão instalada da Supabase CLI não é compatível.",
        )
    if code is AuthFailureCode.PROFILE_MISMATCH:
        return (
            code,
            "O perfil da Supabase CLI não corresponde à conta selecionada.",
        )
    if code is AuthFailureCode.API_AUTH_FAILED:
        return (
            code,
            "A API da Supabase não pôde autenticar a conta.",
        )
    return (
        AuthFailureCode.COMMAND_FAILED,
        "A Supabase CLI não pôde concluir o comando.",
    )


class _FailureObserver:
    _TAIL_LIMIT = 128
    _PRECEDENCE = (
        AuthFailureCode.TOKEN_REJECTED,
        AuthFailureCode.TOKEN_MISSING,
        AuthFailureCode.ENVIRONMENT_BLOCKED,
        AuthFailureCode.NETWORK_FAILURE,
        AuthFailureCode.CLI_INCOMPATIBLE,
        AuthFailureCode.PROFILE_MISMATCH,
        AuthFailureCode.API_AUTH_FAILED,
    )

    def __init__(self):
        self._tails = {}
        self._codes = set()
        self._lock = threading.Lock()

    def feed(self, stream: str, text: str) -> None:
        if not text:
            return
        with self._lock:
            normalized = self._tails.get(stream, "") + text.lower()
            if (
                _UNAUTHORIZED_RESPONSE_REGEX.search(normalized)
                or _contains_any(normalized, _TOKEN_REJECTED_MARKERS)
            ):
                self._codes.add(AuthFailureCode.TOKEN_REJECTED)
            if _contains_any(normalized, _TOKEN_MISSING_MARKERS):
                self._codes.add(AuthFailureCode.TOKEN_MISSING)
            if _contains_any(normalized, _ENVIRONMENT_BLOCKED_MARKERS):
                self._codes.add(AuthFailureCode.ENVIRONMENT_BLOCKED)
            if _contains_any(normalized, _NETWORK_MARKERS):
                self._codes.add(AuthFailureCode.NETWORK_FAILURE)
            if _contains_any(normalized, _CLI_INCOMPATIBLE_MARKERS):
                self._codes.add(AuthFailureCode.CLI_INCOMPATIBLE)
            if "profile mismatch" in normalized:
                self._codes.add(AuthFailureCode.PROFILE_MISMATCH)
            if (
                "authentication failed" in normalized
                or "authentication error" in normalized
            ):
                self._codes.add(AuthFailureCode.API_AUTH_FAILED)
            self._tails[stream] = normalized[-self._TAIL_LIMIT :]

    def result(self) -> tuple[AuthFailureCode, str]:
        with self._lock:
            for code in self._PRECEDENCE:
                if code in self._codes:
                    return _failure_result(code)
        return _failure_result(AuthFailureCode.COMMAND_FAILED)


def _contains_sensitive_argument(arguments: Sequence[str]) -> bool:
    for argument in arguments:
        lowered = argument.lower()
        transports_pat = argument.startswith(
            ACCESS_TOKEN_PREFIX
        ) or contains_pat(argument)
        uses_token_option = any(
            lowered == option or lowered.startswith(f"{option}=")
            for option in _SENSITIVE_ARGUMENTS
        )
        if transports_pat or uses_token_option:
            return True
    return False


class _StreamingPATRedactor:
    """Redator incremental que retém somente um possível prefixo `sbp_`."""

    def __init__(self):
        self._pending_prefix = ""
        self._inside_token = False

    def feed(self, text: str) -> str:
        output: List[str] = []
        for character in text:
            if self._inside_token:
                if is_access_token_body_character(character):
                    continue
                output.append("[REDACTED]")
                self._inside_token = False
                self._consume_normal(character, output)
            else:
                self._consume_normal(character, output)
        return "".join(output)

    def _consume_normal(self, character: str, output: List[str]) -> None:
        self._pending_prefix += character
        while self._pending_prefix and not ACCESS_TOKEN_PREFIX.startswith(
            self._pending_prefix
        ):
            output.append(self._pending_prefix[0])
            self._pending_prefix = self._pending_prefix[1:]
        if self._pending_prefix == ACCESS_TOKEN_PREFIX:
            self._pending_prefix = ""
            self._inside_token = True

    def finish(self) -> str:
        if self._inside_token:
            self._inside_token = False
            return "[REDACTED]"
        pending = self._pending_prefix
        self._pending_prefix = ""
        return pending


class _BoundedSample:
    def __init__(self, limit: int):
        self.limit = max(0, int(limit))
        content_limit = max(0, self.limit - len(STREAM_SAMPLE_SEPARATOR))
        self._head_limit = content_limit // 2
        self._tail_limit = content_limit - self._head_limit
        self._full = ""
        self._head = ""
        self._tail = ""
        self._truncated = False

    def add(self, text: str) -> None:
        if self.limit == 0 or not text:
            return
        if not self._truncated and len(self._full) + len(text) <= self.limit:
            self._full += text
            return
        if not self._truncated:
            combined = self._full + text
            self._head = combined[: self._head_limit]
            self._tail = combined[-self._tail_limit :] if self._tail_limit else ""
            self._full = ""
            self._truncated = True
            return
        if self._tail_limit:
            self._tail = (self._tail + text)[-self._tail_limit :]

    @property
    def value(self) -> str:
        if not self._truncated:
            return self._full
        if self.limit < len(STREAM_SAMPLE_SEPARATOR):
            return self._tail[-self.limit :]
        return self._head + STREAM_SAMPLE_SEPARATOR + self._tail


class SupabaseConfig:
    def __init__(
        self,
        binary_resolver: Optional[BinaryResolver] = None,
        validation_timeout_seconds: float = AUTH_VALIDATION_TIMEOUT_SECONDS,
    ):
        resolver = binary_resolver if binary_resolver is not None else shutil.which
        try:
            resolved = resolver("supabase")
        except OSError:
            resolved = None
        self.supabase_cli_invoked = os.path.abspath(resolved) if resolved else None
        self.supabase_cli = (
            os.path.realpath(self.supabase_cli_invoked)
            if self.supabase_cli_invoked
            else None
        )
        self.validation_timeout_seconds = validation_timeout_seconds

    def is_installed(self) -> bool:
        """Indica se um executável real da Supabase CLI foi resolvido."""
        return self.supabase_cli is not None

    def validate_access_token(self, account: Account) -> AuthResult:
        """Valida um PAT sem persistir ou alterar credenciais da Supabase CLI."""
        result = self.execute_authenticated(
            account,
            ["projects", "list"],
            timeout_seconds=self.validation_timeout_seconds,
        )
        if result.ok:
            return AuthResult.success("Conta autenticada pela API da Supabase.")
        return AuthResult.failure(
            result.code,
            result.message,
            exit_code=result.exit_code,
        )

    def login_with_access_token(self, account: Account) -> AuthResult:
        result = self.execute_authenticated(
            account, ["login"], timeout_seconds=self.validation_timeout_seconds
        )
        return self._native_auth_result(
            result, AuthFailureCode.NATIVE_LOGIN_FAILED, "Sessão nativa autenticada."
        )

    def verify_persisted_session(self) -> AuthResult:
        result = self._execute_without_access_token(["projects", "list"])
        return self._native_auth_result(
            result,
            AuthFailureCode.NATIVE_VERIFICATION_FAILED,
            "Sessão nativa verificada.",
        )

    def logout_session(self) -> AuthResult:
        result = self._execute_without_access_token(["logout", "--yes"])
        return self._native_auth_result(
            result, AuthFailureCode.NATIVE_LOGOUT_FAILED, "Sessão nativa encerrada."
        )

    @staticmethod
    def _native_auth_result(
        result: CommandResult, fallback_code: AuthFailureCode, success_message: str
    ) -> AuthResult:
        if result.ok:
            return AuthResult.success(success_message)
        code = fallback_code if result.code is AuthFailureCode.COMMAND_FAILED else result.code
        return AuthResult.failure(code, result.message, exit_code=result.exit_code)

    def _execute_without_access_token(self, arguments: Sequence[str]) -> CommandResult:
        if self.supabase_cli is None:
            return CommandResult.failure(
                AuthFailureCode.CLI_NOT_FOUND, "Supabase CLI não encontrada."
            )
        env = os.environ.copy()
        env.pop("SUPABASE_ACCESS_TOKEN", None)
        return self._execute_engine(
            [self.supabase_cli, *arguments],
            env,
            stdout_sink=lambda _chunk: None,
            stderr_sink=lambda _chunk: None,
            sample_limit=STREAM_SAMPLE_LIMIT,
            timeout_seconds=self.validation_timeout_seconds,
        )

    def execute_authenticated(
        self,
        account: Account,
        arguments: Sequence[str],
        timeout_seconds: Optional[float] = None,
    ) -> CommandResult:
        """Executa de modo bounded; usado pela validação read-only."""
        return self._execute_authenticated_engine(
            account,
            arguments,
            stdout_sink=lambda _chunk: None,
            stderr_sink=lambda _chunk: None,
            sample_limit=STREAM_SAMPLE_LIMIT,
            timeout_seconds=timeout_seconds,
        )

    def _prepare_authenticated_invocation(
        self,
        account: Account,
        arguments: Sequence[str],
    ) -> Tuple[
        Optional[List[str]],
        Optional[dict],
        Optional[CommandResult],
    ]:
        command_arguments = [str(argument) for argument in arguments]
        if not command_arguments:
            return None, None, CommandResult.failure(
                AuthFailureCode.COMMAND_EMPTY,
                "Informe um comando da Supabase CLI para executar.",
            )
        if _contains_sensitive_argument(command_arguments):
            return None, None, CommandResult.failure(
                AuthFailureCode.UNSAFE_ARGUMENT,
                "Argumentos que transportam token não são permitidos.",
            )
        if not account.token:
            return None, None, CommandResult.failure(
                AuthFailureCode.TOKEN_MISSING,
                "Token de acesso não encontrado.",
            )
        if not account.validate_token():
            return None, None, CommandResult.failure(
                AuthFailureCode.TOKEN_FORMAT_INVALID,
                "O token armazenado tem formato inválido.",
            )
        if self.supabase_cli is None:
            return None, None, CommandResult.failure(
                AuthFailureCode.CLI_NOT_FOUND,
                "Supabase CLI não encontrada.",
            )

        env = os.environ.copy()
        env["SUPABASE_ACCESS_TOKEN"] = account.token
        return [self.supabase_cli, *command_arguments], env, None

    def execute_authenticated_streaming(
        self,
        account: Account,
        arguments: Sequence[str],
        stdout_sink: OutputSink,
        stderr_sink: OutputSink,
        sample_limit: int = STREAM_SAMPLE_LIMIT,
    ) -> CommandResult:
        """Executa com stdin herdado e redige stdout/stderr enquanto chegam."""
        return self._execute_authenticated_engine(
            account,
            arguments,
            stdout_sink=stdout_sink,
            stderr_sink=stderr_sink,
            sample_limit=sample_limit,
            timeout_seconds=None,
        )

    def _execute_authenticated_engine(
        self,
        account: Account,
        arguments: Sequence[str],
        stdout_sink: OutputSink,
        stderr_sink: OutputSink,
        sample_limit: int,
        timeout_seconds: Optional[float],
    ) -> CommandResult:
        argv, env, failure = self._prepare_authenticated_invocation(
            account, arguments
        )
        if failure is not None:
            return failure
        assert argv is not None and env is not None

        return self._execute_engine(
            argv, env, stdout_sink, stderr_sink, sample_limit, timeout_seconds
        )

    def _execute_engine(
        self,
        argv: Sequence[str],
        env: dict,
        stdout_sink: OutputSink,
        stderr_sink: OutputSink,
        sample_limit: int,
        timeout_seconds: Optional[float],
    ) -> CommandResult:

        try:
            process = subprocess.Popen(
                argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                bufsize=0,
                start_new_session=(os.name == "posix"),
            )
        except FileNotFoundError:
            return CommandResult.failure(
                AuthFailureCode.CLI_NOT_FOUND,
                "Supabase CLI não encontrada.",
            )
        except PermissionError:
            return CommandResult.failure(
                AuthFailureCode.ENVIRONMENT_BLOCKED,
                "O ambiente bloqueou a execução da Supabase CLI.",
            )
        except ValueError:
            return CommandResult.failure(
                AuthFailureCode.UNSAFE_ARGUMENT,
                "Um argumento inválido foi bloqueado antes da execução.",
                exit_code=2,
            )
        except OSError:
            return CommandResult.failure(
                AuthFailureCode.COMMAND_FAILED,
                "A Supabase CLI não pôde ser executada.",
            )

        stdout_sample = _BoundedSample(sample_limit)
        stderr_sample = _BoundedSample(sample_limit)
        reader_errors: List[Exception] = []
        reader_failed = threading.Event()
        observer = _FailureObserver()

        def drain(
            stream_name: str,
            pipe,
            sink: OutputSink,
            sample: _BoundedSample,
        ) -> None:
            decoder = codecs.getincrementaldecoder("utf-8")("replace")
            redactor = _StreamingPATRedactor()
            sink_available = True

            def publish(text: str) -> None:
                nonlocal sink_available
                if not text:
                    return
                sample.add(text)
                observer.feed(stream_name, text)
                if not sink_available:
                    return
                try:
                    sink(text)
                except Exception as error:
                    if not reader_errors:
                        reader_errors.append(error)
                    sink_available = False
                    reader_failed.set()

            try:
                while True:
                    chunk = os.read(pipe.fileno(), 4096)
                    if not chunk:
                        break
                    publish(redactor.feed(decoder.decode(chunk)))
                publish(redactor.feed(decoder.decode(b"", final=True)))
                publish(redactor.finish())
            except Exception as error:
                if not reader_errors:
                    reader_errors.append(error)
                reader_failed.set()
            finally:
                pipe.close()

        assert process.stdout is not None and process.stderr is not None
        stdout_thread = threading.Thread(
            target=drain,
            args=("stdout", process.stdout, stdout_sink, stdout_sample),
        )
        stderr_thread = threading.Thread(
            target=drain,
            args=("stderr", process.stderr, stderr_sink, stderr_sample),
        )
        stdout_thread.start()
        stderr_thread.start()
        deadline = (
            time.monotonic() + timeout_seconds
            if timeout_seconds is not None
            else None
        )
        termination_reason = None
        try:
            while True:
                return_code = process.poll()
                if return_code is not None:
                    break
                if reader_failed.wait(timeout=0.02):
                    termination_reason = "reader"
                    self._terminate_process_group(process)
                    return_code = process.poll()
                    break
                if deadline is not None and time.monotonic() >= deadline:
                    termination_reason = "timeout"
                    self._terminate_process_group(process)
                    return_code = process.poll()
                    break
        except (KeyboardInterrupt, SystemExit):
            self._terminate_process_group(process)
            stdout_thread.join()
            stderr_thread.join()
            raise

        while stdout_thread.is_alive() or stderr_thread.is_alive():
            if reader_failed.is_set() and termination_reason is None:
                termination_reason = "reader"
                self._terminate_process_group(process)
            if (
                deadline is not None
                and time.monotonic() >= deadline
                and termination_reason is None
            ):
                termination_reason = "timeout"
                self._terminate_process_group(process)
            stdout_thread.join(timeout=0.02)
            stderr_thread.join(timeout=0.02)

        stdout_thread.join()
        stderr_thread.join()

        if termination_reason == "timeout":
            return CommandResult.failure(
                AuthFailureCode.NETWORK_FAILURE,
                "A comunicação com a API da Supabase excedeu o tempo limite.",
                stdout=stdout_sample.value,
                stderr=stderr_sample.value,
            )

        if reader_errors:
            return CommandResult.failure(
                AuthFailureCode.COMMAND_FAILED,
                "A saída da Supabase CLI não pôde ser processada.",
                stdout=stdout_sample.value,
                stderr=stderr_sample.value,
            )
        if return_code == 0:
            return CommandResult.success(
                stdout=stdout_sample.value,
                stderr=stderr_sample.value,
            )

        code, message = observer.result()
        return CommandResult.failure(
            code,
            message,
            exit_code=normalize_exit_code(return_code),
            stdout=stdout_sample.value,
            stderr=stderr_sample.value,
        )

    @staticmethod
    def _terminate_process_group(process: subprocess.Popen) -> None:
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
            try:
                process.wait(timeout=0.2)
            except (subprocess.TimeoutExpired, ProcessLookupError):
                pass
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            try:
                process.wait(timeout=1)
            except (subprocess.TimeoutExpired, ProcessLookupError):
                pass
            return

        try:
            process.terminate()
            process.wait(timeout=0.2)
        except (subprocess.TimeoutExpired, ProcessLookupError):
            try:
                process.kill()
                process.wait(timeout=1)
            except (subprocess.TimeoutExpired, ProcessLookupError):
                pass
