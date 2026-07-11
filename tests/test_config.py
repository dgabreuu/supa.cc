import os
import signal
import subprocess
from unittest.mock import Mock, patch

import pytest

from supa_cc.auth import AuthFailureCode, AuthResult
from supa_cc.config import SupabaseConfig
from supa_cc.models import Account

from helpers import fake_pat


def _process(returncode=0, stdout="", stderr=""):
    stdout_read, stdout_write = os.pipe()
    stderr_read, stderr_write = os.pipe()
    os.write(stdout_write, stdout.encode())
    os.write(stderr_write, stderr.encode())
    os.close(stdout_write)
    os.close(stderr_write)
    process = Mock()
    process.stdout = os.fdopen(stdout_read, "rb", buffering=0)
    process.stderr = os.fdopen(stderr_read, "rb", buffering=0)
    process.poll.return_value = returncode
    return process


def test_resolves_supabase_binary_to_real_path(tmp_path):
    binary = tmp_path / "bin" / "supabase-real"
    binary.parent.mkdir()
    binary.write_text("", encoding="utf-8")
    link = tmp_path / "supabase"
    link.symlink_to(binary)

    config = SupabaseConfig(binary_resolver=lambda _: str(link))

    assert config.supabase_cli == str(binary.resolve())
    assert config.is_installed() is True


def test_is_installed_is_false_when_binary_cannot_be_resolved():
    config = SupabaseConfig(binary_resolver=lambda _: None)

    assert config.is_installed() is False


