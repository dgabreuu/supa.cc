import os
import signal
import subprocess
import sys
from unittest.mock import Mock, patch

import pytest

from supa_cc.auth import AuthFailureCode, AuthResult, CommandResult
from supa_cc.supabase_cli import SupabaseCLI as SupabaseConfig
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


def _binary(tmp_path, name="supabase"):
    binary = tmp_path / name
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o700)
    return str(binary)


def _assert_verified_invocation(invocation, binary):
    command = invocation.args[0][0]
    if os.name == "nt" or sys.platform == "darwin":
        assert command == str(os.path.realpath(binary))
        assert invocation.kwargs["pass_fds"] == ()
    else:
        assert command.startswith(("/proc/self/fd/", "/dev/fd/"))
        assert invocation.kwargs["pass_fds"]


def test_macos_popen_assertion_does_not_expect_consumed_pre_spawn_callback(
    tmp_path, monkeypatch
):
    binary = _binary(tmp_path)
    monkeypatch.setattr(sys, "platform", "darwin")
    invocation = Mock(
        args=([str(os.path.realpath(binary)), "projects", "list"],),
        kwargs={"pass_fds": ()},
    )

    _assert_verified_invocation(invocation, binary)


def test_macos_run_process_executes_pre_spawn_revalidation(tmp_path, monkeypatch):
    binary = _binary(tmp_path)
    config = SupabaseConfig(binary_resolver=lambda _: binary)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(
        "supa_cc.supabase_cli._has_trusted_path_ancestors", lambda _: True
    )

    def run_at_spawn(argv, _env, *_args, **kwargs):
        assert argv[0] == str(os.path.realpath(binary))
        kwargs["pre_spawn_check"]()
        return CommandResult.success()

    with patch.object(config, "_require_same_binary") as revalidate, patch(
        "supa_cc.supabase_cli.run_process", side_effect=run_at_spawn
    ):
        result = config.execute_authenticated(
            Account("work", fake_pat("macos-config-boundary")),
            ["projects", "list"],
        )

    assert result.ok
    descriptor, path = revalidate.call_args.args
    assert isinstance(descriptor, int)
    assert path == str(os.path.realpath(binary))


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
    binary = _binary(tmp_path, "real-supabase")
    config = SupabaseConfig(binary_resolver=lambda _: binary)
    account = Account(name="work", token=token)

    with patch.dict(
        "supa_cc.supabase_cli.os.environ",
        {"PARENT_VALUE": "present"},
        clear=True,
    ), patch(
        "supa_cc.process.subprocess.Popen",
        return_value=_process(),
    ) as popen:
        result = config.validate_access_token(account)

    assert result.ok is True
    assert result.code is AuthFailureCode.NONE
    assert token not in result.message
    assert token not in repr(result)
    assert "SUPABASE_ACCESS_TOKEN" not in os.environ
    invocation = popen.call_args
    _assert_verified_invocation(invocation, binary)
    assert invocation.args[0][1:] == ["projects", "list"]
    assert invocation.kwargs["env"] == {"PARENT_VALUE": "present", "SUPABASE_ACCESS_TOKEN": token}
    assert "login" not in popen.call_args.args[0]
    assert token not in popen.call_args.args[0]


def test_login_passes_token_only_in_child_environment(tmp_path):
    token = fake_pat("native-login")
    binary = _binary(tmp_path)
    config = SupabaseConfig(binary_resolver=lambda _: binary)
    account = Account(name="work", token=token)

    with patch.dict(
        "supa_cc.supabase_cli.os.environ", {"PARENT": "yes"}, clear=True
    ), patch(
        "supa_cc.process.subprocess.Popen", return_value=_process()
    ) as popen:
        result = config.login_with_access_token(account)

    _assert_verified_invocation(popen.call_args, binary)
    assert popen.call_args.args[0][1:] == ["login"]
    assert token not in popen.call_args.args[0]
    assert popen.call_args.kwargs["env"] == {
        "PARENT": "yes",
        "SUPABASE_ACCESS_TOKEN": token,
    }
    assert result.ok is True


def test_native_login_classifies_cli_session_persistence_failure(tmp_path):
    config = SupabaseConfig(binary_resolver=lambda _: _binary(tmp_path))

    with patch(
        "supa_cc.process.subprocess.Popen",
        return_value=_process(returncode=7, stderr="unexpected persistence failure"),
    ):
        result = config.login_with_access_token(
            Account(name="work", token=fake_pat("native-persist"))
        )

    assert result.code is AuthFailureCode.NATIVE_LOGIN_FAILED
    assert result.message == "The Supabase CLI could not persist the native session."


def test_native_verification_classifies_keychain_denial_as_permission_failure(tmp_path):
    config = SupabaseConfig(binary_resolver=lambda _: _binary(tmp_path))

    with patch(
        "supa_cc.process.subprocess.Popen",
        return_value=_process(
            returncode=7,
            stderr="macOS Keychain access denied: user interaction is not allowed",
        ),
    ):
        result = config.verify_persisted_session()

    assert result.code is AuthFailureCode.KEYCHAIN_PERMISSION_DENIED
    assert result.message == (
        "The native credential store did not authorize the Supabase CLI session."
    )


