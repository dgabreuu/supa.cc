import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

import supa_cc
from supa_cc.__main__ import _check_for_updates, main
from supa_cc.auth import (
    AccountIndexInvalidError,
    AccountTransactionError,
    AuthFailureCode,
    AuthResult,
    CommandResult,
    InvalidAccessTokenError,
    InvalidAccountNameError,
    KeychainPermissionDeniedError,
    CredentialAccessError,
)
from supa_cc.diagnostics import DoctorReport
from supa_cc.models import Account

from helpers import click_runner, fake_pat


class TestCLICommands:
    def test_help_uses_english_product_text(self):
        result = CliRunner().invoke(main, ["--help"])

        assert result.exit_code == 0
        assert "Supabase account manager" in result.output
        assert "Add a new account." in result.output
        assert "Adicionar" not in result.output

    def test_help_import_path_does_not_load_tui_or_keyring(self):
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sys; import supa_cc.__main__; "
                    "print(','.join(sorted(name for name in sys.modules "
                    "if name == 'questionary' or name == 'keyring' "
                    "or name.startswith('supa_cc.ui') or name == 'supa_cc.tui')))"
                ),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        assert completed.stdout.strip() == ""

    def test_version_shows_version_and_deterministic_update_guidance(self):
        runner = CliRunner()
        with patch("subprocess.run", side_effect=AssertionError("no subprocess")):
            result = runner.invoke(main, ["version"])
        assert result.exit_code == 0
        assert f"Supa.cc v{supa_cc.__version__}" in result.output
        assert "Update:" in result.output

    def test_version_command_reads_package_version(self, monkeypatch):
        runner = CliRunner()
        monkeypatch.setattr(supa_cc, "__version__", "9.9.9")
        result = runner.invoke(main, ["version"])
        assert result.exit_code == 0
        assert "Supa.cc v9.9.9" in result.output

    def test_update_check_mentions_homebrew_for_non_git_installs(self):
        from supa_cc.environment import detect_environment

        with patch(
            "supa_cc.environment.detect_environment",
            return_value=detect_environment(system_name="Darwin"),
        ):
            message = _check_for_updates()

        assert "brew upgrade supa-cc" in message
        assert 'pipx install --force "git+https://github.com/dgabreuu/supa.cc.git"' in message
        assert "pipx upgrade supa.cc" not in message

    def test_update_check_uses_linux_guidance(self, monkeypatch):
        from supa_cc.environment import detect_environment

        monkeypatch.setattr(
            "supa_cc.environment.detect_environment",
            lambda: detect_environment(system_name="Linux", os_release="ID=arch\n"),
        )
        message = _check_for_updates()

        assert 'pipx install --force "git+https://github.com/dgabreuu/supa.cc.git"' in message
        assert "pipx upgrade supa.cc" not in message
        assert "brew" not in message

    def test_update_check_never_invokes_subprocess(self):
        with patch("subprocess.run", side_effect=AssertionError("no subprocess")):
            message = _check_for_updates()

        assert "Update:" in message

    def test_list_empty_accounts(self):
        runner = CliRunner()
        with patch("supa_cc.accounts.AccountManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.list.return_value = []
            mock_manager_class.return_value = mock_manager
            result = runner.invoke(main, ["list"])
        assert result.exit_code == 0
        assert "No accounts registered." in result.output

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
        token = fake_pat("prompt_only")
        runner = CliRunner()
        with patch("supa_cc.accounts.AccountManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager_class.return_value = mock_manager
            result = runner.invoke(main, ["add", "work"], input=f"{token}\n")
        assert result.exit_code == 0
        assert "Account 'work' added." in result.output
        assert token not in result.output
        mock_manager.add.assert_called_once_with("work", token)

    def test_add_rejects_public_token_option(self):
        token = fake_pat("must_not_be_argv")
        runner = CliRunner()

        result = runner.invoke(main, ["add", "work", "--token", token])

        assert result.exit_code == 2
        assert "No such option" in result.output
        assert "--token" in result.output
        assert token not in result.output

    def test_add_invalid_token_shows_sanitized_error(self):
        runner = CliRunner()
        with patch("supa_cc.accounts.AccountManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.add.side_effect = InvalidAccessTokenError("private")
            mock_manager_class.return_value = mock_manager
            result = runner.invoke(main, ["add", "work"], input="bad\n")
        assert result.exit_code != 0
        assert "Invalid token: provide a Supabase PAT in valid sbp_ format." in result.output

    def test_add_invalid_name_shows_error(self):
        runner = CliRunner()
        with patch("supa_cc.accounts.AccountManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.add.side_effect = InvalidAccountNameError(
                "Account name must contain between 1 and 50 characters."
            )
            mock_manager_class.return_value = mock_manager
            result = runner.invoke(main, ["add", ""], input=f"{fake_pat()}\n")
        assert result.exit_code != 0
        assert "Invalid account name: use 1 to 50 characters" in result.output

    def test_add_keychain_failure_is_nonzero_and_sanitized(self):
        token = fake_pat("keychain_failure")
        runner = CliRunner()
        with patch("supa_cc.accounts.AccountManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.add.side_effect = KeychainPermissionDeniedError(
                f"storage failed {token}"
            )
            mock_manager_class.return_value = mock_manager
            result = runner.invoke(main, ["add", "work"], input=f"{token}\n")

        assert result.exit_code != 0
        assert token not in result.output
        assert "Keychain access was not authorized." in result.output

    def test_list_maps_index_failure_without_traceback(self):
        runner = CliRunner()
        with patch("supa_cc.accounts.AccountManager") as manager_class:
            manager_class.return_value.list.side_effect = AccountIndexInvalidError(
                "private index detail"
            )
            result = runner.invoke(main, ["list"])

        assert result.exit_code != 0
        assert "The local account index is invalid." in result.output
        assert "private index detail" not in result.output

    def test_remove_maps_transaction_failure_without_traceback(self):
        runner = CliRunner()
        with patch("supa_cc.accounts.AccountManager") as manager_class:
            manager_class.return_value.remove.side_effect = AccountTransactionError(
                "private transaction detail"
            )
            result = runner.invoke(main, ["remove", "work", "--yes"])

        assert result.exit_code != 0
        assert "could not be completed safely" in result.output
        assert "private transaction detail" not in result.output

    @pytest.mark.parametrize(
        "command,input_text",
        [
            (["add", "work"], f"{fake_pat('blocked_add')}\n"),
            (["list"], None),
            (["switch", "work"], None),
            (["remove", "work", "--yes"], None),
        ],
        ids=["add", "list", "switch", "remove"],
    )
    def test_commands_sanitize_account_manager_construction_failures(
        self, command, input_text
    ):
        runner = CliRunner()
        with patch("supa_cc.accounts.AccountManager") as manager_class:
            manager_class.side_effect = CredentialAccessError("private backend detail")
            result = runner.invoke(main, command, input=input_text)

        assert result.exit_code != 0
        assert "Unable to access the credential-store credential." in result.output
        assert "private backend detail" not in result.output

    def test_add_sanitizes_typed_credential_store_failure(self):
        runner = CliRunner()
        with patch("supa_cc.accounts.AccountManager") as manager_class:
            manager_class.return_value.add.side_effect = CredentialAccessError(
                "private backend detail"
            )
            result = runner.invoke(
                main, ["add", "work"], input=f"{fake_pat('blocked_add')}\n"
            )

        assert result.exit_code != 0
        assert "Unable to access the credential-store credential." in result.output
        assert "private backend detail" not in result.output

    @pytest.mark.parametrize(
        "token_like_name",
        [
            fake_pat("remove_cli_namespace"),
            "acct_" + fake_pat("embedded_cli"),
        ],
    )
    def test_remove_rejects_pat_like_name_without_echoing_it_or_touching_keychain(
        self, token_like_name
    ):
        runner = CliRunner()

        result = runner.invoke(main, ["remove", token_like_name, "--yes"])

        assert result.exit_code != 0
        assert token_like_name not in result.output
        assert "Invalid account name" in result.output

    def test_switch_nonexistent_account_shows_failure(self):
        runner = CliRunner()
        with patch("supa_cc.accounts.AccountManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.set_active.return_value = AuthResult.failure(
                AuthFailureCode.TOKEN_MISSING,
                "Token not found for the selected account.",
                exit_code=7,
            )
            mock_manager_class.return_value = mock_manager
            result = runner.invoke(main, ["switch", "missing"])
        assert result.exit_code == 7
        assert "Token not found for the selected account." in result.output

    def test_switch_valid_account(self):
        runner = CliRunner()
        with patch("supa_cc.accounts.AccountManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.set_active.return_value = AuthResult.success(
                "Account 'work' activated and native session synchronized."
            )
            mock_manager_class.return_value = mock_manager
            result = runner.invoke(main, ["switch", "work"])
        assert result.exit_code == 0
        assert "Account 'work' activated and native session synchronized." in result.output
        assert "supa.cc run" not in result.output
        mock_manager.set_active.assert_called_once_with("work")

    @pytest.mark.parametrize(
        "code,message",
        [
            (AuthFailureCode.NATIVE_LOGIN_FAILED, "Native login failed."),
            (AuthFailureCode.NATIVE_VERIFICATION_FAILED, "Native session verification failed."),
            (AuthFailureCode.PLAINTEXT_FALLBACK_BLOCKED, "Fallback plaintext bloqueado."),
            (AuthFailureCode.SYNC_ROLLBACK_FAILED, "Failed to restore the previous session."),
        ],
    )
    def test_switch_preserves_native_sync_failure_category(self, code, message):
        runner = CliRunner()
        with patch("supa_cc.accounts.AccountManager") as manager_class:
            manager_class.return_value.set_active.return_value = AuthResult.failure(
                code, message, exit_code=9
            )
            result = runner.invoke(main, ["switch", "work"])

        assert result.exit_code == 9
        assert message in result.output
        manager_class.return_value.set_active.assert_called_once_with("work")

    def test_run_requires_command(self):
        runner = CliRunner()

        result = runner.invoke(main, ["run", "--"])

        assert result.exit_code != 0
        assert "Missing argument" in result.output

    def test_run_accepts_unknown_supabase_options_and_emits_sanitized_streams(self):
        runner = click_runner()
        command_result = CommandResult.success(
            stdout="safe stdout\n", stderr="safe stderr\n"
        )
        with patch("supa_cc.accounts.AccountManager") as manager_class:
            manager = MagicMock()
            def stream(_arguments, stdout_sink, stderr_sink):
                stdout_sink("safe stdout\n")
                stderr_sink("safe stderr\n")
                return command_result

            manager.run_active.side_effect = stream
            manager_class.return_value = manager

            result = runner.invoke(
                main,
                ["run", "--", "projects", "list", "--profile", "work"],
            )

        assert result.exit_code == 0
        assert result.stdout == "safe stdout\n"
        assert result.stderr == "safe stderr\n"
        assert manager.run_active.call_count == 1
        assert manager.run_active.call_args.args == (
            ["projects", "list", "--profile", "work"],
        )
        assert callable(manager.run_active.call_args.kwargs["stdout_sink"])
        assert callable(manager.run_active.call_args.kwargs["stderr_sink"])

    def test_run_propagates_normalized_failure_exit_and_message(self):
        runner = click_runner()
        command_result = CommandResult.failure(
            AuthFailureCode.TOKEN_REJECTED,
            "The token was rejected by the Supabase API.",
            exit_code=17,
            stdout="partial\n",
            stderr="401 Unauthorized [REDACTED]\n",
        )
        with patch("supa_cc.accounts.AccountManager") as manager_class:
            manager = MagicMock()
            manager.run_active.return_value = command_result
            manager_class.return_value = manager
            result = runner.invoke(main, ["run", "--", "projects", "list"])

        assert result.exit_code == 17
        assert result.stdout == ""
        assert "401 Unauthorized [REDACTED]" not in result.stderr
        assert "The token was rejected" in result.stderr

    def test_remove_prompts_for_confirmation(self):
        runner = CliRunner()
        with patch("supa_cc.accounts.AccountManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager_class.return_value = mock_manager
            result = runner.invoke(main, ["remove", "work"], input="y\n")
        assert result.exit_code == 0
        assert "Account 'work' removed." in result.output
        mock_manager.remove.assert_called_once_with("work")

    def test_remove_with_yes_flag_skips_confirmation(self):
        runner = CliRunner()
        with patch("supa_cc.accounts.AccountManager") as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager_class.return_value = mock_manager
            result = runner.invoke(main, ["remove", "work", "--yes"])
        assert result.exit_code == 0
        assert "Account 'work' removed." in result.output
        mock_manager.remove.assert_called_once_with("work")

    def test_doctor_default_renders_human_report(self):
        runner = CliRunner()
        report = DoctorReport(
            ok=True,
            exit_code=0,
            runtime={"launcher": "/safe/supa.cc"},
            supabase_cli={"path": "/safe/supabase", "version": "2.109.1", "provenance": "homebrew"},
            keychain_service="supa.cc.supabase.accounts.v2",
            keychain_backend="macOS",
            index={"path": "/safe/accounts.json", "state": "valid", "account_count": 1},
            active_account={"selected": True, "indexed": True},
            environment={"supabase_access_token_present": False},
            diagnostic_codes=[],
        )
        with patch("supa_cc.diagnostics.DiagnosticService") as service_class:
            service_class.return_value.run.return_value = report
            result = runner.invoke(main, ["doctor"])

        assert result.exit_code == 0
        assert "Supabase CLI" in result.output
        assert "/safe/supabase" in result.output
        service_class.return_value.run.assert_called_once_with(
            account=None, live=False
        )

    def test_doctor_json_and_live_failure_exit(self):
        runner = CliRunner()
        report = DoctorReport(
            ok=False,
            exit_code=11,
            runtime={},
            supabase_cli={},
            keychain_service="supa.cc.supabase.accounts.v2",
            keychain_backend="macOS",
            index={"state": "valid"},
            active_account={"selected": True, "indexed": True},
            environment={"supabase_access_token_present": False},
            diagnostic_codes=[AuthFailureCode.TOKEN_REJECTED.value],
            live_result=AuthResult.failure(
                AuthFailureCode.TOKEN_REJECTED,
                "O token foi rejeitado pela API da Supabase.",
                exit_code=11,
            ),
        )
        with patch("supa_cc.diagnostics.DiagnosticService") as service_class:
            service_class.return_value.run.return_value = report
            result = runner.invoke(
                main, ["doctor", "--json", "--account", "work", "--live"]
            )

        assert result.exit_code == 11
        assert '"token_rejected"' in result.output
        service_class.return_value.run.assert_called_once_with(
            account="work", live=True
        )

    def test_main_without_command_launches_tui(self):
        runner = CliRunner()
        with patch("supa_cc.__main__._run_tui", return_value=0) as mock_run_tui:
            result = runner.invoke(main, [])
        assert result.exit_code == 0
        mock_run_tui.assert_called_once()

    def test_main_without_command_propagates_tui_failure_exit(self):
        runner = CliRunner()
        with patch("supa_cc.__main__._run_tui", return_value=7):
            result = runner.invoke(main, [])

        assert result.exit_code == 7
