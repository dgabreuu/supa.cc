import json
import os
from contextlib import contextmanager

import pytest

from supa_cc.accounts.state import (
    AccountState,
    StateInvalidError,
    StateConflictError,
    StateReadError,
    StateRepository,
    StateTransition,
    StateWriteError,
)
import supa_cc.accounts.state as account_state


def _private_text(path, contents):
    path.write_text(contents, encoding="utf-8")
    path.chmod(0o600)


def test_state_repository_round_trips_versioned_secret_free_state(tmp_path):
    repository = StateRepository(tmp_path / "state.json")
    expected = AccountState(
        aliases=("personal", "work"),
        confirmed_active="work",
        pending_transition=StateTransition(
            operation="switch",
            target_account="personal",
            previous_account="work",
            phase="prepared",
        ),
    )

    repository.save(expected)

    assert repository.load() == expected
    contents = repository.path.read_text(encoding="utf-8")
    assert "token" not in contents.lower()


def test_state_repository_rejects_corrupt_state_without_replacing_it(tmp_path):
    path = tmp_path / "state.json"
    _private_text(path, '{"version": 3, "accounts": "invalid"}\n')
    repository = StateRepository(path)

    with pytest.raises(StateInvalidError):
        repository.load()

    assert json.loads(path.read_text(encoding="utf-8"))["accounts"] == "invalid"


def test_state_repository_migrates_legacy_aliases_and_requires_reactivation(
    tmp_path,
):
    _private_text(
        tmp_path / "accounts.json",
        json.dumps({"accounts": ["personal", "work"]}),
    )
    _private_text(tmp_path / "active-account", "work\n")
    repository = StateRepository(tmp_path / "state.json")

    state = repository.load()

    assert state == AccountState(
        aliases=("personal", "work"),
        confirmed_active=None,
        pending_transition=StateTransition(
            operation="migrate",
            target_account="work",
            previous_account=None,
            phase="awaiting_activation",
        ),
    )
    assert repository.path.exists()
    assert not (tmp_path / "accounts.json").exists()
    assert not (tmp_path / "active-account").exists()


def test_state_repository_converts_legacy_journal_and_migration_is_idempotent(
    tmp_path,
):
    _private_text(
        tmp_path / "accounts.json",
        json.dumps({"accounts": ["personal", "work"]}),
    )
    _private_text(tmp_path / "active-account", "personal\n")
    _private_text(
        tmp_path / "session-sync.json",
        json.dumps(
            {
                "operation": "activate",
                "target_account": "work",
                "previous_account": "personal",
                "phase": "native_login",
            }
        ),
    )
    repository = StateRepository(tmp_path / "state.json")

    first = repository.load()
    second = repository.load()

    assert first == second
    assert first.confirmed_active is None
    assert first.pending_transition == StateTransition(
        operation="switch",
        target_account="work",
        previous_account="personal",
        phase="prepared",
    )
    assert not (tmp_path / "session-sync.json").exists()


def test_state_repository_keeps_legacy_files_when_post_write_verification_fails(
    tmp_path, monkeypatch
):
    legacy = tmp_path / "accounts.json"
    _private_text(legacy, json.dumps({"accounts": ["personal"]}))
    repository = StateRepository(tmp_path / "state.json")

    def fail_verification():
        raise StateReadError("safe verification failure")

    monkeypatch.setattr(repository, "_verify_persisted_state", fail_verification)

    with pytest.raises(StateReadError):
        repository.load()

    assert legacy.exists()


def test_state_validation_rejects_unindexed_active_account():
    with pytest.raises(StateInvalidError):
        AccountState(aliases=("personal",), confirmed_active="work")


@pytest.mark.parametrize(
    "transition",
    [
        StateTransition,
    ],
)
def test_state_transition_rejects_unknown_operation(transition):
    with pytest.raises(StateInvalidError):
        transition("unknown", "personal", None, "prepared")


def test_state_transition_rejects_invalid_phase_for_operation():
    with pytest.raises(StateInvalidError):
        StateTransition("switch", "personal", None, "credential_deleted")


def test_state_transition_requires_switch_target():
    with pytest.raises(StateInvalidError):
        StateTransition("switch", None, None, "prepared")


def test_state_repository_rejects_multiline_legacy_active_selection(tmp_path):
    _private_text(tmp_path / "accounts.json", json.dumps({"accounts": ["work"]}))
    _private_text(tmp_path / "active-account", "work\nextra\n")
    repository = StateRepository(tmp_path / "state.json")

    with pytest.raises(StateInvalidError):
        repository.load()

    assert (tmp_path / "accounts.json").exists()


def test_state_repository_classifies_atomic_write_failure(tmp_path, monkeypatch):
    repository = StateRepository(tmp_path / "state.json")

    def fail_write(*_args, **_kwargs):
        raise OSError("private path")

    monkeypatch.setattr(account_state, "atomic_write_json", fail_write)

    with pytest.raises(StateWriteError, match="local account state"):
        repository.save(AccountState())


@pytest.mark.skipif(os.name == "nt", reason="symlink privilege varies on Windows")
def test_state_repository_rejects_unsafe_lock_as_typed_error(tmp_path):
    target = tmp_path / "target"
    _private_text(target, "lock")
    (tmp_path / ".state.lock").symlink_to(target)

    with pytest.raises(StateReadError, match="local account state"):
        StateRepository(tmp_path / "state.json").load()


@pytest.mark.skipif(os.name == "nt", reason="symlink privilege varies on Windows")
def test_state_repository_classifies_save_lock_failure_as_write_error(tmp_path):
    target = tmp_path / "target"
    _private_text(target, "lock")
    (tmp_path / ".state.lock").symlink_to(target)

    with pytest.raises(StateWriteError, match="local account state"):
        StateRepository(tmp_path / "state.json").save(AccountState())


