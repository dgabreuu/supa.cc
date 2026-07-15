import hmac
import os
import re
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Optional
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
    CredentialAccessCancelledError,
    CredentialAccessError,
    CredentialInteractionUnavailableError,
    CredentialPermissionDeniedError,
    CredentialReadError,
    CredentialStoreLockedError,
    CredentialStoreUnavailableError,
    KeychainConfigurationError,
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
    "-60005",
)
_CANCELLED_ERROR_MARKERS = ("-60006", "-128")
_UNAVAILABLE_ERROR_MARKERS = ("-25291", "-25292")
_LOCKED_ERROR_MARKERS = ("-25293",)
_INVALID_CONFIGURATION_MARKERS = ("-25307",)
_INTERACTION_UNAVAILABLE_MARKERS = (
    "-25308",
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


_SECURITY_EXECUTABLE = "/usr/bin/security"


def _keychain_paths(output: str) -> tuple[Path, ...]:
    paths = []
    for line in output.splitlines():
        value = line.strip()
        if len(value) >= 2 and value[0] == value[-1] == '"':
            value = value[1:-1]
        if value:
            paths.append(Path(value))
    return tuple(paths)


def inspect_macos_keychain_configuration(
    *,
    run=subprocess.run,
    uid: Optional[int] = None,
) -> None:
    """Validate macOS Keychain routing without inspecting stored items."""
    owner = os.getuid() if uid is None else uid
    command_options = {
        "capture_output": True,
        "text": True,
        "check": False,
        "timeout": 5,
    }
    try:
        default_result = run(
            [_SECURITY_EXECUTABLE, "default-keychain", "-d", "user"],
            **command_options,
        )
        search_result = run(
            [_SECURITY_EXECUTABLE, "list-keychains", "-d", "user"],
            **command_options,
        )
    except (OSError, subprocess.SubprocessError):
        raise KeychainConfigurationError() from None

    default_paths = _keychain_paths(default_result.stdout)
    search_paths = _keychain_paths(search_result.stdout)
    if (
        default_result.returncode != 0
        or search_result.returncode != 0
        or len(default_paths) != 1
    ):
        raise KeychainConfigurationError()

    default = default_paths[0]
    if not default.is_absolute() or default not in search_paths:
        raise KeychainConfigurationError()
    try:
        metadata = default.lstat()
    except OSError:
        raise KeychainConfigurationError() from None
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != owner:
        raise KeychainConfigurationError()


_default_macos_keychain_preflight = inspect_macos_keychain_configuration


@dataclass(frozen=True)
class CredentialStoreStatus:
    backend_name: str
    available: bool = True
    message: str = ""
    live_probed: bool = False


class CredentialStore:
    def __init__(
        self,
        backend_name: str,
        service: str = _CREDENTIAL_SERVICE,
        preflight: Optional[Callable[[], None]] = None,
    ):
        self.backend_name = backend_name
        self.service = service
        self._preflight = preflight
        self._backend = _create_backend(backend_name)
        self._status = CredentialStoreStatus(backend_name=backend_name)

    def status(self) -> CredentialStoreStatus:
        return self._status

    def probe(self) -> CredentialStoreStatus:
        self._run_preflight()
        self._status = _probe_backend(self._backend, self.backend_name)
        return self._status

    def _run_preflight(self) -> None:
        if self._preflight is not None:
            self._preflight()

    def get(self, name: str) -> Optional[str]:
        self._run_preflight()
        try:
            return self._backend.get_password(self.service, name)
        except Exception as error:
            _raise_credential_operation_error(error, self.backend_name)

    def set(self, account: Account) -> None:
        self._run_preflight()
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
        self._run_preflight()
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
        return CredentialStore(
            _MACOS_BACKEND_NAME,
            service=service,
            preflight=_default_macos_keychain_preflight,
        )
    if environment.operating_system is OperatingSystem.LINUX:
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


def _probe_secret_service_without_unlock(backend, secretstorage_module=None) -> None:
    """Check the default collection without prompting for or changing its lock."""
    storage = (
        getattr(SecretService, "secretstorage")
        if secretstorage_module is None
        else secretstorage_module
    )
    connection = storage.dbus_init()
    try:
        if hasattr(backend, "preferred_collection"):
            collection = storage.Collection(
                connection, backend.preferred_collection
            )
        else:
            collection = storage.get_default_collection(connection)
        if collection.is_locked():
            raise KeyringLocked("The Secret Service collection is locked.")
        suffix = uuid4().hex
        collection.search_items(
            backend._query(
                f"supa.cc.probe.{suffix}",
                f"probe-{suffix}",
            )
        )
    finally:
        connection.close()


def _probe_backend(backend, backend_name: str) -> CredentialStoreStatus:
    try:
        if backend_name == _SECRET_SERVICE_BACKEND_NAME:
            _probe_secret_service_provider()
            _probe_secret_service_without_unlock(backend)
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
    if backend_name == _MACOS_BACKEND_NAME:
        if _contains_error_marker(message, _INVALID_CONFIGURATION_MARKERS):
            raise KeychainConfigurationError() from None
        if _contains_error_marker(message, _CANCELLED_ERROR_MARKERS):
            raise CredentialAccessCancelledError() from None
        if _contains_error_marker(message, _UNAVAILABLE_ERROR_MARKERS):
            raise CredentialStoreUnavailableError() from None
        if _contains_error_marker(message, _LOCKED_ERROR_MARKERS):
            raise CredentialStoreLockedError() from None
        if _contains_error_marker(message, _INTERACTION_UNAVAILABLE_MARKERS):
            raise CredentialInteractionUnavailableError() from None
        if isinstance(error, KeyringLocked):
            raise CredentialStoreLockedError() from None
    if isinstance(error, PermissionError) or _contains_error_marker(
        message, _PERMISSION_ERROR_MARKERS
    ):
        raise CredentialPermissionDeniedError(
            "Credential-store access was not authorized."
        ) from None
    raise CredentialReadError(
        "Unable to access the credential in the credential store."
    ) from None


def _contains_error_marker(message: str, markers: tuple[str, ...]) -> bool:
    for marker in markers:
        if marker.startswith("-"):
            if re.search(rf"(?<!\d){re.escape(marker)}(?!\d)", message):
                return True
        elif marker in message:
            return True
    return False


def _is_missing_credential(error: BaseException) -> bool:
    if not isinstance(error, PasswordDeleteError):
        return False
    message = str(error).strip().lower()
    return (
        message == _SECRET_SERVICE_PASSWORD_MISSING
        or _MACOS_KEYCHAIN_ITEM_NOT_FOUND in message
        or any(marker in message for marker in _MISSING_ITEM_MARKERS)
    )
