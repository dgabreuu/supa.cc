import json
import pytest
from unittest.mock import patch
from supa_cc.accounts import AccountManager
from supa_cc.keychain import KEYCHAIN_SERVICE, LEGACY_SUPAKILLER_KEYCHAIN_SERVICE
from supa_cc.models import Account

from helpers import fake_pat


class TestAccountManager:
    def test_add_valid_account(self, tmp_path):
        manager = AccountManager()
        manager.keychain.index_path = tmp_path / "accounts.json"
        manager.keychain.update_index([])
        with patch.object(manager.keychain, 'save_account') as mock_save, \
             patch.object(manager.keychain, 'update_index') as mock_index:
            account = manager.add("test", fake_pat())
            assert account.name == "test"
            assert account.token == fake_pat()
            mock_save.assert_called_once()
            mock_index.assert_called_once()

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
        with patch.object(manager.keychain, 'delete_account') as mock_delete, \
             patch.object(manager.keychain, 'update_index') as mock_index:
            manager.remove("test")
            mock_delete.assert_called_once_with("test")
            mock_index.assert_called_once()

    def test_set_active_success(self):
        manager = AccountManager()
        mock_account = Account(name="test", token=fake_pat("test"))
        with patch.object(manager.keychain, 'get_account', return_value=mock_account), \
             patch('supa_cc.config.SupabaseConfig.set_active_account', return_value=True):
            assert manager.set_active("test") is True

    def test_set_active_not_found(self):
        manager = AccountManager()
        with patch.object(manager.keychain, 'get_account', return_value=None):
            assert manager.set_active("nonexistent") is False

    @pytest.mark.parametrize("name,expected_error", [
        ("", "Nome da conta deve ter entre 1 e 50 caracteres"),
        ("a" * 51, "Nome da conta deve ter entre 1 e 50 caracteres"),
        ("name with space", "Nome da conta contém caracteres inválidos"),
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
        with patch.object(manager.keychain, 'save_account') as mock_save, \
             patch.object(manager.keychain, 'update_index') as mock_index:
            manager.add("work", fake_pat("token_one"))
            manager.add("work", fake_pat("token_two"))
            assert mock_save.call_count == 2
            assert mock_index.call_count == 2

    def test_add_legacy_duplicate_writes_new_token_after_migration(self, tmp_path):
        manager = AccountManager()
        manager.keychain.index_path = tmp_path / "new" / "accounts.json"

        legacy_index = tmp_path / "old-supakiller" / "accounts.json"
        legacy_index.parent.mkdir(parents=True)
        legacy_index.write_text(json.dumps({"accounts": ["work"]}), encoding="utf-8")

        with patch("supa_cc.keychain.LEGACY_SUPAKILLER_INDEX_PATH", legacy_index):
            with patch("supa_cc.keychain.LEGACY_INDEX_PATH", tmp_path / "missing-sbc.json"):
                with patch(
                    "supa_cc.keychain.keyring.get_password",
                    side_effect=lambda svc, name: fake_pat("legacy_token") if svc == LEGACY_SUPAKILLER_KEYCHAIN_SERVICE else None,
                ):
                    with patch("supa_cc.keychain.keyring.set_password") as mock_set:
                        manager.add("work", fake_pat("new_token"))

        assert mock_set.call_args_list[-1].args == (KEYCHAIN_SERVICE, "work", fake_pat("new_token"))
