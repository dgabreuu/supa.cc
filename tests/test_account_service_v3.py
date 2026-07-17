import hashlib
import json
from unittest.mock import ANY, Mock, call

import pytest

from helpers import FakeCredentialStore, fake_pat
from supa_cc.accounts.service import AccountService
from supa_cc.accounts.state import AccountState, StateRepository, StateTransition
from supa_cc.auth import AuthFailureCode, AuthResult
from supa_cc.models import Account
from supa_cc.session import MutationState


def _service(tmp_path, *, state=None, credentials=None, cli=None, session=None):
    repository = StateRepository(tmp_path / "state.json")
    repository.save(state or AccountState())
    return AccountService(
        state_repository=repository,
        credential_store=credentials or FakeCredentialStore(),
        cli=cli or Mock(),
        native_session=session or Mock(),
    )


def _successful_session():
    session = Mock()

    def activate(_account, phase_callback=None):
        if phase_callback is not None:
            for phase in ("logged_out", "logged_in", "verified"):
                phase_callback(phase)
        return AuthResult.success("activated")

    session.activate.side_effect = activate
    session.logout.return_value = AuthResult.success("logged out")
    return session


def test_add_validates_before_storing_token_or_alias(tmp_path):
    credentials = FakeCredentialStore()
    cli = Mock()
    cli.validate_access_token.return_value = AuthResult.success("valid")
    service = _service(tmp_path, credentials=credentials, cli=cli)
    token = fake_pat("add-v3")

    result = service.add("work", token)

    assert result.ok
    cli.validate_access_token.assert_called_once_with(Account("work", token))
    assert credentials.operations == ["set:work"]
    assert service.list()[0].name == "work"


def test_add_rejected_token_does_not_store_anything(tmp_path):
    credentials = FakeCredentialStore()
    cli = Mock()
    rejected = AuthResult.failure(AuthFailureCode.TOKEN_REJECTED, "safe")
    cli.validate_access_token.return_value = rejected
    service = _service(tmp_path, credentials=credentials, cli=cli)

    result = service.add("work", fake_pat("rejected-v3"))

    assert result.code is rejected.code
    assert result.operation == "add"
    assert result.phase == "validate_pat"
    assert credentials.operations == []
    assert service.list() == []


def test_replacing_active_pat_resynchronizes_native_session(tmp_path):
    credentials = FakeCredentialStore()
    old_token = fake_pat("replace-active-old")
    new_token = fake_pat("replace-active-new")
    credentials.tokens["work"] = old_token
    cli = Mock()
    cli.validate_access_token.return_value = AuthResult.success("valid")
    session = _successful_session()
    service = _service(
        tmp_path,
        state=AccountState(aliases=("work",), confirmed_active="work"),
        credentials=credentials,
        cli=cli,
        session=session,
    )

    result = service.add("work", new_token)

    assert result.ok
    session.activate.assert_called_once()
    assert session.activate.call_args.args == (Account("work", new_token),)
    assert credentials.tokens["work"] == new_token
    assert service.get_active_name() == "work"


def test_active_replacement_keeps_old_credential_until_session_is_verified(tmp_path):
    credentials = FakeCredentialStore()
    old_token = fake_pat("replace-order-old")
    new_token = fake_pat("replace-order-new")
    credentials.tokens["work"] = old_token
    cli = Mock()
    cli.validate_access_token.return_value = AuthResult.success("valid")
    session = Mock()

    def activate(account, phase_callback=None):
        assert account.token == new_token
        assert credentials.tokens["work"] == old_token
        return AuthResult.success("activated")

    session.activate.side_effect = activate
    service = _service(
        tmp_path,
        state=AccountState(aliases=("work",), confirmed_active="work"),
        credentials=credentials,
        cli=cli,
        session=session,
    )

    assert service.add("work", new_token).ok
    assert credentials.tokens["work"] == new_token


def test_recovery_commits_inactive_add_written_before_metadata(tmp_path):
    credentials = FakeCredentialStore()
    credentials.tokens["work"] = fake_pat("add-recovery")
    service = _service(
        tmp_path,
        state=AccountState(
            pending_transition=StateTransition(
                "add", "work", None, "credential_written"
            )
        ),
        credentials=credentials,
    )

    result = service.recover_pending_sync()

    assert result.ok
    assert [account.name for account in service.list()] == ["work"]
    assert service.state_repository.load().pending_transition is None


