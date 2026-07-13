"""Account-only mutation and recovery operations.

The service receives the cross-feature coordinator as a narrow transaction context so
that journal replacement and test instrumentation remain authoritative in one place.
"""

from ..auth import AccountTransactionError, AuthResult
from ..models import Account


class AccountMutationService:
    def __init__(self, transaction, pending_failure):
        self.transaction = transaction
        self._pending_failure = pending_failure

    def index_names(self):
        summaries = self.transaction.keychain.list_accounts()
        if not isinstance(summaries, (list, tuple)):
            return []
        return [summary.name for summary in summaries]

    def add_inactive(self, account: Account) -> None:
        tx = self.transaction
        previous = tx.keychain.get_account(account.name)
        operation = "account_replace" if previous is not None else "account_add"
        committed = False
        try:
            tx.sync_journal.write(operation, account.name, None, "intent")
            if previous is not None:
                tx.keychain.create_account_backup(account.name)
                tx.sync_journal.write(
                    operation, account.name, None, "credential_backup"
                )
            tx.keychain.save_account(account)
            tx.sync_journal.write(
                operation, account.name, None, "credential_written"
            )
            names = tx._index_names()
            if account.name not in names:
                names.append(account.name)
            tx.keychain.update_index(names)
            committed = True
            tx.sync_journal.write(operation, account.name, None, "index_committed")
            if previous is not None:
                tx.keychain.delete_account_backup(account.name)
            tx.sync_journal.clear()
        except Exception:
            if committed:
                raise AccountTransactionError(
                    self._pending_failure().message
                ) from None
            try:
                if previous is None:
                    tx.keychain.delete_account(account.name)
                else:
                    tx.keychain.restore_account_backup(account.name)
                    tx.keychain.delete_account_backup(account.name)
                tx.sync_journal.clear()
            except Exception:
                raise AccountTransactionError(
                    "The operation failed and could not be safely rolled back."
                ) from None
            raise

    def remove_inactive(self, name: str) -> None:
        tx = self.transaction
        previous = tx.keychain.get_account(name)
        committed = False
        try:
            tx.sync_journal.write("account_remove", name, None, "intent")
            if previous is not None:
                tx.keychain.create_account_backup(name)
                tx.sync_journal.write(
                    "account_remove", name, None, "credential_backup"
                )
            tx.keychain.delete_account(name)
            tx.keychain.update_index(
                [existing for existing in tx._index_names() if existing != name]
            )
            committed = True
            tx.sync_journal.write(
                "account_remove", name, None, "index_committed"
            )
            if previous is not None:
                tx.keychain.delete_account_backup(name)
            tx.sync_journal.clear()
        except Exception:
            if committed:
                raise AccountTransactionError(
                    self._pending_failure().message
                ) from None
            try:
                if previous is not None:
                    tx.keychain.restore_account_backup(name)
                    tx.keychain.delete_account_backup(name)
                tx.sync_journal.clear()
            except Exception:
                raise AccountTransactionError(
                    "The operation failed and could not be safely rolled back."
                ) from None
            raise

    def recover(self, payload) -> AuthResult:
        tx = self.transaction
        operation = payload["operation"]
        name = payload["target_account"]
        phase = payload["phase"]
        try:
            if operation == "active_account_add":
                account = tx.keychain.get_account(name)
                if account is None:
                    if phase == "intent":
                        tx.sync_journal.clear()
                        return AuthResult.success("Pending mutation cancelled.")
                    return self._pending_failure()
                names = tx._index_names()
                if name not in names:
                    names.append(name)
                    tx.keychain.update_index(names)
                activation = tx.native_session.activate(account)
                if not activation.ok:
                    return self._pending_failure()
            elif operation == "account_add":
                if tx.keychain.get_account(name) is not None:
                    names = tx._index_names()
                    if name not in names:
                        names.append(name)
                        tx.keychain.update_index(names)
            elif operation == "account_replace":
                backup = tx.keychain.read_account_backup(name)
                if phase == "intent" and backup is None:
                    tx.sync_journal.clear()
                    return AuthResult.success("Pending mutation cancelled.")
                if phase != "index_committed":
                    tx.keychain.restore_account_backup(name)
                tx.keychain.delete_account_backup(name)
            else:
                backup = tx.keychain.read_account_backup(name)
                if phase == "intent" and backup is None:
                    tx.sync_journal.clear()
                    return AuthResult.success("Pending mutation cancelled.")
                tx.keychain.delete_account(name)
                tx.keychain.update_index(
                    [existing for existing in tx._index_names() if existing != name]
                )
                if backup is not None:
                    tx.keychain.delete_account_backup(name)
            tx.sync_journal.clear()
        except Exception:
            return self._pending_failure()
        return AuthResult.success("Pending mutation completed.")
