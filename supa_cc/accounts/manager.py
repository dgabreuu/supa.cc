import os
from contextlib import contextmanager
from typing import Callable, Iterator, List, Optional, Sequence

from .store import AccountStore
from ..auth import (
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
from ..environment import detect_environment
from ..models import Account, AccountSummary
from ..session import NativeSessionSynchronizer, SessionSyncJournal
from ..file_lock import (
    LockCloseError,
    LockReleaseError,
    acquire_file_lock,
    locked_file,
    release_file_lock,
    validate_lock_file,
)
from ..supabase_cli import SupabaseCLI
from .transactions import AccountTransactionCoordinator, pending_sync_failure


_SyncUnlockError = LockReleaseError
_SyncCloseError = LockCloseError


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
        with locked_file(
            self._sync_lock_path,
            open_file=os.open,
            close_file=os.close,
            acquire=acquire_file_lock,
            release=release_file_lock,
            validate=validate_lock_file,
        ):
            yield

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
                "The operation completed, but the synchronization lock could not be finalized.",
            )
        except (OSError, ValueError):
            return pending_sync_failure()

    def add(self, name: str, token: str) -> Account:
        if not name or len(name) < 1 or len(name) > 50:
            raise InvalidAccountNameError("Account name must contain between 1 and 50 characters.")
        if not is_valid_account_name(name):
            raise InvalidAccountNameError(
                "Account name contains invalid characters. Use only letters, numbers, hyphens, and underscores."
            )
        account = Account(name=name, token=token)
        if not account.validate_token():
            raise InvalidAccessTokenError(
                "Invalid token: the value does not use the Supabase PAT format."
            )
        try:
            with self._sync_lock():
                self.transactions.add(account)
        except (AccountTransactionError, CredentialAccessError, OSError):
            raise
        except Exception:
            raise AccountTransactionError(
                "Unable to update the active account safely."
            ) from None
        return account

    def list(self) -> List[AccountSummary]:
        return self.keychain.list_accounts()

    def get(self, name: str) -> Optional[Account]:
        return self.keychain.get_account(name)

    def remove(self, name: str) -> None:
        if not is_valid_account_name(name):
            raise InvalidAccountNameError("Invalid account name.")
        try:
            with self._sync_lock():
                self.transactions.remove(name)
        except (AccountTransactionError, CredentialAccessError, OSError):
            raise
        except Exception:
            raise AccountTransactionError(
                "Unable to remove the active account safely."
            ) from None

    def _load_account_for_auth(self, name: str):
        try:
            account = self.get(name)
        except CredentialAccessError as error:
            return None, classify_local_failure(error)
        if not account:
            return None, AuthResult.failure(
                AuthFailureCode.TOKEN_MISSING,
                "Token not found for the selected account.",
            )
        if not account.validate_token():
            return None, AuthResult.failure(
                AuthFailureCode.TOKEN_FORMAT_INVALID,
                "The stored token uses an invalid format.",
            )
        return account, None

    def validate_named_account(self, name: str) -> AuthResult:
        if not is_valid_account_name(name):
            return AuthResult.failure(
                AuthFailureCode.ACCOUNT_REQUIRED,
                "Provide a valid account name.",
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
                "Provide a valid account name.",
                exit_code=2,
            )
        return self._run_with_sync_lock(lambda: self.transactions.set_active(name))

    def recover_pending_sync(self) -> AuthResult:
        return self._run_with_sync_lock(self.transactions.recover_pending_sync)

    def get_active_name(self) -> Optional[str]:
        """Return the selected account name without reading its credential."""
        return self.active_store.read()

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
                "No active account was selected. Run 'supa.cc switch <name>'.",
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
