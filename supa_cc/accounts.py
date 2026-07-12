import os
import stat
from contextlib import contextmanager
from typing import Callable, Iterator, List, Optional, Sequence

from .account_store import AccountStore
from .auth import (
    ActiveAccountError,
    ActiveAccountStore,
    AccountTransactionError,
    AuthFailureCode,
    AuthResult,
    CommandResult,
    CredentialAccessError,
    InvalidAccessTokenError,
    InvalidAccountNameError,
    classify_local_failure,
    is_valid_account_name,
)
from .environment import detect_environment
from .models import Account, AccountSummary
from .native_session import NativeSessionSynchronizer, SessionSyncJournal
from .file_lock import acquire_file_lock, release_file_lock
from .supabase_cli import SupabaseCLI
from .transactions import AccountTransactionCoordinator, pending_sync_failure


class _SyncUnlockError(OSError):
    pass


class _SyncCloseError(OSError):
    pass


def _is_windows() -> bool:
    return os.name == "nt"


class AccountManager:
    def __init__(
        self,
        keychain: Optional[AccountStore] = None,
        config: Optional[SupabaseCLI] = None,
        active_store: Optional[ActiveAccountStore] = None,
        native_session: Optional[NativeSessionSynchronizer] = None,
        sync_journal: Optional[SessionSyncJournal] = None,
    ):
        environment = detect_environment()
        self.keychain = keychain if keychain is not None else AccountStore(environment=environment)
        self.config = config if config is not None else SupabaseCLI()
        config_directory = environment.config_directory()
        self.active_store = active_store if active_store is not None else ActiveAccountStore(
            path=config_directory / "active-account"
        )
        self._sync_journal = sync_journal if sync_journal is not None else SessionSyncJournal(
            config_directory / "session-sync.json"
        )
        self.native_session = (
            native_session
            if native_session is not None
            else NativeSessionSynchronizer(self.config)
        )
        self.transactions = AccountTransactionCoordinator(
            self.keychain,
            self.config,
            self.active_store,
            self.native_session,
            self._sync_journal,
        )
        self._sync_lock_path = self._sync_journal.path.with_name(".session-sync.lock")

    @property
    def sync_journal(self):
        return self._sync_journal

    @sync_journal.setter
    def sync_journal(self, journal):
        self._sync_journal = journal
        self._sync_lock_path = journal.path.with_name(".session-sync.lock")
        if hasattr(self, "transactions"):
            self.transactions.sync_journal = journal

    @contextmanager
    def _sync_lock(self) -> Iterator[None]:
        self._sync_lock_path.parent.mkdir(parents=True, exist_ok=True)
        if not _is_windows():
            self._sync_lock_path.parent.chmod(0o700)
        flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(self._sync_lock_path, flags, 0o600)
        locked = False
        body_error = None
        unlock_failed = False
        close_failed = False
        try:
            opened = os.fstat(descriptor)
            current = self._sync_lock_path.lstat()
            unsafe_posix_metadata = not _is_windows() and (
                opened.st_uid != os.getuid()
                or stat.S_IMODE(opened.st_mode) != 0o600
                or current.st_uid != os.getuid()
                or stat.S_IMODE(current.st_mode) != 0o600
            )
            if (
                not stat.S_ISREG(opened.st_mode)
                or not stat.S_ISREG(current.st_mode)
                or unsafe_posix_metadata
                or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino)
            ):
                raise ValueError("O lock de sincronização é inválido.")
            acquire_file_lock(descriptor)
            locked = True
            current = self._sync_lock_path.lstat()
            unsafe_posix_metadata = not _is_windows() and (
                current.st_uid != os.getuid()
                or stat.S_IMODE(current.st_mode) != 0o600
            )
            if (
                not stat.S_ISREG(current.st_mode)
                or unsafe_posix_metadata
                or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino)
            ):
                raise ValueError("O lock de sincronização é inválido.")
            try:
                yield
            except BaseException as error:
                body_error = error
        finally:
            try:
                if locked:
                    release_file_lock(descriptor)
            except OSError:
                unlock_failed = True
            finally:
                try:
                    os.close(descriptor)
                except OSError:
                    close_failed = True
        if body_error is not None:
            raise body_error
        if unlock_failed:
            raise _SyncUnlockError()
        if close_failed:
            raise _SyncCloseError()

    def _run_with_sync_lock(self, operation: Callable[[], AuthResult]) -> AuthResult:
        result = None
        try:
            with self._sync_lock():
                result = operation()
            return result
        except _SyncCloseError:
            if result is not None:
                return result
            return pending_sync_failure()
        except _SyncUnlockError:
            try:
                pending = self.sync_journal.read() is not None
            except (OSError, ValueError):
                pending = True
            if pending:
                return pending_sync_failure()
            return AuthResult.failure(
                AuthFailureCode.ENVIRONMENT_BLOCKED,
                "A operação foi concluída, mas o lock de sincronização não pôde ser finalizado.",
            )
        except (OSError, ValueError):
            return pending_sync_failure()

    def add(self, name: str, token: str) -> Account:
        if not name or len(name) < 1 or len(name) > 50:
            raise InvalidAccountNameError("Nome da conta deve ter entre 1 e 50 caracteres.")
        if not is_valid_account_name(name):
            raise InvalidAccountNameError(
                "Nome da conta contém caracteres inválidos. Use apenas letras, números, hífens e underscores."
            )
        account = Account(name=name, token=token)
        if not account.validate_token():
            raise InvalidAccessTokenError(
                "Token inválido: o valor não atende ao formato PAT Supabase."
            )
        try:
            with self._sync_lock():
                self.transactions.add(account)
        except (AccountTransactionError, CredentialAccessError, OSError):
            raise
        except Exception:
            raise AccountTransactionError(
                "Não foi possível atualizar a conta ativa com segurança."
            ) from None
        return account

    def list(self) -> List[AccountSummary]:
        return self.keychain.list_accounts()

    def get(self, name: str) -> Optional[Account]:
        return self.keychain.get_account(name)

    def remove(self, name: str) -> None:
        if not is_valid_account_name(name):
            raise InvalidAccountNameError("Nome de conta inválido.")
        try:
            with self._sync_lock():
                self.transactions.remove(name)
        except (AccountTransactionError, CredentialAccessError, OSError):
            raise
        except Exception:
            raise AccountTransactionError(
                "Não foi possível remover a conta ativa com segurança."
            ) from None

    def _load_account_for_auth(self, name: str):
        try:
            account = self.get(name)
        except CredentialAccessError as error:
            return None, classify_local_failure(error)
        if not account:
            return None, AuthResult.failure(
                AuthFailureCode.TOKEN_MISSING,
                "Token não encontrado para a conta selecionada.",
            )
        if not account.validate_token():
            return None, AuthResult.failure(
                AuthFailureCode.TOKEN_FORMAT_INVALID,
                "O token armazenado tem formato inválido.",
            )
        return account, None

    def validate_named_account(self, name: str) -> AuthResult:
        if not is_valid_account_name(name):
            return AuthResult.failure(
                AuthFailureCode.ACCOUNT_REQUIRED,
                "Informe um nome de conta válido.",
                exit_code=2,
            )
        account, failure = self._load_account_for_auth(name)
        if failure is not None:
            return failure
        return self.config.validate_access_token(account)

    def set_active(self, name: str) -> AuthResult:
        if not is_valid_account_name(name):
            return AuthResult.failure(
                AuthFailureCode.ACCOUNT_REQUIRED,
                "Informe um nome de conta válido.",
                exit_code=2,
            )
        return self._run_with_sync_lock(lambda: self.transactions.set_active(name))

    def recover_pending_sync(self) -> AuthResult:
        return self._run_with_sync_lock(self.transactions.recover_pending_sync)

    def run_active(
        self,
        arguments: Sequence[str],
        stdout_sink: Optional[Callable[[str], None]] = None,
        stderr_sink: Optional[Callable[[str], None]] = None,
    ) -> CommandResult:
        try:
            name = self.active_store.read()
        except ActiveAccountError as error:
            failure = classify_local_failure(error)
            return CommandResult.failure(
                failure.code, failure.message, exit_code=failure.exit_code
            )
        if name is None:
            return CommandResult.failure(
                AuthFailureCode.ACTIVE_ACCOUNT_MISSING,
                "Nenhuma conta ativa foi selecionada. Execute 'supa.cc switch <conta>'.",
            )
        account, failure = self._load_account_for_auth(name)
        if failure is not None:
            return CommandResult.failure(
                failure.code, failure.message, exit_code=failure.exit_code
            )
        return self.config.execute_authenticated_streaming(
            account,
            arguments,
            stdout_sink=stdout_sink or (lambda _chunk: None),
            stderr_sink=stderr_sink or (lambda _chunk: None),
        )
