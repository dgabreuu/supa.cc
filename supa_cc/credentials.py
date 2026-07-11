import hmac
from dataclasses import dataclass
from typing import Optional
from uuid import uuid4

from keyring.backends import SecretService, macOS
from keyring.errors import KeyringLocked, PasswordDeleteError

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
    def __init__(self, backend_name: str, service: str = _CREDENTIAL_SERVICE):
        self.backend_name = backend_name
        self.service = service
        self._backend = _create_backend(backend_name)
        self._status = _probe_backend(self._backend, backend_name)

    def status(self) -> CredentialStoreStatus:
        return self._status

    def get(self, name: str) -> Optional[str]:
        self._require_available()
        try:
            return self._backend.get_password(self.service, name)
        except Exception as error:
            _raise_credential_operation_error(error, self.backend_name)

    def set(self, account: Account) -> None:
        self._require_available()
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
                "Não foi possível confirmar a credencial no armazenamento de credenciais."
            )

    def delete(self, name: str) -> None:
        self._require_available()
        try:
            self._backend.delete_password(self.service, name)
        except Exception as error:
            if _is_missing_credential(error):
                return
            _raise_credential_operation_error(error, self.backend_name)

    def _require_available(self) -> None:
        if not self._status.available:
            raise CredentialAccessError(self._status.message)


def create_credential_store(
    environment: Environment,
    service: str = _CREDENTIAL_SERVICE,
) -> CredentialStore:
    if environment.operating_system is OperatingSystem.MACOS:
        return CredentialStore(_MACOS_BACKEND_NAME, service=service)
    if environment.operating_system is OperatingSystem.LINUX and environment.is_supported:
        return CredentialStore(_SECRET_SERVICE_BACKEND_NAME, service=service)
    raise CredentialAccessError(
        "O armazenamento de credenciais não está disponível neste ambiente."
    )


def _create_backend(backend_name: str):
    try:
        if backend_name == _MACOS_BACKEND_NAME:
            backend = _create_macos_backend()
            expected_backend_type = macOS.Keyring
        elif backend_name == _SECRET_SERVICE_BACKEND_NAME:
            backend = _create_secret_service_backend()
            expected_backend_type = SecretService.Keyring
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
        else:
            raise CredentialAccessError(_CREDENTIAL_STORE_UNAVAILABLE_MESSAGE)
    except Exception:
        return CredentialStoreStatus(
            backend_name=backend_name,
            available=False,
            message=_unavailable_message(backend_name),
        )
    return CredentialStoreStatus(backend_name=backend_name)


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