def test_validate_access_token_uses_projects_list_and_copied_environment(tmp_path):
    token = fake_pat("env-only")
    binary = str(tmp_path / "real-supabase")
    config = SupabaseConfig(binary_resolver=lambda _: binary)
    account = Account(name="work", token=token)

    with patch.dict(
        "supa_cc.config.os.environ",
        {"PARENT_VALUE": "present"},
        clear=True,
    ), patch(
        "supa_cc.config.subprocess.Popen",
        return_value=_process(),
    ) as popen:
        result = config.validate_access_token(account)

    assert result.ok is True
    assert result.code is AuthFailureCode.NONE
    assert token not in result.message
    assert token not in repr(result)
    assert "SUPABASE_ACCESS_TOKEN" not in os.environ
    popen.assert_called_once_with(
        [os.path.realpath(binary), "projects", "list"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={"PARENT_VALUE": "present", "SUPABASE_ACCESS_TOKEN": token},
        bufsize=0,
        start_new_session=(os.name == "posix"),
    )
    assert "login" not in popen.call_args.args[0]
    assert token not in popen.call_args.args[0]


def test_validate_access_token_does_not_run_when_token_is_missing(tmp_path):
    config = SupabaseConfig(binary_resolver=lambda _: str(tmp_path / "supabase"))

    with patch("supa_cc.config.subprocess.Popen") as run:
        result = config.validate_access_token(Account(name="work", token=""))

    assert result.ok is False
    assert result.code is AuthFailureCode.TOKEN_MISSING
    run.assert_not_called()


def test_validate_access_token_does_not_run_when_cli_is_missing():
    config = SupabaseConfig(binary_resolver=lambda _: None)

    with patch("supa_cc.config.subprocess.Popen") as run:
        result = config.validate_access_token(
            Account(name="work", token=fake_pat("missing-cli"))
        )

    assert result.ok is False
    assert result.code is AuthFailureCode.CLI_NOT_FOUND
    run.assert_not_called()


@pytest.mark.parametrize(
    "output,expected",
    [
        ("401 Unauthorized: sbp_sensitive", AuthFailureCode.TOKEN_REJECTED),
        (
            "permission denied while decoding response; HTTP status 401 Unauthorized",
            AuthFailureCode.TOKEN_REJECTED,
        ),
        ("permission denied for internal code 4010", AuthFailureCode.ENVIRONMENT_BLOCKED),
        ("Access token not provided", AuthFailureCode.TOKEN_MISSING),
        ("lookup api.supabase.com: no such host", AuthFailureCode.NETWORK_FAILURE),
        ("operation not permitted", AuthFailureCode.ENVIRONMENT_BLOCKED),
        ('unknown command "projects"', AuthFailureCode.CLI_INCOMPATIBLE),
        ("API authentication failed", AuthFailureCode.API_AUTH_FAILED),
        ("profile mismatch", AuthFailureCode.PROFILE_MISMATCH),
        ("unexpected command failure", AuthFailureCode.COMMAND_FAILED),
    ],
)
def test_validate_access_token_classifies_cli_failures_without_echoing_output(
    tmp_path, output, expected
):
    config = SupabaseConfig(binary_resolver=lambda _: str(tmp_path / "supabase"))

    with patch(
        "supa_cc.config.subprocess.Popen",
        return_value=_process(returncode=7, stderr=output),
    ):
        result = config.validate_access_token(
            Account(name="work", token=fake_pat("classified"))
        )

    assert result.ok is False
    assert result.code is expected
    assert result.exit_code == 7
    assert output not in result.message
    assert "sbp_sensitive" not in result.message
    assert output not in repr(result)


@pytest.mark.parametrize(
    "failure,expected",
    [
        (FileNotFoundError("sensitive path"), AuthFailureCode.CLI_NOT_FOUND),
        (PermissionError("sensitive EPERM"), AuthFailureCode.ENVIRONMENT_BLOCKED),
        (OSError("sensitive os detail"), AuthFailureCode.COMMAND_FAILED),
    ],
    ids=["missing", "permission", "os-error"],
)
def test_validate_access_token_classifies_execution_failures_safely(
    tmp_path, failure, expected
):
    config = SupabaseConfig(binary_resolver=lambda _: str(tmp_path / "supabase"))

    with patch("supa_cc.config.subprocess.Popen", side_effect=failure):
        result = config.validate_access_token(
            Account(name="work", token=fake_pat("execution"))
        )

    assert result.ok is False
    assert result.code is expected
    assert "sensitive" not in result.message
    assert "sensitive" not in repr(result)


def test_validate_access_token_never_calls_native_keychain_repair(tmp_path):
    config = SupabaseConfig(binary_resolver=lambda _: str(tmp_path / "supabase"))

    with patch(
        "supa_cc.config.subprocess.Popen", return_value=_process()
    ) as run:
        result = config.validate_access_token(
            Account(name="work", token=fake_pat("no-repair"))
        )

    assert result.ok is True
    assert all("security" not in str(argument) for argument in run.call_args.args[0])


def test_execute_authenticated_passes_pat_only_in_copied_environment(tmp_path):
    token = fake_pat("command_env_only")
    binary = str(tmp_path / "supabase")
    config = SupabaseConfig(binary_resolver=lambda _: binary)

    with patch.dict(
        "supa_cc.config.os.environ", {"PARENT": "yes"}, clear=True
    ), patch(
        "supa_cc.config.subprocess.Popen",
        return_value=_process(stdout="project output\n"),
    ) as popen:
        result = config.execute_authenticated(
            Account(name="work", token=token),
            ["projects", "list", "--profile", "work"],
        )

    assert result.ok is True
    assert result.stdout == "project output\n"
    assert result.stderr == ""
    assert token not in repr(result)
    assert token not in popen.call_args.args[0]
    assert popen.call_args.args[0] == [
        os.path.realpath(binary),
        "projects",
        "list",
        "--profile",
        "work",
    ]
    assert popen.call_args.kwargs["env"] == {
        "PARENT": "yes",
        "SUPABASE_ACCESS_TOKEN": token,
    }
    assert "SUPABASE_ACCESS_TOKEN" not in os.environ


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["projects", "list", "--token", "secret"],
        ["projects", "list", "--token=secret"],
        ["projects", "list", "--access-token", "secret"],
        ["projects", "list", "--access-token=secret"],
        ["projects", "list", fake_pat("positional_secret")],
        ["projects", "list", f"{fake_pat('trailing_newline')}\n"],
        ["projects", "list", "x" + fake_pat("hex_suffix_argv") + "f"],
    ],
)
def test_execute_authenticated_rejects_empty_or_sensitive_arguments(
    tmp_path, arguments
):
    config = SupabaseConfig(binary_resolver=lambda _: str(tmp_path / "supabase"))

    with patch("supa_cc.config.subprocess.Popen") as run:
        result = config.execute_authenticated(
            Account(name="work", token=fake_pat("unsafe")), arguments
        )

    assert result.ok is False
    assert result.code in {
        AuthFailureCode.COMMAND_EMPTY,
        AuthFailureCode.UNSAFE_ARGUMENT,
    }
    run.assert_not_called()


