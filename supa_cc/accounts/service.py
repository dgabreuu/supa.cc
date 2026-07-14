"""Account orchestration backed by the versioned, secret-free state document."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from functools import wraps
from threading import local
from typing import Callable, Optional, Sequence

from ..auth import (
    AuthFailureCode,
    AuthResult,
    CommandResult,
    InvalidAccessTokenError,
    InvalidAccountNameError,
    classify_local_failure,
    is_valid_account_name,
)
from ..models import Account, AccountSummary
from ..security.tokens import is_valid_access_token
from ..credentials import create_credential_store
from ..environment import detect_environment
from ..file_lock import locked_file
from ..session import MutationState, NativeSessionSynchronizer
from ..supabase_cli import SupabaseCLI
from .state import AccountState, StateRepository, StateTransition


TokenProvider = Callable[[str], Optional[str]]


def _exclusive_operation(operation: str):
    """Serialize account/session mutations across processes and nested calls."""
    def decorate(method):
        @wraps(method)
        def wrapped(self, *args, **kwargs):
            depth = getattr(self._operation_context, "depth", 0)
            if depth:
                return method(self, *args, **kwargs)
            try:
                with locked_file(self._operation_lock_path):
                    self._operation_context.depth = 1
                    try:
                        return method(self, *args, **kwargs)
                    finally:
                        self._operation_context.depth = 0
            except Exception as error:
                return classify_local_failure(error, operation=operation)

        return wrapped

    return decorate


class AccountService:
    """Coordinate account intent, native credentials, and the derived CLI session."""

    def __init__(
        self,
        *,
        state_repository: Optional[StateRepository] = None,
        credential_store=None,
        cli=None,
        native_session=None,
    ) -> None:
        environment = detect_environment()
        config_directory = environment.config_directory()
        self.state_repository = state_repository or StateRepository(
            config_directory / "state.json"
        )
        self.credential_store = credential_store or create_credential_store(
            environment
        )
        self.cli = cli or SupabaseCLI()
        self.native_session = native_session or NativeSessionSynchronizer(self.cli)
        self._operation_lock_path = self.state_repository.path.with_name(
            ".operation.lock"
        )
        self._operation_context = local()

    def list(self) -> list[AccountSummary]:
        """List aliases without opening the native credential store."""
        state = self.state_repository.load()
        return [AccountSummary(name) for name in state.aliases]

    def get(self, name: str) -> Optional[Account]:
        state = self.state_repository.load()
        if name not in state.aliases:
            return None
        token = self.credential_store.get(name)
        return None if token is None else Account(name, token)

    @_exclusive_operation("add")
    def add(self, name: str, token: str) -> AuthResult:
        try:
            account = self._validated_account(name, token)
            recovery = self.recover_pending_sync()
            if not recovery.ok:
                return self._with_context(
                    recovery, "add", "recover_session"
                )
            validation = self.cli.validate_access_token(account)
            if not validation.ok:
                return self._with_context(validation, "add", "validate_pat")

            state = self.state_repository.load()
            if state.confirmed_active == name:
                transition = StateTransition(
                    "replace_active", name, name, "prepared"
                )
                self.state_repository.save(
                    replace(state, pending_transition=transition)
                )
                activation = self.native_session.activate(account)
                if activation.ok:
                    current = self.state_repository.load()
                    self.state_repository.save(
                        replace(
                            current,
                            pending_transition=replace(
                                transition, phase="session_verified"
                            ),
                        )
                    )
                    self.credential_store.set(account)
                    current = self.state_repository.load()
                    self.state_repository.save(
                        replace(
                            current,
                            pending_transition=replace(
                                transition, phase="credential_written"
                            ),
                        )
                    )
                    self._commit_active(name)
                    return self._with_context(
                        AuthResult.success(
                            "Active account updated and session synchronized."
                        ),
                        "add",
                        "complete",
                    )
                restored_failure = self._restore_after_failed_active_replacement(
                    transition, activation
                )
                return self._with_context(
                    restored_failure,
                    "add",
                    restored_failure.phase,
                )

            transition = StateTransition("add", name, None, "prepared")
            self.state_repository.save(replace(state, pending_transition=transition))
            self.credential_store.set(account)
            state = self.state_repository.load()
            self.state_repository.save(
                replace(
                    state,
                    pending_transition=replace(
                        transition, phase="credential_written"
                    ),
                )
            )
            aliases = state.aliases if name in state.aliases else (*state.aliases, name)
            self.state_repository.save(
                replace(state, aliases=aliases, pending_transition=None)
            )
            return self._with_context(
                AuthResult.success("Account saved."), "add", "complete"
            )
        except Exception as error:
            return classify_local_failure(error, operation="add")

    @_exclusive_operation("switch")
    def set_active(
        self,
        name: str,
        *,
        token_provider: Optional[TokenProvider] = None,
    ) -> AuthResult:
        try:
            recovery = self.recover_pending_sync()
            if not recovery.ok:
                return recovery
            state = self.state_repository.load()
            if name not in state.aliases:
                return AuthResult.failure(
                    AuthFailureCode.ACCOUNT_REQUIRED,
                    "The requested account is not registered.",
                    operation="switch",
                    phase="load_account",
                )
            (
                account,
                credential_created,
                already_validated,
                credential_failure,
            ) = self._load_or_reauthorize(name, token_provider)
            if credential_failure is not None:
                return self._with_context(
                    credential_failure, "switch", "credential_access"
                )
            assert account is not None

            validation = (
                AuthResult.success("Account authenticated by the Supabase API.")
                if already_validated
                else self.cli.validate_access_token(account)
            )
            if not validation.ok:
                if credential_created:
                    self.credential_store.delete(name)
                return self._with_context(validation, "switch", "validate_pat")

            transition = StateTransition(
                "switch", name, state.confirmed_active, "prepared"
            )
            self.state_repository.save(replace(state, pending_transition=transition))
            result = self.native_session.activate(
                account,
                phase_callback=self._phase_callback(transition),
            )
            if result.ok:
                self._commit_active(name)
                return self._with_context(result, "switch", "complete")
            return self._restore_after_failed_switch(transition, result)
        except Exception as error:
            return classify_local_failure(error, operation="switch")

    @_exclusive_operation("recover_session")
    def recover_pending_sync(self) -> AuthResult:
        try:
            state = self.state_repository.load()
            transition = state.pending_transition
            if transition is None:
                return AuthResult.success("No pending session recovery.")
            if transition.operation == "migrate":
                migrated = self._account_from_store(transition.target_account)
                if migrated is None:
                    self.state_repository.save(
                        replace(
                            state,
                            confirmed_active=None,
                            pending_transition=None,
                        )
                    )
                    return AuthResult.success(
                        "Legacy selection imported; credential reauthentication is required."
                    )
                transition = StateTransition(
                    "switch",
                    transition.target_account,
                    None,
                    "prepared",
                )
                self.state_repository.save(
                    replace(state, pending_transition=transition)
                )
            if transition.operation in {
                "activate",
                "active_account_add",
                "logout",
                "account_add",
                "account_replace",
                "account_remove",
            }:
                normalized = self.state_repository._normalize_legacy_transition(
                    transition
                )
                if normalized is None:
                    self.state_repository.save(
                        replace(state, confirmed_active=None, pending_transition=None)
                    )
                    return self._with_context(
                        AuthResult.success("Interrupted operation reconciled."),
                        "recover_session",
                        "complete",
                    )
                transition = normalized
                state = replace(state, pending_transition=transition)
                self.state_repository.save(state)
            if transition.operation == "remove":
                return self._recover_remove(state, transition)
            if transition.operation == "reset":
                return self._recover_reset(state, transition)
            if transition.operation == "add":
                return self._recover_add(state, transition)
            if transition.operation == "replace_active":
                return self._recover_active_replacement(state, transition)
            if transition.operation == "legacy_replace":
                return self._recover_legacy_replacement(state, transition)
            if transition.operation == "legacy_remove":
                return self._recover_legacy_remove(state, transition)
            if transition.operation != "switch":
                return AuthResult.failure(
                    AuthFailureCode.SYNC_PENDING,
                    "A pending local operation requires recovery.",
                    operation="recover_session",
                    phase="pending_transition",
                )

            target = self._account_from_store(transition.target_account)
            if target is not None:
                if target.name not in state.aliases:
                    state = replace(state, aliases=(*state.aliases, target.name))
                    self.state_repository.save(state)
                result = self.native_session.activate(
                    target,
                    phase_callback=self._phase_callback(transition),
                )
                if result.ok:
                    self._commit_active(target.name)
                    return result

            previous = self._account_from_store(transition.previous_account)
            if previous is not None:
                restored = self.native_session.activate(previous)
                if restored.ok:
                    self._commit_active(previous.name)
                    return AuthResult.success("Previous session restored.")

            failed = replace(
                self.state_repository.load(),
                confirmed_active=None,
                pending_transition=StateTransition(
                    "switch",
                    transition.target_account,
                    transition.previous_account,
                    "recovery_failed",
                ),
            )
            self.state_repository.save(failed)
            return AuthResult.failure(
                AuthFailureCode.SYNC_ROLLBACK_FAILED,
                "The Supabase CLI session could not be recovered.",
                operation="recover_session",
                phase="restore_previous",
            )
        except Exception as error:
            return classify_local_failure(error, operation="recover_session")

    def get_active_name(self) -> Optional[str]:
        return self.state_repository.load().confirmed_active

    def validate_named_account(self, name: str) -> AuthResult:
        try:
            account = self.get(name)
            if account is None:
                return AuthResult.failure(
                    AuthFailureCode.CREDENTIAL_MISSING,
                    "The credential for this account is missing.",
                    operation="validate_account",
                    phase="credential_access",
                )
            return self.cli.validate_access_token(account)
        except Exception as error:
            return classify_local_failure(error, operation="validate_account")

    @_exclusive_operation("remove")
    def remove(self, name: str) -> AuthResult:
        try:
            if not is_valid_account_name(name):
                raise InvalidAccountNameError()
            recovery = self.recover_pending_sync()
            if not recovery.ok:
                return recovery
            state = self.state_repository.load()
            if name not in state.aliases:
                return self._with_context(
                    AuthResult.success("Account was already removed."),
                    "remove",
                    "complete",
                )

            transition = StateTransition(
                "remove", name, state.confirmed_active, "prepared"
            )
            self.state_repository.save(replace(state, pending_transition=transition))
            if state.confirmed_active == name:
                logout = self.native_session.logout()
                if not logout.ok:
                    mutation_state = getattr(
                        self.native_session, "mutation_state", None
                    )
                    if mutation_state is MutationState.NONE:
                        self.state_repository.save(
                            replace(state, pending_transition=None)
                        )
                    else:
                        self.state_repository.save(
                            replace(
                                state,
                                confirmed_active=None,
                                pending_transition=transition,
                            )
                        )
                    return logout
                state = replace(
                    self.state_repository.load(),
                    confirmed_active=None,
                    pending_transition=replace(transition, phase="logged_out"),
                )
                self.state_repository.save(state)

            self.credential_store.delete(name)
            state = self.state_repository.load()
            self.state_repository.save(
                replace(
                    state,
                    aliases=tuple(alias for alias in state.aliases if alias != name),
                    confirmed_active=(
                        None if state.confirmed_active == name else state.confirmed_active
                    ),
                    pending_transition=None,
                )
            )
            return self._with_context(
                AuthResult.success("Account removed."), "remove", "complete"
            )
        except Exception as error:
            return classify_local_failure(error, operation="remove")

    @_exclusive_operation("reset")
    def reset_all(self) -> AuthResult:
        try:
            state = self.state_repository.load()
            pending_target = (
                None
                if state.pending_transition is None
                else state.pending_transition.target_account
            )
            aliases = state.aliases
            if pending_target is not None and pending_target not in aliases:
                aliases = (*aliases, pending_target)
            transition = StateTransition(
                "reset", None, state.confirmed_active, "prepared"
            )
            state = replace(
                state, aliases=aliases, pending_transition=transition
            )
            self.state_repository.save(state)
            return self._recover_reset(state, transition)
        except Exception as error:
            return classify_local_failure(error, operation="reset")

    def run_active(
        self,
        arguments: Sequence[str],
        stdout_sink=None,
        stderr_sink=None,
    ) -> CommandResult:
        try:
            active = self.get_active_name()
            if active is None:
                return CommandResult.failure(
                    AuthFailureCode.ACTIVE_ACCOUNT_MISSING,
                    "No active account was selected. Run 'supa.cc switch <name>'.",
                    operation="run",
                    phase="load_active",
                )
            account = self.get(active)
            if account is None:
                return CommandResult.failure(
                    AuthFailureCode.CREDENTIAL_MISSING,
                    "The credential for the active account was removed.",
                    operation="run",
                    phase="credential_access",
                )
            result = self.cli.execute_authenticated_streaming(
                account,
                arguments,
                stdout_sink=stdout_sink or (lambda _chunk: None),
                stderr_sink=stderr_sink or (lambda _chunk: None),
            )
            return replace(result, operation="run")
        except Exception as error:
            failure = classify_local_failure(error, operation="run")
            return CommandResult.failure(
                failure.code,
                failure.message,
                exit_code=failure.exit_code,
                operation="run",
                phase=failure.phase,
            )

    def _load_or_reauthorize(
        self, name: str, token_provider: Optional[TokenProvider]
    ) -> tuple[Optional[Account], bool, bool, Optional[AuthResult]]:
        token = self.credential_store.get(name)
        if token is not None:
            return Account(name, token), False, False, None
        if token_provider is None:
            return None, False, False, AuthResult.failure(
                AuthFailureCode.CREDENTIAL_MISSING,
                "The credential for this account was removed. Provide a new PAT.",
                operation="switch",
                phase="credential_access",
            )
        supplied = token_provider(name)
        if supplied is None:
            return None, False, False, AuthResult.failure(
                AuthFailureCode.TOKEN_MISSING,
                "A PAT is required to restore this account credential.",
                operation="switch",
                phase="credential_prompt",
            )
        account = self._validated_account(name, supplied)
        validation = self.cli.validate_access_token(account)
        if not validation.ok:
            return None, False, False, validation
        self.credential_store.set(account)
        return account, True, True, None

    def _restore_after_failed_switch(
        self, transition: StateTransition, failure: AuthResult
    ) -> AuthResult:
        if getattr(self.native_session, "mutation_state", None) is MutationState.NONE:
            state = self.state_repository.load()
            self.state_repository.save(
                replace(
                    state,
                    confirmed_active=transition.previous_account,
                    pending_transition=None,
                )
            )
            return self._with_context(failure, "switch", "native_session")
        previous = self._account_from_store(transition.previous_account)
        if previous is not None:
            restored = self.native_session.activate(previous)
            if restored.ok:
                self._commit_active(previous.name)
                return self._with_context(
                    failure, "switch", "native_session"
                )
        state = self.state_repository.load()
        self.state_repository.save(
            replace(
                state,
                confirmed_active=None,
                pending_transition=StateTransition(
                    "switch",
                    transition.target_account,
                    transition.previous_account,
                    "recovery_failed",
                ),
            )
        )
        return AuthResult.failure(
            AuthFailureCode.SYNC_ROLLBACK_FAILED,
            "The previous Supabase CLI session could not be restored.",
            operation="switch",
            phase="restore_previous",
        )

    def _recover_remove(
        self, state: AccountState, transition: StateTransition
    ) -> AuthResult:
        target = transition.target_account
        assert target is not None
        if transition.phase == "prepared" and (
            state.confirmed_active == target
            or transition.previous_account == target
        ):
            logout = self.native_session.logout()
            if not logout.ok:
                return self._with_context(
                    logout, "recover_session", "logout"
                )
            state = replace(
                state,
                confirmed_active=None,
                pending_transition=replace(transition, phase="logged_out"),
            )
            self.state_repository.save(state)
        self.credential_store.delete(target)
        self.credential_store.delete(self._legacy_backup_name(target))
        self.state_repository.save(
            replace(
                self.state_repository.load(),
                aliases=tuple(alias for alias in state.aliases if alias != target),
                confirmed_active=(
                    None if state.confirmed_active == target else state.confirmed_active
                ),
                pending_transition=None,
            )
        )
        return self._with_context(
            AuthResult.success("Interrupted account removal completed."),
            "recover_session",
            "complete",
        )

    def _restore_after_failed_active_replacement(
        self, transition: StateTransition, failure: AuthResult
    ) -> AuthResult:
        if getattr(self.native_session, "mutation_state", None) is MutationState.NONE:
            self._commit_active(transition.target_account)
            return failure
        previous = self._account_from_store(transition.target_account)
        if previous is not None:
            restored = self.native_session.activate(previous)
            if restored.ok:
                self._commit_active(previous.name)
                return failure
        state = self.state_repository.load()
        self.state_repository.save(
            replace(
                state,
                confirmed_active=None,
                pending_transition=replace(
                    transition, phase="recovery_failed"
                ),
            )
        )
        return AuthResult.failure(
            AuthFailureCode.SYNC_ROLLBACK_FAILED,
            "The previous Supabase CLI session could not be restored.",
            operation="add",
            phase="restore_previous",
        )

    def _recover_add(
        self, state: AccountState, transition: StateTransition
    ) -> AuthResult:
        target = transition.target_account
        assert target is not None
        account = self._account_from_store(target)
        aliases = state.aliases
        if account is not None and target not in aliases:
            aliases = (*aliases, target)
        self.state_repository.save(
            replace(state, aliases=aliases, pending_transition=None)
        )
        return self._with_context(
            AuthResult.success("Interrupted account save reconciled."),
            "recover_session",
            "complete",
        )

    def _recover_active_replacement(
        self, state: AccountState, transition: StateTransition
    ) -> AuthResult:
        account = self._account_from_store(transition.target_account)
        if account is not None:
            activation = self.native_session.activate(account)
            if activation.ok:
                self._commit_active(account.name)
                return self._with_context(
                    activation, "recover_session", "complete"
                )
        self.state_repository.save(
            replace(
                state,
                confirmed_active=None,
                pending_transition=replace(
                    transition, phase="recovery_failed"
                ),
            )
        )
        return AuthResult.failure(
            AuthFailureCode.SYNC_ROLLBACK_FAILED,
            "The active credential and CLI session could not be reconciled.",
            operation="recover_session",
            phase="restore_previous",
        )

    def _recover_legacy_replacement(
        self, state: AccountState, transition: StateTransition
    ) -> AuthResult:
        target = transition.target_account
        assert target is not None
        backup_name = self._legacy_backup_name(target)
        backup_token = self.credential_store.get(backup_name)
        active_replacement = transition.previous_account == target
        rollback_phases = {
            "credential_backup", "credential_written", "native_login", "rollback"
        }
        if transition.phase == "intent" and backup_token is None:
            self.state_repository.save(replace(state, pending_transition=None))
            return AuthResult.success("Interrupted credential update cancelled.")
        if transition.phase in rollback_phases and backup_token is not None:
            restored = Account(target, backup_token)
            self.credential_store.set(restored)
            if active_replacement and transition.phase in {"native_login", "rollback"}:
                activation = self.native_session.activate(restored)
                if not activation.ok:
                    return self._with_context(
                        activation, "recover_session", "restore_previous"
                    )
        elif active_replacement and transition.phase in {
            "native_verified", "local_write", "verified"
        }:
            current = self._account_from_store(target)
            if current is None:
                return AuthResult.failure(
                    AuthFailureCode.CREDENTIAL_MISSING,
                    "The interrupted credential update cannot be recovered.",
                    operation="recover_session",
                    phase="credential_access",
                )
            activation = self.native_session.activate(current)
            if not activation.ok:
                return self._with_context(
                    activation, "recover_session", "native_session"
                )
        self.credential_store.delete(backup_name)
        aliases = state.aliases if target in state.aliases else (*state.aliases, target)
        self.state_repository.save(
            replace(
                state,
                aliases=aliases,
                confirmed_active=(
                    target if active_replacement else state.confirmed_active
                ),
                pending_transition=None,
            )
        )
        return AuthResult.success("Interrupted credential update reconciled.")

    def _recover_legacy_remove(
        self, state: AccountState, transition: StateTransition
    ) -> AuthResult:
        target = transition.target_account
        assert target is not None
        backup_name = self._legacy_backup_name(target)
        backup_token = self.credential_store.get(backup_name)
        if transition.phase == "intent" and backup_token is None:
            self.state_repository.save(replace(state, pending_transition=None))
            return AuthResult.success("Interrupted account removal cancelled.")
        self.credential_store.delete(target)
        self.credential_store.delete(backup_name)
        self.state_repository.save(
            replace(
                state,
                aliases=tuple(alias for alias in state.aliases if alias != target),
                confirmed_active=(
                    None if state.confirmed_active == target else state.confirmed_active
                ),
                pending_transition=None,
            )
        )
        return AuthResult.success("Interrupted account removal completed.")

    def _recover_reset(
        self, state: AccountState, transition: StateTransition
    ) -> AuthResult:
        logout = self.native_session.logout()
        failed_names = []
        for name in state.aliases:
            try:
                self.credential_store.delete(name)
                self.credential_store.delete(self._legacy_backup_name(name))
            except Exception:
                failed_names.append(name)
        if failed_names:
            self.state_repository.save(
                AccountState(
                    aliases=tuple(failed_names),
                    confirmed_active=None,
                    pending_transition=replace(
                        transition, phase="credentials_deleted"
                    ),
                )
            )
        else:
            self.state_repository.clear()
        if not logout.ok or failed_names:
            return AuthResult.failure(
                AuthFailureCode.RESET_PARTIAL,
                "Local cleanup was partial and can be retried safely.",
                operation="reset",
                phase="native_cleanup",
            )
        return self._with_context(
            AuthResult.success(
                "All Supa.cc accounts and local state were removed."
            ),
            "reset",
            "complete",
        )

    def _phase_callback(self, transition: StateTransition):
        def record(phase: str) -> None:
            state = self.state_repository.load()
            self.state_repository.save(
                replace(
                    state,
                    pending_transition=replace(transition, phase=phase),
                )
            )

        return record

    def _commit_active(self, name: str) -> None:
        state = self.state_repository.load()
        self.state_repository.save(
            replace(state, confirmed_active=name, pending_transition=None)
        )

    def _account_from_store(self, name: Optional[str]) -> Optional[Account]:
        if name is None:
            return None
        token = self.credential_store.get(name)
        return None if token is None else Account(name, token)

    @staticmethod
    def _legacy_backup_name(name: str) -> str:
        digest = hashlib.sha256(name.encode("utf-8")).hexdigest()
        return f"!supa.cc-backup!{digest}"

    @staticmethod
    def _with_context(result: AuthResult, operation: str, phase: str) -> AuthResult:
        return replace(result, operation=operation, phase=phase)

    @staticmethod
    def _validated_account(name: str, token: str) -> Account:
        if not is_valid_account_name(name):
            raise InvalidAccountNameError()
        if not is_valid_access_token(token):
            raise InvalidAccessTokenError()
        return Account(name, token)
