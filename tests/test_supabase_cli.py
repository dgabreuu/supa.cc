import os
from unittest.mock import patch

import pytest

from supa_cc.auth import AuthFailureCode, CommandResult
from supa_cc.models import Account
from supa_cc.supabase_cli import SupabaseCLI

from helpers import fake_pat


def _executable(tmp_path, content="#!/bin/sh\nexit 0\n"):
    binary = tmp_path / "supabase"
    binary.write_text(content, encoding="utf-8")
    binary.chmod(0o700)
    return binary


@pytest.mark.parametrize("mode", [0o600, 0o722, 0o702])
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


@pytest.mark.parametrize(
    "output,expected",
    [
        ("2.109.1", (2, 109, 1)),
        ("supabase version 2.110.0", (2, 110, 0)),
        ("supabase version 2.109.1", (2, 109, 1)),
    ],
)
def test_detect_version_robustly_parses_cli_output(tmp_path, output, expected):
    cli = SupabaseCLI(binary_resolver=lambda _: str(_executable(tmp_path)))
    result = CommandResult.success(stdout=output + "\n")

    with patch("supa_cc.supabase_cli.run_process", return_value=result) as run:
        detected = cli.detect_version()

    assert detected == expected
    assert run.call_args.args[0][1:] == ["--version"]
    assert "SUPABASE_ACCESS_TOKEN" not in run.call_args.args[1]


@pytest.mark.parametrize(
    "output",
    [
        "warning: dependency 9.8.7 is old\nnot a version\n",
        "warning 9.8.7\nsupabase version unknown\n",
        "2.109.1.4\n",
        "supabase version 2.109.1.4\n",
    ],
)
def test_detect_version_rejects_unrelated_or_malformed_versions(tmp_path, output):
    cli = SupabaseCLI(binary_resolver=lambda _: str(_executable(tmp_path)))

    with patch.object(cli, "_version_command", return_value=CommandResult.success(stdout=output)):
        assert cli.detect_version() is None


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
    assert result.message == "O perfil da Supabase CLI não corresponde à conta selecionada."
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
