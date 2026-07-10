import os
import re
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


DEFAULT_ACTIVE_ACCOUNT_PATH = (
    Path.home() / ".config" / "supa.cc" / "active-account"
)
_ACCOUNT_NAME_REGEX = re.compile(r"[a-zA-Z0-9_-]{1,50}")
ACCESS_TOKEN_PREFIX = "sbp_"
ACCESS_TOKEN_BODY_CHARACTERS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._~-"
)
_ACCESS_TOKEN_REGEX = re.compile(
    r"sbp_(?:oauth_)?[a-f0-9]{40}",
    re.ASCII,
)
_PAT_CANDIDATE_REGEX = re.compile(
    r"sbp_(?:oauth_)?[a-f0-9]{40}",
    re.ASCII,
)
REDACTED = "[REDACTED]"


def is_valid_account_name(name: object) -> bool:
    return (
        isinstance(name, str)
        and not name.startswith(ACCESS_TOKEN_PREFIX)
        and not contains_pat(name)
        and _ACCOUNT_NAME_REGEX.fullmatch(name) is not None
    )


def is_valid_access_token(token: object) -> bool:
    """Valida o formato oficial aceito pelas Supabase CLI 2.98.2/2.109.1."""
    return (
        isinstance(token, str)
        and _ACCESS_TOKEN_REGEX.fullmatch(token) is not None
    )


def is_access_token_body_character(value: str) -> bool:
    return len(value) == 1 and value in ACCESS_TOKEN_BODY_CHARACTERS


class AuthFailureCode(str, Enum):
    NONE = "none"
    TOKEN_MISSING = "token_missing"
    TOKEN_FORMAT_INVALID = "token_format_invalid"
    TOKEN_REJECTED = "token_rejected"
    KEYCHAIN_PERMISSION_DENIED = "keychain_permission_denied"
    KEYCHAIN_READ_FAILED = "keychain_read_failed"
    CLI_NOT_FOUND = "cli_not_found"
    CLI_INCOMPATIBLE = "cli_incompatible"
    API_AUTH_FAILED = "api_auth_failed"
    NETWORK_FAILURE = "network_failure"
    ENVIRONMENT_BLOCKED = "environment_blocked"
    PROFILE_MISMATCH = "profile_mismatch"
    ACTIVE_ACCOUNT_MISSING = "active_account_missing"
    ACCOUNT_REQUIRED = "account_required"
    COMMAND_EMPTY = "command_empty"
    UNSAFE_ARGUMENT = "unsafe_argument"
    INDEX_INVALID = "index_invalid"
    INDEX_READ_FAILED = "index_read_failed"
    ACCOUNT_TRANSACTION_FAILED = "account_transaction_failed"
    ACTIVE_ACCOUNT_PERMISSION_DENIED = "active_account_permission_denied"
    ACTIVE_ACCOUNT_READ_FAILED = "active_account_read_failed"
    ACTIVE_ACCOUNT_WRITE_FAILED = "active_account_write_failed"
    ACTIVE_ACCOUNT_INVALID = "active_account_invalid"
    INVALID_INPUT = "invalid_input"
    COMMAND_FAILED = "command_failed"


class KeychainAccessError(RuntimeError):
    """Base segura para falhas de acesso ao Keychain."""


class KeychainPermissionDeniedError(KeychainAccessError):
    """O Keychain recusou acesso à credencial."""


class KeychainReadError(KeychainAccessError):
    """A credencial não pôde ser lida ou confirmada."""


class AccountIndexError(RuntimeError):
    """Base segura para falhas do índice local de contas."""


class AccountIndexInvalidError(AccountIndexError):
    """O índice existe, mas não respeita o formato esperado."""


class AccountIndexReadError(AccountIndexError):
    """O índice existe, mas não pôde ser lido."""


class AccountTransactionError(RuntimeError):
    """Uma mutação falhou e sua compensação não pôde ser confirmada."""


