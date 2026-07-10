import json
import hmac
from unittest.mock import patch

import pytest
from keyring.errors import KeyringError, KeyringLocked, PasswordDeleteError

import supa_cc.keychain as keychain
from supa_cc.auth import KeychainPermissionDeniedError, KeychainReadError
from supa_cc.keychain import (
    KEYCHAIN_SERVICE,
    KeychainManager,
)
from supa_cc.models import Account

from helpers import fake_pat


def test_index_rejects_pat_like_account_name_without_overwriting(tmp_path):
    path = tmp_path / "accounts.json"
    token_like_name = fake_pat("index_namespace")
    original = '{"accounts": ["' + token_like_name + '"]}'
    path.write_text(original, encoding="utf-8")
    manager = KeychainManager(index_path=path)

    with pytest.raises(Exception) as raised:
        manager.update_index(["work"])

    assert type(raised.value).__name__ == "AccountIndexInvalidError"
    assert path.read_text(encoding="utf-8") == original


def test_index_rejects_embedded_pat_name_without_overwriting(tmp_path):
    path = tmp_path / "accounts.json"
    token_like_name = "acct_" + fake_pat("embedded_index")
    original = '{"accounts": ["' + token_like_name + '"]}'
    path.write_text(original, encoding="utf-8")
    manager = KeychainManager(index_path=path)

    with pytest.raises(Exception) as raised:
        manager.update_index(["work"])

    assert type(raised.value).__name__ == "AccountIndexInvalidError"
    assert path.read_text(encoding="utf-8") == original


def test_index_rejects_embedded_pat_with_hex_suffix_without_overwriting(tmp_path):
    path = tmp_path / "accounts.json"
    token_like_name = "x" + fake_pat("index_hex_suffix") + "f"
    original = '{"accounts": ["' + token_like_name + '"]}'
    path.write_text(original, encoding="utf-8")
    manager = KeychainManager(index_path=path)

    with pytest.raises(Exception) as raised:
        manager.update_index(["work"])

    assert type(raised.value).__name__ == "AccountIndexInvalidError"
    assert path.read_text(encoding="utf-8") == original


@pytest.fixture(autouse=True)
def prohibit_subprocess_calls():
    with patch("subprocess.run", side_effect=AssertionError("security commands are forbidden")):
        yield


