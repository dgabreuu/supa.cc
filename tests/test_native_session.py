import json
import os
import stat
from pathlib import Path
from unittest.mock import Mock

import pytest

from helpers import fake_pat
from supa_cc.auth import AuthFailureCode, AuthResult
from supa_cc.models import Account
from supa_cc.native_session import (
    NativeSessionSynchronizer,
    SessionSyncJournal,
    access_token_fallback_path,
)


def test_access_token_fallback_path_honors_supabase_home(tmp_path):
    path = access_token_fallback_path({"SUPABASE_HOME": str(tmp_path / "home")})

    assert path == tmp_path / "home" / "access-token"


def test_access_token_fallback_path_uses_explicit_home(tmp_path):
    assert access_token_fallback_path({}, home=tmp_path) == (
        tmp_path / ".supabase" / "access-token"
    )


def test_access_token_fallback_path_uses_default_home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    assert access_token_fallback_path({}) == tmp_path / ".supabase" / "access-token"


def test_activate_rejects_inherited_access_token_without_login(tmp_path):
    config = Mock()
    journal = SessionSyncJournal(tmp_path / "session-sync.json")
    synchronizer = NativeSessionSynchronizer(
        config=config,
        env={"SUPABASE_ACCESS_TOKEN": fake_pat("parent")},
        supabase_home=tmp_path / "supabase",
        journal=journal,
    )
    account = Account(name="work", token=fake_pat("work"))

    result = synchronizer.activate(account)

    assert result.ok is False
    assert result.code is AuthFailureCode.ENVIRONMENT_BLOCKED
    assert "SUPABASE_ACCESS_TOKEN" in result.message
    config.login_with_access_token.assert_not_called()


def test_activate_rejects_preexisting_plaintext_fallback(tmp_path):
    supabase_home = tmp_path / "supabase"
    supabase_home.mkdir()
    (supabase_home / "access-token").write_text("secret", encoding="utf-8")
    config = Mock()
    synchronizer = NativeSessionSynchronizer(
        config=config,
        env={},
        supabase_home=supabase_home,
        journal=SessionSyncJournal(tmp_path / "session-sync.json"),
    )

    result = synchronizer.activate(Account(name="work", token=fake_pat("work")))

    assert result.ok is False
    assert result.code is AuthFailureCode.PLAINTEXT_FALLBACK_BLOCKED
    config.login_with_access_token.assert_not_called()
    assert (supabase_home / "access-token").exists()


@pytest.mark.parametrize("entry_kind", ["dangling_symlink", "directory"])
def test_activate_rejects_any_preexisting_fallback_entry(tmp_path, entry_kind):
    supabase_home = tmp_path / "supabase"
    supabase_home.mkdir()
    fallback = supabase_home / "access-token"
    if entry_kind == "dangling_symlink":
        fallback.symlink_to(tmp_path / "missing")
    else:
        fallback.mkdir()
    config = Mock()
    synchronizer = NativeSessionSynchronizer(config, env={}, supabase_home=supabase_home)

    result = synchronizer.activate(Account("work", fake_pat("entry")))

    assert result.code is AuthFailureCode.PLAINTEXT_FALLBACK_BLOCKED
    config.login_with_access_token.assert_not_called()


def test_activate_rejects_fallback_inspection_error(tmp_path, monkeypatch):
    fallback = tmp_path / "supabase" / "access-token"
    config = Mock()
    synchronizer = NativeSessionSynchronizer(config, env={}, supabase_home=fallback.parent)
    original_lstat = Path.lstat

    def fail_lstat(path):
        if path == fallback:
            raise PermissionError("private")
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", fail_lstat)

    result = synchronizer.activate(Account("work", fake_pat("stat")))

    assert result.code is AuthFailureCode.PLAINTEXT_FALLBACK_BLOCKED
    config.login_with_access_token.assert_not_called()


def test_activate_logs_in_verifies_without_env_and_blocks_created_fallback(tmp_path):
    supabase_home = tmp_path / "supabase"
    supabase_home.mkdir()
    config = Mock()
    account = Account(name="work", token=fake_pat("work"))

    def login(_account):
        (supabase_home / "access-token").write_text(account.token, encoding="utf-8")
        return AuthResult.success("login ok")

    config.login_with_access_token.side_effect = login
    synchronizer = NativeSessionSynchronizer(
        config=config,
        env={},
        supabase_home=supabase_home,
        journal=SessionSyncJournal(tmp_path / "session-sync.json"),
    )

    result = synchronizer.activate(account)

    assert result.ok is False
    assert result.code is AuthFailureCode.PLAINTEXT_FALLBACK_BLOCKED
    assert not (supabase_home / "access-token").exists()
    config.verify_persisted_session.assert_not_called()
    assert account.token not in result.message


