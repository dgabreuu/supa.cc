import hmac
import sys
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Optional
from uuid import uuid4

from keyring.errors import KeyringLocked, PasswordDeleteError

from keyring.backends import Windows

if sys.platform.startswith("linux"):
    from keyring.backends import SecretService
else:  # Keep simulated-platform tests independent of Linux-only dependencies.
    SecretService = SimpleNamespace(Keyring=type("UnavailableSecretService", (), {}))

if sys.platform == "darwin":
    from keyring.backends import macOS
else:
    try:
        from keyring.backends import macOS
    except ImportError:  # pragma: no cover - exercised on Windows CI
        macOS = SimpleNamespace(Keyring=type("UnavailableMacOSKeyring", (), {}))

from supa_cc.auth import (
    CredentialAccessError,
    CredentialPermissionDeniedError,
    CredentialReadError,
    SecretServiceUnavailableError,
)
from supa_cc.environment import Environment, OperatingSystem
from supa_cc.models import Account


_CREDENTIAL_SERVICE = "supa.cc.supabase.accounts.v2"
_MACOS_BACKEND_NAME = "keyring.backends.macOS.Keyring"
_SECRET_SERVICE_BACKEND_NAME = "keyring.backends.SecretService.Keyring"
_WINDOWS_BACKEND_NAME = "keyring.backends.Windows.WinVaultKeyring"
_MACOS_KEYCHAIN_ITEM_NOT_FOUND = "-25300"
_PERMISSION_ERROR_MARKERS = (
    "permission denied",
    "interaction is not allowed",
    "user interaction is not allowed",
)
_MISSING_ITEM_MARKERS = (
    "item not found",
    "could not be found",
    "no such item",
    "no such secret",
)
_SECRET_SERVICE_PASSWORD_MISSING = "no such password!"
_SECRET_SERVICE_UNAVAILABLE_MESSAGE = (
    "The Secret Service is unavailable. Check D-Bus and unlock "
    "the Secret Service."
)
_CREDENTIAL_STORE_UNAVAILABLE_MESSAGE = (
    "The credential store is unavailable."
)


@dataclass(frozen=True)
class CredentialStoreStatus:
    backend_name: str
    available: bool = True
    message: str = ""
    live_probed: bool = False


class CredentialStore:
    def __init__(self, backend_name: str, service: str = _CREDENTIAL_SERVICE):
        self.backend_name = backend_name
        self.service = service
        self._backend = _create_backend(backend_name)
        self._status = CredentialStoreStatus(backend_name=backend_name)

    def status(self) -> CredentialStoreStatus:
        return self._status

    def probe(self) -> CredentialStoreStatus:
        self._status = _probe_backend(self._backend, self.backend_name)
        return self._status

    def get(self, name: str) -> Optional[str]:
        try:
            return self._backend.get_password(self.service, name)
        except Exception as error:
            _raise_credential_operation_error(error, self.backend_name)

    def set(self, account: Account) -> None:
        try:
            self._backend.set_password(
                self.service,
                account.name,
                account.token,
            )
            saved_token = self._backend.get_password(self.service, account.name)
        except Exception as error:
            _raise_credential_operation_error(error, self.backend_name)

        if not isinstance(saved_token, str) or not hmac.compare_digest(
            account.token,
            saved_token,
        ):
            raise CredentialReadError(
                "Unable to verify the credential in the credential store."
            )

    def delete(self, name: str) -> None:
        try:
            self._backend.delete_password(self.service, name)
        except Exception as error:
            if _is_missing_credential(error):
                return
            _raise_credential_operation_error(error, self.backend_name)

    def matches(self, name: str, expected: str) -> bool:
        stored = self.get(name)
        return isinstance(stored, str) and hmac.compare_digest(stored, expected)


