import fcntl
import hmac
import json
import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator, List, Optional

import keyring
from keyring.errors import KeyringError, KeyringLocked, PasswordDeleteError

from .auth import (
    AccountIndexError,
    AccountIndexInvalidError,
    AccountIndexReadError,
    AccountTransactionError,
    KeychainPermissionDeniedError,
    KeychainReadError,
    is_valid_account_name,
)
from .models import Account


KEYCHAIN_SERVICE = "supa.cc.supabase.accounts.v2"
DEFAULT_INDEX_PATH = Path.home() / ".config" / "supa.cc" / "accounts.json"
_MACOS_KEYCHAIN_ITEM_NOT_FOUND = "-25300"
DEFAULT_TOKEN_CACHE_TTL_SECONDS = 5.0
_PERMISSION_ERROR_MARKERS = (
    "permission denied",
    "interaction is not allowed",
    "user interaction is not allowed",
)


def _raise_keychain_access_error(error: BaseException) -> None:
    message = str(error).lower()
    if (
        isinstance(error, (KeyringLocked, PermissionError))
        or any(marker in message for marker in _PERMISSION_ERROR_MARKERS)
    ):
        raise KeychainPermissionDeniedError(
            "Acesso ao Keychain não autorizado."
        ) from None
    raise KeychainReadError("Não foi possível ler a credencial no Keychain.") from None


def _is_missing_keychain_item(error: PasswordDeleteError) -> bool:
    message = str(error).lower()
    return (
        _MACOS_KEYCHAIN_ITEM_NOT_FOUND in message
        or "item not found" in message
        or "could not be found" in message
    )


def _validated_unique_names(names: List[str]) -> List[str]:
    unique_names = []
    for name in names:
        if not is_valid_account_name(name):
            raise AccountIndexInvalidError(
                "O índice local de contas contém um nome inválido."
            )
        if name not in unique_names:
            unique_names.append(name)
    return unique_names


def safe_load_json_index(path: Path) -> Optional[List[str]]:
    """Lê o índice; None significa exclusivamente que ele não existe."""
    try:
        contents = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError:
        raise AccountIndexReadError(
            "Não foi possível ler o índice local de contas."
        ) from None

    try:
        data = json.loads(contents)
    except json.JSONDecodeError:
        raise AccountIndexInvalidError(
            "O índice local de contas é inválido."
        ) from None

    if not isinstance(data, dict) or not isinstance(data.get("accounts"), list):
        raise AccountIndexInvalidError(
            "O índice local de contas é inválido."
        )
    return _validated_unique_names(data["accounts"])


