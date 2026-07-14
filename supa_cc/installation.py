import json
import sys
from dataclasses import dataclass
from enum import Enum
from importlib import metadata

from .environment import Environment, LinuxDistribution, OperatingSystem


DEBIAN = (
    "sudo apt install python3 python3-venv pipx gnome-keyring libsecret-tools"
)
ARCH = "sudo pacman -S python python-pipx gnome-keyring libsecret"
FEDORA = "sudo dnf install python3 pipx gnome-keyring libsecret"
VCS_INSTALL = 'pipx install "git+https://github.com/dgabreuu/supa.cc.git"'
VCS_UPDATE = 'pipx install --force "git+https://github.com/dgabreuu/supa.cc.git"'
HOMEBREW_TAP = "dgabreuu/supa-cc"
HOMEBREW_FORMULA = f"{HOMEBREW_TAP}/supa-cc"
HOMEBREW_TAP_COMMAND = (
    f"brew tap {HOMEBREW_TAP} https://github.com/dgabreuu/supa.cc.git"
)
HOMEBREW_INSTALL = f"brew install {HOMEBREW_FORMULA}"
HOMEBREW_UPDATE = f"brew upgrade {HOMEBREW_FORMULA}"
HOMEBREW_HEAD_UPDATE = f"brew upgrade --fetch-HEAD {HOMEBREW_FORMULA}"


@dataclass(frozen=True)
class InstallationGuidance:
    install_hint: str
    update_hint: str
    remediation: str


class InstallationChannel(str, Enum):
    HOMEBREW = "homebrew"
    PIPX = "pipx"
    EDITABLE = "editable"
    VCS = "vcs"
    WHEEL = "wheel"
    PACKAGE = "package"
    UNKNOWN = "unknown"


def detect_installation_channel(
    *, distribution=None, executable=None
) -> InstallationChannel:
    """Infer the local install channel from package metadata without subprocesses."""
    runtime = str(sys.executable if executable is None else executable).lower()
    if distribution is None:
        try:
            distribution = metadata.distribution("supa.cc")
        except metadata.PackageNotFoundError:
            return InstallationChannel.UNKNOWN
    try:
        direct_url_text = distribution.read_text("direct_url.json")
        direct_url = json.loads(direct_url_text) if direct_url_text else {}
    except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
        direct_url = {}
    if isinstance(direct_url.get("dir_info"), dict) and direct_url[
        "dir_info"
    ].get("editable") is True:
        return InstallationChannel.EDITABLE
    if isinstance(direct_url.get("vcs_info"), dict):
        return InstallationChannel.VCS
    direct_url_value = direct_url.get("url")
    if (
        isinstance(direct_url_value, str)
        and direct_url_value.lower().split("?", 1)[0].endswith(".whl")
        and isinstance(direct_url.get("archive_info"), dict)
    ):
        return InstallationChannel.WHEEL
    if "/cellar/" in runtime.replace("\\", "/"):
        return InstallationChannel.HOMEBREW
    if "pipx" in runtime and "venv" in runtime:
        return InstallationChannel.PIPX
    try:
        installer = (distribution.read_text("INSTALLER") or "").strip().lower()
    except AttributeError:
        installer = ""
    return InstallationChannel.PACKAGE if installer else InstallationChannel.UNKNOWN


def installation_guidance(
    environment: Environment,
    channel: InstallationChannel | None = None,
) -> InstallationGuidance:
    if environment.operating_system is OperatingSystem.MACOS:
        if channel in {
            InstallationChannel.PIPX,
            InstallationChannel.EDITABLE,
            InstallationChannel.VCS,
            InstallationChannel.WHEEL,
            InstallationChannel.PACKAGE,
        }:
            update_hint = VCS_UPDATE
        elif channel is InstallationChannel.HOMEBREW:
            update_hint = f"{HOMEBREW_UPDATE} or {HOMEBREW_HEAD_UPDATE}"
        else:
            update_hint = (
                f"{HOMEBREW_UPDATE} or {HOMEBREW_HEAD_UPDATE}; "
                f"for pipx: {VCS_UPDATE}"
            )
        return InstallationGuidance(
            install_hint=(
                f"{HOMEBREW_TAP_COMMAND} && {HOMEBREW_INSTALL}; or {VCS_INSTALL}"
            ),
            update_hint=update_hint,
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
