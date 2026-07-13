import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from supa_cc.environment import config_directory
from supa_cc.security.tokens import (
    ACCESS_TOKEN_BODY_CHARACTERS,
    ACCESS_TOKEN_PREFIX,
    REDACTED,
    contains_pat,
    is_access_token_body_character,
    is_valid_access_token,
    sanitize_sensitive_text,
)
from supa_cc.state import atomic_write_text, read_text, secure_remove

_ACCOUNT_NAME_REGEX = re.compile(r"[a-zA-Z0-9_-]{1,50}")
_ACTIVE_ACCOUNT_MAX_BYTES = 256


def is_valid_account_name(name: object) -> bool:
    return (
        isinstance(name, str)
        and not name.startswith(ACCESS_TOKEN_PREFIX)
        and not contains_pat(name)
        and _ACCOUNT_NAME_REGEX.fullmatch(name) is not None
    )


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
    PLAINTEXT_FALLBACK_BLOCKED = "plaintext_fallback_blocked"
    NATIVE_LOGIN_FAILED = "native_login_failed"
    NATIVE_LOGOUT_FAILED = "native_logout_failed"
    NATIVE_VERIFICATION_FAILED = "native_verification_failed"
    SYNC_PENDING = "sync_pending"
    SYNC_ROLLBACK_FAILED = "sync_rollback_failed"


class CredentialAccessError(RuntimeError):
    """Base safe error for system credential-store access."""


class CredentialPermissionDeniedError(CredentialAccessError):
    """The system credential store denied access."""


class CredentialReadError(CredentialAccessError):
    """The credential could not be read or verified."""


class SecretServiceUnavailableError(CredentialAccessError):
    """Linux Secret Service cannot be used for the requested operation."""

    def __init__(self):
        super().__init__(
            "The Secret Service is unavailable. Check D-Bus and unlock "
            "the Secret Service."
        )


class KeychainAccessError(CredentialAccessError):
    """Safe base for Keychain access failures."""


class KeychainPermissionDeniedError(
    KeychainAccessError, CredentialPermissionDeniedError
):
    """The Keychain denied access to the credential."""


class KeychainReadError(KeychainAccessError, CredentialReadError):
    """The credential could not be read or verified."""


class AccountIndexError(RuntimeError):
    """Safe base for local account index failures."""


class AccountIndexInvalidError(AccountIndexError):
    """The index exists but does not use the expected format."""


class AccountIndexReadError(AccountIndexError):
    """The index exists but could not be read."""


class AccountTransactionError(RuntimeError):
    """A mutation failed and its compensation could not be verified."""


class ActiveAccountError(RuntimeError):
    """Safe base for active-account file failures."""


class ActiveAccountPermissionDeniedError(ActiveAccountError):
    """The active-account file could not be read because of permissions."""


class ActiveAccountReadError(ActiveAccountError):
    """The active-account file could not be read."""


class ActiveAccountWriteError(ActiveAccountError):
    """The active-account file could not be written."""


class ActiveAccountInvalidError(ActiveAccountError):
    """The active-account file contains an invalid name."""


class InvalidAccessTokenError(ValueError):
    """The supplied PAT does not meet the secure contract."""


class InvalidAccountNameError(ValueError):
    """The supplied account name does not meet the contract."""


