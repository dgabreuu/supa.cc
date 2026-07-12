import json
import os
import stat

import pytest

import supa_cc.account_store as keychain
from supa_cc.account_store import AccountStore
from supa_cc.auth import (
    AccountIndexInvalidError,
    AccountIndexReadError,
    AccountTransactionError,
)
from supa_cc.environment import detect_environment
from supa_cc.account_store import KEYCHAIN_SERVICE, AccountStore as KeychainManager
from supa_cc.models import Account, AccountSummary

from helpers import FakeCredentialStore, fake_pat


def ubuntu_environment():
    return detect_environment(system_name="Linux", os_release="ID=ubuntu\n")


def test_manager_uses_the_injected_credential_store_for_add_get_and_remove(tmp_path):
    store = FakeCredentialStore()
    manager = KeychainManager(
        index_path=tmp_path / "accounts.json", credential_store=store
    )
    account = Account(name="work", token=fake_pat("work"))

    manager.add_account(account)

    assert manager.get_account("work") == account
    manager.remove_account("work")
    assert store.operations == [
        "get:work", "set:work", "get:work", "get:work", "delete:work"
    ]


def test_default_index_path_uses_linux_xdg_config_home(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    manager = KeychainManager(
        environment=ubuntu_environment(), credential_store=FakeCredentialStore()
    )

    assert manager.index_path == tmp_path / "supa.cc" / "accounts.json"


def test_default_store_is_created_for_the_detected_environment(monkeypatch, tmp_path):
    environment = ubuntu_environment()
    store = FakeCredentialStore()
    calls = []
    monkeypatch.setattr(keychain, "detect_environment", lambda: environment)
    monkeypatch.setattr(
        keychain,
        "create_credential_store",
        lambda value, service: calls.append((value, service)) or store,
    )

    manager = KeychainManager(index_path=tmp_path / "accounts.json")

    assert manager.credential_store is store
    assert calls == [(environment, KEYCHAIN_SERVICE)]


def test_custom_service_is_passed_to_the_default_credential_store(
    monkeypatch, tmp_path
):
    environment = ubuntu_environment()
    service = "supa.cc.tests.custom"
    store = FakeCredentialStore()
    calls = []
    monkeypatch.setattr(keychain, "detect_environment", lambda: environment)
    monkeypatch.setattr(
        keychain,
        "create_credential_store",
        lambda value, service: calls.append((value, service)) or store,
    )

    manager = KeychainManager(index_path=tmp_path / "accounts.json", service=service)

    assert manager.credential_store is store
    assert manager.service == service
    assert calls == [(environment, service)]


def test_injected_store_namespace_is_used_for_diagnostics(tmp_path):
    store = FakeCredentialStore()
    store.service = "supa.cc.tests.injected"

    manager = KeychainManager(index_path=tmp_path / "accounts.json", credential_store=store)

    assert manager.service == store.service


def test_keychain_manager_has_no_direct_keyring_dependency():
    assert not hasattr(keychain, "keyring")


def test_service_property_remains_canonical_by_default(tmp_path):
    manager = KeychainManager(
        index_path=tmp_path / "accounts.json", credential_store=FakeCredentialStore()
    )

    assert manager.service == KEYCHAIN_SERVICE


def test_get_account_always_reads_authoritative_store(tmp_path):
    store = FakeCredentialStore()
    store.tokens["work"] = fake_pat("work")
    manager = KeychainManager(
        index_path=tmp_path / "accounts.json", credential_store=store
    )

    first = manager.get_account("work")
    second = manager.get_account("work")

    assert first == Account(name="work", token=fake_pat("work"))
    assert second == first
    assert store.operations == ["get:work", "get:work"]


def test_two_managers_see_credential_replacement_immediately(tmp_path):
    store = FakeCredentialStore()
    store.tokens["work"] = fake_pat("old")
    first = AccountStore(index_path=tmp_path / "accounts.json", credential_store=store)
    second = AccountStore(index_path=tmp_path / "accounts.json", credential_store=store)

    assert first.get_account("work") == Account(name="work", token=fake_pat("old"))
    second.save_account(Account("work", fake_pat("new")))

    assert first.get_account("work") == Account(name="work", token=fake_pat("new"))


def test_list_accounts_does_not_read_tokens(tmp_path):
    path = tmp_path / "accounts.json"
    path.write_text(json.dumps({"accounts": ["personal", "work"]}), encoding="utf-8")
    path.chmod(0o600)
    store = FakeCredentialStore()
    manager = KeychainManager(index_path=path, credential_store=store)

    assert manager.list_accounts() == [
        AccountSummary(name="personal"),
        AccountSummary(name="work"),
    ]
    assert store.operations == []


def test_add_persists_account_names_without_tokens_in_the_index(tmp_path):
    store = FakeCredentialStore()
    account = Account(name="work", token=fake_pat("work"))
    path = tmp_path / "accounts.json"
    manager = KeychainManager(index_path=path, credential_store=store)

    manager.add_account(account)

    assert json.loads(path.read_text(encoding="utf-8")) == {"accounts": ["work"]}
    assert account.token not in path.read_text(encoding="utf-8")


def test_add_restores_previous_token_when_index_commit_fails(tmp_path, monkeypatch):
    store = FakeCredentialStore()
    previous = fake_pat("previous")
    replacement = fake_pat("replacement")
    store.tokens["work"] = previous
    manager = KeychainManager(
        index_path=tmp_path / "accounts.json", credential_store=store
    )
    manager.update_index(["work"])
    monkeypatch.setattr(
        manager, "_write_index_locked", lambda _names: (_ for _ in ()).throw(OSError("failed"))
    )

    with pytest.raises(OSError, match="failed"):
        manager.add_account(Account(name="work", token=replacement))

    assert store.tokens == {"work": previous}


def test_remove_restores_token_when_index_commit_fails(tmp_path, monkeypatch):
    store = FakeCredentialStore()
    previous = fake_pat("previous")
    store.tokens["work"] = previous
    manager = KeychainManager(
        index_path=tmp_path / "accounts.json", credential_store=store
    )
    manager.update_index(["work"])
    monkeypatch.setattr(
        manager, "_write_index_locked", lambda _names: (_ for _ in ()).throw(OSError("failed"))
    )

    with pytest.raises(OSError, match="failed"):
        manager.remove_account("work")

    assert store.tokens == {"work": previous}


def test_add_raises_transaction_error_when_token_rollback_fails(tmp_path, monkeypatch):
    store = FakeCredentialStore()
    previous = fake_pat("previous")
    replacement = fake_pat("replacement")
    store.tokens["work"] = previous
    manager = KeychainManager(
        index_path=tmp_path / "accounts.json", credential_store=store
    )
    manager.update_index(["work"])
    monkeypatch.setattr(
        manager, "_write_index_locked", lambda _names: (_ for _ in ()).throw(OSError("failed"))
    )

    original_set = store.set

    def fail_rollback(account):
        if account.token == previous:
            raise RuntimeError("rollback failed")
        original_set(account)

    store.set = fail_rollback

    with pytest.raises(AccountTransactionError) as raised:
        manager.add_account(Account(name="work", token=replacement))

    assert raised.value.__cause__ is None
    assert previous not in str(raised.value)
    assert replacement not in str(raised.value)


def test_save_account_replaces_credential_without_changing_index(tmp_path):
    store = FakeCredentialStore()
    manager = KeychainManager(
        index_path=tmp_path / "accounts.json", credential_store=store
    )
    manager.update_index(["work", "personal"])

    manager.save_account(Account(name="work", token=fake_pat("previous")))

    assert store.tokens == {"work": fake_pat("previous")}
    assert [account.name for account in manager.list_accounts()] == ["work", "personal"]


def test_secure_backup_round_trip_does_not_touch_index_or_cache_backup_name(tmp_path):
    old = fake_pat("old")
    replacement = fake_pat("replacement")
    store = FakeCredentialStore()
    store.tokens["work"] = old
    manager = KeychainManager(
        index_path=tmp_path / "accounts.json", credential_store=store
    )
    manager.update_index(["work"])

    manager.create_account_backup("work")
    store.tokens["work"] = replacement
    manager.restore_account_backup("work")
    manager.delete_account_backup("work")

    assert store.tokens == {"work": old}
    assert [account.name for account in manager.list_accounts()] == ["work"]
    backup_names = {operation.split(":", 1)[1] for operation in store.operations if ":" in operation} - {"work"}
    assert len(backup_names) == 1
    assert all(not keychain.is_valid_account_name(name) for name in backup_names)
    assert not hasattr(manager, "_token_cache")


def test_backup_write_is_read_back_verified_and_failure_is_sanitized(tmp_path):
    old = fake_pat("old_secret")
    store = FakeCredentialStore()
    store.tokens["work"] = old
    manager = KeychainManager(
        index_path=tmp_path / "accounts.json", credential_store=store
    )
    manager.update_index(["work"])
    original_set = store.set

    def discard_backup(account):
        if account.name == "work":
            original_set(account)

    store.set = discard_backup

    with pytest.raises(AccountTransactionError) as raised:
        manager.create_account_backup("work")

    assert old not in str(raised.value)
    assert "work" not in str(raised.value)


def test_update_index_does_not_overwrite_invalid_json(tmp_path):
    path = tmp_path / "accounts.json"
    path.write_text("not-json", encoding="utf-8")
    path.chmod(0o600)
    manager = KeychainManager(index_path=path, credential_store=FakeCredentialStore())

    with pytest.raises(AccountIndexInvalidError):
        manager.update_index(["work"])

    assert path.read_text(encoding="utf-8") == "not-json"


def test_update_index_writes_only_account_names_with_private_permissions(tmp_path):
    path = tmp_path / "accounts.json"
    manager = KeychainManager(index_path=path, credential_store=FakeCredentialStore())

    manager.update_index(["work", "personal", "work"])

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "accounts": ["work", "personal"]
    }
    assert path.stat().st_mode & 0o777 == 0o600


