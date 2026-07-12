from dataclasses import FrozenInstanceError

import pytest

from supa_cc.environment import detect_environment
from supa_cc.installation import installation_guidance


@pytest.mark.parametrize(
    ("system_name", "os_release", "command"),
    [
        ("Darwin", None, "brew install supa-cc"),
        ("Linux", "ID=debian\n", "sudo apt install python3 python3-venv pipx gnome-keyring libsecret-tools"),
        ("Linux", "ID=ubuntu\n", "sudo apt install python3 python3-venv pipx gnome-keyring libsecret-tools"),
        ("Linux", "ID=arch\n", "sudo pacman -S python python-pipx gnome-keyring libsecret"),
        ("Linux", "ID=fedora\n", "sudo dnf install python3 pipx gnome-keyring libsecret"),
    ],
)
def test_supported_platform_guidance_includes_display_only_install_commands(
    system_name, os_release, command
):
    guidance = installation_guidance(
        detect_environment(system_name=system_name, os_release=os_release)
    )

    assert command in guidance.install_hint
    assert 'pipx install "git+https://github.com/dgabreuu/supa.cc.git"' in guidance.install_hint
    assert "pipx install supa.cc" not in guidance.install_hint
    assert 'pipx install --force "git+https://github.com/dgabreuu/supa.cc.git"' in guidance.update_hint
    assert "pipx upgrade supa.cc" not in guidance.update_hint


def test_unsupported_linux_guidance_does_not_offer_package_manager_commands():
    guidance = installation_guidance(
        detect_environment(system_name="Linux", os_release="ID=void\n")
    )

    assert "apt" not in guidance.install_hint
    assert "pacman" not in guidance.install_hint
    assert "dnf" not in guidance.install_hint


def test_guidance_is_immutable():
    guidance = installation_guidance(detect_environment(system_name="Darwin"))

    with pytest.raises(FrozenInstanceError):
        guidance.install_hint = "other"