class TestKeychainManager:
    def test_default_service_is_canonical(self, tmp_path):
        manager = KeychainManager(index_path=tmp_path / "accounts.json")

        assert manager.service == KEYCHAIN_SERVICE

    def test_custom_service_is_used_for_direct_token_operations(self, tmp_path):
        service = "supa.cc.tests.unit-direct"
        account = Account(name="custom", token=fake_pat("custom"))
        manager = KeychainManager(
            index_path=tmp_path / "accounts.json",
            service=service,
            cache_ttl_seconds=0,
        )
        manager.update_index([])

        with patch("supa_cc.keychain.keyring.set_password") as mock_set, patch(
            "supa_cc.keychain.keyring.get_password",
            side_effect=[account.token, account.token, None],
        ) as mock_get, patch(
            "supa_cc.keychain.keyring.delete_password"
        ) as mock_delete:
            manager.save_account(account)
            assert manager.get_account(account.name) == account
            manager.delete_account(account.name)
            assert manager.get_account(account.name) is None

        mock_set.assert_called_once_with(service, account.name, account.token)
        assert mock_get.call_args_list == [
            ((service, account.name),),
            ((service, account.name),),
            ((service, account.name),),
        ]
        mock_delete.assert_called_once_with(service, account.name)

    def test_custom_service_is_used_for_add_rollback(self, tmp_path):
        service = "supa.cc.tests.unit-add-rollback"
        old_token = fake_pat("old")
        account = Account(name="custom", token=fake_pat("new"))
        index_path = tmp_path / "accounts.json"
        index_path.write_text('{"accounts": ["custom"]}', encoding="utf-8")
        manager = KeychainManager(index_path=index_path, service=service)

        with patch("supa_cc.keychain.keyring.set_password") as mock_set, patch(
            "supa_cc.keychain.keyring.get_password",
            side_effect=[old_token, account.token, old_token],
        ) as mock_get, patch.object(
            manager, "_write_index_locked", side_effect=OSError("write failed")
        ):
            with pytest.raises(OSError, match="write failed"):
                manager.add_account(account)

        assert mock_set.call_args_list == [
            ((service, account.name, account.token),),
            ((service, account.name, old_token),),
        ]
        assert mock_get.call_args_list == [
            ((service, account.name),),
            ((service, account.name),),
            ((service, account.name),),
        ]

    def test_custom_service_is_used_for_remove_rollback(self, tmp_path):
        service = "supa.cc.tests.unit-remove-rollback"
        old_token = fake_pat("old")
        index_path = tmp_path / "accounts.json"
        index_path.write_text('{"accounts": ["custom"]}', encoding="utf-8")
        manager = KeychainManager(index_path=index_path, service=service)

        with patch("supa_cc.keychain.keyring.set_password") as mock_set, patch(
            "supa_cc.keychain.keyring.get_password",
            side_effect=[old_token, old_token],
        ) as mock_get, patch(
            "supa_cc.keychain.keyring.delete_password"
        ) as mock_delete, patch.object(
            manager, "_write_index_locked", side_effect=OSError("write failed")
        ):
            with pytest.raises(OSError, match="write failed"):
                manager.remove_account("custom")

        mock_delete.assert_called_once_with(service, "custom")
        mock_set.assert_called_once_with(service, "custom", old_token)
        assert mock_get.call_args_list == [
            ((service, "custom"),),
            ((service, "custom"),),
        ]

    def test_save_account_uses_keyring_and_seeds_cache(self, tmp_path):
        manager = KeychainManager(index_path=tmp_path / "accounts.json")
        manager.update_index([])
        account = Account(name="test", token=fake_pat("test123"))

        with patch("supa_cc.keychain.keyring.set_password") as mock_set, patch(
            "supa_cc.keychain.keyring.get_password", return_value=account.token
        ) as mock_get:
            manager.save_account(account)
            loaded = manager.get_account("test")

        mock_set.assert_called_once_with(KEYCHAIN_SERVICE, "test", fake_pat("test123"))
        mock_get.assert_called_once_with(KEYCHAIN_SERVICE, "test")
        assert loaded == account

    def test_save_account_verifies_round_trip_with_constant_time_compare(self, tmp_path):
        manager = KeychainManager(index_path=tmp_path / "accounts.json")
        manager.update_index([])
        account = Account(name="test", token=fake_pat("test123"))

        with patch("supa_cc.keychain.keyring.set_password"), patch(
            "supa_cc.keychain.keyring.get_password", return_value=account.token
        ), patch(
            "supa_cc.keychain.hmac.compare_digest", wraps=hmac.compare_digest
        ) as compare_digest:
            manager.save_account(account)

        compare_digest.assert_called_once_with(account.token, account.token)

    def test_save_account_rejects_round_trip_mismatch_without_exposing_token(self, tmp_path):
        manager = KeychainManager(index_path=tmp_path / "accounts.json")
        manager.update_index([])
        account = Account(name="test", token=fake_pat("expected"))

        with patch("supa_cc.keychain.keyring.set_password"), patch(
            "supa_cc.keychain.keyring.get_password", return_value=fake_pat("other")
        ):
            with pytest.raises(KeychainReadError) as raised:
                manager.save_account(account)

        assert account.token not in str(raised.value)
        assert account.token not in repr(raised.value)

    @pytest.mark.parametrize(
        "failure",
        [KeyringLocked("locked"), PermissionError("sensitive permission detail")],
        ids=["locked", "permission-error"],
    )
    def test_get_account_maps_permission_failures_to_domain_error(
        self, tmp_path, failure
    ):
        manager = KeychainManager(index_path=tmp_path / "accounts.json")
        manager.update_index([])

        with patch("supa_cc.keychain.keyring.get_password", side_effect=failure):
            with pytest.raises(KeychainPermissionDeniedError) as raised:
                manager.get_account("test")

        assert "sensitive" not in str(raised.value)
        assert "locked" not in str(raised.value)

    def test_get_account_maps_other_keyring_errors_to_read_failure(self, tmp_path):
        manager = KeychainManager(index_path=tmp_path / "accounts.json")
        manager.update_index([])

        with patch(
            "supa_cc.keychain.keyring.get_password",
            side_effect=KeyringError("sensitive backend detail"),
        ):
            with pytest.raises(KeychainReadError) as raised:
                manager.get_account("test")

        assert "sensitive" not in str(raised.value)

    def test_get_account_reads_keyring_once_then_uses_cache(self, tmp_path):
        manager = KeychainManager(index_path=tmp_path / "accounts.json")
        manager.update_index([])

        with patch(
            "supa_cc.keychain.keyring.get_password", return_value=fake_pat("test123")
        ) as mock_get:
            first = manager.get_account("test")
            second = manager.get_account("test")

        assert first == Account(name="test", token=fake_pat("test123"))
        assert second == first
        mock_get.assert_called_once_with(KEYCHAIN_SERVICE, "test")

    def test_get_account_does_not_require_local_index_access(self, tmp_path):
        blocked_parent = tmp_path / "blocked"
        blocked_parent.write_text("not a directory", encoding="utf-8")
        manager = KeychainManager(index_path=blocked_parent / "accounts.json")

        with patch(
            "supa_cc.keychain.keyring.get_password",
            return_value=fake_pat("test123"),
        ) as mock_get:
            account = manager.get_account("test")

        assert account == Account(name="test", token=fake_pat("test123"))
        mock_get.assert_called_once_with(KEYCHAIN_SERVICE, "test")

    def test_get_account_returns_none_when_keyring_has_no_token(self, tmp_path):
        manager = KeychainManager(index_path=tmp_path / "accounts.json")
        manager.update_index([])

        with patch("supa_cc.keychain.keyring.get_password", return_value=None) as mock_get:
            account = manager.get_account("nonexistent")

        assert account is None
        mock_get.assert_called_once_with(KEYCHAIN_SERVICE, "nonexistent")

    def test_get_account_ignores_legacy_service_when_v2_token_is_missing(self, tmp_path):
        legacy_service = "supa.cc.supabase.accounts"
        legacy_token = fake_pat("legacy-only")
        manager = KeychainManager(index_path=tmp_path / "accounts.json")
        manager.update_index([])

        def get_password(service, name):
            assert name == "legacy-only"
            if service == legacy_service:
                return legacy_token
            assert service == KEYCHAIN_SERVICE
            return None

        with patch(
            "supa_cc.keychain.keyring.get_password", side_effect=get_password
        ) as mock_get, patch(
            "supa_cc.keychain.keyring.set_password"
        ) as mock_set, patch(
            "supa_cc.keychain.keyring.delete_password"
        ) as mock_delete:
            assert manager.get_account("legacy-only") is None

        mock_get.assert_called_once_with(KEYCHAIN_SERVICE, "legacy-only")
        mock_set.assert_not_called()
        mock_delete.assert_not_called()

    def test_get_account_does_not_cache_missing_keyring_tokens(self, tmp_path):
        manager = KeychainManager(index_path=tmp_path / "accounts.json")
        manager.update_index([])

        with patch("supa_cc.keychain.keyring.get_password", return_value=None) as mock_get:
            assert manager.get_account("nonexistent") is None
            assert manager.get_account("nonexistent") is None

        assert mock_get.call_count == 2
        mock_get.assert_called_with(KEYCHAIN_SERVICE, "nonexistent")

    def test_get_account_refreshes_positive_cache_after_ttl(self, tmp_path):
        now = [100.0]
        manager = KeychainManager(
            index_path=tmp_path / "accounts.json",
            cache_ttl_seconds=1.0,
            clock=lambda: now[0],
        )
        manager.update_index([])

        with patch(
            "supa_cc.keychain.keyring.get_password",
            side_effect=[fake_pat("old_token"), fake_pat("new_token")],
        ) as mock_get:
            first = manager.get_account("work")
            now[0] = 100.5
            cached = manager.get_account("work")
            now[0] = 101.1
            refreshed = manager.get_account("work")

        assert first == Account(name="work", token=fake_pat("old_token"))
        assert cached == first
        assert refreshed == Account(name="work", token=fake_pat("new_token"))
        assert mock_get.call_count == 2

    def test_save_account_clears_cached_missing_token(self, tmp_path):
        manager = KeychainManager(index_path=tmp_path / "accounts.json")
        manager.update_index([])
        account = Account(name="saved", token=fake_pat("saved"))

        with patch(
            "supa_cc.keychain.keyring.get_password",
            side_effect=[None, account.token],
        ), patch(
            "supa_cc.keychain.keyring.set_password"
        ) as mock_set:
            assert manager.get_account("saved") is None
            manager.save_account(account)
            assert manager.get_account("saved") == account

        mock_set.assert_called_once_with(KEYCHAIN_SERVICE, "saved", fake_pat("saved"))

    def test_delete_account_invalidates_cached_token_before_deleting(self, tmp_path):
        manager = KeychainManager(index_path=tmp_path / "accounts.json")
        manager.update_index([])

        with patch(
            "supa_cc.keychain.keyring.get_password", return_value=fake_pat("test123")
        ) as mock_get, patch("supa_cc.keychain.keyring.delete_password") as mock_delete:
            assert manager.get_account("test") is not None
            manager.delete_account("test")
            mock_get.return_value = None
            assert manager.get_account("test") is None

        mock_delete.assert_called_once_with(KEYCHAIN_SERVICE, "test")
        assert mock_get.call_count == 2

    def test_delete_account_ignores_only_missing_item_error(self, tmp_path):
        manager = KeychainManager(index_path=tmp_path / "accounts.json")
        manager.update_index([])
        error = PasswordDeleteError(
            "Can't delete password in keychain: (-25300, 'Item not found')"
        )

        with patch("supa_cc.keychain.keyring.delete_password", side_effect=error):
            manager.delete_account("missing")

    def test_delete_account_ignores_missing_item_status_code_only(self, tmp_path):
        manager = KeychainManager(index_path=tmp_path / "accounts.json")
        manager.update_index([])

        with patch(
            "supa_cc.keychain.keyring.delete_password",
            side_effect=PasswordDeleteError("-25300"),
        ):
            manager.delete_account("missing")

    def test_delete_account_ignores_missing_item_wording_only(self, tmp_path):
        manager = KeychainManager(index_path=tmp_path / "accounts.json")
        manager.update_index([])

        with patch(
            "supa_cc.keychain.keyring.delete_password",
            side_effect=PasswordDeleteError("The item could not be found"),
        ):
            manager.delete_account("missing")

    @pytest.mark.parametrize(
        "failure",
        [
            PasswordDeleteError(
                "Can't delete password in keychain: permission denied"
            ),
            KeyringLocked("locked backend detail"),
        ],
        ids=["permission-message", "locked"],
    )
    def test_delete_account_maps_permission_error(self, tmp_path, failure):
        manager = KeychainManager(index_path=tmp_path / "accounts.json")
        manager.update_index([])

        with patch("supa_cc.keychain.keyring.delete_password", side_effect=failure):
            with pytest.raises(KeychainPermissionDeniedError) as raised:
                manager.delete_account("test")

        assert "backend" not in str(raised.value)
        assert "permission denied" not in str(raised.value).lower()

    def test_delete_account_maps_other_keyring_error_to_read_failure(self, tmp_path):
        manager = KeychainManager(index_path=tmp_path / "accounts.json")
        manager.update_index([])

        with patch(
            "supa_cc.keychain.keyring.delete_password",
            side_effect=PasswordDeleteError("sensitive backend detail"),
        ):
            with pytest.raises(KeychainReadError) as raised:
                manager.delete_account("test")

        assert "sensitive" not in str(raised.value)

    def test_get_account_does_not_rewrite_tokens(self, tmp_path):
        index_path = tmp_path / "accounts.json"
        index_path.write_text(json.dumps({"accounts": ["a1"]}), encoding="utf-8")
        manager = KeychainManager(index_path=index_path)

        with patch(
            "supa_cc.keychain.keyring.get_password", return_value=fake_pat("a1")
        ), patch(
            "supa_cc.keychain.keyring.set_password"
        ) as mock_set, patch(
            "supa_cc.keychain.keyring.delete_password"
        ) as mock_delete:
            account = manager.get_account("a1")

        assert account == Account(name="a1", token=fake_pat("a1"))
        mock_set.assert_not_called()
        mock_delete.assert_not_called()

    def test_module_has_no_security_command_helpers(self):
        for name in (
            "_security_run",
            "_security_get_password",
            "_security_set_password",
            "_security_delete_password",
            "KeychainError",
        ):
            assert not hasattr(keychain, name)

    def test_public_token_operations_use_v2_service_only(self, tmp_path):
        v2_service = "supa.cc.supabase.accounts.v2"
        old_service = "supa.cc.supabase.accounts"
        manager = KeychainManager(index_path=tmp_path / "accounts.json")
        manager.update_index([])
        account = Account(name="saved", token=fake_pat("saved"))

        def get_password(service, name):
            assert service == v2_service
            return fake_pat(name)

        with patch("supa_cc.keychain.keyring.set_password") as mock_set, patch(
            "supa_cc.keychain.keyring.get_password", side_effect=get_password
        ) as mock_get, patch(
            "supa_cc.keychain.keyring.delete_password"
        ) as mock_delete, patch("subprocess.run") as mock_run:
            manager.save_account(account)
            assert manager.get_account("loaded") == Account(
                name="loaded", token=fake_pat("loaded")
            )
            manager.delete_account("loaded")

        assert KEYCHAIN_SERVICE == v2_service
        mock_set.assert_called_once_with(v2_service, "saved", fake_pat("saved"))
        assert mock_get.call_args_list == [
            ((v2_service, "saved"),),
            ((v2_service, "loaded"),),
        ]
        mock_delete.assert_called_once_with(v2_service, "loaded")
        for mock in (mock_set, mock_get, mock_delete):
            assert all(call.args[0] != old_service for call in mock.call_args_list)
        mock_run.assert_not_called()

    def test_list_accounts_with_accounts(self, tmp_path):
        index_path = tmp_path / "accounts.json"
        index_path.write_text(
            json.dumps({"accounts": ["account1", "account2"]}), encoding="utf-8"
        )
        manager = KeychainManager(index_path=index_path)

        accounts = manager.list_accounts()

        assert accounts == [Account(name="account1", token=""), Account(name="account2", token="")]

    def test_list_accounts_does_not_fetch_tokens(self, tmp_path):
        index_path = tmp_path / "accounts.json"
        index_path.write_text(
            json.dumps({"accounts": ["account1", "account2"]}), encoding="utf-8"
        )
        manager = KeychainManager(index_path=index_path)

        with patch("supa_cc.keychain.keyring.get_password") as mock_get:
            accounts = manager.list_accounts()

        assert [account.name for account in accounts] == ["account1", "account2"]
        assert [account.token for account in accounts] == ["", ""]
        mock_get.assert_not_called()

    def test_list_accounts_persists_empty_index_when_missing(self, tmp_path):
        index_path = tmp_path / "accounts.json"
        manager = KeychainManager(index_path=index_path)

        assert manager.list_accounts() == []
        assert manager.list_accounts() == []
        assert index_path.exists()

    def test_list_accounts_rejects_invalid_json_without_overwriting_it(self, tmp_path):
        index_path = tmp_path / "accounts.json"
        index_path.write_text("not-json", encoding="utf-8")
        manager = KeychainManager(index_path=index_path)

        with pytest.raises(keychain.AccountIndexInvalidError):
            manager.list_accounts()

        assert index_path.read_text(encoding="utf-8") == "not-json"

    def test_list_accounts_maps_index_read_oserror_without_overwriting(self, tmp_path):
        index_path = tmp_path / "accounts.json"
        original = '{"accounts": ["work"]}'
        index_path.write_text(original, encoding="utf-8")
        manager = KeychainManager(index_path=index_path)

        with patch.object(
            keychain.Path,
            "read_text",
            side_effect=PermissionError("sensitive path"),
        ):
            with pytest.raises(keychain.AccountIndexReadError) as raised:
                manager.list_accounts()

        assert "sensitive" not in str(raised.value)
        assert index_path.read_text(encoding="utf-8") == original

    def test_list_accounts_rejects_invalid_names_without_overwriting(self, tmp_path):
        index_path = tmp_path / "accounts.json"
        original = json.dumps({"accounts": ["work", "bad name"]})
        index_path.write_text(original, encoding="utf-8")
        manager = KeychainManager(index_path=index_path)

        with pytest.raises(keychain.AccountIndexInvalidError):
            manager.list_accounts()

        assert index_path.read_text(encoding="utf-8") == original

    def test_update_index_rejects_invalid_names_and_preserves_previous(self, tmp_path):
        index_path = tmp_path / "accounts.json"
        original = json.dumps({"accounts": ["work"]})
        index_path.write_text(original, encoding="utf-8")
        manager = KeychainManager(index_path=index_path)

        with pytest.raises(keychain.AccountIndexInvalidError):
            manager.update_index(["work", "bad name"])

        assert index_path.read_text(encoding="utf-8") == original

    def test_update_index_never_overwrites_existing_invalid_json(self, tmp_path):
        index_path = tmp_path / "accounts.json"
        index_path.write_text("not-json", encoding="utf-8")
        manager = KeychainManager(index_path=index_path)

        with pytest.raises(keychain.AccountIndexInvalidError):
            manager.update_index(["work"])

        assert index_path.read_text(encoding="utf-8") == "not-json"

    def test_update_index_deduplicates_names_and_restricts_permissions(self, tmp_path):
        index_path = tmp_path / "accounts.json"
        manager = KeychainManager(index_path=index_path)

        manager.update_index(["account1", "account2", "account1"])

        assert [account.name for account in manager.list_accounts()] == ["account1", "account2"]
        assert index_path.stat().st_mode & 0o777 == 0o600

    def test_update_index_restricts_permissions_on_existing_file(self, tmp_path):
        index_path = tmp_path / "accounts.json"
        index_path.write_text('{"accounts": ["old"]}', encoding="utf-8")
        index_path.chmod(0o644)
        manager = KeychainManager(index_path=index_path)

        manager.update_index(["new"])

        assert index_path.stat().st_mode & 0o777 == 0o600
        assert [account.name for account in manager.list_accounts()] == ["new"]

    def test_update_index_preserves_previous_file_when_write_fails(self, tmp_path):
        index_path = tmp_path / "accounts.json"
        original = '{"accounts": ["old"]}'
        index_path.write_text(original, encoding="utf-8")
        manager = KeychainManager(index_path=index_path)

        with patch(
            "supa_cc.keychain.os.fdopen",
            side_effect=OSError("write failed"),
        ):
            with pytest.raises(OSError, match="write failed"):
                manager.update_index(["new"])

        assert index_path.read_text(encoding="utf-8") == original
        leftovers = [
            path
            for path in tmp_path.glob(".accounts.json.*")
            if path != manager.index_lock_path
        ]
        assert leftovers == []
