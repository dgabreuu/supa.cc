import json
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
    config.verify_persisted_session.return_value = AuthResult.failure(
        AuthFailureCode.TOKEN_MISSING,
        "Token de acesso não foi fornecido à Supabase CLI.",
    )
    synchronizer = NativeSessionSynchronizer(
        config=config,
        env={},
        supabase_home=tmp_path / "supabase",
        journal=SessionSyncJournal(tmp_path / "session-sync.json"),
    )

    result = synchronizer.logout()

    assert result.ok is True
    config.logout_session.assert_called_once_with()
    config.verify_persisted_session.assert_called_once_with()


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


def test_journal_rejects_token_fields_without_exposing_file_contents(tmp_path):
    path = tmp_path / "session-sync.json"
    path.write_text(
        json.dumps({"operation": "activate", "target_account": "work", "phase": "native_login", "token": fake_pat("journal")}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        SessionSyncJournal(path).read()
