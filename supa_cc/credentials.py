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


@dataclass(frozen=True)
class CredentialStoreStatus:
    backend_name: str
    available: bool = True


class CredentialStore:
    def __init__(self, backend: Any, backend_name: str):
        self._backend = backend
        self.backend_name = backend_name

    def status(self) -> CredentialStoreStatus:
        return CredentialStoreStatus(backend_name=self.backend_name)

    def get(self, name: str) -> Optional[str]:
        try:
            return self._backend.get_password(_CREDENTIAL_SERVICE, name)
        except Exception as error:
            _raise_credential_operation_error(error)

    def set(self, account: Account) -> None:
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
        try:
            self._backend.delete_password(_CREDENTIAL_SERVICE, name)
        except Exception as error:
            if _is_missing_credential(error):
                return
            _raise_credential_operation_error(error)


def create_credential_store(
    environment: Environment,
    secret_service_factory: Callable[[], Any] = SecretService.Keyring,
    macos_factory: Callable[[], Any] = macOS.Keyring,
) -> CredentialStore:
    if environment.operating_system is OperatingSystem.MACOS:
        return CredentialStore(
            _create_backend(macos_factory),
            "keyring.backends.macOS.Keyring",
        )
    if environment.operating_system is OperatingSystem.LINUX and environment.is_supported:
        return CredentialStore(
            _create_backend(secret_service_factory),
            "keyring.backends.SecretService.Keyring",
        )
    raise CredentialAccessError(
        "O armazenamento de credenciais não está disponível neste ambiente."
    )


def _create_backend(factory: Callable[[], Any]) -> Any:
    try:
        return factory()
    except Exception:
        raise CredentialAccessError(
            "O armazenamento de credenciais não está disponível."
        ) from None


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
