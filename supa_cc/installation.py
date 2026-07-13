from dataclasses import dataclass

from .environment import Environment, LinuxDistribution, OperatingSystem


DEBIAN = (
    "sudo apt install python3 python3-venv pipx gnome-keyring libsecret-tools"
)
ARCH = "sudo pacman -S python python-pipx gnome-keyring libsecret"
FEDORA = "sudo dnf install python3 pipx gnome-keyring libsecret"
VCS_INSTALL = 'pipx install "git+https://github.com/dgabreuu/supa.cc.git"'
VCS_UPDATE = 'pipx install --force "git+https://github.com/dgabreuu/supa.cc.git"'


@dataclass(frozen=True)
class InstallationGuidance:
    install_hint: str
    update_hint: str
    remediation: str


def installation_guidance(environment: Environment) -> InstallationGuidance:
    if environment.operating_system is OperatingSystem.MACOS:
        return InstallationGuidance(
            install_hint=f"brew install supa-cc; or {VCS_INSTALL}",
            update_hint=(
                "brew upgrade supa-cc or brew upgrade --fetch-HEAD supa-cc; "
                f"for pipx: {VCS_UPDATE}"
            ),
            remediation="Check whether the macOS credential store is available.",
        )

    if environment.operating_system is OperatingSystem.WINDOWS:
        return InstallationGuidance(
            install_hint=VCS_INSTALL,
            update_hint=VCS_UPDATE,
            remediation=(
                "Check whether Windows Credential Manager is available "
                "for the user session."
            ),
        )

    commands = {
        LinuxDistribution.DEBIAN: DEBIAN,
        LinuxDistribution.UBUNTU: DEBIAN,
        LinuxDistribution.ARCH: ARCH,
        LinuxDistribution.FEDORA: FEDORA,
    }
    command = commands.get(environment.distribution)
    if command is not None:
        return InstallationGuidance(
            install_hint=f"Prerequisites (informational only): {command}; {VCS_INSTALL}",
            update_hint=VCS_UPDATE,
            remediation=(
                "Install the listed prerequisites and verify that the Secret "
                "Service is available and unlocked."
            ),
        )

    return InstallationGuidance(
        install_hint="This Linux system is not supported for automatic installation.",
        update_hint=VCS_UPDATE,
        remediation="Use a supported Linux distribution and configure a compatible credential store.",
    )
