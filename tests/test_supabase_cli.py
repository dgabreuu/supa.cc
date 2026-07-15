import os
import sys
from unittest.mock import patch

import pytest

import supa_cc.supabase_cli as supabase_cli
from supa_cc.auth import AuthFailureCode, CommandResult
from supa_cc.models import Account
from supa_cc.supabase_cli import (
    MINIMUM_VERSION_TEXT,
    SupabaseCLI,
    SupabaseCLICompatibilityState,
)

from helpers import fake_pat


class _NoCharacterIteration(str):
    def __iter__(self):
        raise AssertionError("normal output must be copied as a slice")


def _executable(tmp_path, content="#!/bin/sh\nexit 0\n"):
    binary = tmp_path / ("supabase.cmd" if os.name == "nt" else "supabase")
    if os.name == "nt":
        content = (
            "@echo %SUPABASE_ACCESS_TOKEN%: 401 Unauthorized 1>&2\r\n@exit /b 7\r\n"
            if "401 Unauthorized" in content
            else "@exit /b 0\r\n"
        )
    binary.write_text(content, encoding="utf-8")
    binary.chmod(0o700)
    return binary


def test_streaming_redactor_copies_normal_blocks_without_character_iteration():
    redactor = supabase_cli._StreamingPATRedactor()
    text = _NoCharacterIteration("normal output " * 1000)

    assert redactor.feed(text, final=True) == text


def test_streaming_redactor_preserves_state_across_every_token_split():
    token = fake_pat("every-split")
    value = f"before {token} after"

    for split in range(len(value) + 1):
        redactor = supabase_cli._StreamingPATRedactor()
        rendered = redactor.feed(value[:split])
        rendered += redactor.feed(value[split:], final=True)
        assert rendered == "before [REDACTED] after"


def test_windows_executes_verified_absolute_binary_path(tmp_path, monkeypatch):
    binary = _executable(tmp_path)
    cli = SupabaseCLI(binary_resolver=lambda _: str(binary))
    monkeypatch.setattr(supabase_cli, "_is_windows", lambda: True)

    with patch(
        "supa_cc.supabase_cli.run_process", return_value=CommandResult.success()
    ) as run:
        result = cli.execute_authenticated(
            Account("work", fake_pat("windows-binary")), ["projects", "list"]
        )

    assert result.ok
    assert run.call_args.args[0][0] == str(binary.resolve())
    assert run.call_args.kwargs["pass_fds"] == ()
    assert not run.call_args.args[0][0].startswith(("/proc/self/fd", "/dev/fd"))


def test_macos_executes_verified_absolute_binary_path(tmp_path, monkeypatch):
    binary = _executable(tmp_path)
    cli = SupabaseCLI(binary_resolver=lambda _: str(binary))
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(supabase_cli, "_has_trusted_path_ancestors", lambda _: True)

    def run_at_spawn(argv, _env, *_args, **kwargs):
        assert argv[0] == str(binary.resolve())
        kwargs["pre_spawn_check"]()
        return CommandResult.success()

    with patch.object(cli, "_require_same_binary") as revalidate, patch(
        "supa_cc.supabase_cli.run_process", side_effect=run_at_spawn
    ) as run:
        result = cli.execute_authenticated(
            Account("work", fake_pat("macos-binary")), ["projects", "list"]
        )

    assert result.ok
    assert run.call_args.args[0][0] == str(binary.resolve())
    assert run.call_args.kwargs["pass_fds"] == ()
    descriptor, path = revalidate.call_args.args
    assert isinstance(descriptor, int)
    assert path == str(binary.resolve())


@pytest.mark.skipif(os.name != "posix", reason="POSIX directory modes")
def test_macos_rejects_binary_below_group_or_world_writable_ancestor(
    tmp_path, monkeypatch
):
    unsafe_directory = tmp_path / "unsafe-bin"
    unsafe_directory.mkdir()
    binary = _executable(unsafe_directory)
    unsafe_directory.chmod(0o777)
    cli = SupabaseCLI(binary_resolver=lambda _: str(binary))
    monkeypatch.setattr(sys, "platform", "darwin")

    with patch("supa_cc.supabase_cli.run_process") as run:
        result = cli.execute_authenticated(
            Account("work", fake_pat("macos-unsafe-ancestor")),
            ["projects", "list"],
        )

    assert result.code is AuthFailureCode.ENVIRONMENT_BLOCKED
    run.assert_not_called()