def create_credential_store(
    environment: Environment,
    service: str = _CREDENTIAL_SERVICE,
) -> CredentialStore:
    if environment.operating_system is OperatingSystem.MACOS:
        return CredentialStore(_MACOS_BACKEND_NAME, service=service)
    if environment.operating_system is OperatingSystem.LINUX and environment.is_supported:
        return CredentialStore(_SECRET_SERVICE_BACKEND_NAME, service=service)
    if environment.operating_system is OperatingSystem.WINDOWS:
        return CredentialStore(_WINDOWS_BACKEND_NAME, service=service)
    raise CredentialAccessError(
        "The credential store is unavailable in this environment."
    )


def _create_backend(backend_name: str):
    try:
        if backend_name == _MACOS_BACKEND_NAME:
            backend = _create_macos_backend()
            expected_backend_type = macOS.Keyring
        elif backend_name == _SECRET_SERVICE_BACKEND_NAME:
            backend = _create_secret_service_backend()
            expected_backend_type = SecretService.Keyring
        elif backend_name == _WINDOWS_BACKEND_NAME:
            backend = _create_windows_backend()
            expected_backend_type = Windows.WinVaultKeyring
        else:
            raise CredentialAccessError(_CREDENTIAL_STORE_UNAVAILABLE_MESSAGE)
    except Exception:
        raise CredentialAccessError(
            _CREDENTIAL_STORE_UNAVAILABLE_MESSAGE
        ) from None
    if type(backend) is not expected_backend_type:
        raise CredentialAccessError(_CREDENTIAL_STORE_UNAVAILABLE_MESSAGE)
    return backend


def _create_macos_backend():
    return macOS.Keyring()


def _create_secret_service_backend():
    return SecretService.Keyring()


def _create_windows_backend():
    return Windows.WinVaultKeyring()


def _probe_secret_service_provider() -> None:
    SecretService.Keyring.priority


def _probe_backend(backend, backend_name: str) -> CredentialStoreStatus:
    try:
        if backend_name == _SECRET_SERVICE_BACKEND_NAME:
            _probe_secret_service_provider()
            suffix = uuid4().hex
            backend.get_password(
                f"supa.cc.probe.{suffix}",
                f"probe-{suffix}",
            )
        elif backend_name == _MACOS_BACKEND_NAME:
            macOS.Keyring.priority
            suffix = uuid4().hex
            backend.get_password(
                f"supa.cc.probe.{suffix}",
                f"probe-{suffix}",
            )
        elif backend_name == _WINDOWS_BACKEND_NAME:
            suffix = uuid4().hex
            backend.get_password(
                f"supa.cc.probe.{suffix}",
                f"probe-{suffix}",
            )
        else:
            raise CredentialAccessError(_CREDENTIAL_STORE_UNAVAILABLE_MESSAGE)
    except Exception:
        return CredentialStoreStatus(
            backend_name=backend_name,
            available=False,
            message=_unavailable_message(backend_name),
            live_probed=True,
        )
    return CredentialStoreStatus(backend_name=backend_name, live_probed=True)


def _unavailable_message(backend_name: str) -> str:
    if backend_name == _SECRET_SERVICE_BACKEND_NAME:
        return _SECRET_SERVICE_UNAVAILABLE_MESSAGE
    return _CREDENTIAL_STORE_UNAVAILABLE_MESSAGE


def _raise_credential_operation_error(
    error: BaseException,
    backend_name: str,
) -> None:
    if backend_name == _SECRET_SERVICE_BACKEND_NAME:
        raise SecretServiceUnavailableError() from None
    message = str(error).lower()
    if isinstance(error, (KeyringLocked, PermissionError)) or any(
        marker in message for marker in _PERMISSION_ERROR_MARKERS
    ):
        raise CredentialPermissionDeniedError(
            "Credential-store access was not authorized."
        ) from None
    raise CredentialReadError(
        "Unable to access the credential in the credential store."
    ) from None


def _is_missing_credential(error: BaseException) -> bool:
    if not isinstance(error, PasswordDeleteError):
        return False
    message = str(error).strip().lower()
    return (
        message == _SECRET_SERVICE_PASSWORD_MISSING
        or _MACOS_KEYCHAIN_ITEM_NOT_FOUND in message
        or any(marker in message for marker in _MISSING_ITEM_MARKERS)
    )
