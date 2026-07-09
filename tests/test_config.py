import subprocess
from unittest.mock import patch, MagicMock
from supa_cc.config import SupabaseConfig
from supa_cc.models import Account

from helpers import fake_pat


class TestSupabaseConfig:
    def test_is_installed_true(self):
        config = SupabaseConfig()
        with patch('supa_cc.config.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            assert config.is_installed() is True

    def test_is_installed_false(self):
        config = SupabaseConfig()
        with patch('supa_cc.config.subprocess.run', side_effect=FileNotFoundError()):
            assert config.is_installed() is False

    def test_set_active_account_success(self):
        config = SupabaseConfig()
        account = Account(name="test", token=fake_pat("test123"))

        with patch('supa_cc.config.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            assert config.set_active_account(account) is True

    def test_set_active_account_failure(self):
        config = SupabaseConfig()
        account = Account(name="test", token=fake_pat("test123"))

        with patch('supa_cc.config.subprocess.run', side_effect=subprocess.CalledProcessError(1, "supabase")):
            assert config.set_active_account(account) is False

    def test_set_active_account_when_cli_missing(self):
        config = SupabaseConfig()
        account = Account(name="test", token=fake_pat("test123"))

        with patch('supa_cc.config.subprocess.run', side_effect=FileNotFoundError()):
            assert config.set_active_account(account) is False