@pytest.mark.parametrize(
    "path",
    [
        "/opt/homebrew/Cellar/supabase/2.109.1/bin/supabase",
        "/usr/local/Cellar/supabase/2.109.1/bin/supabase",
    ],
)
def test_macos_accepts_only_canonical_group_writable_homebrew_cellar(
    monkeypatch, path
):
    def metadata(candidate):
        mode = 0o40775 if candidate in {
            "/opt/homebrew/Cellar",
            "/usr/local/Cellar",
        } else 0o40755
        return type(
            "Metadata",
            (),
            {"st_mode": mode, "st_uid": os.getuid()},
        )()

    monkeypatch.setattr(supabase_cli.os, "lstat", metadata)

    assert supabase_cli._has_trusted_path_ancestors(path) is True


def test_macos_rejects_group_writable_noncanonical_cellar(monkeypatch):
    def metadata(candidate):
        mode = 0o40775 if candidate == "/custom/Cellar" else 0o40755
        return type(
            "Metadata",
            (),
            {"st_mode": mode, "st_uid": os.getuid()},
        )()

    monkeypatch.setattr(supabase_cli.os, "lstat", metadata)

    assert (
        supabase_cli._has_trusted_path_ancestors(
            "/custom/Cellar/supabase/2.109.1/bin/supabase"
        )
        is False
    )


def test_windows_revalidates_binary_at_process_spawn_boundary(tmp_path, monkeypatch):
    binary = _executable(tmp_path)
    replacement = tmp_path / "replacement"
    replacement.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    replacement.chmod(0o700)
    cli = SupabaseCLI(binary_resolver=lambda _: str(binary))
    monkeypatch.setattr(supabase_cli, "_is_windows", lambda: True)
    original_open = cli._open_binary

    def open_then_replace():
        opened = original_open()
        os.replace(replacement, binary)
        return opened

    monkeypatch.setattr(cli, "_open_binary", open_then_replace)

    with patch("supa_cc.process.subprocess.Popen") as popen:
        result = cli.execute_authenticated(
            Account("work", fake_pat("windows-replacement")),
            ["projects", "list"],
        )

    assert result.code is AuthFailureCode.ENVIRONMENT_BLOCKED
    popen.assert_not_called()


@pytest.mark.parametrize("mode", [0o600, 0o722, 0o702])
@pytest.mark.skipif(os.name != "posix", reason="POSIX executable permission modes")
def test_rejects_binary_that_is_not_safely_executable(tmp_path, mode):
    binary = _executable(tmp_path)
    binary.chmod(mode)
    cli = SupabaseCLI(binary_resolver=lambda _: str(binary))

    with patch("supa_cc.process.subprocess.Popen") as popen:
        result = cli.execute_authenticated(
            Account(name="work", token=fake_pat("unsafe-binary")),
            ["projects", "list"],
        )

    assert result.code is AuthFailureCode.ENVIRONMENT_BLOCKED
    assert fake_pat("unsafe-binary") not in repr(result)
    popen.assert_not_called()


@pytest.mark.skipif(os.name != "posix", reason="POSIX executable permission modes")
def test_revalidates_binary_metadata_before_each_invocation(tmp_path):
    binary = _executable(tmp_path)
    cli = SupabaseCLI(binary_resolver=lambda _: str(binary))
    binary.chmod(0o722)

    with patch("supa_cc.process.subprocess.Popen") as popen:
        result = cli.execute_authenticated(
            Account(name="work", token=fake_pat("changed-binary")),
            ["projects", "list"],
        )

    assert result.code is AuthFailureCode.ENVIRONMENT_BLOCKED
    popen.assert_not_called()


def test_rejects_nonregular_executable_path(tmp_path):
    binary = tmp_path / "supabase"
    binary.mkdir()
    cli = SupabaseCLI(binary_resolver=lambda _: str(binary))

    result = cli.execute_authenticated(Account("work", fake_pat("directory")), ["projects", "list"])

    assert result.code is AuthFailureCode.ENVIRONMENT_BLOCKED


