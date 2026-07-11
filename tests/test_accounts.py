import threading
import stat
import traceback
import time

import pytest
from unittest.mock import Mock, call, patch

from supa_cc.accounts import AccountManager
from supa_cc.auth import (
    AccountTransactionError,
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

from helpers import (
    FakeCredentialStore,
    FaultInjectingJournal,
    MemoryActiveAccountStore,
    fake_pat,
)
from supa_cc.native_session import SessionSyncJournal
from supa_cc.native_session import NativeSessionSynchronizer


class InterruptingJournal:
    def __init__(self, journal, write_call):
        self.journal = journal
        self.path = journal.path
        self.write_call = write_call
        self.calls = 0

    def read(self):
        return self.journal.read()

    def write(self, *args):
        self.calls += 1
        if self.calls == self.write_call:
            raise KeyboardInterrupt()
        self.journal.write(*args)

    def clear(self):
        self.journal.clear()


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
    def durable_manager(self, tmp_path, store, active_store, native_session, journal=None):
        keychain = KeychainManager(
            index_path=tmp_path / "accounts.json", credential_store=store
        )
        return AccountManager(
            keychain=keychain,
            config=Mock(),
            active_store=active_store,
            native_session=native_session,
            sync_journal=journal or SessionSyncJournal(tmp_path / "session-sync.json"),
        )

    def transactional_manager(self, tmp_path, previous=None):
        keychain = Mock()
        config = Mock()
        active_store = MemoryActiveAccountStore(previous)
        native_session = Mock()
        native_session.activate.return_value = AuthResult.success()
        native_session.logout.return_value = AuthResult.success()
        journal = SessionSyncJournal(tmp_path / "session-sync.json")
        accounts = {
            "work": Account(name="work", token=fake_pat("work")),
            "old": Account(name="old", token=fake_pat("old")),
        }
        keychain.get_account.side_effect = accounts.get
        keychain.read_account_backup.side_effect = accounts.get
        config.validate_access_token.return_value = AuthResult.success()
        manager = AccountManager(
            keychain=keychain,
            config=config,
            active_store=active_store,
            native_session=native_session,
            sync_journal=journal,
        )
        return manager

    def test_set_active_synchronizes_native_before_local_success(self, tmp_path):
        manager = self.transactional_manager(tmp_path)
        events = Mock()
        events.attach_mock(manager.native_session, "native")
        manager.active_store.write = Mock(wraps=manager.active_store.write)
        events.attach_mock(manager.active_store.write, "local_write")

        result = manager.set_active("work")

        assert result.ok
        assert events.mock_calls == [
            call.native.activate(Account(name="work", token=fake_pat("work"))),
            call.local_write("work"),
        ]
        assert manager.active_store.name == "work"
        assert manager.sync_journal.read() is None

    def test_set_active_first_activation_logs_out_when_native_sync_fails(self, tmp_path):
        manager = self.transactional_manager(tmp_path)
        failure = AuthResult.failure(AuthFailureCode.NATIVE_LOGIN_FAILED, "safe")
        manager.native_session.activate.return_value = failure

        result = manager.set_active("work")

        assert result is failure
        manager.native_session.logout.assert_called_once_with()
        assert manager.active_store.name is None
        assert manager.sync_journal.read() is None

    def test_set_active_restores_previous_account_when_native_sync_fails(self, tmp_path):
        manager = self.transactional_manager(tmp_path, previous="old")
        failure = AuthResult.failure(AuthFailureCode.NATIVE_LOGIN_FAILED, "safe")
        manager.native_session.activate.side_effect = [failure, AuthResult.success()]

        result = manager.set_active("work")

        assert result is failure
        assert [call.args[0].name for call in manager.native_session.activate.call_args_list] == ["work", "old"]
        assert manager.active_store.name == "old"
        assert manager.sync_journal.read() is None

    def test_set_active_retains_journal_when_compensation_fails(self, tmp_path):
        manager = self.transactional_manager(tmp_path, previous="old")
        manager.native_session.activate.side_effect = [
            AuthResult.failure(AuthFailureCode.NATIVE_LOGIN_FAILED, "safe"),
            AuthResult.failure(AuthFailureCode.NATIVE_LOGIN_FAILED, "safe"),
        ]

        result = manager.set_active("work")

        assert not result.ok
        assert result.code is AuthFailureCode.SYNC_ROLLBACK_FAILED
        assert manager.sync_journal.read()["phase"] == "rollback"
        assert manager.active_store.name == "old"

    def test_set_active_does_not_report_success_when_local_write_fails(self, tmp_path):
        manager = self.transactional_manager(tmp_path, previous="old")
        manager.active_store.write = Mock(side_effect=OSError("private"))

        result = manager.set_active("work")

        assert not result.ok
        assert result.code is AuthFailureCode.SYNC_ROLLBACK_FAILED
        manager.native_session.activate.assert_has_calls([
            call(Account(name="work", token=fake_pat("work"))),
            call(Account(name="old", token=fake_pat("old"))),
        ])
        assert manager.sync_journal.read()["phase"] == "rollback"

    def test_recover_pending_sync_rolls_forward_without_token_in_journal(self, tmp_path):
        manager = self.transactional_manager(tmp_path, previous="old")
        manager.sync_journal.write("activate", "work", "old", "native_verified")
        persisted = manager.sync_journal.path.read_text(encoding="utf-8")

        assert fake_pat("work") not in persisted
        assert fake_pat("old") not in persisted

        result = manager.recover_pending_sync()

        assert result.ok
        manager.keychain.get_account.assert_called_once_with("work")
        manager.native_session.activate.assert_called_once_with(
            Account(name="work", token=fake_pat("work"))
        )
        assert manager.active_store.name == "work"
        assert manager.sync_journal.read() is None

    @pytest.mark.parametrize(
        "phase,expected,native_account",
        [
            ("intent", "old", "old"),
            ("native_login", "old", "old"),
            ("native_verified", "work", "work"),
            ("local_write", "work", "work"),
            ("verified", "old", None),
            ("rollback", "old", "old"),
        ],
    )
    def test_restart_recovery_is_deterministic_for_every_phase(
        self, tmp_path, phase, expected, native_account
    ):
        manager = self.transactional_manager(tmp_path, previous="old")
        manager.sync_journal.write("activate", "work", "old", phase)

        result = manager.recover_pending_sync()

        assert result.ok
        assert manager.active_store.name == expected
        assert manager.sync_journal.read() is None
        if native_account is None:
            manager.native_session.activate.assert_not_called()
        else:
            assert manager.native_session.activate.call_args.args[0].name == native_account

    @pytest.mark.parametrize(
        "failure_method,failure_call,expected_phase",
        [
            ("write", 1, None),
            ("write", 2, "intent"),
            ("write", 3, "native_login"),
            ("write", 4, "native_verified"),
            ("write", 5, "local_write"),
            ("clear", 1, "verified"),
        ],
    )
    def test_set_active_sanitizes_transition_failures_and_keeps_recovery_state(
        self, tmp_path, failure_method, failure_call, expected_phase
    ):
        manager = self.transactional_manager(tmp_path, previous="old")
        durable = manager.sync_journal
        manager.sync_journal = FaultInjectingJournal(
            durable, failure_method, failure_call
        )

        result = manager.set_active("work")

        assert not result.ok
        assert "private" not in result.message
        payload = durable.read()
        assert (payload["phase"] if payload else None) == expected_phase

    @pytest.mark.parametrize("method", ["read", "clear"])
    def test_recovery_sanitizes_journal_failures(self, tmp_path, method):
        manager = self.transactional_manager(tmp_path, previous="old")
        durable = manager.sync_journal
        durable.write("activate", "work", "old", "verified")
        manager.sync_journal = FaultInjectingJournal(durable, method, 1)

        result = manager.recover_pending_sync()

        assert not result.ok
        assert result.code is AuthFailureCode.SYNC_PENDING
        assert "private" not in result.message
        assert durable.read() is not None

    @pytest.mark.parametrize("operation", ["mkdir", "chmod", "open", "flock"])
    def test_set_active_sanitizes_sync_lock_failures(self, tmp_path, operation):
        manager = self.transactional_manager(tmp_path)
        target = {
            "mkdir": "pathlib.Path.mkdir",
            "chmod": "pathlib.Path.chmod",
            "open": "supa_cc.accounts.os.open",
            "flock": "supa_cc.accounts.fcntl.flock",
        }[operation]
        with patch(target, side_effect=OSError("private lock path")):
            result = manager.set_active("work")

        assert not result.ok
        assert result.code is AuthFailureCode.SYNC_PENDING
        assert "private" not in result.message

    def test_sync_lock_rejects_symlink_and_permissive_file(self, tmp_path):
        manager = self.transactional_manager(tmp_path)
        lock_path = manager._sync_lock_path
        lock_path.symlink_to(tmp_path / "victim")

        symlink_result = manager.set_active("work")

        assert not symlink_result.ok
        lock_path.unlink()
        lock_path.write_text("", encoding="utf-8")
        lock_path.chmod(0o644)

        permissive_result = manager.set_active("work")

        assert not permissive_result.ok
        assert stat.S_IMODE(lock_path.stat().st_mode) == 0o644

    def test_sync_lock_is_private(self, tmp_path):
        manager = self.transactional_manager(tmp_path)

        assert manager.set_active("work").ok

        assert stat.S_IMODE(manager._sync_lock_path.stat().st_mode) == 0o600

    def test_sync_lock_detects_path_replacement_after_acquire(self, tmp_path):
        manager = self.transactional_manager(tmp_path)
        manager._sync_lock_path.touch(mode=0o600)
        original = manager._sync_lock_path.lstat()
        replaced = Mock(
            st_mode=original.st_mode,
            st_uid=original.st_uid,
            st_dev=original.st_dev,
            st_ino=original.st_ino + 1,
        )

        with patch.object(
            type(manager._sync_lock_path),
            "lstat",
            side_effect=[original, replaced],
        ):
            result = manager.set_active("work")

        assert not result.ok
        manager.native_session.activate.assert_not_called()

    def release_failure_patches(self, fail_unlock=False, fail_close=False):
        real_flock = __import__("fcntl").flock
        real_open = __import__("os").open
        real_close = __import__("os").close
        descriptors = []
        lock_descriptors = set()

        def open_lock(path, flags, mode=0o777):
            descriptor = real_open(path, flags, mode)
            if str(path).endswith(".session-sync.lock"):
                lock_descriptors.add(descriptor)
            return descriptor

        def flock(descriptor, operation):
            if operation == __import__("fcntl").LOCK_UN and fail_unlock:
                real_flock(descriptor, operation)
                raise OSError("private unlock path")
            return real_flock(descriptor, operation)

        def close(descriptor):
            is_lock = descriptor in lock_descriptors
            if is_lock:
                descriptors.append(descriptor)
            real_close(descriptor)
            if is_lock and fail_close:
                raise OSError("private close path")

        return (
            patch("supa_cc.accounts.fcntl.flock", side_effect=flock),
            patch("supa_cc.accounts.os.open", side_effect=open_lock),
            patch("supa_cc.accounts.os.close", side_effect=close),
            descriptors,
        )

    def test_unlock_failure_closes_descriptor_and_reports_committed_cleanup(self, tmp_path):
        manager = self.transactional_manager(tmp_path)
        flock_patch, open_patch, close_patch, descriptors = self.release_failure_patches(
            fail_unlock=True
        )

        with flock_patch, open_patch, close_patch:
            result = manager.set_active("work")

        assert not result.ok
        assert result.code is AuthFailureCode.ENVIRONMENT_BLOCKED
        assert "private" not in result.message
        assert manager.sync_journal.read() is None
        assert len(descriptors) == 1
        with pytest.raises(OSError):
            __import__("os").fstat(descriptors[0])

    def test_close_failure_after_successful_unlock_preserves_committed_result(self, tmp_path):
        manager = self.transactional_manager(tmp_path)
        flock_patch, open_patch, close_patch, descriptors = self.release_failure_patches(
            fail_close=True
        )

        with flock_patch, open_patch, close_patch:
            result = manager.set_active("work")

        assert result.ok
        assert manager.sync_journal.read() is None
        with pytest.raises(OSError):
            __import__("os").fstat(descriptors[0])

    def test_combined_unlock_and_close_failure_still_closes_descriptor(self, tmp_path):
        manager = self.transactional_manager(tmp_path)
        flock_patch, open_patch, close_patch, descriptors = self.release_failure_patches(
            fail_unlock=True, fail_close=True
        )

        with flock_patch, open_patch, close_patch:
            result = manager.set_active("work")

        assert not result.ok
        assert result.code is AuthFailureCode.ENVIRONMENT_BLOCKED
        assert manager.sync_journal.read() is None
        with pytest.raises(OSError):
            __import__("os").fstat(descriptors[0])

    def test_unlock_failure_retains_unresolved_journal_as_pending(self, tmp_path):
        manager = self.transactional_manager(tmp_path)
        durable = manager.sync_journal
        manager.sync_journal = FaultInjectingJournal(durable, "clear", 1)
        flock_patch, open_patch, close_patch, _descriptors = self.release_failure_patches(
            fail_unlock=True
        )

        with flock_patch, open_patch, close_patch:
            result = manager.set_active("work")

        assert not result.ok
        assert result.code is AuthFailureCode.SYNC_PENDING
        assert durable.read()["phase"] == "verified"

    def test_concurrent_set_active_calls_are_serialized(self, tmp_path):
        first = self.transactional_manager(tmp_path)
        second = self.transactional_manager(tmp_path)
        entered = threading.Event()
        release = threading.Event()

        def block(_account):
            entered.set()
            release.wait(timeout=2)
            return AuthResult.success()

        first.native_session.activate.side_effect = block
        first_thread = threading.Thread(target=first.set_active, args=("work",))
        second_thread = threading.Thread(target=second.set_active, args=("work",))
        first_thread.start()
        assert entered.wait(timeout=1)
        second_thread.start()
        time.sleep(0.05)
        assert second.native_session.activate.called is False
        release.set()
        first_thread.join(timeout=2)
        second_thread.join(timeout=2)
        assert second.native_session.activate.called

    @pytest.mark.parametrize("operation", ["add", "remove"])
    def test_switch_serializes_inactive_mutation_until_recovery_finishes(
        self, tmp_path, operation
    ):
        switcher = self.transactional_manager(tmp_path, previous="old")
        mutator = self.transactional_manager(tmp_path, previous="old")
        entered = threading.Event()
        release = threading.Event()

        def block(_account):
            entered.set()
            release.wait(timeout=2)
            return AuthResult.success()

        switcher.native_session.activate.side_effect = block
        switch_thread = threading.Thread(target=switcher.set_active, args=("work",))
        if operation == "add":
            mutation_thread = threading.Thread(
                target=mutator.add, args=("new", fake_pat("concurrent-new"))
            )
        else:
            mutation_thread = threading.Thread(target=mutator.remove, args=("old",))

        switch_thread.start()
        assert entered.wait(timeout=1)
        mutation_thread.start()
        time.sleep(0.05)
        mutator.keychain.add_account.assert_not_called()
        mutator.keychain.remove_account.assert_not_called()
        release.set()
        switch_thread.join(timeout=2)
        mutation_thread.join(timeout=2)

        assert not switch_thread.is_alive()
        assert not mutation_thread.is_alive()
        if operation == "add":
            mutator.keychain.add_account.assert_called_once()
        else:
            mutator.keychain.remove_account.assert_called_once_with("old")

    def test_recovery_and_selection_share_sync_lock(self, tmp_path):
        recovery = self.transactional_manager(tmp_path, previous="old")
        selection = self.transactional_manager(tmp_path, previous="old")
        recovery.sync_journal.write("activate", "work", "old", "native_verified")
        entered = threading.Event()
        release = threading.Event()

        def block(_account):
            entered.set()
            release.wait(timeout=2)
            return AuthResult.success()

        recovery.native_session.activate.side_effect = block
        recovery_thread = threading.Thread(target=recovery.recover_pending_sync)
        selection_thread = threading.Thread(target=selection.set_active, args=("work",))
        recovery_thread.start()
        assert entered.wait(timeout=1)
        selection_thread.start()
        time.sleep(0.05)
        selection.config.validate_access_token.assert_not_called()
        release.set()
        recovery_thread.join(timeout=2)
        selection_thread.join(timeout=2)
        selection.config.validate_access_token.assert_called_once()

    def test_recover_pending_sync_retains_journal_when_credential_is_missing(self, tmp_path):
        manager = self.transactional_manager(tmp_path, previous="old")
        manager.sync_journal.write("activate", "work", "old", "native_verified")
        manager.keychain.get_account.side_effect = lambda _name: None

        result = manager.recover_pending_sync()

        assert not result.ok
        assert result.code is AuthFailureCode.SYNC_PENDING
        assert manager.sync_journal.read() is not None
        manager.native_session.activate.assert_not_called()

    def test_set_active_stops_when_pending_recovery_cannot_complete(self, tmp_path):
        manager = self.transactional_manager(tmp_path, previous="old")
        manager.sync_journal.write("activate", "missing", "old", "native_verified")

        result = manager.set_active("work")

        assert not result.ok
        assert result.code is AuthFailureCode.SYNC_PENDING
        manager.native_session.activate.assert_not_called()

    def test_set_active_preserves_environment_override_failure(self, tmp_path):
        manager = self.transactional_manager(tmp_path, previous="old")
        blocked = AuthResult.failure(AuthFailureCode.ENVIRONMENT_BLOCKED, "safe")
        manager.native_session.activate.side_effect = [blocked, AuthResult.success()]

        result = manager.set_active("work")

        assert result is blocked
        assert manager.active_store.name == "old"

    @pytest.mark.parametrize(
        "name",
        [
            "",
            "name with space",
            "work\n",
            fake_pat("selected_name"),
            "acct_" + fake_pat("embedded_selected_name"),
        ],
        ids=["empty", "space", "newline", "pat", "embedded-pat"],
    )
    def test_set_active_rejects_invalid_name_before_transaction_dependencies(
        self, tmp_path, name
    ):
        keychain = Mock()
        config = Mock()
        active_store = Mock()
        native_session = Mock()
        journal = Mock()
        journal.path = tmp_path / "session-sync.json"
        manager = AccountManager(
            keychain=keychain,
            config=config,
            active_store=active_store,
            native_session=native_session,
            sync_journal=journal,
        )

        result = manager.set_active(name)

        assert not result.ok
        assert result.code is AuthFailureCode.ACCOUNT_REQUIRED
        assert result.exit_code == 2
        assert result.message == "Informe um nome de conta válido."
        assert keychain.method_calls == []
        assert journal.method_calls == []
        assert active_store.method_calls == []
        assert native_session.method_calls == []
        assert not manager._sync_lock_path.exists()

    def test_add_valid_account(self, tmp_path):
        manager = AccountManager()
        manager.keychain.index_path = tmp_path / "accounts.json"
        manager.keychain.update_index([])
        with patch.object(manager.keychain, 'add_account') as add_account:
            account = manager.add("test", fake_pat())
            assert account.name == "test"
            assert account.token == fake_pat()
            add_account.assert_called_once_with(account)

    def test_add_inactive_account_does_not_synchronize_native_session(self, tmp_path):
        manager = self.transactional_manager(tmp_path, previous="old")

        manager.add("work", fake_pat("replacement"))

        manager.native_session.activate.assert_not_called()
        manager.native_session.logout.assert_not_called()

    def test_add_active_account_resynchronizes_replacement_token(self, tmp_path):
        manager = self.transactional_manager(tmp_path, previous="work")
        replacement = Account(name="work", token=fake_pat("replacement"))

        assert manager.add("work", replacement.token) == replacement

        manager.keychain.add_account.assert_called_once_with(replacement)
        manager.native_session.activate.assert_called_once_with(replacement)

    def test_add_active_account_restores_old_credential_and_session_on_failure(self, tmp_path):
        manager = self.transactional_manager(tmp_path, previous="work")
        old = manager.keychain.get_account("work")
        failed = AuthResult.failure(AuthFailureCode.NATIVE_LOGIN_FAILED, "safe")
        manager.native_session.activate.side_effect = [failed, AuthResult.success()]

        with pytest.raises(AccountTransactionError):
            manager.add("work", fake_pat("replacement"))

        manager.keychain.create_account_backup.assert_called_once_with("work")
        manager.keychain.restore_account_backup.assert_called_once_with("work")
        assert manager.native_session.activate.call_args_list[-1] == call(old)
        assert manager.sync_journal.read() is None

    @pytest.mark.parametrize("write_call", [1, 2, 3, 4, 5])
    def test_active_overwrite_restart_restores_old_pat_from_secure_backup(
        self, tmp_path, write_call
    ):
        old = fake_pat("durable_old")
        replacement = fake_pat("durable_replacement")
        store = FakeCredentialStore()
        active_store = MemoryActiveAccountStore("work")
        native = Mock()
        native.activate.return_value = AuthResult.success()
        native.logout.return_value = AuthResult.success()
        durable = SessionSyncJournal(tmp_path / "session-sync.json")
        manager = self.durable_manager(tmp_path, store, active_store, native, durable)
        manager.keychain.add_account(Account("work", old))
        manager.sync_journal = InterruptingJournal(durable, write_call=write_call)

        with pytest.raises(KeyboardInterrupt):
            manager.add("work", replacement)

        restarted_native = Mock()
        restarted_native.activate.return_value = AuthResult.success()
        restarted = self.durable_manager(
            tmp_path, store, active_store, restarted_native, durable
        )
        result = restarted.recover_pending_sync()

        assert result.ok
        assert restarted.get("work").token == old
        if write_call == 1:
            restarted_native.activate.assert_not_called()
        else:
            restarted_native.activate.assert_called_once_with(Account("work", old))
        assert set(store.tokens) == {"work"}
        assert not durable.path.exists()

    def test_active_overwrite_restart_after_native_activation_restores_old_pat(self, tmp_path):
        old = fake_pat("activation_old")
        replacement = fake_pat("activation_replacement")
        store = FakeCredentialStore()
        active_store = MemoryActiveAccountStore("work")
        durable = SessionSyncJournal(tmp_path / "session-sync.json")
        native = Mock()

        def interrupt(account):
            assert account.token == replacement
            raise KeyboardInterrupt()

        native.activate.side_effect = interrupt
        manager = self.durable_manager(tmp_path, store, active_store, native, durable)
        manager.keychain.add_account(Account("work", old))

        with pytest.raises(KeyboardInterrupt):
            manager.add("work", replacement)

        restarted_native = Mock()
        restarted_native.activate.return_value = AuthResult.success()
        restarted = self.durable_manager(
            tmp_path, store, active_store, restarted_native, durable
        )
        assert restarted.recover_pending_sync().ok
        assert restarted.get("work").token == old
        restarted_native.activate.assert_called_once_with(Account("work", old))
        assert set(store.tokens) == {"work"}

    def test_active_overwrite_success_removes_secure_backup(self, tmp_path):
        store = FakeCredentialStore()
        active_store = MemoryActiveAccountStore("work")
        native = Mock()
        native.activate.return_value = AuthResult.success()
        manager = self.durable_manager(tmp_path, store, active_store, native)
        manager.keychain.add_account(Account("work", fake_pat("old")))
        replacement = fake_pat("committed")

        manager.add("work", replacement)

        assert manager.get("work").token == replacement
        assert set(store.tokens) == {"work"}
        assert manager.sync_journal.read() is None

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

    def test_remove_inactive_account_does_not_touch_native_session(self, tmp_path):
        manager = self.transactional_manager(tmp_path, previous="old")

        manager.remove("work")

        manager.keychain.remove_account.assert_called_once_with("work")
        manager.native_session.logout.assert_not_called()
        assert manager.active_store.name == "old"

    def test_remove_active_account_logs_out_before_clearing_and_deleting(self, tmp_path):
        manager = self.transactional_manager(tmp_path, previous="work")
        events = Mock()
        events.attach_mock(manager.native_session, "native")
        manager.active_store.clear = Mock(wraps=manager.active_store.clear)
        events.attach_mock(manager.active_store.clear, "clear")
        events.attach_mock(manager.keychain, "keychain")

        manager.remove("work")

        assert events.mock_calls == [
            call.native.logout(),
            call.clear(),
            call.keychain.remove_account("work"),
        ]
        assert manager.active_store.name is None
        assert manager.sync_journal.read() is None

    def test_remove_active_account_logout_failure_preserves_all_local_state(self, tmp_path):
        manager = self.transactional_manager(tmp_path, previous="work")
        manager.native_session.logout.return_value = AuthResult.failure(
            AuthFailureCode.NATIVE_LOGOUT_FAILED, "safe"
        )

        with pytest.raises(AccountTransactionError):
            manager.remove("work")

        assert manager.active_store.name == "work"
        manager.keychain.remove_account.assert_not_called()
        assert manager.sync_journal.read() is None

    def test_remove_active_retains_intent_after_post_logout_uncertainty(self, tmp_path):
        manager = self.transactional_manager(tmp_path, previous="work")
        manager.native_session.logout.return_value = AuthResult.failure(
            AuthFailureCode.SYNC_PENDING, "safe"
        )

        with pytest.raises(AccountTransactionError):
            manager.remove("work")

        assert manager.active_store.name == "work"
        manager.keychain.remove_account.assert_not_called()
        assert manager.sync_journal.read()["phase"] == "intent"

    def test_logout_recovery_retains_intent_when_preverification_is_inconclusive(self, tmp_path):
        manager = self.transactional_manager(tmp_path, previous="work")
        manager.sync_journal.write("logout", None, "work", "intent")
        manager.native_session.logout.return_value = AuthResult.failure(
            AuthFailureCode.NETWORK_FAILURE, "safe"
        )

        result = manager.recover_pending_sync()

        assert result.code is AuthFailureCode.SYNC_PENDING
        assert manager.active_store.name == "work"
        manager.keychain.remove_account.assert_not_called()
        assert manager.sync_journal.read()["phase"] == "intent"

    def test_inactive_add_runs_pending_recovery_before_mutation(self, tmp_path):
        manager = self.transactional_manager(tmp_path, previous="old")
        manager.sync_journal.write("activate", "missing", "old", "native_verified")

        with pytest.raises(AccountTransactionError):
            manager.add("new", fake_pat("new"))

        manager.keychain.add_account.assert_not_called()

    def test_inactive_remove_runs_pending_recovery_before_deletion(self, tmp_path):
        manager = self.transactional_manager(tmp_path, previous="old")
        manager.sync_journal.write("activate", "missing", "old", "native_verified")

        with pytest.raises(AccountTransactionError):
            manager.remove("work")

        manager.keychain.remove_account.assert_not_called()

    def test_remove_active_account_retains_recoverable_journal_after_local_failure(self, tmp_path):
        manager = self.transactional_manager(tmp_path, previous="work")
        manager.keychain.remove_account.side_effect = OSError("private")

        with pytest.raises(OSError, match="private"):
            manager.remove("work")

        assert manager.active_store.name is None
        assert manager.sync_journal.read() == {
            "operation": "logout",
            "target_account": None,
            "previous_account": "work",
            "phase": "local_write",
        }

    def test_active_removal_restart_after_logout_does_not_logout_twice(self, tmp_path):
        store = FakeCredentialStore()
        active_store = MemoryActiveAccountStore("work")
        config = Mock()
        session_present = [True]

        def verify():
            if session_present[0]:
                return AuthResult.success()
            return AuthResult.failure(AuthFailureCode.TOKEN_MISSING, "safe")

        def logout():
            session_present[0] = False
            return AuthResult.success()

        config.verify_persisted_session.side_effect = verify
        config.logout_session.side_effect = logout
        native = NativeSessionSynchronizer(config, env={}, supabase_home=tmp_path / "home")
        durable = SessionSyncJournal(tmp_path / "session-sync.json")
        manager = self.durable_manager(tmp_path, store, active_store, native, durable)
        manager.keychain.add_account(Account("work", fake_pat("remove")))
        manager.sync_journal = InterruptingJournal(durable, write_call=2)

        with pytest.raises(KeyboardInterrupt):
            manager.remove("work")

        restarted = self.durable_manager(tmp_path, store, active_store, native, durable)
        assert restarted.recover_pending_sync().ok
        assert config.logout_session.call_count == 1
        assert active_store.name is None
        assert restarted.get("work") is None

    @pytest.mark.parametrize(
        "code",
        [AuthFailureCode.NETWORK_FAILURE, AuthFailureCode.ENVIRONMENT_BLOCKED, AuthFailureCode.CLI_INCOMPATIBLE],
    )
    def test_active_removal_restart_recovers_after_uncertain_post_logout_verification(
        self, tmp_path, code
    ):
        store = FakeCredentialStore()
        active_store = MemoryActiveAccountStore("work")
        config = Mock()
        config.logout_session.return_value = AuthResult.success()
        config.verify_persisted_session.side_effect = [
            AuthResult.success(),
            AuthResult.failure(code, "safe"),
            AuthResult.failure(AuthFailureCode.TOKEN_MISSING, "safe"),
        ]
        native = NativeSessionSynchronizer(config, env={}, supabase_home=tmp_path / "home")
        durable = SessionSyncJournal(tmp_path / "session-sync.json")
        manager = self.durable_manager(tmp_path, store, active_store, native, durable)
        manager.keychain.add_account(Account("work", fake_pat("uncertain-remove")))

        with pytest.raises(AccountTransactionError):
            manager.remove("work")

        assert active_store.name == "work"
        assert durable.read()["phase"] == "intent"
        restarted = self.durable_manager(tmp_path, store, active_store, native, durable)
        assert restarted.recover_pending_sync().ok
        assert config.logout_session.call_count == 1
        assert active_store.name is None
        assert restarted.get("work") is None
        assert durable.read() is None

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

    def test_set_active_validates_before_persisting_name(self, tmp_path):
        keychain = Mock()
        config = Mock()
        active_store = Mock()
        active_store.read.return_value = None
        native_session = Mock()
        native_session.activate.return_value = AuthResult.success()
        account = Account(name="work", token=fake_pat("valid_token"))
        keychain.get_account.return_value = account
        config.validate_access_token.return_value = AuthResult.success()
        manager = AccountManager(
            keychain=keychain,
            config=config,
            active_store=active_store,
            native_session=native_session,
            sync_journal=SessionSyncJournal(tmp_path / "session-sync.json"),
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
            call.store.read(),
            call.store.write("work"),
        ]
        native_session.activate.assert_called_once_with(account)

    def test_set_active_returns_token_missing_without_validation_or_write(self, tmp_path):
        keychain = Mock()
        config = Mock()
        active_store = Mock()
        active_store.read.return_value = None
        native_session = Mock()
        native_session.activate.return_value = AuthResult.success()
        native_session.logout.return_value = AuthResult.success()
        keychain.get_account.return_value = None
        manager = AccountManager(
            keychain=keychain,
            config=config,
            active_store=active_store,
            native_session=native_session,
            sync_journal=SessionSyncJournal(tmp_path / "session-sync.json"),
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

    def test_set_active_maps_active_name_write_failure(self, tmp_path):
        keychain = Mock()
        config = Mock()
        active_store = Mock()
        active_store.read.return_value = None
        native_session = Mock()
        native_session.activate.return_value = AuthResult.success()
        native_session.logout.return_value = AuthResult.success()
        account = Account(name="work", token=fake_pat("valid_token"))
        keychain.get_account.return_value = account
        config.validate_access_token.return_value = AuthResult.success()
        active_store.write.side_effect = OSError("sensitive path")
        manager = AccountManager(
            keychain=keychain,
            config=config,
            active_store=active_store,
            native_session=native_session,
            sync_journal=SessionSyncJournal(tmp_path / "session-sync.json"),
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