def test_failed_active_pat_replacement_restores_old_pat_and_session(tmp_path):
    credentials = FakeCredentialStore()
    old = Account("work", fake_pat("replace-fail-old"))
    replacement = Account("work", fake_pat("replace-fail-new"))
    credentials.tokens["work"] = old.token
    cli = Mock()
    cli.validate_access_token.return_value = AuthResult.success("valid")
    session = Mock()
    failed = AuthResult.failure(AuthFailureCode.NATIVE_LOGIN_FAILED, "safe")
    session.activate.side_effect = [failed, AuthResult.success("restored")]
    service = _service(
        tmp_path,
        state=AccountState(aliases=("work",), confirmed_active="work"),
        credentials=credentials,
        cli=cli,
        session=session,
    )

    result = service.add("work", replacement.token)

    assert result.code is failed.code
    assert credentials.tokens["work"] == old.token
    assert session.activate.call_args_list[1] == call(old)
    assert service.get_active_name() == "work"


def test_list_never_reads_credentials(tmp_path):
    credentials = FakeCredentialStore()
    service = _service(
        tmp_path,
        state=AccountState(aliases=("personal", "work")),
        credentials=credentials,
    )

    assert [account.name for account in service.list()] == ["personal", "work"]
    assert credentials.operations == []


def test_switch_missing_credential_prompts_reauth_and_continues(tmp_path):
    credentials = FakeCredentialStore()
    cli = Mock()
    cli.validate_access_token.return_value = AuthResult.success("valid")
    session = _successful_session()
    service = _service(
        tmp_path,
        state=AccountState(aliases=("work",)),
        credentials=credentials,
        cli=cli,
        session=session,
    )
    token = fake_pat("orphan-recovery")
    provider = Mock(return_value=token)

    result = service.set_active("work", token_provider=provider)

    assert result.ok
    provider.assert_called_once_with("work")
    assert credentials.tokens["work"] == token
    assert service.get_active_name() == "work"
    cli.validate_access_token.assert_called_once_with(Account("work", token))
    session.activate.assert_called_once()


def test_switch_without_reauth_provider_returns_credential_missing(tmp_path):
    service = _service(
        tmp_path,
        state=AccountState(aliases=("work",)),
        credentials=FakeCredentialStore(),
    )

    result = service.set_active("work")

    assert result.code is AuthFailureCode.CREDENTIAL_MISSING
    assert "credential" in result.message.lower()


def test_switching_to_active_account_revalidates_and_resynchronizes(tmp_path):
    token = fake_pat("already-active")
    credentials = FakeCredentialStore()
    credentials.tokens["work"] = token
    cli = Mock()
    cli.validate_access_token.return_value = AuthResult.success("valid")
    session = _successful_session()
    service = _service(
        tmp_path,
        state=AccountState(aliases=("work",), confirmed_active="work"),
        credentials=credentials,
        cli=cli,
        session=session,
    )

    result = service.set_active("work")

    assert result.ok
    cli.validate_access_token.assert_called_once_with(Account("work", token))
    session.activate.assert_called_once()
    assert session.activate.call_args.args == (Account("work", token),)
    state = service.state_repository.load()
    assert state.confirmed_active == "work"
    assert state.pending_transition is None


def test_failed_switch_restores_previous_confirmed_session(tmp_path):
    credentials = FakeCredentialStore()
    old = Account("old", fake_pat("old-v3"))
    target = Account("target", fake_pat("target-v3"))
    credentials.tokens.update({old.name: old.token, target.name: target.token})
    cli = Mock()
    cli.validate_access_token.return_value = AuthResult.success("valid")
    session = Mock()
    failed = AuthResult.failure(AuthFailureCode.NATIVE_LOGIN_FAILED, "safe")
    session.activate.side_effect = [failed, AuthResult.success("restored")]
    service = _service(
        tmp_path,
        state=AccountState(
            aliases=("old", "target"), confirmed_active="old"
        ),
        credentials=credentials,
        cli=cli,
        session=session,
    )

    result = service.set_active("target")

    assert result.code is failed.code
    assert result.operation == "switch"
    assert result.phase == "native_session"
    assert service.get_active_name() == "old"
    assert session.activate.call_args_list == [call(target, phase_callback=ANY), call(old)]
    assert service.state_repository.load().pending_transition is None