@pytest.mark.skipif(os.name != "posix", reason="POSIX ownership metadata")
def test_rejects_executable_owned_by_another_user(tmp_path, monkeypatch):
    binary = _executable(tmp_path)
    real_fstat = os.fstat

    def wrong_owner(descriptor):
        metadata = real_fstat(descriptor)
        values = list(metadata)
        values[4] = os.getuid() + 1
        return os.stat_result(values)

    monkeypatch.setattr("supa_cc.supabase_cli.os.fstat", wrong_owner)
    cli = SupabaseCLI(binary_resolver=lambda _: str(binary))

    result = cli.execute_authenticated(Account("work", fake_pat("owner")), ["projects", "list"])

    assert result.code is AuthFailureCode.ENVIRONMENT_BLOCKED


@pytest.mark.skipif(os.name != "posix", reason="POSIX ownership metadata")
def test_accepts_root_owned_executable(tmp_path, monkeypatch):
    binary = _executable(tmp_path)
    real_fstat = os.fstat

    def root_owner(descriptor):
        metadata = real_fstat(descriptor)
        values = list(metadata)
        values[4] = 0
        return os.stat_result(values)

    monkeypatch.setattr("supa_cc.supabase_cli.os.fstat", root_owner)
    cli = SupabaseCLI(binary_resolver=lambda _: str(binary))

    with patch("supa_cc.supabase_cli.run_process", return_value=CommandResult.success()) as run:
        result = cli.execute_authenticated(Account("work", fake_pat("root")), ["projects", "list"])

    assert result.ok
    assert run.called


def test_each_invocation_opens_and_revalidates_executable(tmp_path, monkeypatch):
    binary = _executable(tmp_path)
    cli = SupabaseCLI(binary_resolver=lambda _: str(binary))
    opens = 0
    real_open = os.open

    def count_open(path, flags):
        nonlocal opens
        opens += 1
        return real_open(path, flags)

    monkeypatch.setattr("supa_cc.supabase_cli.os.open", count_open)

    assert cli.execute_authenticated(Account("work", fake_pat("first")), ["projects", "list"]).ok
    assert cli.execute_authenticated(Account("work", fake_pat("second")), ["projects", "list"]).ok
    assert opens == 2


def test_path_replacement_after_open_is_rejected_and_never_executed(tmp_path, monkeypatch):
    marker = tmp_path / "executed"
    binary = _executable(tmp_path, f"#!/bin/sh\ntouch '{marker}'\n")
    replacement = tmp_path / "replacement"
    replacement.write_text(f"#!/bin/sh\ntouch '{marker}'\n", encoding="utf-8")
    replacement.chmod(0o700)
    cli = SupabaseCLI(binary_resolver=lambda _: str(binary))
    resolved_binary = str(binary.resolve())
    real_stat = os.stat
    replaced = False

    def replace_before_revalidation(path, *args, **kwargs):
        nonlocal replaced
        if path == resolved_binary and not replaced:
            replaced = True
            os.replace(replacement, binary)
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr("supa_cc.supabase_cli.os.stat", replace_before_revalidation)

    result = cli.execute_authenticated(Account("work", fake_pat("race")), ["projects", "list"])

    assert result.code is AuthFailureCode.ENVIRONMENT_BLOCKED
    assert not marker.exists()


def test_supabase_cli_classifies_and_redacts_neutral_process_output(tmp_path):
    token = fake_pat("classification")
    binary = _executable(tmp_path, "#!/bin/sh\necho \"$SUPABASE_ACCESS_TOKEN: 401 Unauthorized\" >&2\nexit 7\n")
    cli = SupabaseCLI(binary_resolver=lambda _: str(binary))

    result = cli.execute_authenticated(
        Account("work", token),
        ["projects", "list"],
    )

    assert result.code is AuthFailureCode.TOKEN_REJECTED
    assert result.stderr == "[REDACTED]: 401 Unauthorized\n"


