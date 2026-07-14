"""Versioned, secret-free account state and legacy migration."""

from __future__ import annotations

import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional

from ..auth import (
    AccountIndexInvalidError,
    AccountIndexReadError,
    is_valid_account_name,
)
from ..file_lock import locked_file
from ..state import atomic_write_json, read_json, read_text, secure_remove
from .store import safe_load_json_index


STATE_VERSION = 3
_STATE_MAX_BYTES = 1024 * 1024
_ACTIVE_ACCOUNT_MAX_BYTES = 256
_SAFE_STATE_WORD = re.compile(r"[a-z][a-z0-9_]{0,49}")
_TRANSITION_PHASES = {
    "switch": frozenset(
        {
            "prepared",
            "logged_out",
            "logged_in",
            "verified",
            "rollback",
            "recovery_failed",
        }
    ),
    "remove": frozenset(
        {"prepared", "logged_out", "credential_deleted", "metadata_committed"}
    ),
    "reset": frozenset(
        {"prepared", "logged_out", "credentials_deleted", "completed"}
    ),
    "add": frozenset({"prepared", "credential_written", "metadata_committed"}),
    "replace_active": frozenset(
        {
            "prepared",
            "session_verified",
            "credential_written",
            "recovery_failed",
        }
    ),
    "legacy_replace": frozenset(
        {
            "intent", "credential_backup", "credential_written",
            "index_committed", "native_login", "native_verified",
            "local_write", "verified", "rollback",
        }
    ),
    "legacy_remove": frozenset(
        {"intent", "credential_backup", "index_committed"}
    ),
    "migrate": frozenset({"awaiting_activation"}),
    # Accepted only so a validated legacy journal can be recovered by v3.
    "activate": frozenset(
        {
            "intent",
            "credential_backup",
            "native_login",
            "native_verified",
            "local_write",
            "verified",
            "rollback",
        }
    ),
    "logout": frozenset(
        {
            "intent",
            "credential_backup",
            "native_verified",
            "local_write",
            "verified",
            "rollback",
        }
    ),
    "account_add": frozenset({"intent", "credential_written", "index_committed"}),
    "account_replace": frozenset(
        {"intent", "credential_backup", "credential_written", "index_committed"}
    ),
    "account_remove": frozenset(
        {"intent", "credential_backup", "index_committed"}
    ),
    "active_account_add": frozenset(
        {"intent", "index_committed", "native_login", "native_verified"}
    ),
}


class StateError(RuntimeError):
    """Base class for safe account-state failures."""


class StateReadError(StateError):
    """The account state could not be read safely."""


class StateInvalidError(StateError):
    """The account state does not match the supported schema."""


class StateConflictError(StateInvalidError):
    """Legacy and current state coexist with incompatible information."""


class StateWriteError(StateError):
    """The account state could not be persisted safely."""


def _valid_state_word(value: object) -> bool:
    return isinstance(value, str) and _SAFE_STATE_WORD.fullmatch(value) is not None