def test_failed_switch_and_restore_leave_no_false_active_account(tmp_path):
    credentials = FakeCredentialStore()
    credentials.tokens.update(
        {"old": fake_pat("old-fail"), "target": fake_pat("target-fail")}
    )
    cli = Mock()
    cli.validate_access_token.return_value = AuthResult.success("valid")
    session = Mock()
    session.activate.side_effect = [
        AuthResult.failure(AuthFailureCode.NATIVE_LOGIN_FAILED, "target failed"),
        AuthResult.failure(AuthFailureCode.NATIVE_LOGIN_FAILED, "restore failed"),
    ]
    service = _service(
        tmp_path,
        state=AccountState(
            aliases=("old", "target"), confirmed_active="old"
        ),
        credentials=credentials,
        cli=cli,
        session=session,
    )

    result = service.set_active("target")

    state = service.state_repository.load()
    assert result.code is AuthFailureCode.SYNC_ROLLBACK_FAILED
    assert state.confirmed_active is None
    assert state.pending_transition == StateTransition(
        "switch", "target", "old", "recovery_failed"
    )


def test_failed_switch_before_native_mutation_preserves_previous_without_restore(
    tmp_path,
):
    credentials = FakeCredentialStore()
    credentials.tokens.update(
        {"old": fake_pat("old-preflight"), "target": fake_pat("target-preflight")}
    )
    cli = Mock()
    cli.validate_access_token.return_value = AuthResult.success("valid")
    session = Mock()
    session.mutation_state = MutationState.NONE
    failure = AuthResult.failure(AuthFailureCode.ENVIRONMENT_BLOCKED, "safe")
    session.activate.return_value = failure
    service = _service(
        tmp_path,
        state=AccountState(aliases=("old", "target"), confirmed_active="old"),
        credentials=credentials,
        cli=cli,
        session=session,
    )

    result = service.set_active("target")

    assert result.code is failure.code
    assert service.get_active_name() == "old"
    assert service.state_repository.load().pending_transition is None
    session.activate.assert_called_once()


@pytest.mark.parametrize("phase", ["prepared", "logged_out", "logged_in", "verified"])
def test_recovery_rolls_forward_pending_switch_idempotently(tmp_path, phase):
    credentials = FakeCredentialStore()
    credentials.tokens["work"] = fake_pat("recover-v3")
    session = _successful_session()
    service = _service(
        tmp_path,
        state=AccountState(
            aliases=("work",),
            pending_transition=StateTransition(
                "switch", "work", None, phase
            ),
        ),
        credentials=credentials,
        session=session,
    )

    result = service.recover_pending_sync()

    assert result.ok
    assert service.get_active_name() == "work"
    assert service.state_repository.load().pending_transition is None


def test_remove_is_idempotent_when_credential_was_already_deleted(tmp_path):
    credentials = FakeCredentialStore()
    service = _service(
        tmp_path,
        state=AccountState(aliases=("work",)),
        credentials=credentials,
    )

    result = service.remove("work")

    assert result.ok
    assert service.list() == []
    assert credentials.operations == ["delete:work"]


def test_remove_active_account_logs_out_before_deleting_metadata(tmp_path):
    credentials = FakeCredentialStore()
    credentials.tokens["work"] = fake_pat("remove-active")
    session = Mock()
    session.logout.return_value = AuthResult.success("logged out")
    service = _service(
        tmp_path,
        state=AccountState(aliases=("work",), confirmed_active="work"),
        credentials=credentials,
        session=session,
    )

    result = service.remove("work")

    assert result.ok
    session.logout.assert_called_once_with()
    assert service.get_active_name() is None
    assert service.list() == []


