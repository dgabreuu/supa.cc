import hmac
from dataclasses import dataclass
from typing import Any, Callable, Optional

from keyring.backends import SecretService, macOS
from keyring.errors import KeyringLocked, PasswordDeleteError

from supa_cc.auth import (
    CredentialAccessError,
    CredentialPermissionDeniedError,
    CredentialReadError,
)
from supa_cc.environment import Environment, OperatingSystem
from supa_cc.models import Account


_CREDENTIAL_SERVICE = "supa.cc.supabase.accounts.v2"
_MACOS_BACKEND_NAME = "keyring.backends.macOS.Keyring"
_SECRET_SERVICE_BACKEND_NAME = "keyring.backends.SecretService.Keyring"
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
_SECRET_SERVICE_UNAVAILABLE_MESSAGE = (
    "O Secret Service não está disponível. Verifique o D-Bus e desbloqueie "
    "o Secret Service."
)
_CREDENTIAL_STORE_UNAVAILABLE_MESSAGE = (
    "O armazenamento de credenciais não está disponível."
)


@dataclass(frozen=True)
class CredentialStoreStatus:
    backend_name: str
    available: bool = True
    message: str = ""


class CredentialStore:
    def __init__(self, backend: Any, backend_name: str):
        expected_backend_type = _expected_backend_type(backend_name)
        if not _is_expected_backend(backend, expected_backend_type, backend_name):
            raise CredentialAccessError(_CREDENTIAL_STORE_UNAVAILABLE_MESSAGE)
        self._backend = backend
        self.backend_name = backend_name
        self._status = _probe_backend(
            backend,
            expected_backend_type,
            backend_name,
        )

    def status(self) -> CredentialStoreStatus:
        return self._status

    def get(self, name: str) -> Optional[str]:
        self._require_available()
        try:
            return self._backend.get_password(_CREDENTIAL_SERVICE, name)
        except Exception as error:
            _raise_credential_operation_error(error)

    def set(self, account: Account) -> None:
        self._require_available()
        try:
            self._backend.set_password(
                _CREDENTIAL_SERVICE,
                account.name,
                account.token,
            )
            saved_token = self._backend.get_password(_CREDENTIAL_SERVICE, account.name)
        except Exception as error:
            _raise_credential_operation_error(error)

        if not isinstance(saved_token, str) or not hmac.compare_digest(
            account.token,
            saved_token,
        ):
            raise CredentialReadError(
                "Não foi possível confirmar a credencial no armazenamento de credenciais."
            )

    def delete(self, name: str) -> None:
        self._require_available()
        try:
            self._backend.delete_password(_CREDENTIAL_SERVICE, name)
        except Exception as error:
            if _is_missing_credential(error):
                return
            _raise_credential_operation_error(error)

    def _require_available(self) -> None:
        if not self._status.available:
            raise CredentialAccessError(self._status.message)


def create_credential_store(
    environment: Environment,
    secret_service_factory: Callable[[], Any] = SecretService.Keyring,
    macos_factory: Callable[[], Any] = macOS.Keyring,
) -> CredentialStore:
    if environment.operating_system is OperatingSystem.MACOS:
        return CredentialStore(
            _create_backend(macos_factory),
            _MACOS_BACKEND_NAME,
        )
    if environment.operating_system is OperatingSystem.LINUX and environment.is_supported:
        return CredentialStore(
            _create_backend(secret_service_factory),
            _SECRET_SERVICE_BACKEND_NAME,
        )
    raise CredentialAccessError(
        "O armazenamento de credenciais não está disponível neste ambiente."
    )


def _create_backend(factory: Callable[[], Any]) -> Any:
    try:
        return factory()
    except Exception:
        raise CredentialAccessError(
            _CREDENTIAL_STORE_UNAVAILABLE_MESSAGE
        ) from None


def _expected_backend_type(backend_name: str) -> Any:
    if backend_name == _MACOS_BACKEND_NAME:
        return macOS.Keyring
    if backend_name == _SECRET_SERVICE_BACKEND_NAME:
        return SecretService.Keyring
    raise CredentialAccessError(_CREDENTIAL_STORE_UNAVAILABLE_MESSAGE)


def _is_expected_backend(
    backend: Any,
    expected_backend_type: Any,
    backend_name: str,
) -> bool:
    return type(backend) is expected_backend_type or _is_test_double(
        backend,
        backend_name,
    )


def _is_test_double(backend: Any, backend_name: str) -> bool:
    return (
        getattr(backend, "credential_store_test_double", False) is True
        and getattr(backend, "credential_store_backend_name", None) == backend_name
        and callable(getattr(backend, "credential_store_probe", None))
    )


def _probe_backend(
    backend: Any,
    expected_backend_type: Any,
    backend_name: str,
) -> CredentialStoreStatus:
    try:
        if _is_test_double(backend, backend_name):
            available = backend.credential_store_probe() is not False
        else:
            expected_backend_type.priority
            available = True
    except Exception:
        available = False

    if available:
        return CredentialStoreStatus(backend_name=backend_name)
    return CredentialStoreStatus(
        backend_name=backend_name,
        available=False,
        message=_unavailable_message(backend_name),
    )


def _unavailable_message(backend_name: str) -> str:
    if backend_name == _SECRET_SERVICE_BACKEND_NAME:
        return _SECRET_SERVICE_UNAVAILABLE_MESSAGE
    return _CREDENTIAL_STORE_UNAVAILABLE_MESSAGE


def _raise_credential_operation_error(error: BaseException) -> None:
    message = str(error).lower()
    if isinstance(error, (KeyringLocked, PermissionError)) or any(
        marker in message for marker in _PERMISSION_ERROR_MARKERS
    ):
        raise CredentialPermissionDeniedError(
            "Acesso ao armazenamento de credenciais não autorizado."
        ) from None
    raise CredentialReadError(
        "Não foi possível acessar a credencial no armazenamento de credenciais."
    ) from None


def _is_missing_credential(error: BaseException) -> bool:
    if not isinstance(error, PasswordDeleteError):
        return False
    message = str(error).lower()
    return _MACOS_KEYCHAIN_ITEM_NOT_FOUND in message or any(
        marker in message for marker in _MISSING_ITEM_MARKERS
    )