@pytest.mark.parametrize("failure_kind", ["symlink", "directory", "wrong_owner"])
def test_activate_refuses_unsafe_post_login_fallback_cleanup(
    tmp_path, monkeypatch, failure_kind
):
    supabase_home = tmp_path / "supabase"
    supabase_home.mkdir()
    fallback = supabase_home / "access-token"
    config = Mock()

    def login(_account):
        if failure_kind == "symlink":
            fallback.symlink_to(tmp_path / "missing")
        elif failure_kind == "directory":
            fallback.mkdir()
        else:
            fallback.write_text("not-read", encoding="utf-8")
        return AuthResult.success()

    config.login_with_access_token.side_effect = login
    if failure_kind == "wrong_owner":
        original_lstat = Path.lstat

        def wrong_owner(path):
            value = original_lstat(path)
            if path == fallback:
                values = list(value)
                values[4] = os.getuid() + 1
                return os.stat_result(values)
            return value

        monkeypatch.setattr(Path, "lstat", wrong_owner)
    synchronizer = NativeSessionSynchronizer(config, env={}, supabase_home=supabase_home)

    result = synchronizer.activate(Account("work", fake_pat("unsafe-cleanup")))

    assert result.code is AuthFailureCode.SYNC_ROLLBACK_FAILED
    config.verify_persisted_session.assert_not_called()


def test_activate_detects_fallback_substitution_before_unlink(tmp_path, monkeypatch):
    supabase_home = tmp_path / "supabase"
    supabase_home.mkdir()
    fallback = supabase_home / "access-token"
    config = Mock()

    def login(_account):
        fallback.write_text("not-read", encoding="utf-8")
        return AuthResult.success()

    config.login_with_access_token.side_effect = login
    original_lstat = Path.lstat
    calls = 0

    def substitute(path):
        nonlocal calls
        value = original_lstat(path)
        if path == fallback:
            calls += 1
            if calls == 2:
                fallback.unlink()
                fallback.symlink_to(tmp_path / "missing")
                value = original_lstat(path)
        return value

    monkeypatch.setattr(Path, "lstat", substitute)
    synchronizer = NativeSessionSynchronizer(config, env={}, supabase_home=supabase_home)

    result = synchronizer.activate(Account("work", fake_pat("substitution")))

    assert result.code is AuthFailureCode.SYNC_ROLLBACK_FAILED
    assert fallback.is_symlink()


def test_activate_reports_post_login_unlink_failure(tmp_path, monkeypatch):
    supabase_home = tmp_path / "supabase"
    supabase_home.mkdir()
    fallback = supabase_home / "access-token"
    config = Mock()

    def login(_account):
        fallback.write_text("not-read", encoding="utf-8")
        return AuthResult.success()

    config.login_with_access_token.side_effect = login
    original_unlink = Path.unlink

    def fail_unlink(path, *args, **kwargs):
        if path == fallback:
            raise PermissionError("private")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_unlink)
    synchronizer = NativeSessionSynchronizer(config, env={}, supabase_home=supabase_home)

    result = synchronizer.activate(Account("work", fake_pat("unlink")))

    assert result.code is AuthFailureCode.SYNC_ROLLBACK_FAILED
    assert fallback.exists()


def test_activate_reports_post_login_inspection_failure(tmp_path, monkeypatch):
    supabase_home = tmp_path / "supabase"
    fallback = supabase_home / "access-token"
    config = Mock()

    def login(_account):
        supabase_home.mkdir()
        fallback.write_text("not-read", encoding="utf-8")
        return AuthResult.success()

    config.login_with_access_token.side_effect = login
    original_lstat = Path.lstat

    def fail_after_login(path):
        if path == fallback and fallback.parent.exists():
            raise PermissionError("private")
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", fail_after_login)
    synchronizer = NativeSessionSynchronizer(config, env={}, supabase_home=supabase_home)

    result = synchronizer.activate(Account("work", fake_pat("post-stat")))

    assert result.code is AuthFailureCode.SYNC_ROLLBACK_FAILED
    config.verify_persisted_session.assert_not_called()


def test_activate_succeeds_after_login_and_persisted_verification(tmp_path):
    config = Mock()
    account = Account(name="work", token=fake_pat("work"))
    config.login_with_access_token.return_value = AuthResult.success("login ok")
    config.verify_persisted_session.return_value = AuthResult.success("verified")
    synchronizer = NativeSessionSynchronizer(
        config=config,
        env={},
        supabase_home=tmp_path / "supabase",
        journal=SessionSyncJournal(tmp_path / "session-sync.json"),
    )

    result = synchronizer.activate(account)

    assert result.ok is True
    config.login_with_access_token.assert_called_once_with(account)
    config.verify_persisted_session.assert_called_once_with()
    assert "sincronizada" in result.message.lower() or "ativada" in result.message.lower()
    assert account.token not in result.message


