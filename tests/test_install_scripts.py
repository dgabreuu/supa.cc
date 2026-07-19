import re
import shutil
import subprocess
import os
from pathlib import Path

import pytest
import tomllib

from supa_cc.supabase_cli import MINIMUM_VERSION_TEXT


ROOT = Path(__file__).parents[1]
POSIX_INSTALLER = ROOT / "install.sh"
WINDOWS_INSTALLER = ROOT / "install.ps1"


def _bash(*arguments, input_text=None):
    return subprocess.run(
        ["bash", *map(str, arguments)],
        cwd=ROOT,
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
    )


def _source(expression, *arguments):
    return _bash(
        "-c",
        f'source "$1"; {expression}',
        "test",
        POSIX_INSTALLER,
        *arguments,
    )


def test_posix_installer_has_valid_syntax_and_public_options():
    assert POSIX_INSTALLER.is_file()
    assert _bash("-n", POSIX_INSTALLER).returncode == 0

    help_result = _bash(POSIX_INSTALLER, "--help")

    assert help_result.returncode == 0
    assert "--yes" in help_result.stdout
    assert "--dry-run" in help_result.stdout
    assert "--help" in help_result.stdout


def test_posix_installer_requires_tty_or_explicit_yes():
    result = _bash(POSIX_INSTALLER, "--dry-run", input_text="")

    assert result.returncode == 2
    assert "--yes" in result.stderr
    assert "/dev/tty" in result.stderr


def test_macos_plan_uses_pinned_homebrew_and_formula_scoped_trust():
    result = _source(
        'has_command(){ return 1; }; locate_brew(){ return 1; }; '
        'OS=macos; DISTRO=none; ARCH=arm64; build_plan; print_plan'
    )

    assert result.returncode == 0, result.stderr
    assert re.search(
        r"raw\.githubusercontent\.com/Homebrew/install/[0-9a-f]{40}/install\.sh",
        result.stdout,
    )
    assert "brew tap dgabreuu/supa-cc https://github.com/dgabreuu/supa.cc.git" in result.stdout
    assert "brew install supabase/tap/supabase" in result.stdout
    assert "brew install dgabreuu/supa-cc/supa-cc" in result.stdout
    assert "brew trust" not in result.stdout
    assert "HOMEBREW_NO_REQUIRE_TAP_TRUST" not in POSIX_INSTALLER.read_text()


@pytest.mark.parametrize(
    ("distribution", "package_command"),
    [
        ("debian", "apt install python3 python3-venv pipx gnome-keyring"),
        ("ubuntu", "apt install python3 python3-venv pipx gnome-keyring"),
        ("arch", "pacman -S python python-pipx gnome-keyring"),
        ("fedora", "dnf install python3 pipx gnome-keyring"),
    ],
)
def test_linux_plans_share_the_secure_bootstrap_flow(
    distribution, package_command
):
    result = _source(
        f'has_command(){{ return 1; }}; OS=linux; DISTRO={distribution}; ARCH=arm64; build_plan; print_plan'
    )

    assert result.returncode == 0, result.stderr
    assert package_command in result.stdout
    assert "libsecret" not in result.stdout
    assert "checksums.txt" in result.stdout
    assert f"supabase_{MINIMUM_VERSION_TEXT}_linux_arm64.tar.gz" in result.stdout
    assert "pipx ensurepath" in result.stdout
    assert "pipx install supa.cc" in result.stdout
    assert "doctor --installation-check" in result.stdout


