from dataclasses import FrozenInstanceError

import pytest

from supa_cc.environment import detect_environment
from supa_cc.installation import (
    InstallationRequirement,
    RequirementState,
    installation_guidance,
)


@pytest.mark.parametrize(
    ("system_name", "os_release", "command"),
    [
        ("Darwin", None, "brew install dgabreuu/supa-cc/supa-cc"),
        ("Windows", None, "pipx install supa.cc"),
        ("Linux", "ID=debian\n", "sudo apt install python3 python3-venv pipx gnome-keyring"),
        ("Linux", "ID=ubuntu\n", "sudo apt install python3 python3-venv pipx gnome-keyring"),
        ("Linux", "ID=arch\n", "sudo pacman -S python python-pipx gnome-keyring"),
        ("Linux", "ID=fedora\n", "sudo dnf install python3 pipx gnome-keyring"),
    ],
)
def test_supported_platform_guidance_includes_display_only_install_commands(
    system_name, os_release, command
):
    guidance = installation_guidance(
        detect_environment(system_name=system_name, os_release=os_release)
    )

    assert command in guidance.install_hint
    if system_name != "Darwin":
        assert "pipx install supa.cc" in guidance.install_hint
    assert "git+https://" not in guidance.install_hint
    assert "pipx install --force" not in guidance.update_hint
    if system_name != "Darwin":
        assert "pipx upgrade supa.cc" in guidance.update_hint


def test_unsupported_linux_guidance_does_not_offer_package_manager_commands():
    guidance = installation_guidance(
        detect_environment(system_name="Linux", os_release="ID=void\n")
    )

    assert "apt" not in guidance.install_hint
    assert "pacman" not in guidance.install_hint
    assert "dnf" not in guidance.install_hint


def test_macos_guidance_uses_formula_scoped_homebrew_flow():
    guidance = installation_guidance(detect_environment(system_name="Darwin"))

    assert (
        "brew tap dgabreuu/supa-cc https://github.com/dgabreuu/supa.cc.git"
        in guidance.install_hint
    )
    assert "brew install dgabreuu/supa-cc/supa-cc" in guidance.install_hint
    assert "brew upgrade dgabreuu/supa-cc/supa-cc" in guidance.update_hint
    assert "brew install supa-cc" not in guidance.install_hint
    assert "brew upgrade supa-cc" not in guidance.update_hint
    assert "brew trust" not in guidance.install_hint
    assert "HOMEBREW_NO_REQUIRE_TAP_TRUST" not in guidance.install_hint


def test_guidance_is_immutable():
    guidance = installation_guidance(detect_environment(system_name="Darwin"))

    with pytest.raises(FrozenInstanceError):
        guidance.install_hint = "other"


@pytest.mark.parametrize("state", list(RequirementState))
def test_installation_requirement_states_are_immutable(state):
    requirement = InstallationRequirement(
        name="example",
        state=state,
        message="safe message",
        remediation="safe remediation",
    )

    assert requirement.state is state
    with pytest.raises(FrozenInstanceError):
        requirement.state = RequirementState.AVAILABLE


def test_linux_guidance_does_not_install_non_runtime_libsecret_tools():
    for distribution in ("debian", "ubuntu", "arch", "fedora"):
        guidance = installation_guidance(
            detect_environment(
                system_name="Linux", os_release=f"ID={distribution}\n"
            )
        )

        assert "libsecret" not in guidance.install_hint
