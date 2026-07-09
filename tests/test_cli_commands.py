from unittest.mock import MagicMock, patch

from click.testing import CliRunner

import supa_cc
from supa_cc.__main__ import _check_for_updates, main
from supa_cc.models import Account

from helpers import fake_pat


class TestCLICommands:
    def test_version_shows_version_and_update_status(self):
        runner = CliRunner()
        with patch("supa_cc.__main__._check_for_updates", return_value="up-to-date"):
            result = runner.invoke(main, ["version"])
        assert result.exit_code == 0
        assert f"Supa.cc v{supa_cc.__version__}" in result.output
        assert "up-to-date" in result.output

    def test_version_command_reads_package_version(self, monkeypatch):
        runner = CliRunner()
        monkeypatch.setattr(supa_cc, "__version__", "9.9.9")
        with patch("supa_cc.__main__._check_for_updates", return_value="up-to-date"):
            result = runner.invoke(main, ["version"])
        assert result.exit_code == 0
        assert "Supa.cc v9.9.9" in result.output

    def test_update_check_mentions_homebrew_for_non_git_installs(self):
        with patch("os.path.isdir", return_value=False):
            message = _check_for_updates()

        assert "brew upgrade supa-cc" in message
        assert "pipx upgrade supa.cc" in message

    def test_list_empty_accounts(self):
        runner = CliRunner()
        with patch("supa_cc.accounts.AccountManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.list.return_value = []
            mock_manager_class.return_value = mock_manager
            result = runner.invoke(main, ["list"])
        assert result.exit_code == 0
        assert "Nenhuma conta cadastrada." in result.output

    def test_list_shows_account_names(self):
        runner = CliRunner()
        with patch("supa_cc.accounts.AccountManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.list.return_value = [
                Account(name="personal", token=""),
                Account(name="work", token=""),
            ]
            mock_manager_class.return_value = mock_manager
            result = runner.invoke(main, ["list"])
        assert result.exit_code == 0
        assert "personal" in result.output
        assert "work" in result.output

    def test_add_valid_account(self):
        runner = CliRunner()
        with patch("supa_cc.accounts.AccountManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager_class.return_value = mock_manager
            result = runner.invoke(main, ["add", "work", "--token", fake_pat()])
        assert result.exit_code == 0
        assert "Conta 'work' adicionada." in result.output
        mock_manager.add.assert_called_once_with("work", fake_pat())

    def test_add_invalid_token_shows_sanitized_error(self):
        runner = CliRunner()
        with patch("supa_cc.accounts.AccountManager") as mock_manager_class:
            mock_manager = MagicMock()
            token_prefix = "sbp" + "_"
            mock_manager.add.side_effect = ValueError(f"Token inválido. Deve começar com '{token_prefix}'")
            mock_manager_class.return_value = mock_manager
            result = runner.invoke(main, ["add", "work", "--token", "bad"])
        assert result.exit_code == 0
        assert "Erro de validação. Verifique os dados fornecidos." in result.output

    def test_add_invalid_name_shows_error(self):
        runner = CliRunner()
        with patch("supa_cc.accounts.AccountManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.add.side_effect = ValueError("Nome da conta deve ter entre 1 e 50 caracteres.")
            mock_manager_class.return_value = mock_manager
            result = runner.invoke(main, ["add", "", "--token", fake_pat()])
        assert result.exit_code == 0
        assert "Nome da conta deve ter entre 1 e 50 caracteres." in result.output

    def test_switch_nonexistent_account_shows_failure(self):
        runner = CliRunner()
        with patch("supa_cc.accounts.AccountManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.set_active.return_value = False
            mock_manager_class.return_value = mock_manager
            result = runner.invoke(main, ["switch", "missing"])
        assert result.exit_code == 0
        assert "Falha ao ativar conta 'missing'." in result.output

    def test_switch_valid_account(self):
        runner = CliRunner()
        with patch("supa_cc.accounts.AccountManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.set_active.return_value = True
            mock_manager_class.return_value = mock_manager
            result = runner.invoke(main, ["switch", "work"])
        assert result.exit_code == 0
        assert "Conta 'work' ativada." in result.output

    def test_remove_prompts_for_confirmation(self):
        runner = CliRunner()
        with patch("supa_cc.accounts.AccountManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager_class.return_value = mock_manager
            result = runner.invoke(main, ["remove", "work"], input="y\n")
        assert result.exit_code == 0
        assert "Conta 'work' removida." in result.output
        mock_manager.remove.assert_called_once_with("work")

    def test_remove_with_yes_flag_skips_confirmation(self):
        runner = CliRunner()
        with patch("supa_cc.accounts.AccountManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager_class.return_value = mock_manager
            result = runner.invoke(main, ["remove", "work", "--yes"])
        assert result.exit_code == 0
        assert "Conta 'work' removida." in result.output
        mock_manager.remove.assert_called_once_with("work")

    def test_main_without_command_launches_tui(self):
        runner = CliRunner()
        with patch("supa_cc.__main__.run_tui") as mock_run_tui:
            result = runner.invoke(main, [])
        assert result.exit_code == 0
        mock_run_tui.assert_called_once()