@dataclass(frozen=True)
class StateTransition:
    operation: str
    target_account: Optional[str]
    previous_account: Optional[str]
    phase: str

    def __post_init__(self) -> None:
        if not _valid_state_word(self.operation) or not _valid_state_word(self.phase):
            raise StateInvalidError("The local account state is invalid.")
        phases = _TRANSITION_PHASES.get(self.operation)
        if phases is None or self.phase not in phases:
            raise StateInvalidError("The local account state is invalid.")
        for name in (self.target_account, self.previous_account):
            if name is not None and not is_valid_account_name(name):
                raise StateInvalidError("The local account state is invalid.")
        target_required = self.operation in {
            "switch",
            "remove",
            "migrate",
            "activate",
            "account_add",
            "account_replace",
            "account_remove",
            "active_account_add",
            "add",
            "replace_active",
            "legacy_replace",
            "legacy_remove",
        }
        if target_required and self.target_account is None:
            raise StateInvalidError("The local account state is invalid.")
        if self.operation in {"logout", "reset"} and self.target_account is not None:
            raise StateInvalidError("The local account state is invalid.")
        if self.operation in {
            "migrate",
            "account_add",
            "account_replace",
            "account_remove",
            "active_account_add",
            "add",
        } and self.previous_account is not None:
            raise StateInvalidError("The local account state is invalid.")
        if self.operation == "replace_active" and (
            self.previous_account != self.target_account
        ):
            raise StateInvalidError("The local account state is invalid.")

    def to_payload(self) -> dict[str, object]:
        return {
            "operation": self.operation,
            "target_account": self.target_account,
            "previous_account": self.previous_account,
            "phase": self.phase,
        }

    @classmethod
    def from_payload(cls, payload: object) -> "StateTransition":
        if not isinstance(payload, dict) or set(payload) != {
            "operation",
            "target_account",
            "previous_account",
            "phase",
        }:
            raise StateInvalidError("The local account state is invalid.")
        return cls(
            operation=payload["operation"],
            target_account=payload["target_account"],
            previous_account=payload["previous_account"],
            phase=payload["phase"],
        )


@dataclass(frozen=True)
class AccountState:
    aliases: tuple[str, ...] = ()
    confirmed_active: Optional[str] = None
    pending_transition: Optional[StateTransition] = None
    version: int = field(default=STATE_VERSION, init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.aliases, tuple):
            raise StateInvalidError("The local account state is invalid.")
        if any(not is_valid_account_name(name) for name in self.aliases):
            raise StateInvalidError("The local account state is invalid.")
        if len(set(self.aliases)) != len(self.aliases):
            raise StateInvalidError("The local account state is invalid.")
        if (
            self.confirmed_active is not None
            and self.confirmed_active not in self.aliases
        ):
            raise StateInvalidError("The local account state is invalid.")
        if self.pending_transition is not None and not isinstance(
            self.pending_transition, StateTransition
        ):
            raise StateInvalidError("The local account state is invalid.")

    @property
    def accounts(self) -> tuple[str, ...]:
        return self.aliases

    @property
    def active_account(self) -> Optional[str]:
        return self.confirmed_active

    @property
    def transition(self) -> Optional[StateTransition]:
        return self.pending_transition

    def to_payload(self) -> dict[str, object]:
        return {
            "version": self.version,
            "aliases": list(self.aliases),
            "confirmed_active": self.confirmed_active,
            "pending_transition": (
                None
                if self.pending_transition is None
                else self.pending_transition.to_payload()
            ),
        }

    @classmethod
    def from_payload(cls, payload: object) -> "AccountState":
        if not isinstance(payload, dict) or set(payload) != {
            "version",
            "aliases",
            "confirmed_active",
            "pending_transition",
        }:
            raise StateInvalidError("The local account state is invalid.")
        if payload["version"] != STATE_VERSION or not isinstance(
            payload["aliases"], list
        ):
            raise StateInvalidError("The local account state is invalid.")
        transition_payload = payload["pending_transition"]
        transition = (
            None
            if transition_payload is None
            else StateTransition.from_payload(transition_payload)
        )
        return cls(
            aliases=tuple(payload["aliases"]),
            confirmed_active=payload["confirmed_active"],
            pending_transition=transition,
        )


class StateTransaction:
    """Mutable handle to one state snapshot while the repository lock is held."""

    def __init__(self, repository: "StateRepository", state: AccountState) -> None:
        self._repository = repository
        self.state = state

    def save(self, state: AccountState) -> None:
        if not isinstance(state, AccountState):
            raise StateInvalidError("The local account state is invalid.")
        self._repository._write_state_unlocked(state)
        self.state = state


