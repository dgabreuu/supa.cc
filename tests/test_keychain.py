import json
from unittest.mock import patch

from supa_cc.keychain import (
    KEYCHAIN_SERVICE,
    LEGACY_KEYCHAIN_SERVICE,
    LEGACY_SUPAKILLER_KEYCHAIN_SERVICE,
    KeychainManager,
)
from supa_cc.models import Account

from helpers import fake_pat


class TestKeychainManager:
    def test_save_account(self, tmp_path):
        manager = KeychainManager(index_path=tmp_path / "accounts.json")
        manager.update_index([])
        account = Account(name="test", token=fake_pat("test123"))

        with patch("supa_cc.keychain.keyring.set_password") as mock_set:
            manager.save_account(account)
            mock_set.assert_called_once_with(KEYCHAIN_SERVICE, "test", fake_pat("test123"))

    def test_get_account_found(self, tmp_path):
        manager = KeychainManager(index_path=tmp_path / "accounts.json")
        manager.update_index([])

        with patch("supa_cc.keychain.keyring.get_password", return_value=fake_pat("test123")):
            account = manager.get_account("test")
            assert account is not None
            assert account.name == "test"
            assert account.token == fake_pat("test123")

    def test_get_account_not_found(self, tmp_path):
        manager = KeychainManager(index_path=tmp_path / "accounts.json")
        manager.update_index([])

        with patch("supa_cc.keychain.keyring.get_password", return_value=None):
            account = manager.get_account("nonexistent")
            assert account is None

    def test_delete_account(self, tmp_path):
        manager = KeychainManager(index_path=tmp_path / "accounts.json")
        manager.update_index([])

        with patch("supa_cc.keychain.keyring.delete_password") as mock_delete:
            manager.delete_account("test")
            mock_delete.assert_called_once_with(KEYCHAIN_SERVICE, "test")

    def test_list_accounts_with_accounts(self, tmp_path):
        index_path = tmp_path / "accounts.json"
        index_path.write_text(json.dumps({"accounts": ["account1", "account2"]}), encoding="utf-8")
        manager = KeychainManager(index_path=index_path)

        with patch.object(manager, "get_account") as mock_get:
            accounts = manager.list_accounts()

        assert len(accounts) == 2
        assert accounts[0].name == "account1"
        assert accounts[0].token == ""
        assert accounts[1].name == "account2"
        assert accounts[1].token == ""
        mock_get.assert_not_called()

    def test_list_accounts_no_accounts(self, tmp_path):
        index_path = tmp_path / "accounts.json"
        index_path.write_text(json.dumps({"accounts": []}), encoding="utf-8")
        manager = KeychainManager(index_path=index_path)

        accounts = manager.list_accounts()

        assert accounts == []

    def test_list_accounts_does_not_fetch_tokens(self, tmp_path):
        index_path = tmp_path / "accounts.json"
        index_path.write_text(json.dumps({"accounts": ["account1", "account2"]}), encoding="utf-8")
        manager = KeychainManager(index_path=index_path)

        with patch("supa_cc.keychain.keyring.get_password") as mock_get_password:
            accounts = manager.list_accounts()

        assert [account.name for account in accounts] == ["account1", "account2"]
        assert [account.token for account in accounts] == ["", ""]
        mock_get_password.assert_not_called()

    def test_list_accounts_prefers_local_index_file(self, tmp_path):
        manager = KeychainManager(index_path=tmp_path / "accounts.txt")
        manager.update_index(["account1", "account2"])

        with patch("keyring.backends.macOS.Keyring") as mock_backend, patch(
            "supa_cc.keychain.keyring.get_password"
        ) as mock_get_password:
            accounts = manager.list_accounts()

        assert [account.name for account in accounts] == ["account1", "account2"]
        assert [account.token for account in accounts] == ["", ""]
        mock_backend.assert_not_called()
        mock_get_password.assert_not_called()

    def test_list_accounts_persists_empty_index_after_empty_legacy_lookup(self, tmp_path):
        index_path = tmp_path / "accounts.json"
        manager = KeychainManager(index_path=index_path)

        with patch.object(manager, "_migrate_legacy_data", return_value=False), patch.object(
            manager, "_read_legacy_keychain_index", return_value=[]
        ):
            assert manager.list_accounts() == []
            assert manager.list_accounts() == []

    def test_list_accounts_recovers_from_invalid_local_index(self, tmp_path):
        index_path = tmp_path / "accounts.json"
        index_path.write_text("not-json", encoding="utf-8")
        manager = KeychainManager(index_path=index_path)

        with patch("keyring.backends.macOS.Keyring") as mock_backend:
            accounts = manager.list_accounts()

        assert accounts == []
        assert index_path.exists()
        mock_backend.assert_not_called()

    def test_list_accounts_import_error(self, tmp_path):
        index_path = tmp_path / "accounts.json"
        manager = KeychainManager(index_path=index_path)

        with patch.object(manager, "_migrate_legacy_data", return_value=False), patch.object(
            manager, "_read_legacy_keychain_index", return_value=[]
        ):
            accounts = manager.list_accounts()

        assert accounts == []

    def test_update_index(self, tmp_path):
        index_path = tmp_path / "accounts.json"
        manager = KeychainManager(index_path=index_path)
        names = ["account1", "account2", "account3"]

        with patch("keyring.backends.macOS.Keyring") as mock_backend:
            manager.update_index(names)

        assert [account.name for account in manager.list_accounts()] == names
        assert index_path.stat().st_mode & 0o777 == 0o600
        mock_backend.assert_not_called()

    def test_legacy_keychain_index_copies_tokens_to_new_service(self, tmp_path):
        index_path = tmp_path / "accounts.json"
        manager = KeychainManager(index_path=index_path)

        def get_password(service, name):
            if service == LEGACY_KEYCHAIN_SERVICE and name == "account1":
                return "token_account1"
            if service == LEGACY_KEYCHAIN_SERVICE and name == "account2":
                return "token_account2"
            return None

        with patch.object(manager, "_migrate_legacy_data", return_value=False):
            with patch("keyring.backends.macOS.Keyring") as mock_backend:
                mock_backend.return_value.get_password.return_value = "account1,account2"
                with patch("supa_cc.keychain.keyring.get_password", side_effect=get_password):
                    with patch("supa_cc.keychain.keyring.set_password") as mock_set:
                        accounts = manager.list_accounts()

        assert [account.name for account in accounts] == ["account1", "account2"]
        mock_set.assert_any_call(KEYCHAIN_SERVICE, "account1", "token_account1")
        mock_set.assert_any_call(KEYCHAIN_SERVICE, "account2", "token_account2")

    def test_migrate_legacy_data_copies_index_and_tokens(self, tmp_path):
        legacy_index = tmp_path / "legacy" / "accounts.json"
        legacy_index.parent.mkdir(parents=True)
        legacy_index.write_text(json.dumps({"accounts": ["acc1", "acc2"]}), encoding="utf-8")

        new_index = tmp_path / "new" / "accounts.json"

        with patch("supa_cc.keychain.LEGACY_SUPAKILLER_INDEX_PATH", tmp_path / "missing-supakiller.json"), patch("supa_cc.keychain.KeychainManager._read_legacy_keychain_index", return_value=[]):
            with patch("supa_cc.keychain.LEGACY_INDEX_PATH", legacy_index):
                with patch(
                    "supa_cc.keychain.keyring.get_password",
                    side_effect=lambda svc, name: f"token_{name}" if svc == LEGACY_KEYCHAIN_SERVICE else None,
                ):
                    with patch("supa_cc.keychain.keyring.set_password") as mock_set:
                        manager = KeychainManager(index_path=new_index)
                        manager._migrate_legacy_data()

        assert new_index.exists()
        assert [a.name for a in manager.list_accounts()] == ["acc1", "acc2"]
        mock_set.assert_any_call(KEYCHAIN_SERVICE, "acc1", "token_acc1")
        mock_set.assert_any_call(KEYCHAIN_SERVICE, "acc2", "token_acc2")

    def test_migrate_supakiller_data_copies_index_and_tokens(self, tmp_path):
        legacy_index = tmp_path / "old-supakiller" / "accounts.json"
        legacy_index.parent.mkdir(parents=True)
        legacy_index.write_text(json.dumps({"accounts": ["old_acc"]}), encoding="utf-8")

        new_index = tmp_path / "new" / "accounts.json"

        with patch("supa_cc.keychain.LEGACY_SUPAKILLER_INDEX_PATH", legacy_index), patch("supa_cc.keychain.KeychainManager._read_legacy_keychain_index", return_value=[]):
            with patch("supa_cc.keychain.LEGACY_INDEX_PATH", tmp_path / "missing-sbc.json"):
                with patch(
                    "supa_cc.keychain.keyring.get_password",
                    side_effect=lambda svc, name: "token_old" if svc == LEGACY_SUPAKILLER_KEYCHAIN_SERVICE else None,
                ):
                    with patch("supa_cc.keychain.keyring.set_password") as mock_set:
                        manager = KeychainManager(index_path=new_index)
                        result = manager._migrate_legacy_data()

        assert result is True
        assert [a.name for a in manager.list_accounts()] == ["old_acc"]
        mock_set.assert_called_once_with(KEYCHAIN_SERVICE, "old_acc", "token_old")

    def test_get_account_migrates_legacy_data_before_lookup(self, tmp_path):
        legacy_index = tmp_path / "old-supakiller" / "accounts.json"
        legacy_index.parent.mkdir(parents=True)
        legacy_index.write_text(json.dumps({"accounts": ["work"]}), encoding="utf-8")

        new_index = tmp_path / "new" / "accounts.json"

        def get_password(service, name):
            if service == LEGACY_SUPAKILLER_KEYCHAIN_SERVICE:
                return fake_pat("legacy_token")
            if service == KEYCHAIN_SERVICE:
                return fake_pat("legacy_token")
            return None

        with patch("supa_cc.keychain.LEGACY_SUPAKILLER_INDEX_PATH", legacy_index):
            with patch("supa_cc.keychain.LEGACY_INDEX_PATH", tmp_path / "missing-sbc.json"):
                with patch("supa_cc.keychain.keyring.get_password", side_effect=get_password):
                    with patch("supa_cc.keychain.keyring.set_password") as mock_set:
                        manager = KeychainManager(index_path=new_index)
                        account = manager.get_account("work")

        assert account == Account(name="work", token=fake_pat("legacy_token"))
        assert new_index.exists()
        mock_set.assert_called_once_with(KEYCHAIN_SERVICE, "work", fake_pat("legacy_token"))

    def test_save_account_migrates_before_writing_new_token(self, tmp_path):
        legacy_index = tmp_path / "old-supakiller" / "accounts.json"
        legacy_index.parent.mkdir(parents=True)
        legacy_index.write_text(json.dumps({"accounts": ["work"]}), encoding="utf-8")

        new_index = tmp_path / "new" / "accounts.json"

        with patch("supa_cc.keychain.LEGACY_SUPAKILLER_INDEX_PATH", legacy_index):
            with patch("supa_cc.keychain.LEGACY_INDEX_PATH", tmp_path / "missing-sbc.json"):
                with patch(
                    "supa_cc.keychain.keyring.get_password",
                    side_effect=lambda svc, name: fake_pat("legacy_token") if svc == LEGACY_SUPAKILLER_KEYCHAIN_SERVICE else None,
                ):
                    with patch("supa_cc.keychain.keyring.set_password") as mock_set:
                        manager = KeychainManager(index_path=new_index)
                        manager.save_account(Account(name="work", token=fake_pat("new_token")))

        assert mock_set.call_args_list[-1].args == (KEYCHAIN_SERVICE, "work", fake_pat("new_token"))

    def test_migrate_legacy_data_combines_supakiller_and_sbc_sources(self, tmp_path):
        supakiller_index = tmp_path / "old-supakiller" / "accounts.json"
        supakiller_index.parent.mkdir(parents=True)
        supakiller_index.write_text(json.dumps({"accounts": ["old_acc"]}), encoding="utf-8")

        sbc_index = tmp_path / "old-sbc" / "accounts.json"
        sbc_index.parent.mkdir(parents=True)
        sbc_index.write_text(json.dumps({"accounts": ["sbc_acc"]}), encoding="utf-8")

        new_index = tmp_path / "new" / "accounts.json"

        def get_password(service, name):
            if service == LEGACY_SUPAKILLER_KEYCHAIN_SERVICE:
                return "token_old"
            if service == LEGACY_KEYCHAIN_SERVICE:
                return "token_sbc"
            return None

        with patch("supa_cc.keychain.LEGACY_SUPAKILLER_INDEX_PATH", supakiller_index), patch("supa_cc.keychain.KeychainManager._read_legacy_keychain_index", return_value=[]):
            with patch("supa_cc.keychain.LEGACY_INDEX_PATH", sbc_index):
                with patch("supa_cc.keychain.keyring.get_password", side_effect=get_password):
                    with patch("supa_cc.keychain.keyring.set_password") as mock_set:
                        manager = KeychainManager(index_path=new_index)
                        result = manager._migrate_legacy_data()

        assert result is True
        assert [a.name for a in manager.list_accounts()] == ["old_acc", "sbc_acc"]
        mock_set.assert_any_call(KEYCHAIN_SERVICE, "old_acc", "token_old")
        mock_set.assert_any_call(KEYCHAIN_SERVICE, "sbc_acc", "token_sbc")

    def test_migrate_legacy_data_combines_json_sources_and_keychain_index(self, tmp_path):
        supakiller_index = tmp_path / "old-supakiller" / "accounts.json"
        supakiller_index.parent.mkdir(parents=True)
        supakiller_index.write_text(json.dumps({"accounts": ["old_acc"]}), encoding="utf-8")

        new_index = tmp_path / "new" / "accounts.json"

        def get_password(service, name):
            if service == LEGACY_SUPAKILLER_KEYCHAIN_SERVICE:
                return "token_old"
            if service == LEGACY_KEYCHAIN_SERVICE and name == "keychain_acc":
                return "token_keychain"
            return None

        with patch("supa_cc.keychain.LEGACY_SUPAKILLER_INDEX_PATH", supakiller_index):
            with patch("supa_cc.keychain.LEGACY_INDEX_PATH", tmp_path / "missing-sbc.json"):
                with patch("keyring.backends.macOS.Keyring") as mock_backend:
                    mock_backend.return_value.get_password.return_value = "keychain_acc"
                    with patch("supa_cc.keychain.keyring.get_password", side_effect=get_password):
                        with patch("supa_cc.keychain.keyring.set_password") as mock_set:
                            manager = KeychainManager(index_path=new_index)
                            accounts = manager.list_accounts()

        assert [account.name for account in accounts] == ["old_acc", "keychain_acc"]
        mock_set.assert_any_call(KEYCHAIN_SERVICE, "old_acc", "token_old")
        mock_set.assert_any_call(KEYCHAIN_SERVICE, "keychain_acc", "token_keychain")

    def test_migrate_legacy_data_skips_when_new_index_exists(self, tmp_path):
        new_index = tmp_path / "accounts.json"
        new_index.write_text(json.dumps({"accounts": ["new_acc"]}), encoding="utf-8")

        legacy_index = tmp_path / "legacy" / "accounts.json"
        legacy_index.parent.mkdir(parents=True)
        legacy_index.write_text(json.dumps({"accounts": ["legacy_acc"]}), encoding="utf-8")

        with patch("supa_cc.keychain.LEGACY_INDEX_PATH", legacy_index):
            with patch("supa_cc.keychain.keyring.set_password") as mock_set:
                manager = KeychainManager(index_path=new_index)
                result = manager._migrate_legacy_data()

        assert result is False
        assert [a.name for a in manager.list_accounts()] == ["new_acc"]
        mock_set.assert_not_called()

    def test_migrate_legacy_data_skips_when_no_legacy_index(self, tmp_path):
        new_index = tmp_path / "accounts.json"
        fake_legacy = tmp_path / "nonexistent" / "accounts.json"

        with patch("supa_cc.keychain.LEGACY_INDEX_PATH", fake_legacy), patch("supa_cc.keychain.KeychainManager._read_legacy_keychain_index", return_value=[]):
            with patch("supa_cc.keychain.LEGACY_SUPAKILLER_INDEX_PATH", fake_legacy):
                with patch("supa_cc.keychain.keyring.set_password") as mock_set:
                    manager = KeychainManager(index_path=new_index)
                    result = manager._migrate_legacy_data()

        assert result is False
        assert not new_index.exists()
        mock_set.assert_not_called()

    def test_migrate_legacy_data_handles_invalid_legacy_json(self, tmp_path):
        legacy_index = tmp_path / "legacy" / "accounts.json"
        legacy_index.parent.mkdir(parents=True)
        legacy_index.write_text("not-json", encoding="utf-8")

        new_index = tmp_path / "new" / "accounts.json"

        with patch("supa_cc.keychain.LEGACY_INDEX_PATH", legacy_index), patch("supa_cc.keychain.KeychainManager._read_legacy_keychain_index", return_value=[]):
            with patch("supa_cc.keychain.LEGACY_SUPAKILLER_INDEX_PATH", legacy_index):
                with patch("supa_cc.keychain.keyring.set_password") as mock_set:
                    manager = KeychainManager(index_path=new_index)
                    result = manager._migrate_legacy_data()

        assert result is False
        assert not new_index.exists()
        mock_set.assert_not_called()