def test_windows_index_lock_rejects_link_without_writing_target(tmp_path, monkeypatch):
    path = tmp_path / "accounts.json"
    manager = KeychainManager(index_path=path, credential_store=FakeCredentialStore())
    target = tmp_path / "target"
    target.write_bytes(b"")
    manager.index_lock_path.symlink_to(target)
    real_open = os.open

    monkeypatch.setattr(keychain, "_is_windows", lambda: True)
    monkeypatch.setattr(
        keychain.os,
        "open",
        lambda lock_path, flags, mode=0o777: real_open(
            lock_path, flags & ~getattr(os, "O_NOFOLLOW", 0), mode
        ),
    )

    with pytest.raises(OSError, match="unsafe lock file"):
        manager.update_index(["work"])

    assert target.read_bytes() == b""


@pytest.mark.parametrize("unsafe_kind", ["symlink", "directory", "permissive"])
def test_list_accounts_rejects_unsafe_index_file(tmp_path, unsafe_kind):
    path = tmp_path / "accounts.json"
    if unsafe_kind == "symlink":
        target = tmp_path / "target"
        target.write_text('{"accounts": []}', encoding="utf-8")
        target.chmod(0o600)
        path.symlink_to(target)
    elif unsafe_kind == "directory":
        path.mkdir()
    else:
        path.write_text('{"accounts": []}', encoding="utf-8")
        path.chmod(0o644)
    manager = KeychainManager(index_path=path, credential_store=FakeCredentialStore())

    with pytest.raises(AccountIndexReadError):
        manager.list_accounts()