def test_native_login_classifies_telemetry_eperm_as_environment_failure(tmp_path):
    config = SupabaseConfig(binary_resolver=lambda _: _binary(tmp_path))

    with patch(
        "supa_cc.process.subprocess.Popen",
        return_value=_process(
            returncode=7,
            stderr="EPERM: operation not permitted, open telemetry.json",
        ),
    ):
        result = config.login_with_access_token(
            Account(name="work", token=fake_pat("native-sandbox"))
        )

    assert result.code is AuthFailureCode.ENVIRONMENT_BLOCKED
    assert result.message == "The environment blocked Supabase CLI execution."


@pytest.mark.parametrize(
    "method,arguments",
    [
        ("verify_persisted_session", ["projects", "list"]),
        ("logout_session", ["logout", "--yes"]),
    ],
)
def test_native_commands_remove_inherited_environment_override(
    tmp_path, method, arguments
):
    binary = _binary(tmp_path)
    config = SupabaseConfig(binary_resolver=lambda _: binary)

    with patch.dict(
        "supa_cc.supabase_cli.os.environ",
        {"PARENT": "yes", "SUPABASE_ACCESS_TOKEN": fake_pat("inherited")},
        clear=True,
    ), patch(
        "supa_cc.process.subprocess.Popen", return_value=_process()
    ) as popen:
        result = getattr(config, method)()

    _assert_verified_invocation(popen.call_args, binary)
    assert popen.call_args.args[0][1:] == arguments
    assert popen.call_args.kwargs["env"] == {"PARENT": "yes"}
    assert result.ok is True


def test_validate_access_token_does_not_run_when_token_is_missing(tmp_path):
    config = SupabaseConfig(binary_resolver=lambda _: _binary(tmp_path))

    with patch("supa_cc.process.subprocess.Popen") as run:
        result = config.validate_access_token(Account(name="work", token=""))

    assert result.ok is False
    assert result.code is AuthFailureCode.TOKEN_MISSING
    run.assert_not_called()


def test_validate_access_token_does_not_run_when_cli_is_missing():
    config = SupabaseConfig(binary_resolver=lambda _: None)

    with patch("supa_cc.process.subprocess.Popen") as run:
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
    config = SupabaseConfig(binary_resolver=lambda _: _binary(tmp_path))

    with patch(
        "supa_cc.process.subprocess.Popen",
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
    config = SupabaseConfig(binary_resolver=lambda _: _binary(tmp_path))

    with patch("supa_cc.process.subprocess.Popen", side_effect=failure):
        result = config.validate_access_token(
            Account(name="work", token=fake_pat("execution"))
        )

    assert result.ok is False
    assert result.code is expected
    assert "sensitive" not in result.message
    assert "sensitive" not in repr(result)


def test_validate_access_token_never_calls_native_keychain_repair(tmp_path):
    config = SupabaseConfig(binary_resolver=lambda _: _binary(tmp_path))

    with patch(
        "supa_cc.process.subprocess.Popen", return_value=_process()
    ) as run:
        result = config.validate_access_token(
            Account(name="work", token=fake_pat("no-repair"))
        )

    assert result.ok is True
    assert all("security" not in str(argument) for argument in run.call_args.args[0])


def test_execute_authenticated_passes_pat_only_in_copied_environment(tmp_path):
    token = fake_pat("command_env_only")
    binary = _binary(tmp_path)
    config = SupabaseConfig(binary_resolver=lambda _: binary)

    with patch.dict(
        "supa_cc.supabase_cli.os.environ", {"PARENT": "yes"}, clear=True
    ), patch(
        "supa_cc.process.subprocess.Popen",
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
    _assert_verified_invocation(popen.call_args, binary)
    assert popen.call_args.args[0][1:] == ["projects", "list", "--profile", "work"]
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
    config = SupabaseConfig(binary_resolver=lambda _: _binary(tmp_path))

    with patch("supa_cc.process.subprocess.Popen") as run:
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
    config = SupabaseConfig(binary_resolver=lambda _: _binary(tmp_path))

    with patch(
        "supa_cc.process.subprocess.Popen",
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
    config = SupabaseConfig(binary_resolver=lambda _: _binary(tmp_path))

    with patch("supa_cc.process.subprocess.Popen", side_effect=failure):
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
    config = SupabaseConfig(binary_resolver=lambda _: _binary(tmp_path))

    with patch(
        "supa_cc.process.subprocess.Popen",
        return_value=_process(returncode=raw, stderr="failed"),
    ):
        result = config.execute_authenticated(
            Account(name="work", token=fake_pat("exit_code")), ["projects", "list"]
        )

    assert result.exit_code == expected


def test_validate_access_token_reuses_authenticated_executor(tmp_path):
    config = SupabaseConfig(binary_resolver=lambda _: _binary(tmp_path))
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
    config = SupabaseConfig(binary_resolver=lambda _: _binary(tmp_path))

    result = config.execute_authenticated(
        Account(name="work", token=token),
        ["projects", "bad\x00argument"],
    )

    assert result.ok is False
    assert result.code is AuthFailureCode.UNSAFE_ARGUMENT
    assert token not in repr(result)


def test_streaming_terminates_child_before_propagating_keyboard_interrupt(tmp_path):
    config = SupabaseConfig(binary_resolver=lambda _: _binary(tmp_path))
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
        "supa_cc.process.subprocess.Popen", return_value=process
    ), patch("supa_cc.process.os.killpg", create=True) as killpg:
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