def test_uncertain_logout_does_not_advertise_false_active_session(tmp_path):
    credentials = FakeCredentialStore()
    credentials.tokens["work"] = fake_pat("remove-uncertain")
    session = Mock()
    session.mutation_state = MutationState.UNCERTAIN
    session.logout.return_value = AuthResult.failure(
        AuthFailureCode.NATIVE_LOGOUT_FAILED, "safe"
    )
    service = _service(
        tmp_path,
        state=AccountState(aliases=("work",), confirmed_active="work"),
        credentials=credentials,
        session=session,
    )

    result = service.remove("work")

    state = service.state_repository.load()
    assert result.code is AuthFailureCode.NATIVE_LOGOUT_FAILED
    assert state.confirmed_active is None
    assert state.pending_transition == StateTransition(
        "remove", "work", "work", "prepared"
    )


def test_reset_includes_pending_add_target_in_credential_cleanup(tmp_path):
    credentials = FakeCredentialStore()
    credentials.tokens["orphan"] = fake_pat("pending-add-reset")
    session = Mock()
    session.logout.return_value = AuthResult.success("logged out")
    service = _service(
        tmp_path,
        state=AccountState(
            pending_transition=StateTransition(
                "add", "orphan", None, "credential_written"
            )
        ),
        credentials=credentials,
        session=session,
    )

    assert service.reset_all().ok
    assert credentials.tokens == {}


@pytest.mark.parametrize("phase", ["prepared", "logged_out", "credential_deleted"])
def test_recovery_completes_interrupted_remove_idempotently(tmp_path, phase):
    credentials = FakeCredentialStore()
    credentials.tokens["work"] = fake_pat("remove-recovery")
    session = Mock()
    session.logout.return_value = AuthResult.success("logged out")
    confirmed = None if phase != "prepared" else "work"
    service = _service(
        tmp_path,
        state=AccountState(
            aliases=("work",),
            confirmed_active=confirmed,
            pending_transition=StateTransition(
                "remove", "work", "work", phase
            ),
        ),
        credentials=credentials,
        session=session,
    )

    result = service.recover_pending_sync()

    assert result.ok
    assert service.list() == []
    assert service.get_active_name() is None
    assert credentials.tokens == {}


def test_reset_clears_known_credentials_and_state_even_if_logout_fails(tmp_path):
    credentials = FakeCredentialStore()
    credentials.tokens.update(
        {"one": fake_pat("reset-one"), "two": fake_pat("reset-two")}
    )
    session = Mock()
    session.logout.return_value = AuthResult.failure(
        AuthFailureCode.NATIVE_LOGOUT_FAILED, "safe"
    )
    service = _service(
        tmp_path,
        state=AccountState(aliases=("one", "two"), confirmed_active="one"),
        credentials=credentials,
        session=session,
    )

    result = service.reset_all()

    assert result.code is AuthFailureCode.RESET_PARTIAL
    assert credentials.tokens == {}
    assert not service.state_repository.path.exists()


def test_reset_preserves_failed_credential_alias_for_safe_retry(tmp_path):
    credentials = FakeCredentialStore()
    credentials.tokens["work"] = fake_pat("reset-retry")
    credentials.delete_error = OSError("private")
    session = Mock()
    session.logout.return_value = AuthResult.success("logged out")
    service = _service(
        tmp_path,
        state=AccountState(aliases=("work",), confirmed_active="work"),
        credentials=credentials,
        session=session,
    )

    result = service.reset_all()

    state = service.state_repository.load()
    assert result.code is AuthFailureCode.RESET_PARTIAL
    assert state.aliases == ("work",)
    assert state.confirmed_active is None
    assert state.pending_transition is not None
    assert state.pending_transition.operation == "reset"


def test_run_active_returns_credential_missing_without_executing_cli(tmp_path):
    cli = Mock()
    service = _service(
        tmp_path,
        state=AccountState(aliases=("work",), confirmed_active="work"),
        credentials=FakeCredentialStore(),
        cli=cli,
    )

    result = service.run_active(["projects", "list"])

    assert result.code is AuthFailureCode.CREDENTIAL_MISSING
    cli.execute_authenticated_streaming.assert_not_called()


def test_legacy_active_alias_with_deleted_pat_can_be_reauthorized(tmp_path):
    (tmp_path / "accounts.json").write_text(
        '{"accounts":["work"]}\n', encoding="utf-8"
    )
    (tmp_path / "accounts.json").chmod(0o600)
    (tmp_path / "active-account").write_text("work\n", encoding="utf-8")
    (tmp_path / "active-account").chmod(0o600)
    repository = StateRepository(tmp_path / "state.json")
    credentials = FakeCredentialStore()
    cli = Mock()
    cli.validate_access_token.return_value = AuthResult.success("valid")
    service = AccountService(
        state_repository=repository,
        credential_store=credentials,
        cli=cli,
        native_session=_successful_session(),
    )
    token = fake_pat("legacy-orphan")

    result = service.set_active("work", token_provider=lambda _name: token)

    assert result.ok
    assert service.get_active_name() == "work"
    assert credentials.tokens["work"] == token