class KeychainManager:
    def __init__(
        self,
        index_path: Optional[Path] = None,
        service: str = KEYCHAIN_SERVICE,
        cache_ttl_seconds: float = DEFAULT_TOKEN_CACHE_TTL_SECONDS,
        clock: Optional[Callable[[], float]] = None,
    ):
        self.index_path = Path(index_path) if index_path else DEFAULT_INDEX_PATH
        self.service = service
        self._cache_ttl_seconds = max(0.0, cache_ttl_seconds)
        self._clock = clock if clock is not None else time.monotonic
        self._token_cache: dict[str, tuple[str, float]] = {}

    @property
    def index_lock_path(self) -> Path:
        return self.index_path.with_name(f".{self.index_path.name}.lock")

    def _ensure_index_parent(self) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.index_path.parent.chmod(0o700)

    @contextmanager
    def _index_lock(self) -> Iterator[None]:
        self._ensure_index_parent()
        flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(self.index_lock_path, flags, 0o600)
        locked = False
        try:
            os.fchmod(descriptor, 0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            locked = True
            yield
        finally:
            if locked:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def _read_index_locked(self) -> List[str]:
        names = safe_load_json_index(self.index_path)
        return [] if names is None else names

    def _write_index_locked(self, names: List[str]) -> None:
        unique_names = _validated_unique_names(names)
        self._ensure_index_parent()
        data = json.dumps({"accounts": unique_names}, indent=2)
        descriptor = None
        temporary_path = None
        try:
            descriptor, temporary_path = tempfile.mkstemp(
                prefix=f".{self.index_path.name}.",
                dir=self.index_path.parent,
            )
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                descriptor = None
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, self.index_path)
            temporary_path = None
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if temporary_path is not None:
                try:
                    os.unlink(temporary_path)
                except FileNotFoundError:
                    pass

    def _read_token_uncached(self, name: str) -> Optional[str]:
        try:
            return keyring.get_password(self.service, name)
        except (KeyringError, PermissionError) as exc:
            _raise_keychain_access_error(exc)

    def _write_token_verified(self, account: Account) -> None:
        try:
            keyring.set_password(self.service, account.name, account.token)
            saved_token = keyring.get_password(self.service, account.name)
        except (KeyringError, PermissionError) as exc:
            _raise_keychain_access_error(exc)

        if saved_token is None or not hmac.compare_digest(
            account.token,
            saved_token,
        ):
            raise KeychainReadError(
                "Não foi possível confirmar a credencial no Keychain."
            )

    def _delete_token(self, name: str) -> None:
        try:
            keyring.delete_password(self.service, name)
        except (KeyringError, PermissionError) as exc:
            if isinstance(exc, PasswordDeleteError) and _is_missing_keychain_item(exc):
                return
            _raise_keychain_access_error(exc)

    def _cache_token(self, name: str, token: str) -> None:
        self._token_cache[name] = (token, self._clock())

    def _restore_token_best_effort(self, name: str, token: Optional[str]) -> bool:
        try:
            if token is None:
                self._delete_token(name)
            else:
                self._write_token_verified(Account(name=name, token=token))
        except Exception:
            return False
        finally:
            self._token_cache.pop(name, None)
        return True

    def _ensure_initialized(self) -> None:
        self._read_index()

    def save_account(self, account: Account) -> None:
        """Salva e confirma uma credencial sem alterar nomes do índice."""
        self._ensure_initialized()
        self._token_cache.pop(account.name, None)
        self._write_token_verified(account)
        self._cache_token(account.name, account.token)

    def get_account(self, name: str) -> Optional[Account]:
        """Recupera uma credencial com cache positivo de curta duração."""
        cached = self._token_cache.get(name)
        if cached is not None:
            token, cached_at = cached
            if (
                self._cache_ttl_seconds > 0
                and self._clock() - cached_at < self._cache_ttl_seconds
            ):
                return Account(name=name, token=token)
            self._token_cache.pop(name, None)

        token = self._read_token_uncached(name)
        if token:
            self._cache_token(name, token)
            return Account(name=name, token=token)
        return None

    def list_accounts(self) -> List[Account]:
        """Lista nomes sem recuperar tokens do Keychain."""
        return [Account(name=name, token="") for name in self._read_index()]

    def delete_account(self, name: str) -> None:
        """Remove uma credencial sem alterar nomes do índice."""
        self._ensure_initialized()
        self._token_cache.pop(name, None)
        self._delete_token(name)

    def update_index(self, names: List[str]) -> None:
        """Substitui o índice sob lock, sem sobrescrever conteúdo inválido."""
        unique_names = _validated_unique_names(names)
        with self._index_lock():
            safe_load_json_index(self.index_path)
            self._write_index_locked(unique_names)

    def add_account(self, account: Account) -> None:
        """Grava credencial e nome como uma transação lógica serializada."""
        with self._index_lock():
            names = self._read_index_locked()
            previous_token = self._read_token_uncached(account.name)
            self._token_cache.pop(account.name, None)
            try:
                self._write_token_verified(account)
                if account.name not in names:
                    names.append(account.name)
                self._write_index_locked(names)
            except Exception:
                if not self._restore_token_best_effort(
                    account.name,
                    previous_token,
                ):
                    raise AccountTransactionError(
                        "A operação falhou e não pôde ser revertida com segurança."
                    ) from None
                raise
            self._cache_token(account.name, account.token)

    def remove_account(self, name: str) -> None:
        """Remove credencial e nome com rollback best-effort sob lock."""
        with self._index_lock():
            names = self._read_index_locked()
            previous_token = self._read_token_uncached(name)
            self._token_cache.pop(name, None)
            try:
                self._delete_token(name)
                names = [existing for existing in names if existing != name]
                self._write_index_locked(names)
            except Exception:
                if (
                    previous_token is not None
                    and not self._restore_token_best_effort(name, previous_token)
                ):
                    raise AccountTransactionError(
                        "A operação falhou e não pôde ser revertida com segurança."
                    ) from None
                raise

    def _read_index(self) -> List[str]:
        names = safe_load_json_index(self.index_path)
        if names is not None:
            return names

        with self._index_lock():
            names = safe_load_json_index(self.index_path)
            if names is None:
                names = []
                self._write_index_locked(names)
            return names

    def _read_file_index(self) -> List[str]:
        return self._read_index()
