import threading
import stat
import traceback

import pytest
from unittest.mock import Mock, call, patch

from supa_cc.accounts import AccountManager
from supa_cc.auth import (
    AuthFailureCode,
    AuthResult,
    CommandResult,
    CredentialPermissionDeniedError,
    CredentialReadError,
    KeychainPermissionDeniedError,
    KeychainReadError,
    ActiveAccountInvalidError,
    ActiveAccountPermissionDeniedError,
    ActiveAccountReadError,
)
from supa_cc.keychain import KeychainManager
from supa_cc.models import Account
from supa_cc.environment import detect_environment

from helpers import FakeCredentialStore, fake_pat


def test_default_stores_use_one_detected_environment(monkeypatch):
    environment = detect_environment(system_name="Linux", os_release="ID=ubuntu\n")
    created_keychain = Mock()
    created_active_store = Mock()
    keychain_arguments = []
    active_store_arguments = []
    monkeypatch.setattr(
        "supa_cc.accounts.detect_environment",
        lambda: environment,
        raising=False,
    )
    monkeypatch.setattr(
        "supa_cc.accounts.KeychainManager",
        lambda **kwargs: keychain_arguments.append(kwargs) or created_keychain,
    )
    monkeypatch.setattr(
        "supa_cc.accounts.ActiveAccountStore",
        lambda **kwargs: active_store_arguments.append(kwargs) or created_active_store,
    )

    manager = AccountManager()

    assert manager.keychain is created_keychain
    assert manager.active_store is created_active_store
    assert keychain_arguments == [{"environment": environment}]
    assert active_store_arguments == [
        {"path": environment.config_directory() / "active-account"}
    ]