def test_migrated_legacy_replacement_restores_backup_and_removes_it(tmp_path):
    (tmp_path / "accounts.json").write_text(
        '{"accounts":["work"]}\n', encoding="utf-8"
    )
    (tmp_path / "accounts.json").chmod(0o600)
    (tmp_path / "session-sync.json").write_text(
        json.dumps(
            {
                "operation": "account_replace",
                "target_account": "work",
                "previous_account": None,
                "phase": "credential_written",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "session-sync.json").chmod(0o600)
    backup_name = "!supa.cc-backup!" + hashlib.sha256(b"work").hexdigest()
    old_token = fake_pat("legacy-replace-old")
    credentials = FakeCredentialStore()
    credentials.tokens.update(
        {"work": fake_pat("legacy-replace-new"), backup_name: old_token}
    )
    service = AccountService(
        state_repository=StateRepository(tmp_path / "state.json"),
        credential_store=credentials,
        cli=Mock(),
        native_session=Mock(),
    )

    result = service.recover_pending_sync()

    assert result.ok
    assert credentials.tokens == {"work": old_token}
    assert [account.name for account in service.list()] == ["work"]
    assert service.state_repository.load().pending_transition is None


def test_migrated_legacy_remove_deletes_credential_and_secure_backup(tmp_path):
    (tmp_path / "session-sync.json").write_text(
        json.dumps(
            {
                "operation": "account_remove",
                "target_account": "work",
                "previous_account": None,
                "phase": "index_committed",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "session-sync.json").chmod(0o600)
    backup_name = "!supa.cc-backup!" + hashlib.sha256(b"work").hexdigest()
    credentials = FakeCredentialStore()
    credentials.tokens.update(
        {"work": fake_pat("legacy-remove"), backup_name: fake_pat("legacy-backup")}
    )
    service = AccountService(
        state_repository=StateRepository(tmp_path / "state.json"),
        credential_store=credentials,
        cli=Mock(),
        native_session=Mock(),
    )

    result = service.recover_pending_sync()

    assert result.ok
    assert credentials.tokens == {}
    assert service.list() == []


def test_migrated_legacy_remove_intent_without_backup_is_cancelled(tmp_path):
    (tmp_path / "accounts.json").write_text(
        '{"accounts":["work"]}\n', encoding="utf-8"
    )
    (tmp_path / "accounts.json").chmod(0o600)
    (tmp_path / "session-sync.json").write_text(
        json.dumps(
            {
                "operation": "account_remove",
                "target_account": "work",
                "previous_account": None,
                "phase": "intent",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "session-sync.json").chmod(0o600)
    token = fake_pat("legacy-remove-intent")
    credentials = FakeCredentialStore()
    credentials.tokens["work"] = token
    service = AccountService(
        state_repository=StateRepository(tmp_path / "state.json"),
        credential_store=credentials,
        cli=Mock(),
        native_session=Mock(),
    )

    result = service.recover_pending_sync()

    assert result.ok
    assert credentials.tokens == {"work": token}
    assert [account.name for account in service.list()] == ["work"]


def test_reset_removes_pending_migrated_secure_backup(tmp_path):
    backup_name = "!supa.cc-backup!" + hashlib.sha256(b"work").hexdigest()
    credentials = FakeCredentialStore()
    credentials.tokens.update(
        {"work": fake_pat("reset-primary"), backup_name: fake_pat("reset-backup")}
    )
    session = Mock()
    session.logout.return_value = AuthResult.success("logged out")
    service = _service(
        tmp_path,
        state=AccountState(
            aliases=("work",),
            pending_transition=StateTransition(
                "legacy_replace", "work", None, "credential_backup"
            ),
        ),
        credentials=credentials,
        session=session,
    )

    assert service.reset_all().ok
    assert credentials.tokens == {}