class ActiveAccountError(RuntimeError):
    """Base segura para falhas do arquivo de conta ativa."""


class ActiveAccountPermissionDeniedError(ActiveAccountError):
    """O arquivo de conta ativa não pôde ser lido por permissão."""


class ActiveAccountReadError(ActiveAccountError):
    """O arquivo de conta ativa não pôde ser lido."""


class ActiveAccountWriteError(ActiveAccountError):
    """O arquivo de conta ativa não pôde ser gravado."""


class ActiveAccountInvalidError(ActiveAccountError):
    """O arquivo de conta ativa contém um nome inválido."""


class InvalidAccessTokenError(ValueError):
    """O PAT fornecido não atende ao contrato seguro."""


class InvalidAccountNameError(ValueError):
    """O nome de conta fornecido não atende ao contrato."""


@dataclass(frozen=True)
class AuthResult:
    ok: bool
    code: AuthFailureCode
    message: str = field(repr=False)
    exit_code: int = 0

    def __bool__(self) -> bool:
        raise TypeError("AuthResult não é booleano; use .ok explicitamente.")

    @classmethod
    def success(cls, message: str = "Autenticação validada.") -> "AuthResult":
        return cls(
            ok=True,
            code=AuthFailureCode.NONE,
            message=message,
            exit_code=0,
        )

    @classmethod
    def failure(
        cls,
        code: AuthFailureCode,
        message: str,
        exit_code: int = 1,
    ) -> "AuthResult":
        return cls(
            ok=False,
            code=code,
            message=message,
            exit_code=exit_code,
        )


def classify_local_failure(error: BaseException) -> AuthResult:
    """Converte falhas locais em códigos e mensagens públicas sem detalhes."""
    if isinstance(error, InvalidAccessTokenError):
        return AuthResult.failure(
            AuthFailureCode.TOKEN_FORMAT_INVALID,
            "Token inválido: informe um PAT Supabase em formato sbp_ válido.",
            exit_code=2,
        )
    if isinstance(error, InvalidAccountNameError):
        return AuthResult.failure(
            AuthFailureCode.INVALID_INPUT,
            "Nome de conta inválido: use entre 1 e 50 caracteres, apenas "
            "letras, números, hífens e underscores.",
            exit_code=2,
        )
    if isinstance(error, KeychainPermissionDeniedError):
        return AuthResult.failure(
            AuthFailureCode.KEYCHAIN_PERMISSION_DENIED,
            "Acesso ao Keychain não autorizado.",
        )
    if isinstance(error, KeychainReadError):
        return AuthResult.failure(
            AuthFailureCode.KEYCHAIN_READ_FAILED,
            "Não foi possível acessar a credencial no Keychain.",
        )
    if isinstance(error, AccountIndexInvalidError):
        return AuthResult.failure(
            AuthFailureCode.INDEX_INVALID,
            "O índice local de contas é inválido.",
        )
    if isinstance(error, AccountIndexReadError):
        return AuthResult.failure(
            AuthFailureCode.INDEX_READ_FAILED,
            "Não foi possível ler o índice local de contas.",
        )
    if isinstance(error, AccountTransactionError):
        return AuthResult.failure(
            AuthFailureCode.ACCOUNT_TRANSACTION_FAILED,
            "A operação no Keychain não pôde ser concluída com segurança.",
        )
    if isinstance(error, ActiveAccountPermissionDeniedError):
        return AuthResult.failure(
            AuthFailureCode.ACTIVE_ACCOUNT_PERMISSION_DENIED,
            "Acesso ao arquivo de conta ativa não autorizado.",
        )
    if isinstance(error, ActiveAccountReadError):
        return AuthResult.failure(
            AuthFailureCode.ACTIVE_ACCOUNT_READ_FAILED,
            "Não foi possível ler o arquivo de conta ativa.",
        )
    if isinstance(error, ActiveAccountWriteError):
        return AuthResult.failure(
            AuthFailureCode.ACTIVE_ACCOUNT_WRITE_FAILED,
            "Não foi possível gravar o arquivo de conta ativa.",
        )
    if isinstance(error, ActiveAccountInvalidError):
        return AuthResult.failure(
            AuthFailureCode.ACTIVE_ACCOUNT_INVALID,
            "O arquivo de conta ativa contém um nome inválido.",
        )
    if isinstance(error, PermissionError):
        return AuthResult.failure(
            AuthFailureCode.ENVIRONMENT_BLOCKED,
            "O ambiente não autorizou a operação local.",
        )
    return AuthResult.failure(
        AuthFailureCode.COMMAND_FAILED,
        "A operação local não pôde ser concluída.",
    )


