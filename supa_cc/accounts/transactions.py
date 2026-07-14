from typing import Optional, Tuple

from ..auth import (
    ActiveAccountStore,
    ActiveAccountError,
    ActiveAccountInvalidError,
    ActiveAccountPermissionDeniedError,
    ActiveAccountWriteError,
    AccountIndexError,
    AccountTransactionError,
    AuthFailureCode,
    AuthResult,
    CredentialAccessError,
    classify_local_failure,
)
from ..supabase_cli import SupabaseCLI
from ..models import Account
from .store import AccountStore
from ..session import MutationState, NativeSessionSynchronizer, SessionSyncJournal
from ..session.mutations import SessionMutationService
from .mutations import AccountMutationService


def pending_sync_failure() -> AuthResult:
    return AuthResult.failure(
        AuthFailureCode.SYNC_PENDING,
        "A pending session synchronization requires recovery.",
    )


class AccountTransactionCoordinator:
    def __init__(
        self,
        keychain: AccountStore,
        config: SupabaseCLI,
        active_store: ActiveAccountStore,
        native_session: NativeSessionSynchronizer,
        sync_journal: SessionSyncJournal,
    ):
        self.keychain = keychain
        self.config = config
        self.active_store = active_store
        self.sync_journal = sync_journal
        self.native_session = native_session
        self.account_mutations = AccountMutationService(self, pending_sync_failure)
        self.session_mutations = SessionMutationService(self)

    def _activate_after_preflight(self, account: Account) -> AuthResult:
        return self.session_mutations.activate_after_preflight(account)

    def _logout_after_preflight(self) -> AuthResult:
        return self.session_mutations.logout_after_preflight()

    def _read_consistent_active_name(self) -> Optional[str]:
        active_name = self.active_store.read()
        if (
            active_name is not None
            and not self.keychain.is_account_indexed(active_name)
        ):
            raise ActiveAccountInvalidError()
        return active_name

    def add(self, account: Account) -> None:
        recovery = self.recover_pending_sync()
        if not recovery.ok:
            raise AccountTransactionError(recovery.message)
        active_name = self._read_consistent_active_name()
        if active_name != account.name:
            self._mutate_inactive_add(account)
            return
        self._replace_active_account(account)

    def _replace_active_account(self, account: Account) -> None:
        previous = self.keychain.get_account(account.name)
        if previous is None:
            preflight = self.native_session.preflight()
            if not preflight.ok:
                raise AccountTransactionError(preflight.message)
            self.sync_journal.write("active_account_add", account.name, None, "intent")
            try:
                self.keychain.add_account(account)
                self.sync_journal.write(
                    "active_account_add", account.name, None, "index_committed"
                )
                self.sync_journal.write(
                    "active_account_add", account.name, None, "native_login"
                )
                activation = self._activate_after_preflight(account)
                if not activation.ok:
                    raise AccountTransactionError(activation.message)
                self.sync_journal.write(
                    "active_account_add", account.name, None, "native_verified"
                )
                self.sync_journal.clear()
            except Exception:
                if self.native_session.mutation_state is not MutationState.NONE:
                    raise AccountTransactionError(pending_sync_failure().message) from None
                try:
                    self.keychain.remove_account(account.name)
                    self.sync_journal.clear()
                except Exception:
                    raise AccountTransactionError(
                        "The operation failed and could not be safely rolled back."
                    ) from None
                raise
            return
        preflight = self.native_session.preflight()
        if preflight.ok is False:
            raise AccountTransactionError(preflight.message)
        try:
            self.sync_journal.write("activate", account.name, account.name, "intent")
            self.keychain.create_account_backup(account.name)
            self.sync_journal.write(
                "activate", account.name, account.name, "credential_backup"
            )
            self.keychain.add_account(account)
            self.sync_journal.write(
                "activate", account.name, account.name, "native_login"
            )
            activation = self._activate_after_preflight(account)
        except Exception:
            activation = pending_sync_failure()
        if not activation.ok:
            rollback = self._rollback_active_replacement(
                account.name,
                restore_native=self.native_session.mutation_state is not MutationState.NONE,
            )
            if not rollback.ok:
                raise AccountTransactionError(rollback.message)
            raise AccountTransactionError(
                "The active account could not be synchronized; the previous session was restored."
            )
        try:
            self.sync_journal.write(
                "activate", account.name, account.name, "native_verified"
            )
            self.sync_journal.write("activate", account.name, account.name, "verified")
            self.keychain.delete_account_backup(account.name)
            self.sync_journal.clear()
        except Exception:
            raise AccountTransactionError(pending_sync_failure().message) from None

    def _rollback_active_replacement(
        self, name: str, restore_native: bool = True
    ) -> AuthResult:
        try:
            self.sync_journal.write("activate", name, name, "rollback")
            self.keychain.restore_account_backup(name)
            previous = self.keychain.read_account_backup(name)
            if previous is None:
                return pending_sync_failure()
            if restore_native:
                activation = self.native_session.activate(previous)
                if not activation.ok:
                    return AuthResult.failure(
                        AuthFailureCode.SYNC_ROLLBACK_FAILED,
                        "Synchronization failed and the previous session could not be restored.",
                    )
            self.active_store.write(name)
            self.keychain.delete_account_backup(name)
            self.sync_journal.clear()
        except Exception:
            return AuthResult.failure(
                AuthFailureCode.SYNC_ROLLBACK_FAILED,
                "Synchronization failed and the previous session could not be restored.",
            )
        return AuthResult.success("The previous credential and session were restored.")

    def remove(self, name: str) -> None:
        recovery = self.recover_pending_sync()
        if not recovery.ok:
            raise AccountTransactionError(recovery.message)
        active_name = self._read_consistent_active_name()
        if active_name != name:
            self._mutate_inactive_remove(name)
            return
        self._remove_active_account(name)

    def _remove_active_account(self, name: str) -> None:
        preflight = self.native_session.preflight()
        if preflight.ok is False:
            raise AccountTransactionError(preflight.message)
        self.sync_journal.write("logout", None, name, "intent")
        if self.keychain.get_account(name) is not None:
            self.keychain.create_account_backup(name)
            self.sync_journal.write("logout", None, name, "credential_backup")
        try:
            logout = self._logout_after_preflight()
        except (OSError, ValueError):
            logout = pending_sync_failure()
        if not logout.ok:
            if (
                logout.code is AuthFailureCode.SYNC_PENDING
                or self.native_session.mutation_state is MutationState.UNCERTAIN
            ):
                raise AccountTransactionError(logout.message)
            try:
                self._clear_logout_journal(name)
            except Exception:
                raise AccountTransactionError(pending_sync_failure().message) from None
            raise AccountTransactionError("The native session could not be ended.")
        self.sync_journal.write("logout", None, name, "native_verified")
        self.active_store.clear()
        self.sync_journal.write("logout", None, name, "local_write")
        self.keychain.remove_account(name)
        self.sync_journal.write("logout", None, name, "verified")
        if self.keychain.read_account_backup(name) is not None:
            self.keychain.delete_account_backup(name)
        self.sync_journal.clear()

    def _load_account_for_auth(
        self, name: str
    ) -> Tuple[Optional[Account], Optional[AuthResult]]:
        try:
            account = self.keychain.get_account(name)
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

    def set_active(self, name: str) -> AuthResult:
        recovery = self.recover_pending_sync()
        if not recovery.ok:
            return recovery

        try:
            previous_name = self.active_store.read()
        except ActiveAccountError as error:
            return classify_local_failure(error)
        try:
            target_is_indexed = self.keychain.is_account_indexed(name)
            previous_is_indexed = (
                previous_name is None
                or previous_name == name
                or self.keychain.is_account_indexed(previous_name)
            )
        except AccountIndexError as error:
            return classify_local_failure(error)
        if not target_is_indexed or not previous_is_indexed:
            return classify_local_failure(ActiveAccountInvalidError())

        account, failure = self._load_account_for_auth(name)
        if failure is not None:
            return failure
        assert account is not None
        validation = self.config.validate_access_token(account)
        if not validation.ok:
            return validation
        preflight = self.native_session.preflight()
        if preflight.ok is False:
            return preflight

        try:
            self.sync_journal.write("activate", name, previous_name, "intent")
            self.sync_journal.write("activate", name, previous_name, "native_login")
        except (OSError, ValueError):
            return pending_sync_failure()
        try:
            activation = self._activate_after_preflight(account)
        except (OSError, ValueError):
            activation = pending_sync_failure()
        if not activation.ok:
            if self.native_session.mutation_state is MutationState.NONE:
                try:
                    self.sync_journal.clear()
                except (OSError, ValueError):
                    return pending_sync_failure()
                return activation
            return self._compensate(name, previous_name, activation)

        try:
            self.sync_journal.write("activate", name, previous_name, "native_verified")
            self.sync_journal.write("activate", name, previous_name, "local_write")
        except (OSError, ValueError):
            return pending_sync_failure()
        try:
            self.active_store.write(name)
        except PermissionError:
            failure = classify_local_failure(ActiveAccountPermissionDeniedError())
            return self._compensate(name, previous_name, failure)
        except OSError:
            failure = classify_local_failure(ActiveAccountWriteError())
            return self._compensate(name, previous_name, failure)
        except ValueError:
            failure = classify_local_failure(ActiveAccountInvalidError())
            return self._compensate(name, previous_name, failure)

        try:
            self.sync_journal.write("activate", name, previous_name, "verified")
            self.sync_journal.clear()
        except (OSError, ValueError):
            return pending_sync_failure()
        return AuthResult.success(
            f"Account '{name}' activated and native session synchronized."
        )

    def _compensate(
        self, target_name: str, previous_name: Optional[str], failure: AuthResult
    ) -> AuthResult:
        journal_failed = False
        try:
            self.sync_journal.write("activate", target_name, previous_name, "rollback")
        except (OSError, ValueError):
            journal_failed = True
        if previous_name is None:
            try:
                compensation = self.native_session.logout()
            except (OSError, ValueError):
                compensation = pending_sync_failure()
            if compensation.ok:
                try:
                    self.active_store.clear()
                except ActiveAccountError:
                    compensation = AuthResult.failure(
                        AuthFailureCode.SYNC_ROLLBACK_FAILED,
                        "The previous selection could not be restored.",
                    )
        else:
            previous, load_failure = self._load_account_for_auth(previous_name)
            if load_failure is not None:
                compensation = load_failure
            else:
                assert previous is not None
                try:
                    compensation = self.native_session.activate(previous)
                except (OSError, ValueError):
                    compensation = pending_sync_failure()
                if compensation.ok:
                    try:
                        self.active_store.write(previous_name)
                    except (ActiveAccountError, OSError, ValueError):
                        compensation = AuthResult.failure(
                            AuthFailureCode.SYNC_ROLLBACK_FAILED,
                            "The previous selection could not be restored.",
                        )
        if compensation.ok and not journal_failed:
            try:
                self.sync_journal.clear()
            except (OSError, ValueError):
                journal_failed = True
            else:
                return failure
        return AuthResult.failure(
            AuthFailureCode.SYNC_ROLLBACK_FAILED,
            "Synchronization failed and the previous session could not be restored.",
        )

    def recover_pending_sync(self) -> AuthResult:
        try:
            payload = self.sync_journal.read()
        except (OSError, ValueError):
            return pending_sync_failure()
        if payload is None:
            return AuthResult.success("No pending synchronization.")
        if payload["operation"].startswith("account_") or payload["operation"] == "active_account_add":
            return self._recover_account_mutation(payload)
        if payload["operation"] == "logout":
            return self._recover_logout(payload)
        if payload["operation"] != "activate":
            return pending_sync_failure()

        phase = payload["phase"]
        if payload["target_account"] == payload["previous_account"]:
            try:
                backup = self.keychain.read_account_backup(payload["target_account"])
            except Exception:
                return pending_sync_failure()
            if phase == "verified":
                try:
                    self.keychain.delete_account_backup(payload["target_account"])
                    self.sync_journal.clear()
                except Exception:
                    return pending_sync_failure()
                return AuthResult.success("Pending update confirmed.")
            if phase == "intent":
                try:
                    if backup is not None:
                        self.keychain.delete_account_backup(payload["target_account"])
                    self.sync_journal.clear()
                except Exception:
                    return pending_sync_failure()
                return AuthResult.success("Pending update cancelled.")
            if phase == "credential_backup":
                if backup is not None:
                    return self._rollback_active_replacement(
                        payload["target_account"], restore_native=False
                    )
                try:
                    self.sync_journal.clear()
                except (OSError, ValueError):
                    return pending_sync_failure()
                return AuthResult.success("Pending update cancelled.")
            if phase in ("native_login", "rollback"):
                if backup is None:
                    return pending_sync_failure()
                return self._rollback_active_replacement(payload["target_account"])
            if phase in ("native_verified", "local_write"):
                result = self._recover_activation(payload["target_account"])
                if not result.ok:
                    return result
                try:
                    self.keychain.delete_account_backup(payload["target_account"])
                    self.sync_journal.clear()
                except Exception:
                    return pending_sync_failure()
                return result
        if phase == "verified":
            try:
                self.sync_journal.clear()
            except (OSError, ValueError):
                return pending_sync_failure()
            return AuthResult.success("Pending synchronization confirmed.")
        if phase == "intent":
            try:
                self.sync_journal.clear()
            except (OSError, ValueError):
                return pending_sync_failure()
            return AuthResult.success("Pending synchronization cancelled.")
        if phase in ("native_login", "rollback"):
            if phase == "native_login" and payload["previous_account"] is None:
                try:
                    preflight = self.native_session.preflight()
                except (OSError, ValueError):
                    return pending_sync_failure()
                if not preflight.ok:
                    return pending_sync_failure()
                result = self._recover_activation(
                    payload["target_account"], preflighted=True
                )
            else:
                result = self._recover_compensation(payload["previous_account"])
        else:
            result = self._recover_activation(payload["target_account"])
        if result.ok:
            try:
                self.sync_journal.clear()
            except (OSError, ValueError):
                return pending_sync_failure()
        return result

    def _index_names(self):
        return self.account_mutations.index_names()

    def _mutate_inactive_add(self, account: Account) -> None:
        self.account_mutations.add_inactive(account)

    def _mutate_inactive_remove(self, name: str) -> None:
        self.account_mutations.remove_inactive(name)

    def _recover_account_mutation(self, payload) -> AuthResult:
        return self.account_mutations.recover(payload)

    def _recover_logout(self, payload) -> AuthResult:
        if payload["phase"] == "verified":
            try:
                self._clear_logout_journal(payload["previous_account"])
            except Exception:
                return pending_sync_failure()
            return AuthResult.success("Pending removal confirmed.")
        if payload["phase"] in ("intent", "credential_backup"):
            try:
                logout = self.native_session.logout()
            except (OSError, ValueError):
                return pending_sync_failure()
            if not logout.ok:
                return pending_sync_failure()
        try:
            self.active_store.clear()
            previous_name = payload["previous_account"]
            if previous_name is not None:
                self.keychain.remove_account(previous_name)
                if self.keychain.read_account_backup(previous_name) is not None:
                    self.keychain.delete_account_backup(previous_name)
            self.sync_journal.clear()
        except (ActiveAccountError, OSError, ValueError):
            return pending_sync_failure()
        return AuthResult.success("Pending removal completed.")

    def _clear_logout_journal(self, name: Optional[str]) -> None:
        if name is not None and self.keychain.read_account_backup(name) is not None:
            self.keychain.delete_account_backup(name)
        self.sync_journal.clear()

    def _recover_activation(self, name: str, preflighted: bool = False) -> AuthResult:
        account, failure = self._load_account_for_auth(name)
        if failure is not None:
            return pending_sync_failure()
        assert account is not None
        activation = (
            self._activate_after_preflight(account)
            if preflighted
            else self.native_session.activate(account)
        )
        if not activation.ok:
            return pending_sync_failure()
        try:
            self.active_store.write(name)
        except (ActiveAccountError, OSError, ValueError):
            return pending_sync_failure()
        return AuthResult.success("Pending synchronization completed.")

    def _recover_compensation(self, previous_name: Optional[str]) -> AuthResult:
        if previous_name is None:
            compensation = self.native_session.logout()
            if compensation.ok:
                try:
                    self.active_store.clear()
                except ActiveAccountError:
                    return pending_sync_failure()
            return compensation if compensation.ok else pending_sync_failure()
        account, failure = self._load_account_for_auth(previous_name)
        if failure is not None:
            return pending_sync_failure()
        assert account is not None
        compensation = self.native_session.activate(account)
        if not compensation.ok:
            return pending_sync_failure()
        try:
            self.active_store.write(previous_name)
        except (ActiveAccountError, OSError, ValueError):
            return pending_sync_failure()
        return AuthResult.success("Previous synchronization restored.")