@pytest.mark.parametrize(
    "operation,target,previous,phase",
    [
        ("logout", "work", None, "intent"),
        ("reset", "work", None, "prepared"),
        ("account_add", "work", "personal", "intent"),
        ("account_replace", "work", "personal", "intent"),
        ("account_remove", "work", "personal", "intent"),
    ],
)
def test_state_transition_rejects_impossible_account_relations(
    operation, target, previous, phase
):
    with pytest.raises(StateInvalidError):
        StateTransition(operation, target, previous, phase)


def test_state_validation_wraps_unhashable_alias_as_invalid():
    with pytest.raises(StateInvalidError):
        AccountState(aliases=(["not", "a", "name"],))


def test_state_repository_checks_legacy_state_while_legacy_locks_are_held(
    tmp_path, monkeypatch
):
    repository = StateRepository(tmp_path / "state.json")
    held = False

    @contextmanager
    def record_lock():
        nonlocal held
        held = True
        try:
            yield
        finally:
            held = False

    def require_lock():
        assert held is True
        return False

    monkeypatch.setattr(repository, "_legacy_locked", record_lock)
    monkeypatch.setattr(repository, "_legacy_state_exists", require_lock)

    assert repository.load() == AccountState()


def test_clear_holds_legacy_locks_while_removing_legacy_state(tmp_path, monkeypatch):
    repository = StateRepository(tmp_path / "state.json")
    repository.save(AccountState())
    held = False

    @contextmanager
    def record_lock():
        nonlocal held
        held = True
        try:
            yield
        finally:
            held = False

    original = account_state.secure_remove

    def require_lock(path):
        if path != repository.path:
            assert held is True
        original(path)

    monkeypatch.setattr(repository, "_legacy_locked", record_lock)
    monkeypatch.setattr(account_state, "secure_remove", require_lock)

    repository.clear()


@pytest.mark.parametrize(
    "operation,phase,expected_operation,expected_phase",
    [
        ("account_add", "credential_written", "add", "credential_written"),
        ("account_remove", "index_committed", "legacy_remove", "index_committed"),
        ("logout", "native_verified", "remove", "logged_out"),
        ("account_replace", "credential_backup", "legacy_replace", "credential_backup"),
    ],
)
def test_migration_preserves_recoverable_legacy_mutations(
    tmp_path, operation, phase, expected_operation, expected_phase
):
    target = None if operation == "logout" else "work"
    previous = "work" if operation == "logout" else None
    _private_text(
        tmp_path / "session-sync.json",
        json.dumps(
            {
                "operation": operation,
                "target_account": target,
                "previous_account": previous,
                "phase": phase,
            }
        ),
    )

    state = StateRepository(tmp_path / "state.json").load()

    assert state.pending_transition is not None
    assert state.pending_transition.operation == expected_operation
    assert state.pending_transition.phase == expected_phase


def test_invalid_legacy_journal_is_preserved(tmp_path):
    journal = tmp_path / "session-sync.json"
    _private_text(
        journal,
        json.dumps(
            {
                "operation": "activate",
                "target_account": None,
                "previous_account": None,
                "phase": "native_login",
            }
        ),
    )

    with pytest.raises(StateInvalidError):
        StateRepository(tmp_path / "state.json").load()

    assert journal.exists()


def test_unhashable_legacy_journal_operation_is_typed_and_preserved(tmp_path):
    journal = tmp_path / "session-sync.json"
    _private_text(
        journal,
        json.dumps(
            {
                "operation": [],
                "target_account": "work",
                "previous_account": None,
                "phase": "native_login",
            }
        ),
    )

    with pytest.raises(StateInvalidError):
        StateRepository(tmp_path / "state.json").load()

    assert journal.exists()


def test_existing_v3_state_rejects_conflicting_legacy_journal(tmp_path):
    repository = StateRepository(tmp_path / "state.json")
    repository.save(AccountState(aliases=("personal",), confirmed_active="personal"))
    journal = tmp_path / "session-sync.json"
    _private_text(
        journal,
        json.dumps(
            {
                "operation": "activate",
                "target_account": "work",
                "previous_account": "personal",
                "phase": "native_login",
            }
        ),
    )

    with pytest.raises(StateConflictError):
        repository.load()

    assert journal.exists()
    assert repository.path.exists()


def test_existing_v3_state_rejects_even_empty_legacy_index(tmp_path):
    repository = StateRepository(tmp_path / "state.json")
    repository.save(AccountState(aliases=("personal",), confirmed_active="personal"))
    legacy_index = tmp_path / "accounts.json"
    _private_text(legacy_index, json.dumps({"accounts": []}))

    with pytest.raises(StateConflictError):
        repository.load()

    assert legacy_index.exists()


def test_state_transaction_holds_and_updates_one_current_snapshot(tmp_path):
    repository = StateRepository(tmp_path / "state.json")
    repository.save(AccountState(aliases=("personal",)))

    with repository.transaction() as transaction:
        assert transaction.state == AccountState(aliases=("personal",))
        transaction.save(
            AccountState(aliases=("personal",), confirmed_active="personal")
        )
        assert transaction.state.confirmed_active == "personal"

    assert repository.load().confirmed_active == "personal"


def test_state_transaction_without_save_preserves_snapshot(tmp_path):
    repository = StateRepository(tmp_path / "state.json")
    expected = AccountState(aliases=("personal",))
    repository.save(expected)

    with repository.transaction() as transaction:
        assert transaction.state == expected

    assert repository.load() == expected