def test_activate_propagates_login_failure_without_verification(tmp_path):
    config = Mock()
    config.login_with_access_token.return_value = AuthResult.failure(
        AuthFailureCode.TOKEN_REJECTED,
        "O token foi rejeitado pela API da Supabase.",
    )
    synchronizer = NativeSessionSynchronizer(
        config=config,
        env={},
        supabase_home=tmp_path / "supabase",
        journal=SessionSyncJournal(tmp_path / "session-sync.json"),
    )

    result = synchronizer.activate(Account(name="work", token=fake_pat("work")))

    assert result.ok is False
    assert result.code is AuthFailureCode.TOKEN_REJECTED
    config.verify_persisted_session.assert_not_called()


def test_logout_requires_successful_logout_and_failed_verification(tmp_path):
    config = Mock()
    config.logout_session.return_value = AuthResult.success("logout ok")
    config.verify_persisted_session.side_effect = [
        AuthResult.success("active"),
        AuthResult.failure(
            AuthFailureCode.TOKEN_MISSING,
            "Token de acesso não foi fornecido à Supabase CLI.",
        ),
    ]
    synchronizer = NativeSessionSynchronizer(
        config=config,
        env={},
        supabase_home=tmp_path / "supabase",
        journal=SessionSyncJournal(tmp_path / "session-sync.json"),
    )

    result = synchronizer.logout()

    assert result.ok is True
    config.logout_session.assert_called_once_with()
    assert config.verify_persisted_session.call_count == 2


def test_logout_returns_success_without_destructive_call_when_already_logged_out(tmp_path):
    config = Mock()
    config.verify_persisted_session.return_value = AuthResult.failure(
        AuthFailureCode.TOKEN_MISSING, "safe"
    )
    synchronizer = NativeSessionSynchronizer(config, env={}, supabase_home=tmp_path)

    result = synchronizer.logout()

    assert result.ok
    config.logout_session.assert_not_called()
    config.verify_persisted_session.assert_called_once_with()


def test_logout_failure_short_circuits_verification(tmp_path):
    config = Mock()
    config.verify_persisted_session.return_value = AuthResult.success()
    failure = AuthResult.failure(AuthFailureCode.NATIVE_LOGOUT_FAILED, "safe")
    config.logout_session.return_value = failure
    synchronizer = NativeSessionSynchronizer(config, env={}, supabase_home=tmp_path)

    result = synchronizer.logout()

    assert result is failure
    config.verify_persisted_session.assert_called_once_with()


def test_logout_fails_when_verification_remains_authenticated(tmp_path):
    config = Mock()
    config.logout_session.return_value = AuthResult.success()
    config.verify_persisted_session.return_value = AuthResult.success()
    synchronizer = NativeSessionSynchronizer(config, env={}, supabase_home=tmp_path)

    result = synchronizer.logout()

    assert result.code is AuthFailureCode.SYNC_PENDING


@pytest.mark.parametrize(
    "code",
    [AuthFailureCode.NETWORK_FAILURE, AuthFailureCode.ENVIRONMENT_BLOCKED, AuthFailureCode.CLI_INCOMPATIBLE],
)
def test_logout_returns_pending_after_inconclusive_postverification(tmp_path, code):
    config = Mock()
    config.logout_session.return_value = AuthResult.success()
    failure = AuthResult.failure(code, "safe")
    config.verify_persisted_session.side_effect = [AuthResult.success(), failure]
    synchronizer = NativeSessionSynchronizer(config, env={}, supabase_home=tmp_path)

    result = synchronizer.logout()

    assert result.code is AuthFailureCode.SYNC_PENDING


@pytest.mark.parametrize(
    "code",
    [AuthFailureCode.NETWORK_FAILURE, AuthFailureCode.ENVIRONMENT_BLOCKED, AuthFailureCode.CLI_INCOMPATIBLE],
)
def test_logout_inconclusive_preverification_never_mutates(tmp_path, code):
    config = Mock()
    config.verify_persisted_session.return_value = AuthResult.failure(code, "safe")
    synchronizer = NativeSessionSynchronizer(config, env={}, supabase_home=tmp_path)

    result = synchronizer.logout()

    assert result.code is code
    config.logout_session.assert_not_called()


def test_journal_round_trip_never_stores_tokens(tmp_path):
    path = tmp_path / "session-sync.json"
    journal = SessionSyncJournal(path)
    token = fake_pat("must-not-persist")

    journal.write(
        operation="activate",
        target_account="work",
        previous_account="old",
        phase="native_login",
    )
    state = journal.read()

    assert state is not None
    assert state["target_account"] == "work"
    assert state["previous_account"] == "old"
    assert state["phase"] == "native_login"
    assert token not in path.read_text(encoding="utf-8")
    assert json.loads(path.read_text(encoding="utf-8"))["operation"] == "activate"
    journal.clear()
    assert journal.read() is None