def test_posix_installer_version_matches_python_canonical_minimum():
    source = POSIX_INSTALLER.read_text(encoding="utf-8")
    package_version = tomllib.loads(
        (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]["version"]

    assert f'SUPABASE_VERSION="{MINIMUM_VERSION_TEXT}"' in source
    assert f'SUPA_CC_VERSION="{package_version}"' in source


def test_complete_posix_environment_plans_validation_without_reinstallation():
    result = _source(
        'has_command(){ return 0; }; supabase_compatible(){ return 0; }; '
        'supa_compatible(){ return 0; }; '
        'linux_prerequisites_ready(){ return 0; }; '
        'OS=linux; DISTRO=ubuntu; ARCH=amd64; build_plan; print_plan'
    )

    assert result.returncode == 0, result.stderr
    assert "doctor --installation-check" in result.stdout
    assert "Download" not in result.stdout
    assert "apt install" not in result.stdout
    assert "pipx install supa.cc" not in result.stdout


def test_outdated_supabase_plan_does_not_reinstall_ready_python_or_supa_cc():
    result = _source(
        'has_command(){ return 0; }; supabase_compatible(){ return 1; }; '
        'supa_compatible(){ return 0; }; '
        'linux_prerequisites_ready(){ return 0; }; '
        'OS=linux; DISTRO=fedora; ARCH=amd64; build_plan; print_plan'
    )

    assert result.returncode == 0, result.stderr
    assert "supabase_2.109.1_linux_amd64.tar.gz" in result.stdout
    assert "dnf install" not in result.stdout
    assert "pipx install supa.cc" not in result.stdout


def test_outdated_supa_cc_uses_stable_channel_upgrade_only():
    linux = _source(
        'has_command(){ return 0; }; supabase_compatible(){ return 0; }; '
        'supa_compatible(){ return 1; }; linux_prerequisites_ready(){ return 0; }; '
        'OS=linux; DISTRO=ubuntu; ARCH=amd64; build_plan; print_plan'
    )
    macos = _source(
        'has_command(){ return 0; }; supabase_compatible(){ return 0; }; '
        'supa_compatible(){ return 1; }; '
        'OS=macos; DISTRO=none; ARCH=arm64; build_plan; print_plan'
    )

    assert "pipx upgrade supa.cc" in linux.stdout
    assert "brew upgrade dgabreuu/supa-cc/supa-cc" in macos.stdout
    assert "git+https://" not in linux.stdout + macos.stdout


def test_supported_debian_and_ubuntu_versions_supply_python_311_or_newer():
    debian_old = _source('OS=linux; DISTRO=debian; DISTRO_VERSION=11; validate_linux_version')
    ubuntu_old = _source('OS=linux; DISTRO=ubuntu; DISTRO_VERSION=22.04; validate_linux_version')
    debian_ready = _source('OS=linux; DISTRO=debian; DISTRO_VERSION=12; validate_linux_version')
    ubuntu_ready = _source('OS=linux; DISTRO=ubuntu; DISTRO_VERSION=24.04; validate_linux_version')

    assert debian_old.returncode != 0
    assert ubuntu_old.returncode != 0
    assert debian_ready.returncode == 0, debian_ready.stderr
    assert ubuntu_ready.returncode == 0, ubuntu_ready.stderr
    assert "Python 3.11" in debian_old.stderr + ubuntu_old.stderr


@pytest.mark.parametrize("distribution", ["debian", "ubuntu", "arch", "fedora"])
def test_linux_distribution_direct_id_takes_precedence(distribution):
    result = _source(
        'resolve_linux_distribution "$2" "ubuntu debian"; '
        'printf "%s:%s\\n" "$DISTRO" "$DISTRO_SOURCE"',
        distribution,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == f"{distribution}:id\n"


def test_linux_metadata_resolves_derivative_without_validating_parent_version(
    tmp_path,
):
    metadata = tmp_path / "os-release"
    metadata.write_text(
        'ID=linuxmint\nID_LIKE="ubuntu debian"\nVERSION_ID="22"\n',
        encoding="utf-8",
    )

    result = _source(
        'read_linux_metadata "$2"; '
        'resolve_linux_distribution "$DISTRO_ID" "$DISTRO_ID_LIKE"; '
        'validate_linux_version; '
        'printf "%s:%s:%s\\n" "$DISTRO" "$DISTRO_SOURCE" "$DISTRO_VERSION"',
        metadata,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "ubuntu:id_like:22\n"


def test_linux_metadata_parses_exact_last_keys_quotes_and_mixed_case(tmp_path):
    metadata = tmp_path / "os-release"
    metadata.write_text(
        "ID='debian'\n"
        'ID=" FeDoRa "\n'
        "ID_EXTRA=arch\n"
        "ID_LIKE=' rhel centos '\n"
        'VERSION_ID=" 40 "\n'
        "MISMATCHED=\"ubuntu'\n",
        encoding="utf-8",
    )

    result = _source(
        'read_linux_metadata "$2"; mismatched="$(read_os_release_value MISMATCHED "$2")"; '
        'resolve_linux_distribution "$DISTRO_ID" "$DISTRO_ID_LIKE"; '
        'printf "%s|%s|%s|%s|%s:%s\\n" "$DISTRO_ID" "$DISTRO_ID_LIKE" '
        '"$DISTRO_VERSION" "$mismatched" "$DISTRO" "$DISTRO_SOURCE"',
        metadata,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == " FeDoRa | rhel centos | 40 |\"ubuntu'|fedora:id\n"


def test_linux_metadata_parsing_never_executes_file_contents(tmp_path):
    metadata = tmp_path / "os-release"
    marker = tmp_path / "executed"
    metadata.write_text(
        f"UNRELATED=$(touch {marker})\n"
        "ID=arch\n"
        f"VERSION_ID='$(touch {marker})'\n",
        encoding="utf-8",
    )

    result = _source(
        'read_linux_metadata "$2"; printf "%s\\n" "$DISTRO_VERSION"', metadata
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == f"$(touch {marker})\n"
    assert not marker.exists()


def test_linux_metadata_unavailable_input_clears_metadata(tmp_path):
    unreadable = tmp_path / "unreadable-os-release"
    unreadable.mkdir()

    for metadata in (tmp_path / "missing-os-release", unreadable):
        result = _source(
            'DISTRO_ID=stale; DISTRO_ID_LIKE=stale; DISTRO_VERSION=stale; '
            'read_linux_metadata "$2"; '
            'printf "%s|%s|%s\\n" "$DISTRO_ID" "$DISTRO_ID_LIKE" "$DISTRO_VERSION"',
            metadata,
        )

        assert result.returncode == 0, result.stderr
        assert result.stdout == "||\n"


def test_linux_resolver_does_not_expand_globs_and_clears_failed_state(tmp_path):
    (tmp_path / "ubuntu").touch()

    result = _source(
        'cd "$2"; DISTRO=stale; DISTRO_SOURCE=stale; '
        'if resolve_linux_distribution custom "*"; then exit 9; fi; '
        'printf "%s:%s\\n" "$DISTRO" "$DISTRO_SOURCE"',
        tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == ":\n"


@pytest.mark.parametrize(
    ("distribution", "distribution_like", "expected"),
    [
        ("", "ubuntu", "ubuntu"),
        ("custom-linux", "unsupported ArCh fedora", "arch"),
    ],
)
def test_linux_distribution_uses_first_supported_id_like_token(
    distribution, distribution_like, expected
):
    result = _source(
        'resolve_linux_distribution "$2" "$3"; '
        'printf "%s:%s\\n" "$DISTRO" "$DISTRO_SOURCE"',
        distribution,
        distribution_like,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == f"{expected}:id_like\n"


@pytest.mark.parametrize(
    ("distribution", "distribution_like"),
    [
        ("", ""),
        ("", "rhel opensuse"),
        ("custom-linux", ""),
        ("custom-linux", "rhel opensuse"),
        ("unsupported", "unsupported"),
    ],
)
def test_linux_distribution_rejects_incomplete_or_unsupported_metadata(
    distribution, distribution_like
):
    result = _source(
        'resolve_linux_distribution "$2" "$3"',
        distribution,
        distribution_like,
    )

    assert result.returncode != 0


@pytest.mark.parametrize(
    ("distribution", "expected"), [("gentoo", "gentoo"), ("", "unknown")]
)
def test_linux_environment_error_identifies_original_distribution(
    distribution, expected
):
    result = _source(
        'fixture_id=$2; '
        'uname(){ case "$1" in -s) printf "Linux\\n" ;; -m) printf "x86_64\\n" ;; esac; }; '
        'read_linux_metadata(){ DISTRO_ID="$fixture_id"; '
        'DISTRO_ID_LIKE="unsupported"; DISTRO_VERSION=1; }; '
        'detect_environment',
        distribution,
    )

    assert result.returncode != 0
    assert f"Linux distribution '{expected}' is not supported" in result.stderr


def test_macos_reuses_homebrew_outside_path_and_still_scopes_supabase_trust():
    result = _source(
        'has_command(){ [ "$1" != "brew" ]; }; '
        'locate_brew(){ printf "%s\\n" /opt/homebrew/bin/brew; }; '
        'supabase_compatible(){ return 0; }; supa_compatible(){ return 1; }; '
        'OS=macos; DISTRO=none; ARCH=arm64; build_plan; print_plan'
    )

    assert result.returncode == 0, result.stderr
    assert "Homebrew installer" not in result.stdout
    assert "brew install supabase/tap/supabase" in result.stdout
    assert result.stdout.index("supabase/tap/supabase") < result.stdout.index(
        "dgabreuu/supa-cc/supa-cc"
    )


def test_posix_installer_rejects_conflicting_channel_before_mutation():
    result = _source(
        'has_command(){ [ "$1" = "supa.cc" ]; }; '
        'resolve_command_path(){ printf "%s\\n" /safe/editable/supa.cc; }; '
        'OS=linux; DISTRO=ubuntu; ARCH=amd64; check_installation_channel'
    )

    assert result.returncode != 0
    assert "already installed" in result.stderr
    assert "remove" in result.stderr.lower()


def test_checksum_mismatch_stops_before_extraction(tmp_path):
    artifact = tmp_path / "artifact.tar.gz"
    checksums = tmp_path / "checksums.txt"
    artifact.write_bytes(b"not the expected artifact")
    checksums.write_text(f"{'0' * 64}  {artifact.name}\n", encoding="utf-8")

    result = _source(
        f'verify_checksum "{artifact}" "{checksums}"'
    )

    assert result.returncode != 0
    assert "checksum" in result.stderr.lower()


def test_posix_dry_run_does_not_download_or_mutate():
    result = _bash(POSIX_INSTALLER, "--dry-run", "--yes")

    assert result.returncode == 0, result.stderr
    assert "Dry run" in result.stdout
    assert "doctor --installation-check" in result.stdout


def test_posix_installer_runs_when_received_through_stdin_pipe():
    result = subprocess.run(
        ["bash", "-s", "--", "--dry-run", "--yes"],
        cwd=ROOT,
        input=POSIX_INSTALLER.read_text(encoding="utf-8"),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Dry run" in result.stdout
    assert "doctor --installation-check" in result.stdout


def test_windows_installer_declares_equivalent_public_options():
    assert WINDOWS_INSTALLER.is_file()
    source = WINDOWS_INSTALLER.read_text(encoding="utf-8")

    assert re.search(r"\[switch\]\s*\$Yes", source)
    assert re.search(r"\[switch\]\s*\$DryRun", source)
    assert re.search(r"\[switch\]\s*\$Help", source)
    assert f'$SupabaseVersion = "{MINIMUM_VERSION_TEXT}"' in source
    package_version = tomllib.loads(
        (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]["version"]
    assert f'$SupaCcVersion = "{package_version}"' in source
    assert "Invoke-Main\n        exit 0" in source


def test_windows_plan_is_self_sufficient_and_does_not_require_scoop():
    source = WINDOWS_INSTALLER.read_text(encoding="utf-8")

    assert "winget" in source
    assert "Python.Python.3.14" in source
    assert "python-3.14.6-amd64.exe" in source
    assert "python-3.14.6-arm64.exe" in source
    assert re.search(r'\$PythonInstallerSha256Amd64\s*=\s*"[0-9a-f]{64}"', source)
    assert re.search(r'\$PythonInstallerSha256Arm64\s*=\s*"[0-9a-f]{64}"', source)
    assert "supabase_2.109.1_windows_amd64.zip" in source
    assert "supabase_2.109.1_windows_arm64.zip" in source
    assert "checksums.txt" in source
    assert "Expand-Archive" in source
    assert "Scoop" not in source


def test_windows_installer_updates_user_and_current_path_without_restart():
    source = WINDOWS_INSTALLER.read_text(encoding="utf-8")

    assert "SetEnvironmentVariable" in source
    assert '"User"' in source
    assert "$env:PATH" in source
    assert "-m pipx ensurepath" in source
    assert "-m pipx install supa.cc" in source
    assert "doctor --installation-check" in source
    assert "Test-PipxModule" in source
    assert source.index("Test-PipxModule") < source.index(
        'Invoke-Python -Python $Python -Arguments @("-m", "pipx", "upgrade", "supa.cc")'
    )


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="PowerShell is unavailable")
def test_windows_installer_parses_and_dry_runs_with_native_powershell():
    help_result = subprocess.run(
        ["pwsh", "-NoProfile", "-File", WINDOWS_INSTALLER, "-Help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    environment = os.environ.copy()
    supa_command = shutil.which("supa.cc")
    if supa_command:
        command_directory = Path(supa_command).parent.resolve()
        environment["PATH"] = os.pathsep.join(
            entry
            for entry in environment.get("PATH", "").split(os.pathsep)
            if Path(entry).resolve() != command_directory
        )
    dry_run = subprocess.run(
        ["pwsh", "-NoProfile", "-File", WINDOWS_INSTALLER, "-DryRun", "-Yes"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert help_result.returncode == 0, help_result.stderr
    assert "-DryRun" in help_result.stdout
    assert dry_run.returncode == 0, dry_run.stderr
    assert "Dry run" in dry_run.stdout