def test_execute_authenticated_sanitizes_exact_and_token_like_output(tmp_path):
    token = fake_pat("exact_secret")
    other_token = fake_pat("other_secret")
    config = SupabaseConfig(binary_resolver=lambda _: str(tmp_path / "supabase"))

    with patch(
        "supa_cc.config.subprocess.Popen",
        return_value=_process(
            returncode=9,
            stdout=f"first={token}\n",
            stderr=f"401 Unauthorized second={other_token}\n",
        ),
    ):
        result = config.execute_authenticated(
            Account(name="work", token=token), ["projects", "list"]
        )

    assert result.ok is False
    assert result.code is AuthFailureCode.TOKEN_REJECTED
    assert result.exit_code == 9
    rendered = f"{result.stdout}\n{result.stderr}\n{result.message}\n{repr(result)}"
    assert token not in rendered
    assert other_token not in rendered
    assert rendered.count("[REDACTED]") >= 2


@pytest.mark.parametrize(
    "failure,expected",
    [
        (FileNotFoundError("secret"), AuthFailureCode.CLI_NOT_FOUND),
        (PermissionError("EPERM secret"), AuthFailureCode.ENVIRONMENT_BLOCKED),
    ],
)
def test_execute_authenticated_classifies_runtime_failures(
    tmp_path, failure, expected
):
    config = SupabaseConfig(binary_resolver=lambda _: str(tmp_path / "supabase"))

    with patch("supa_cc.config.subprocess.Popen", side_effect=failure):
        result = config.execute_authenticated(
            Account(name="work", token=fake_pat("runtime")),
            ["projects", "list"],
        )

    assert result.ok is False
    assert result.code is expected
    assert "secret" not in repr(result)


@pytest.mark.parametrize(
    "raw,expected",
    [(0, 0), (1, 1), (255, 255), (-9, 1), (256, 1), (999, 1)],
)
def test_execute_authenticated_normalizes_child_exit_code(tmp_path, raw, expected):
    config = SupabaseConfig(binary_resolver=lambda _: str(tmp_path / "supabase"))

    with patch(
        "supa_cc.config.subprocess.Popen",
        return_value=_process(returncode=raw, stderr="failed"),
    ):
        result = config.execute_authenticated(
            Account(name="work", token=fake_pat("exit_code")), ["projects", "list"]
        )

    assert result.exit_code == expected


def test_validate_access_token_reuses_authenticated_executor(tmp_path):
    config = SupabaseConfig(binary_resolver=lambda _: str(tmp_path / "supabase"))
    account = Account(name="work", token=fake_pat("reuse"))

    with patch.object(config, "execute_authenticated") as execute:
        execute.return_value = AuthResult.success("ok")
        result = config.validate_access_token(account)

    execute.assert_called_once_with(
        account,
        ["projects", "list"],
        timeout_seconds=30,
    )
    assert result.ok is True


def test_captured_executor_maps_value_error_without_traceback(tmp_path):
    token = fake_pat("nul_argv")
    config = SupabaseConfig(binary_resolver=lambda _: str(tmp_path / "supabase"))

    result = config.execute_authenticated(
        Account(name="work", token=token),
        ["projects", "bad\x00argument"],
    )

    assert result.ok is False
    assert result.code is AuthFailureCode.UNSAFE_ARGUMENT
    assert token not in repr(result)


def test_streaming_terminates_child_before_propagating_keyboard_interrupt(tmp_path):
    config = SupabaseConfig(binary_resolver=lambda _: str(tmp_path / "supabase"))
    stdout_read, stdout_write = os.pipe()
    stderr_read, stderr_write = os.pipe()
    os.close(stdout_write)
    os.close(stderr_write)
    process = Mock()
    process.stdout = os.fdopen(stdout_read, "rb", buffering=0)
    process.stderr = os.fdopen(stderr_read, "rb", buffering=0)
    process.poll.side_effect = [KeyboardInterrupt(), None]
    process.wait.return_value = 0
    process.pid = 99999999

    with patch(
        "supa_cc.config.subprocess.Popen", return_value=process
    ), patch("supa_cc.config.os.killpg") as killpg:
        with pytest.raises(KeyboardInterrupt):
            config.execute_authenticated_streaming(
                Account(name="work", token=fake_pat("interrupt_cleanup")),
                ["projects", "list"],
                stdout_sink=lambda _chunk: None,
                stderr_sink=lambda _chunk: None,
            )

    if os.name == "posix":
        assert [entry.args for entry in killpg.call_args_list] == [
            (process.pid, signal.SIGTERM),
            (process.pid, signal.SIGKILL),
        ]
    else:
        process.terminate.assert_called_once_with()
    assert process.wait.call_args_list[-1].kwargs == {"timeout": 1}