def test_list_accounts_rejects_oversized_index(tmp_path):
    path = tmp_path / "accounts.json"
    path.write_text(" " * (1024 * 1024 + 1), encoding="utf-8")
    path.chmod(0o600)
    manager = KeychainManager(index_path=path, credential_store=FakeCredentialStore())

    with pytest.raises(AccountIndexReadError):
        manager.list_accounts()


def test_update_index_fsyncs_containing_directory(tmp_path, monkeypatch):
    path = tmp_path / "accounts.json"
    manager = KeychainManager(index_path=path, credential_store=FakeCredentialStore())
    directory_fsyncs = 0
    original_fsync = os.fsync

    def record_fsync(descriptor):
        nonlocal directory_fsyncs
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            directory_fsyncs += 1
        original_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", record_fsync)

    manager.update_index(["work"])

    assert directory_fsyncs == 1


def test_update_index_preserves_previous_file_when_atomic_write_fails(
    tmp_path, monkeypatch
):
    path = tmp_path / "accounts.json"
    original = '{"accounts": ["work"]}'
    path.write_text(original, encoding="utf-8")
    path.chmod(0o600)
    manager = KeychainManager(index_path=path, credential_store=FakeCredentialStore())
    monkeypatch.setattr(
        keychain.os,
        "fdopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("write failed")),
    )

    with pytest.raises(OSError, match="write failed"):
        manager.update_index(["personal"])

    assert path.read_text(encoding="utf-8") == original
    assert [
        item
        for item in tmp_path.glob(".accounts.json.*")
        if item != manager.index_lock_path
    ] == []