@pytest.mark.parametrize("output", ["2.109.0", "not a version"])
def test_preflight_rejects_old_or_unparseable_version(tmp_path, output):
    cli = SupabaseCLI(binary_resolver=lambda _: str(_executable(tmp_path)))

    with patch.object(cli, "_version_command", return_value=CommandResult.success(stdout=output)):
        result = cli.preflight()

    assert result.ok is False
    assert result.code is AuthFailureCode.CLI_INCOMPATIBLE


def test_preflight_accepts_minimum_version(tmp_path):
    cli = SupabaseCLI(binary_resolver=lambda _: str(_executable(tmp_path)))

    with patch.object(
        cli, "_version_command", return_value=CommandResult.success(stdout="2.109.1")
    ):
        result = cli.preflight()

    assert result.ok is True


@pytest.mark.parametrize(
    ("command_result", "state"),
    [
        (
            CommandResult.failure(
                AuthFailureCode.CLI_NOT_FOUND, "Supabase CLI not found."
            ),
            SupabaseCLICompatibilityState.MISSING,
        ),
        (
            CommandResult.failure(
                AuthFailureCode.ENVIRONMENT_BLOCKED, "Execution is blocked."
            ),
            SupabaseCLICompatibilityState.BLOCKED,
        ),
        (
            CommandResult.success(stdout="2.109.0"),
            SupabaseCLICompatibilityState.INCOMPATIBLE,
        ),
        (
            CommandResult.success(stdout="2.109.1"),
            SupabaseCLICompatibilityState.COMPATIBLE,
        ),
    ],
)
def test_inspect_compatibility_has_explicit_sanitized_states(
    tmp_path, command_result, state
):
    cli = SupabaseCLI(binary_resolver=lambda _: str(_executable(tmp_path)))

    with patch.object(cli, "_version_command", return_value=command_result) as command:
        compatibility = cli.inspect_compatibility()

    assert compatibility.state is state
    assert compatibility.minimum_version == MINIMUM_VERSION_TEXT == "2.109.1"
    assert compatibility.version in {"2.109.0", "2.109.1", None}
    command.assert_called_once_with()


def test_native_login_uses_captured_sanitized_environment_and_explicit_profile(
    tmp_path,
):
    token = fake_pat("captured-environment")
    base_environment = {
        "KEEP": "value",
        "SUPABASE_ACCESS_TOKEN": fake_pat("inherited"),
        "SUPABASE_PROFILE": "other",
        "SUPABASE_TELEMETRY_DISABLED": "0",
    }
    cli = SupabaseCLI(
        binary_resolver=lambda _: str(_executable(tmp_path)),
        base_environment=base_environment,
    )
    base_environment["KEEP"] = "changed-after-construction"

    with patch.object(
        cli, "_run", return_value=CommandResult.success()
    ) as run:
        result = cli.login_with_access_token(
            Account("work", token), supabase_home=tmp_path / "home"
        )

    assert result.ok
    argv, environment = run.call_args.args[:2]
    assert argv == ["login", "--profile", "supabase"]
    assert environment["SUPABASE_ACCESS_TOKEN"] == token
    assert "SUPABASE_PROFILE" not in environment
    assert environment["SUPABASE_HOME"] == str(tmp_path / "home")
    assert environment["SUPABASE_TELEMETRY_DISABLED"] == "1"
    assert environment["DO_NOT_TRACK"] == "1"
    assert environment["KEEP"] == "value"
    assert token not in argv


def test_native_verify_and_logout_never_receive_access_token(tmp_path):
    cli = SupabaseCLI(
        binary_resolver=lambda _: str(_executable(tmp_path)),
        base_environment={
            "SUPABASE_ACCESS_TOKEN": fake_pat("parent"),
            "SUPABASE_PROFILE": "other",
        },
    )

    with patch.object(
        cli, "_run", return_value=CommandResult.success()
    ) as run:
        assert cli.verify_persisted_session(supabase_home=tmp_path / "home").ok
        assert cli.logout_session(supabase_home=tmp_path / "home").ok

    verify_call, logout_call = run.call_args_list
    assert verify_call.args[0] == ["projects", "list", "--profile", "supabase"]
    assert logout_call.args[0] == ["logout", "--yes", "--profile", "supabase"]
    for call in (verify_call, logout_call):
        assert "SUPABASE_ACCESS_TOKEN" not in call.args[1]
        assert "SUPABASE_PROFILE" not in call.args[1]