@dataclass(frozen=True)
class AuthResult:
    ok: bool
    code: AuthFailureCode
    message: str = field(repr=False)
    exit_code: int = 0

    def __bool__(self) -> bool:
        raise TypeError("AuthResult is not boolean; use .ok explicitly.")

    @classmethod
    def success(cls, message: str = "Authentication validated.") -> "AuthResult":
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
    """Convert local failures to public codes and sanitized messages."""
    if isinstance(error, InvalidAccessTokenError):
        return AuthResult.failure(
            AuthFailureCode.TOKEN_FORMAT_INVALID,
            "Invalid token: provide a Supabase PAT in valid sbp_ format.",
            exit_code=2,
        )
    if isinstance(error, InvalidAccountNameError):
        return AuthResult.failure(
            AuthFailureCode.INVALID_INPUT,
            "Invalid account name: use 1 to 50 characters containing only "
            "letters, numbers, hyphens, and underscores.",
            exit_code=2,
        )
    if isinstance(error, KeychainPermissionDeniedError):
        return AuthResult.failure(
            AuthFailureCode.KEYCHAIN_PERMISSION_DENIED,
            "Keychain access was not authorized.",
        )
    if isinstance(error, CredentialPermissionDeniedError):
        return AuthResult.failure(
            AuthFailureCode.KEYCHAIN_PERMISSION_DENIED,
            "Credential-store access was not authorized.",
        )
    if isinstance(error, KeychainReadError):
        return AuthResult.failure(
            AuthFailureCode.KEYCHAIN_READ_FAILED,
            "Unable to access the Keychain credential.",
        )
    if isinstance(error, CredentialReadError):
        return AuthResult.failure(
            AuthFailureCode.KEYCHAIN_READ_FAILED,
            "Unable to access the credential-store credential.",
        )
    if isinstance(error, SecretServiceUnavailableError):
        return AuthResult.failure(
            AuthFailureCode.KEYCHAIN_READ_FAILED,
            str(error),
        )
    if isinstance(error, CredentialAccessError):
        return AuthResult.failure(
            AuthFailureCode.KEYCHAIN_READ_FAILED,
            "Unable to access the credential-store credential.",
        )
    if isinstance(error, AccountIndexInvalidError):
        return AuthResult.failure(
            AuthFailureCode.INDEX_INVALID,
            "The local account index is invalid.",
        )
    if isinstance(error, AccountIndexReadError):
        return AuthResult.failure(
            AuthFailureCode.INDEX_READ_FAILED,
            "Unable to read the local account index.",
        )
    if isinstance(error, AccountTransactionError):
        return AuthResult.failure(
            AuthFailureCode.ACCOUNT_TRANSACTION_FAILED,
            "The Keychain operation could not be completed safely.",
        )
    if isinstance(error, ActiveAccountPermissionDeniedError):
        return AuthResult.failure(
            AuthFailureCode.ACTIVE_ACCOUNT_PERMISSION_DENIED,
            "Access to the active-account file was not authorized.",
        )
    if isinstance(error, ActiveAccountReadError):
        return AuthResult.failure(
            AuthFailureCode.ACTIVE_ACCOUNT_READ_FAILED,
            "Unable to read the active-account file.",
        )
    if isinstance(error, ActiveAccountWriteError):
        return AuthResult.failure(
            AuthFailureCode.ACTIVE_ACCOUNT_WRITE_FAILED,
            "Unable to write the active-account file.",
        )
    if isinstance(error, ActiveAccountInvalidError):
        return AuthResult.failure(
            AuthFailureCode.ACTIVE_ACCOUNT_INVALID,
            "The active-account file contains an invalid name.",
        )
    if isinstance(error, PermissionError):
        return AuthResult.failure(
            AuthFailureCode.ENVIRONMENT_BLOCKED,
            "The environment did not authorize the local operation.",
        )
    return AuthResult.failure(
        AuthFailureCode.COMMAND_FAILED,
        "The local operation could not be completed.",
    )


def normalize_exit_code(value: object, default: int = 1) -> int:
    """Convert a process return value to the CLI's portable range."""
    try:
        code = int(value)
    except (TypeError, ValueError):
        return default
    if code == 0:
        return 0
    return code if 1 <= code <= 255 else default


def default_active_account_path() -> Path:
    return config_directory() / "active-account"


@dataclass(frozen=True)
class CommandResult:
    ok: bool
    code: AuthFailureCode
    message: str = field(repr=False)
    exit_code: int = 0
    stdout: str = field(default="", repr=False)
    stderr: str = field(default="", repr=False)

    def __bool__(self) -> bool:
        raise TypeError("CommandResult is not boolean; use .ok explicitly.")

    @classmethod
    def success(
        cls,
        message: str = "Authenticated command executed.",
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
        self.path = Path(path) if path is not None else default_active_account_path()

    def read(self) -> Optional[str]:
        try:
            contents = read_text(self.path, _ACTIVE_ACCOUNT_MAX_BYTES)
        except PermissionError:
            raise ActiveAccountPermissionDeniedError(
                "Access to the active-account file was not authorized."
            ) from None
        except OSError:
            raise ActiveAccountReadError(
                "Unable to read the active-account file."
            ) from None
        if contents is None:
            return None
        name = contents[:-1] if contents.endswith("\n") else contents
        if not is_valid_account_name(name):
            raise ActiveAccountInvalidError(
                "The active-account file contains an invalid name."
            )
        return name

    def write(self, name: str) -> None:
        if not is_valid_account_name(name):
            raise ValueError("invalid account name for persistence.")

        atomic_write_text(self.path, f"{name}\n")

    def clear(self) -> None:
        try:
            secure_remove(self.path)
        except PermissionError:
            raise ActiveAccountPermissionDeniedError(
                "Access to the active-account file was not authorized."
            ) from None
        except OSError:
            raise ActiveAccountWriteError(
                "Unable to remove the active-account file."
            ) from None