def sanitize_sensitive_text(value: object, secret: Optional[str] = None) -> str:
    """Remove PATs conhecidos e PATs com formato reconhecível de texto externo."""
    text = "" if value is None else str(value)
    if secret:
        text = text.replace(secret, REDACTED)
    return _PAT_CANDIDATE_REGEX.sub(REDACTED, text)


def contains_pat(value: object) -> bool:
    """Indica se um valor destinado a argv contém um PAT reconhecível."""
    return _PAT_CANDIDATE_REGEX.search(str(value)) is not None


def normalize_exit_code(value: object, default: int = 1) -> int:
    """Converte o retorno do processo para o intervalo portátil da CLI."""
    try:
        code = int(value)
    except (TypeError, ValueError):
        return default
    if code == 0:
        return 0
    return code if 1 <= code <= 255 else default


@dataclass(frozen=True)
class CommandResult:
    ok: bool
    code: AuthFailureCode
    message: str = field(repr=False)
    exit_code: int = 0
    stdout: str = field(default="", repr=False)
    stderr: str = field(default="", repr=False)

    def __bool__(self) -> bool:
        raise TypeError("CommandResult não é booleano; use .ok explicitamente.")

    @classmethod
    def success(
        cls,
        message: str = "Comando autenticado executado.",
        stdout: str = "",
        stderr: str = "",
    ) -> "CommandResult":
        return cls(
            ok=True,
            code=AuthFailureCode.NONE,
            message=message,
            exit_code=0,
            stdout=stdout,
            stderr=stderr,
        )

    @classmethod
    def failure(
        cls,
        code: AuthFailureCode,
        message: str,
        exit_code: int = 1,
        stdout: str = "",
        stderr: str = "",
    ) -> "CommandResult":
        normalized_exit_code = normalize_exit_code(exit_code)
        return cls(
            ok=False,
            code=code,
            message=message,
            exit_code=normalized_exit_code or 1,
            stdout=stdout,
            stderr=stderr,
        )


class ActiveAccountStore:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path is not None else DEFAULT_ACTIVE_ACCOUNT_PATH

    def read(self) -> Optional[str]:
        try:
            contents = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except PermissionError:
            raise ActiveAccountPermissionDeniedError(
                "Acesso ao arquivo de conta ativa não autorizado."
            ) from None
        except OSError:
            raise ActiveAccountReadError(
                "Não foi possível ler o arquivo de conta ativa."
            ) from None
        name = contents[:-1] if contents.endswith("\n") else contents
        if not is_valid_account_name(name):
            raise ActiveAccountInvalidError(
                "O arquivo de conta ativa contém um nome inválido."
            )
        return name

    def write(self, name: str) -> None:
        if not is_valid_account_name(name):
            raise ValueError("nome de conta inválido para persistência.")

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.parent.chmod(0o700)
        descriptor = None
        temporary_path = None
        try:
            descriptor, temporary_path = tempfile.mkstemp(
                prefix=f".{self.path.name}.",
                dir=self.path.parent,
            )
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                descriptor = None
                stream.write(f"{name}\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, self.path)
            temporary_path = None
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if temporary_path is not None:
                try:
                    os.unlink(temporary_path)
                except FileNotFoundError:
                    pass
