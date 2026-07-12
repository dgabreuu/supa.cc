import fcntl
import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, List, Optional

from .auth import (
    AccountIndexInvalidError,
    AccountIndexReadError,
    AccountTransactionError,
    is_valid_account_name,
)
from .credentials import CredentialStore, create_credential_store
from .environment import Environment, detect_environment
from .models import Account, AccountSummary
from .state import atomic_write_text, read_text


KEYCHAIN_SERVICE = "supa.cc.supabase.accounts.v2"
_INDEX_MAX_BYTES = 1024 * 1024


def _validated_unique_names(names: List[str]) -> List[str]:
    unique_names = []
    seen = set()
    for name in names:
        if not is_valid_account_name(name):
            raise AccountIndexInvalidError(
                "O índice local de contas contém um nome inválido."
            )
        if name not in seen:
            seen.add(name)
            unique_names.append(name)
    return unique_names


def safe_load_json_index(path: Path) -> Optional[List[str]]:
    """Lê o índice; None significa exclusivamente que ele não existe."""
    try:
        contents = read_text(path, _INDEX_MAX_BYTES)
    except OSError:
        raise AccountIndexReadError(
            "Não foi possível ler o índice local de contas."
        ) from None
    if contents is None:
        return None

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


class AccountStore:
    def __init__(
        self,
        index_path: Optional[Path] = None,
        service: str = KEYCHAIN_SERVICE,
        credential_store: Optional[CredentialStore] = None,
        environment: Optional[Environment] = None,
    ):
        environment = environment if environment is not None else detect_environment()
        self.index_path = (
            Path(index_path)
            if index_path is not None
            else environment.config_directory() / "accounts.json"
        )
        self.credential_store = (
            credential_store
            if credential_store is not None
            else create_credential_store(environment, service=service)
        )
        stored_service = getattr(self.credential_store, "service", None)
        self.service = stored_service if isinstance(stored_service, str) else service

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
        atomic_write_text(self.index_path, data)

    def _read_token_uncached(self, name: str) -> Optional[str]:
        return self.credential_store.get(name)

    def _write_token_verified(self, account: Account) -> None:
        self.credential_store.set(account)

    def _delete_token(self, name: str) -> None:
        self.credential_store.delete(name)

    @staticmethod
    def _backup_name(name: str) -> str:
        digest = hashlib.sha256(name.encode("utf-8")).hexdigest()
        return f"!supa.cc-backup!{digest}"

    def _backup_failure(self) -> AccountTransactionError:
        return AccountTransactionError(
            "A credencial temporária da transação não pôde ser confirmada com segurança."
        )

    def create_account_backup(self, name: str) -> None:
        """Copia a credencial para armazenamento seguro fora do índice público."""
        backup_name = self._backup_name(name)
        try:
            token = self._read_token_uncached(name)
            if token is None:
                raise self._backup_failure()
            self._write_token_verified(Account(name=backup_name, token=token))
            if self._read_token_uncached(backup_name) != token:
                raise self._backup_failure()
        except AccountTransactionError:
            raise
        except Exception:
            raise self._backup_failure() from None

    def read_account_backup(self, name: str) -> Optional[Account]:
        try:
            token = self._read_token_uncached(self._backup_name(name))
        except Exception:
            raise self._backup_failure() from None
        return Account(name=name, token=token) if token is not None else None

    def restore_account_backup(self, name: str) -> None:
        backup = self.read_account_backup(name)
        if backup is None:
            raise self._backup_failure()
        try:
            self._write_token_verified(backup)
            if self._read_token_uncached(name) != backup.token:
                raise self._backup_failure()
        except AccountTransactionError:
            raise
        except Exception:
            raise self._backup_failure() from None

    def delete_account_backup(self, name: str) -> None:
        backup_name = self._backup_name(name)
        try:
            self._delete_token(backup_name)
            if self._read_token_uncached(backup_name) is not None:
                raise self._backup_failure()
        except AccountTransactionError:
            raise
        except Exception:
            raise self._backup_failure() from None

    def _restore_token_best_effort(self, name: str, token: Optional[str]) -> bool:
        try:
            if token is None:
                self._delete_token(name)
            else:
                self._write_token_verified(Account(name=name, token=token))
        except Exception:
            return False
        return True

    def _ensure_initialized(self) -> None:
        self._read_index()

    def save_account(self, account: Account) -> None:
        """Salva e confirma uma credencial sem alterar nomes do índice."""
        self._ensure_initialized()
        self._write_token_verified(account)

    def get_account(self, name: str) -> Optional[Account]:
        """Recupera uma credencial diretamente do armazenamento autoritativo."""
        token = self._read_token_uncached(name)
        if token:
            return Account(name=name, token=token)
        return None

    def list_accounts(self) -> List[AccountSummary]:
        """Lista nomes sem recuperar tokens do Keychain."""
        return [AccountSummary(name=name) for name in self._read_index()]

    def delete_account(self, name: str) -> None:
        """Remove uma credencial sem alterar nomes do índice."""
        self._ensure_initialized()
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

    def remove_account(self, name: str) -> None:
        """Remove credencial e nome com rollback best-effort sob lock."""
        with self._index_lock():
            names = self._read_index_locked()
            previous_token = self._read_token_uncached(name)
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