def test_token_validation_uses_official_profile_and_child_only_telemetry(tmp_path):
    cli = SupabaseCLI(
        binary_resolver=lambda _: str(_executable(tmp_path)),
        base_environment={"SUPABASE_PROFILE": "other"},
    )

    with patch.object(
        cli, "_run", return_value=CommandResult.success()
    ) as run:
        result = cli.validate_access_token(Account("work", fake_pat("validate")))

    assert result.ok
    argv, environment = run.call_args.args[:2]
    assert argv == ["projects", "list", "--profile", "supabase"]
    assert "SUPABASE_PROFILE" not in environment
    assert environment["SUPABASE_TELEMETRY_DISABLED"] == "1"
    assert environment["DO_NOT_TRACK"] == "1"


def test_version_check_uses_sanitized_captured_environment(tmp_path):
    cli = SupabaseCLI(
        binary_resolver=lambda _: str(_executable(tmp_path)),
        base_environment={
            "SUPABASE_ACCESS_TOKEN": fake_pat("version-parent"),
            "SUPABASE_PROFILE": "other",
            "KEEP": "value",
        },
    )

    with patch.object(
        cli, "_run", return_value=CommandResult.success(stdout="2.109.1")
    ) as run:
        result = cli.preflight()

    assert result.ok
    environment = run.call_args.args[1]
    assert "SUPABASE_ACCESS_TOKEN" not in environment
    assert "SUPABASE_PROFILE" not in environment
    assert environment["KEEP"] == "value"


@pytest.mark.parametrize(
    "method,args",
    [
        ("login_with_access_token", (Account("work", fake_pat("profile")),)),
        ("verify_persisted_session", ()),
        ("logout_session", ()),
    ],
)
@pytest.mark.parametrize(
    "profile", ["work", "Supabase", "supabase ", "", None, fake_pat("profile-name")]
)
def test_native_profile_api_rejects_nondefault_profile_without_execution(
    tmp_path, method, args, profile
):
    cli = SupabaseCLI(binary_resolver=lambda _: str(_executable(tmp_path)))

    with patch.object(cli, "_run") as run:
        result = getattr(cli, method)(*args, profile=profile)

    assert result.code is AuthFailureCode.PROFILE_MISMATCH
    assert result.message == "The Supabase CLI profile does not match the selected account."
    assert fake_pat("profile-name") not in result.message
    run.assert_not_called()


def test_native_login_helper_rejects_nondefault_profile_without_execution(tmp_path):
    cli = SupabaseCLI(binary_resolver=lambda _: str(_executable(tmp_path)))

    with patch.object(cli, "_run") as run:
        result = cli._execute_native(
            Account("work", fake_pat("profile-helper")),
            ["login"],
            tmp_path,
            "Supabase",
        )

    assert result.code is AuthFailureCode.PROFILE_MISMATCH
    run.assert_not_called()


def test_native_unauthenticated_helper_rejects_nondefault_profile_without_execution(tmp_path):
    cli = SupabaseCLI(binary_resolver=lambda _: str(_executable(tmp_path)))

    with patch.object(cli, "_run") as run:
        result = cli._execute_without_access_token(
            ["logout", "--yes"], tmp_path, "supabase "
        )

    assert result.code is AuthFailureCode.PROFILE_MISMATCH
    run.assert_not_called()


@pytest.mark.parametrize(
    "output",
    ["2.109.1-beta.2", "supabase version 2.109.1-rc.1"],
)
def test_preflight_rejects_prerelease_at_stable_minimum(tmp_path, output):
    cli = SupabaseCLI(binary_resolver=lambda _: str(_executable(tmp_path)))

    with patch.object(cli, "_version_command", return_value=CommandResult.success(stdout=output)):
        result = cli.preflight()

    assert result.ok is False
    assert result.code is AuthFailureCode.CLI_INCOMPATIBLE