class StateRepository:
    """Own the single durable account-state document under one process lock."""

    def __init__(
        self,
        path: Path,
        *,
        legacy_accounts_path: Optional[Path] = None,
        legacy_active_path: Optional[Path] = None,
        legacy_journal_path: Optional[Path] = None,
    ) -> None:
        self.path = Path(path)
        parent = self.path.parent
        self.lock_path = parent / ".state.lock"
        self.legacy_accounts_path = Path(
            legacy_accounts_path or parent / "accounts.json"
        )
        self.legacy_active_path = Path(
            legacy_active_path or parent / "active-account"
        )
        self.legacy_journal_path = Path(
            legacy_journal_path or parent / "session-sync.json"
        )
        self.legacy_index_lock_path = self.legacy_accounts_path.with_name(
            f".{self.legacy_accounts_path.name}.lock"
        )
        self.legacy_session_lock_path = self.legacy_journal_path.with_name(
            ".session-sync.lock"
        )

    @contextmanager
    def locked(self, *, writing: bool = False) -> Iterator[None]:
        try:
            with locked_file(self.lock_path):
                yield
        except StateError:
            raise
        except OSError:
            error_type = StateWriteError if writing else StateReadError
            raise error_type("Unable to access the local account state.") from None

    def load(self) -> AccountState:
        with self.locked():
            return self._load_current_unlocked()

    def save(self, state: AccountState) -> None:
        if not isinstance(state, AccountState):
            raise StateInvalidError("The local account state is invalid.")
        with self.locked(writing=True):
            self._write_state_unlocked(state)

    def clear(self) -> None:
        """Remove the durable document after an explicit destructive reset."""
        with self.locked(writing=True):
            try:
                with self._legacy_locked():
                    secure_remove(self.path)
                    for legacy_path in (
                        self.legacy_accounts_path,
                        self.legacy_active_path,
                        self.legacy_journal_path,
                    ):
                        secure_remove(legacy_path)
            except OSError:
                raise StateWriteError(
                    "Unable to clear the local account state."
                ) from None
            except StateReadError:
                raise StateWriteError(
                    "Unable to clear the local account state."
                ) from None

    @contextmanager
    def transaction(self) -> Iterator[StateTransaction]:
        with self.locked(writing=True):
            yield StateTransaction(self, self._load_current_unlocked())

    def _load_current_unlocked(self) -> AccountState:
        state = self._read_state_file()
        with self._legacy_locked():
            if self._legacy_state_exists():
                if state is None:
                    state = self._migrate_unlocked()
                else:
                    raise StateConflictError(
                        "Legacy and current local account state conflict."
                    )
            elif state is None:
                state = AccountState()
                self._write_state_unlocked(state)
        return state

    def _read_state_file(self) -> Optional[AccountState]:
        try:
            payload = read_json(self.path, _STATE_MAX_BYTES)
        except (ValueError, TypeError):
            raise StateInvalidError("The local account state is invalid.") from None
        except OSError:
            raise StateReadError("Unable to read the local account state.") from None
        if payload is None:
            return None
        try:
            return AccountState.from_payload(payload)
        except StateInvalidError:
            raise
        except (TypeError, ValueError):
            raise StateInvalidError("The local account state is invalid.") from None

    def _write_state_unlocked(self, state: AccountState) -> None:
        try:
            atomic_write_json(self.path, state.to_payload(), indent=2)
        except OSError:
            raise StateWriteError("Unable to write the local account state.") from None
        verified = self._verify_persisted_state()
        if verified != state:
            raise StateWriteError("Unable to verify the local account state.")

    def _verify_persisted_state(self) -> AccountState:
        state = self._read_state_file()
        if state is None:
            raise StateReadError("Unable to verify the local account state.")
        return state

    def _migrate_unlocked(self) -> AccountState:
        accounts = self._read_legacy_accounts()
        active = self._read_legacy_active()
        legacy_transition = self._read_legacy_transition()
        transition = legacy_transition

        names = list(accounts)
        if legacy_transition is not None:
            transition = self._normalize_legacy_transition(legacy_transition)
        elif active is not None:
            if active not in names:
                names.append(active)
            transition = StateTransition(
                operation="migrate",
                target_account=active,
                previous_account=None,
                phase="awaiting_activation",
            )

        state = AccountState(
            aliases=tuple(names),
            confirmed_active=None,
            pending_transition=transition,
        )
        self._write_state_unlocked(state)
        self._cleanup_legacy_files()
        return state

    @staticmethod
    def _normalize_legacy_transition(
        transition: StateTransition,
    ) -> Optional[StateTransition]:
        if transition.operation in {"activate", "active_account_add"}:
            if (
                transition.operation == "activate"
                and transition.target_account == transition.previous_account
            ):
                return StateTransition(
                    "legacy_replace",
                    transition.target_account,
                    transition.previous_account,
                    transition.phase,
                )
            return StateTransition(
                operation="switch",
                target_account=transition.target_account,
                previous_account=transition.previous_account,
                phase="prepared",
            )
        if transition.operation == "logout":
            target = transition.previous_account
            if target is None:
                return None
            phase = (
                "logged_out"
                if transition.phase in {"native_verified", "local_write", "verified"}
                else "prepared"
            )
            return StateTransition("remove", target, target, phase)
        if transition.operation == "account_add":
            phase = "prepared" if transition.phase == "intent" else "credential_written"
            return StateTransition("add", transition.target_account, None, phase)
        if transition.operation == "account_replace":
            return StateTransition(
                "legacy_replace", transition.target_account, None, transition.phase
            )
        if transition.operation == "account_remove":
            return StateTransition(
                "legacy_remove",
                transition.target_account,
                None,
                transition.phase,
            )
        return transition

    def _read_legacy_accounts(self) -> list[str]:
        try:
            names = safe_load_json_index(self.legacy_accounts_path)
        except AccountIndexInvalidError:
            raise StateInvalidError("The legacy account state is invalid.") from None
        except AccountIndexReadError:
            raise StateReadError("Unable to read the legacy account state.") from None
        return [] if names is None else names

    def _read_legacy_active(self) -> Optional[str]:
        try:
            contents = read_text(self.legacy_active_path, _ACTIVE_ACCOUNT_MAX_BYTES)
        except OSError:
            raise StateReadError("Unable to read the legacy account state.") from None
        if contents is None:
            return None
        name = contents[:-1] if contents.endswith("\n") else contents
        if not is_valid_account_name(name):
            raise StateInvalidError("The legacy account state is invalid.")
        return name

    def _read_legacy_transition(self) -> Optional[StateTransition]:
        try:
            payload = read_json(self.legacy_journal_path, 4096)
        except (ValueError, TypeError):
            raise StateInvalidError("The legacy account state is invalid.") from None
        except OSError:
            raise StateReadError("Unable to read the legacy account state.") from None
        if payload is None:
            return None
        return StateTransition.from_payload(payload)

    def _cleanup_legacy_files(self) -> None:
        for path in (
            self.legacy_accounts_path,
            self.legacy_active_path,
            self.legacy_journal_path,
        ):
            try:
                secure_remove(path)
            except OSError:
                raise StateWriteError(
                    "Unable to finalize the local account-state migration."
                ) from None

    def _legacy_state_exists(self) -> bool:
        for path in (
            self.legacy_accounts_path,
            self.legacy_active_path,
            self.legacy_journal_path,
        ):
            try:
                path.lstat()
            except FileNotFoundError:
                continue
            except OSError:
                raise StateReadError("Unable to read the legacy account state.") from None
            return True
        return False

    @contextmanager
    def _legacy_locked(self) -> Iterator[None]:
        try:
            with locked_file(self.legacy_session_lock_path):
                with locked_file(self.legacy_index_lock_path):
                    yield
        except StateError:
            raise
        except OSError:
            raise StateReadError("Unable to access the legacy account state.") from None