def test_journal_uses_private_permissions_and_atomic_replacement(tmp_path):
    path = tmp_path / "private" / "session-sync.json"
    journal = SessionSyncJournal(path)

    journal.write("activate", "work", None, "native_login")
    journal.write("activate", "work", "old", "verified")

    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert list(path.parent.glob(".session-sync.json.*")) == []


def test_journal_write_fsyncs_file_and_containing_directory(tmp_path, monkeypatch):
    path = tmp_path / "private" / "session-sync.json"
    calls = []
    original_fsync = os.fsync

    def record_fsync(descriptor):
        calls.append(os.fstat(descriptor).st_mode)
        return original_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", record_fsync)

    SessionSyncJournal(path).write("activate", "work", None, "native_login")

    assert any(stat.S_ISREG(mode) for mode in calls)
    assert any(stat.S_ISDIR(mode) for mode in calls)


def test_journal_clear_fsyncs_containing_directory(tmp_path, monkeypatch):
    path = tmp_path / "private" / "session-sync.json"
    journal = SessionSyncJournal(path)
    journal.write("activate", "work", None, "verified")
    calls = []
    original_fsync = os.fsync

    def record_fsync(descriptor):
        calls.append(os.fstat(descriptor).st_mode)
        return original_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", record_fsync)
    journal.clear()

    assert any(stat.S_ISDIR(mode) for mode in calls)


def test_journal_clear_reports_directory_fsync_failure_after_unlink(tmp_path, monkeypatch):
    path = tmp_path / "private" / "session-sync.json"
    journal = SessionSyncJournal(path)
    journal.write("activate", "work", None, "verified")
    original_fsync = os.fsync

    def fail_directory_fsync(descriptor):
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError("private")
        return original_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", fail_directory_fsync)
    with pytest.raises(OSError):
        journal.clear()

    assert not path.exists()


@pytest.mark.parametrize("unsafe_kind", ["symlink", "directory", "permissive"])
def test_journal_read_rejects_unsafe_file_metadata(tmp_path, unsafe_kind):
    path = tmp_path / "session-sync.json"
    payload = json.dumps(
        {
            "operation": "activate",
            "target_account": "work",
            "previous_account": None,
            "phase": "native_login",
        }
    )
    if unsafe_kind == "symlink":
        target = tmp_path / "target"
        target.write_text(payload, encoding="utf-8")
        path.symlink_to(target)
    elif unsafe_kind == "directory":
        path.mkdir()
    else:
        path.write_text(payload, encoding="utf-8")
        path.chmod(0o644)

    with pytest.raises(ValueError):
        SessionSyncJournal(path).read()


def test_journal_read_rejects_wrong_owner(tmp_path, monkeypatch):
    path = tmp_path / "session-sync.json"
    journal = SessionSyncJournal(path)
    journal.write("activate", "work", None, "native_login")
    original_fstat = os.fstat

    def wrong_owner(descriptor):
        value = original_fstat(descriptor)
        values = list(value)
        values[4] = os.getuid() + 1
        return os.stat_result(values)

    monkeypatch.setattr(os, "fstat", wrong_owner)

    with pytest.raises(ValueError):
        journal.read()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"operation": "invalid", "target_account": "work", "previous_account": None, "phase": "native_login"},
        {"operation": "activate", "target_account": "../work", "previous_account": None, "phase": "native_login"},
        {"operation": "activate", "target_account": "work", "previous_account": "bad name", "phase": "native_login"},
        {"operation": "activate", "target_account": "work", "previous_account": None, "phase": "unknown"},
    ],
)
def test_journal_rejects_invalid_names_operations_and_phases(tmp_path, kwargs):
    journal = SessionSyncJournal(tmp_path / "session-sync.json")

    with pytest.raises(ValueError):
        journal.write(**kwargs)

    assert journal.read() is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"operation": "activate", "target_account": None, "previous_account": None, "phase": "native_login"},
        {"operation": "logout", "target_account": "work", "previous_account": None, "phase": "intent"},
        {"operation": "logout", "target_account": None, "previous_account": "old", "phase": "native_login"},
    ],
)
def test_journal_validates_operation_phase_combinations(tmp_path, kwargs):
    with pytest.raises(ValueError):
        SessionSyncJournal(tmp_path / "journal").write(**kwargs)


def test_journal_rejects_token_fields_without_exposing_file_contents(tmp_path):
    path = tmp_path / "session-sync.json"
    path.write_text(
        json.dumps({"operation": "activate", "target_account": "work", "phase": "native_login", "token": fake_pat("journal")}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        SessionSyncJournal(path).read()
