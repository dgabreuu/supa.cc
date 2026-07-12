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
            install_hint=f"brew install supa-cc; ou {VCS_INSTALL}",
            update_hint=(
                "brew upgrade supa-cc ou brew upgrade --fetch-HEAD supa-cc; "
                f"para pipx: {VCS_UPDATE}"
            ),
            remediation="Verifique se o armazenamento de credenciais do macOS está disponível.",
        )

    if environment.operating_system is OperatingSystem.WINDOWS:
        return InstallationGuidance(
            install_hint=VCS_INSTALL,
            update_hint=VCS_UPDATE,
            remediation=(
                "Verifique se o Windows Credential Manager está disponível "
                "para a sessão do usuário."
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
            install_hint=f"Pré-requisitos (apenas informativo): {command}; {VCS_INSTALL}",
            update_hint=VCS_UPDATE,
            remediation=(
                "Instale os pré-requisitos indicados e verifique se o Secret "
                "Service está disponível e desbloqueado."
            ),
        )

    return InstallationGuidance(
        install_hint="Este sistema Linux não é suportado para instalação automática.",
        update_hint=VCS_UPDATE,
        remediation="Use uma distribuição Linux suportada e configure um armazenamento de credenciais compatível.",
    )