class TestAccountManager:
    def test_add_valid_account(self, tmp_path):
        manager = AccountManager()
        manager.keychain.index_path = tmp_path / "accounts.json"
        manager.keychain.update_index([])
        with patch.object(manager.keychain, 'add_account') as add_account:
            account = manager.add("test", fake_pat())
            assert account.name == "test"
            assert account.token == fake_pat()
            add_account.assert_called_once_with(account)

    def test_add_invalid_token(self):
        manager = AccountManager()
        with pytest.raises(ValueError, match="Token inválido"):
            manager.add("test", "invalid_token")

    def test_list_accounts(self):
        manager = AccountManager()
        mock_accounts = [Account(name="test1", token=fake_pat("one")), Account(name="test2", token=fake_pat("two"))]
        with patch.object(manager.keychain, 'list_accounts', return_value=mock_accounts):
            accounts = manager.list()
            assert len(accounts) == 2

    def test_get_account_found(self):
        manager = AccountManager()
        mock_account = Account(name="test", token=fake_pat("test"))
        with patch.object(manager.keychain, 'get_account', return_value=mock_account):
            account = manager.get("test")
            assert account is not None
            assert account.name == "test"

    def test_get_account_not_found(self):
        manager = AccountManager()
        with patch.object(manager.keychain, 'get_account', return_value=None):
            account = manager.get("nonexistent")
            assert account is None

    def test_remove_account(self, tmp_path):
        manager = AccountManager()
        manager.keychain.index_path = tmp_path / "accounts.json"
        manager.keychain.update_index([])
        with patch.object(manager.keychain, 'remove_account') as remove_account:
            manager.remove("test")
            remove_account.assert_called_once_with("test")

    @pytest.mark.parametrize(
        "name",
        [
            fake_pat("remove_namespace"),
            "acct_" + fake_pat("embedded_remove"),
        ],
    )
    def test_remove_rejects_pat_like_name_before_keychain(self, name):
        keychain = Mock()
        manager = AccountManager(keychain=keychain)

        with pytest.raises(ValueError):
            manager.remove(name)

        keychain.remove_account.assert_not_called()

    def test_add_rejects_embedded_pat_name_before_keychain(self):
        keychain = Mock()
        manager = AccountManager(keychain=keychain)

        with pytest.raises(ValueError):
            manager.add(
                "acct_" + fake_pat("embedded_add"),
                fake_pat("credential"),
            )

        keychain.add_account.assert_not_called()

    def test_remove_account_updates_index_when_keychain_item_is_missing(self, tmp_path):
        manager = AccountManager()
        manager.keychain.index_path = tmp_path / "accounts.json"
        manager.keychain.update_index(["pilon", "work"])

        manager.remove("pilon")

        assert [account.name for account in manager.list()] == ["work"]

    def test_set_active_validates_before_persisting_name(self):
        keychain = Mock()
        config = Mock()
        active_store = Mock()
        account = Account(name="work", token=fake_pat("valid_token"))
        keychain.get_account.return_value = account
        config.validate_access_token.return_value = AuthResult.success()
        manager = AccountManager(
            keychain=keychain,
            config=config,
            active_store=active_store,
        )
        events = Mock()
        events.attach_mock(keychain, "keychain")
        events.attach_mock(config, "config")
        events.attach_mock(active_store, "store")

        result = manager.set_active("work")

        assert result.ok is True
        assert result.code is AuthFailureCode.NONE
        assert events.mock_calls == [
            call.keychain.get_account("work"),
            call.config.validate_access_token(account),
            call.store.write("work"),
        ]

    def test_set_active_returns_token_missing_without_validation_or_write(self):
        keychain = Mock()
        config = Mock()
        active_store = Mock()
        keychain.get_account.return_value = None
        manager = AccountManager(
            keychain=keychain,
            config=config,
            active_store=active_store,
        )

        result = manager.set_active("missing")

        assert result.ok is False
        assert result.code is AuthFailureCode.TOKEN_MISSING
        config.validate_access_token.assert_not_called()
        active_store.write.assert_not_called()

    def test_set_active_rejects_invalid_token_before_validation(self):
        keychain = Mock()
        config = Mock()
        active_store = Mock()
        keychain.get_account.return_value = Account(name="work", token="invalid")
        manager = AccountManager(
            keychain=keychain,
            config=config,
            active_store=active_store,
        )

        result = manager.set_active("work")

        assert result.ok is False
        assert result.code is AuthFailureCode.TOKEN_FORMAT_INVALID
        config.validate_access_token.assert_not_called()
        active_store.write.assert_not_called()

    @pytest.mark.parametrize(
        "failure,expected",
        [
            (
                KeychainPermissionDeniedError("safe"),
                AuthFailureCode.KEYCHAIN_PERMISSION_DENIED,
            ),
            (KeychainReadError("safe"), AuthFailureCode.KEYCHAIN_READ_FAILED),
            (
                CredentialPermissionDeniedError("safe"),
                AuthFailureCode.KEYCHAIN_PERMISSION_DENIED,
            ),
            (CredentialReadError("safe"), AuthFailureCode.KEYCHAIN_READ_FAILED),
        ],
        ids=["keychain-permission", "keychain-read", "credential-permission", "credential-read"],
    )
    def test_set_active_maps_keychain_domain_failures(self, failure, expected):
        keychain = Mock()
        config = Mock()
        active_store = Mock()
        keychain.get_account.side_effect = failure
        manager = AccountManager(
            keychain=keychain,
            config=config,
            active_store=active_store,
        )

        result = manager.set_active("work")

        assert result.ok is False
        assert result.code is expected
        config.validate_access_token.assert_not_called()
        active_store.write.assert_not_called()

    def test_set_active_preserves_validation_failure_without_writing(self):
        keychain = Mock()
        config = Mock()
        active_store = Mock()
        account = Account(name="work", token=fake_pat("rejected"))
        rejected = AuthResult.failure(
            AuthFailureCode.TOKEN_REJECTED,
            "O token foi rejeitado.",
            exit_code=1,
        )
        keychain.get_account.return_value = account
        config.validate_access_token.return_value = rejected
        manager = AccountManager(
            keychain=keychain,
            config=config,
            active_store=active_store,
        )

        result = manager.set_active("work")

        assert result is rejected
        active_store.write.assert_not_called()

    def test_set_active_maps_active_name_write_failure(self):
        keychain = Mock()
        config = Mock()
        active_store = Mock()
        account = Account(name="work", token=fake_pat("valid_token"))
        keychain.get_account.return_value = account
        config.validate_access_token.return_value = AuthResult.success()
        active_store.write.side_effect = OSError("sensitive path")
        manager = AccountManager(
            keychain=keychain,
            config=config,
            active_store=active_store,
        )

        result = manager.set_active("work")

        assert result.ok is False
        assert result.code is AuthFailureCode.ACTIVE_ACCOUNT_WRITE_FAILED
        assert "sensitive" not in result.message

    def test_run_active_loads_selected_account_once_and_executes_without_prevalidation(self):
        keychain = Mock()
        config = Mock()
        active_store = Mock()
        account = Account(name="work", token=fake_pat("run_active"))
        active_store.read.return_value = "work"
        keychain.get_account.return_value = account
        command_result = CommandResult.success("executed")
        config.execute_authenticated_streaming.return_value = command_result
        manager = AccountManager(
            keychain=keychain,
            config=config,
            active_store=active_store,
        )

        stdout_sink = Mock()
        stderr_sink = Mock()
        result = manager.run_active(
            ["projects", "list", "--profile", "work"],
            stdout_sink=stdout_sink,
            stderr_sink=stderr_sink,
        )

        assert result is command_result
        active_store.read.assert_called_once_with()
        keychain.get_account.assert_called_once_with("work")
        config.execute_authenticated_streaming.assert_called_once_with(
            account,
            ["projects", "list", "--profile", "work"],
            stdout_sink=stdout_sink,
            stderr_sink=stderr_sink,
        )
        config.validate_access_token.assert_not_called()

    def test_run_active_requires_selected_account(self):
        keychain = Mock()
        config = Mock()
        active_store = Mock()
        active_store.read.return_value = None
        manager = AccountManager(
            keychain=keychain,
            config=config,
            active_store=active_store,
        )

        result = manager.run_active(["projects", "list"])

        assert result.ok is False
        assert result.code is AuthFailureCode.ACTIVE_ACCOUNT_MISSING
        keychain.get_account.assert_not_called()
        config.execute_authenticated.assert_not_called()
        config.execute_authenticated_streaming.assert_not_called()

    @pytest.mark.parametrize(
        "failure,expected",
        [
            (
                ActiveAccountPermissionDeniedError("private"),
                AuthFailureCode.ACTIVE_ACCOUNT_PERMISSION_DENIED,
            ),
            (
                ActiveAccountReadError("private"),
                AuthFailureCode.ACTIVE_ACCOUNT_READ_FAILED,
            ),
            (
                ActiveAccountInvalidError("private"),
                AuthFailureCode.ACTIVE_ACCOUNT_INVALID,
            ),
        ],
    )
    def test_run_active_maps_active_store_failures(self, failure, expected):
        keychain = Mock()
        config = Mock()
        active_store = Mock()
        active_store.read.side_effect = failure
        manager = AccountManager(
            keychain=keychain,
            config=config,
            active_store=active_store,
        )

        result = manager.run_active(["projects", "list"])

        assert result.ok is False
        assert result.code is expected
        assert "private" not in result.message
        keychain.get_account.assert_not_called()
        config.execute_authenticated_streaming.assert_not_called()

    @pytest.mark.parametrize(
        "failure,expected",
        [
            (
                KeychainPermissionDeniedError("private"),
                AuthFailureCode.KEYCHAIN_PERMISSION_DENIED,
            ),
            (KeychainReadError("private"), AuthFailureCode.KEYCHAIN_READ_FAILED),
        ],
    )
    def test_run_active_maps_keychain_failures(self, failure, expected):
        keychain = Mock()
        config = Mock()
        active_store = Mock()
        active_store.read.return_value = "work"
        keychain.get_account.side_effect = failure
        manager = AccountManager(
            keychain=keychain,
            config=config,
            active_store=active_store,
        )

        result = manager.run_active(["projects", "list"])

        assert result.ok is False
        assert result.code is expected
        assert "private" not in result.message
        config.execute_authenticated.assert_not_called()
        config.execute_authenticated_streaming.assert_not_called()

    @pytest.mark.parametrize(
        "account,expected",
        [
            (None, AuthFailureCode.TOKEN_MISSING),
            (Account(name="work", token="bad"), AuthFailureCode.TOKEN_FORMAT_INVALID),
        ],
    )
    def test_run_active_rejects_missing_or_invalid_stored_token(
        self, account, expected
    ):
        keychain = Mock()
        config = Mock()
        active_store = Mock()
        active_store.read.return_value = "work"
        keychain.get_account.return_value = account
        manager = AccountManager(
            keychain=keychain,
            config=config,
            active_store=active_store,
        )

        result = manager.run_active(["projects", "list"])

        assert result.ok is False
        assert result.code is expected
        config.execute_authenticated.assert_not_called()
        config.execute_authenticated_streaming.assert_not_called()

    def test_validate_named_account_reads_keychain_once(self):
        keychain = Mock()
        config = Mock()
        account = Account(name="work", token=fake_pat("doctor_live"))
        expected = AuthResult.success("valid")
        keychain.get_account.return_value = account
        config.validate_access_token.return_value = expected
        manager = AccountManager(keychain=keychain, config=config)

        result = manager.validate_named_account("work")

        assert result is expected
        keychain.get_account.assert_called_once_with("work")
        config.validate_access_token.assert_called_once_with(account)

    @pytest.mark.parametrize("name,expected_error", [
        ("", "Nome da conta deve ter entre 1 e 50 caracteres"),
        ("a" * 51, "Nome da conta deve ter entre 1 e 50 caracteres"),
        ("name with space", "Nome da conta contém caracteres inválidos"),
        ("work\n", "Nome da conta contém caracteres inválidos"),
        ("café", "Nome da conta contém caracteres inválidos"),
        ("emoji\ud83d\ude00", "Nome da conta contém caracteres inválidos"),
    ])
    def test_add_invalid_name(self, name, expected_error):
        manager = AccountManager()
        with pytest.raises(ValueError, match=expected_error):
            manager.add(name, fake_pat())

    def test_add_duplicate_name_overwrites(self, tmp_path):
        manager = AccountManager()
        manager.keychain.index_path = tmp_path / "accounts.json"
        manager.keychain.update_index([])
        with patch.object(manager.keychain, 'add_account') as add_account:
            manager.add("work", fake_pat("token_one"))
            manager.add("work", fake_pat("token_two"))
            assert add_account.call_count == 2

    def test_index_mutators_use_private_lock_file(self, tmp_path):
        manager = AccountManager()
        manager.keychain.index_path = tmp_path / "accounts.json"

        manager.keychain.update_index([])

        lock_path = tmp_path / ".accounts.json.lock"
        assert lock_path.exists()
        assert stat.S_IMODE(lock_path.stat().st_mode) == 0o600

    def test_concurrent_additions_do_not_lose_names(self, tmp_path):
        index_path = tmp_path / "accounts.json"
        store = FakeCredentialStore()
        first = AccountManager(
            keychain=KeychainManager(index_path=index_path, credential_store=store)
        )
        second = AccountManager(
            keychain=KeychainManager(index_path=index_path, credential_store=store)
        )
        first.keychain.update_index([])

        first_has_lock = threading.Event()
        release_first = threading.Event()
        second_started = threading.Event()
        second_entered_read = threading.Event()
        first_read_index = first.keychain._read_index_locked
        second_read_index = second.keychain._read_index_locked

        def paused_first_read():
            names = first_read_index()
            first_has_lock.set()
            release_first.wait(timeout=2)
            return names

        def observed_second_read():
            second_entered_read.set()
            return second_read_index()

        failures = []

        def add(manager, name, token, started=None):
            try:
                if started is not None:
                    started.set()
                manager.add(name, token)
            except Exception as exc:
                failures.append(exc)

        with patch.object(
            first.keychain,
            "_read_index_locked",
            side_effect=paused_first_read,
        ), patch.object(
            second.keychain,
            "_read_index_locked",
            side_effect=observed_second_read,
        ):
            first_thread = threading.Thread(
                target=add,
                args=(first, "alpha", fake_pat("alpha_token")),
            )
            second_thread = threading.Thread(
                target=add,
                args=(
                    second,
                    "beta",
                    fake_pat("beta_token"),
                    second_started,
                ),
            )
            first_thread.start()
            assert first_has_lock.wait(timeout=1)
            second_thread.start()
            assert second_started.wait(timeout=1)
            try:
                assert second_entered_read.wait(timeout=0.1) is False
                assert second_thread.is_alive() is True
            finally:
                release_first.set()
            first_thread.join(timeout=2)
            second_thread.join(timeout=2)

        assert first_thread.is_alive() is False
        assert second_thread.is_alive() is False
        assert second_entered_read.is_set()
        assert failures == []
        assert sorted(account.name for account in first.list()) == ["alpha", "beta"]

    def test_overwrite_restores_previous_token_when_index_commit_fails(self, tmp_path):
        previous = fake_pat("previous_token")
        store = FakeCredentialStore()
        store.tokens["work"] = previous
        manager = AccountManager(
            keychain=KeychainManager(
                index_path=tmp_path / "accounts.json", credential_store=store
            )
        )
        manager.keychain.update_index([])

        with patch(
            "supa_cc.keychain.os.replace", side_effect=OSError("index write failed")
        ):
            with pytest.raises(OSError, match="index write failed"):
                manager.add("work", fake_pat("replacement_token"))

        assert store.tokens == {"work": previous}
        assert manager.list() == []

    def test_remove_restores_token_when_index_commit_fails(self, tmp_path):
        previous = fake_pat("previous_token")
        store = FakeCredentialStore()
        store.tokens["work"] = previous
        manager = AccountManager(
            keychain=KeychainManager(
                index_path=tmp_path / "accounts.json", credential_store=store
            )
        )
        manager.keychain.update_index(["work"])

        with patch(
            "supa_cc.keychain.os.replace", side_effect=OSError("index write failed")
        ):
            with pytest.raises(OSError, match="index write failed"):
                manager.remove("work")

        assert store.tokens == {"work": previous}
        assert [account.name for account in manager.list()] == ["work"]

    def test_keyboard_interrupt_after_index_commit_does_not_rollback_token(
        self, tmp_path
    ):
        token = fake_pat("committed_token")
        store = FakeCredentialStore()
        manager = AccountManager(
            keychain=KeychainManager(
                index_path=tmp_path / "accounts.json", credential_store=store
            )
        )
        manager.keychain.update_index([])

        write_index = manager.keychain._write_index_locked

        def commit_then_interrupt(names):
            write_index(names)
            raise KeyboardInterrupt()

        with patch.object(
            manager.keychain,
            "_write_index_locked",
            side_effect=commit_then_interrupt,
        ):
            with pytest.raises(KeyboardInterrupt):
                manager.add("work", token)

        assert store.tokens == {"work": token}
        assert [account.name for account in manager.list()] == ["work"]

    def test_add_reports_sanitized_transaction_error_when_rollback_fails(
        self, tmp_path
    ):
        previous = fake_pat("previous_secret")
        replacement = fake_pat("replacement_secret")
        store = FakeCredentialStore()
        store.tokens["work"] = previous
        manager = AccountManager(
            keychain=KeychainManager(
                index_path=tmp_path / "accounts.json", credential_store=store
            )
        )
        manager.keychain.update_index([])
        commit_failure = OSError(f"index failure containing {replacement}")

        original_set = store.set

        def set_account(account):
            if account.token == previous and store.tokens.get(account.name) == replacement:
                raise RuntimeError(f"rollback failure containing {previous}")
            original_set(account)

        store.set = set_account
        with patch(
            "supa_cc.keychain.os.replace", side_effect=commit_failure
        ):
            with pytest.raises(Exception) as raised:
                manager.add("work", replacement)

        assert type(raised.value).__name__ == "AccountTransactionError"
        assert raised.value.__cause__ is None
        rendered = "".join(
            traceback.format_exception(
                type(raised.value),
                raised.value,
                raised.value.__traceback__,
            )
        )
        assert previous not in rendered
        assert replacement not in rendered
        assert "index failure" not in rendered
        assert "rollback failure" not in rendered

    def test_remove_reports_sanitized_transaction_error_when_rollback_fails(
        self, tmp_path
    ):
        previous = fake_pat("previous_secret")
        store = FakeCredentialStore()
        store.tokens["work"] = previous
        manager = AccountManager(
            keychain=KeychainManager(
                index_path=tmp_path / "accounts.json", credential_store=store
            )
        )
        manager.keychain.update_index(["work"])
        commit_failure = OSError(f"index failure containing {previous}")

        def set_account(_account):
            raise RuntimeError(f"rollback failure containing {previous}")

        store.set = set_account
        with patch(
            "supa_cc.keychain.os.replace", side_effect=commit_failure
        ):
            with pytest.raises(Exception) as raised:
                manager.remove("work")

        assert type(raised.value).__name__ == "AccountTransactionError"
        assert raised.value.__cause__ is None
        rendered = "".join(
            traceback.format_exception(
                type(raised.value),
                raised.value,
                raised.value.__traceback__,
            )
        )
        assert previous not in rendered
        assert "index failure" not in rendered
        assert "rollback failure" not in rendered
        assert store.tokens == {}
        assert [account.name for account in manager.list()] == ["work"]
