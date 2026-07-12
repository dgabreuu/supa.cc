import os
import platform
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Mapping, Optional


class OperatingSystem(str, Enum):
    MACOS = "macos"
    LINUX = "linux"
    WINDOWS = "windows"
    UNSUPPORTED = "unsupported"


class LinuxDistribution(str, Enum):
    DEBIAN = "debian"
    UBUNTU = "ubuntu"
    ARCH = "arch"
    FEDORA = "fedora"
    UNKNOWN = "unknown"


_UNSET = object()
_SUPPORTED_DISTRIBUTIONS = {
    distribution.value: distribution
    for distribution in LinuxDistribution
    if distribution is not LinuxDistribution.UNKNOWN
}


@dataclass(frozen=True)
class Environment:
    operating_system: OperatingSystem
    distribution: Optional[LinuxDistribution] = None

    @property
    def is_supported(self) -> bool:
        return self.operating_system in {
            OperatingSystem.MACOS,
            OperatingSystem.WINDOWS,
        } or (
            self.operating_system is OperatingSystem.LINUX
            and self.distribution not in {None, LinuxDistribution.UNKNOWN}
        )

    def config_directory(
        self, environ: Optional[Mapping[str, str]] = None, home=None
    ) -> Path:
        values = os.environ if environ is None else environ
        user_home = Path.home() if home is None else Path(home)
        if self.operating_system is OperatingSystem.WINDOWS:
            appdata = values.get("APPDATA")
            if not appdata or not Path(appdata).is_absolute():
                raise OSError("APPDATA não define um diretório absoluto confiável.")
            return Path(appdata) / "supa.cc"
        if self.operating_system is OperatingSystem.LINUX:
            xdg_home = values.get("XDG_CONFIG_HOME")
            if xdg_home and Path(xdg_home).is_absolute():
                return Path(xdg_home) / "supa.cc"
        return user_home / ".config" / "supa.cc"


def _read_os_release() -> Optional[str]:
    try:
        return Path("/etc/os-release").read_text(encoding="utf-8")
    except OSError:
        return None


def _os_release_values(os_release: Optional[str]) -> Mapping[str, str]:
    if not isinstance(os_release, str):
        return {}

    values = {}
    for line in os_release.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if not key or not key.replace("_", "").isalnum():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def _linux_distribution(os_release: Optional[str]) -> LinuxDistribution:
    values = _os_release_values(os_release)
    distribution = _SUPPORTED_DISTRIBUTIONS.get(values.get("ID", "").lower())
    if distribution is not None:
        return distribution

    for name in values.get("ID_LIKE", "").lower().split():
        distribution = _SUPPORTED_DISTRIBUTIONS.get(name)
        if distribution is not None:
            return distribution
    return LinuxDistribution.UNKNOWN


def detect_environment(
    system_name: Optional[str] = None, os_release=_UNSET
) -> Environment:
    name = platform.system() if system_name is None else system_name
    if name == "Darwin":
        return Environment(OperatingSystem.MACOS)
    if name == "Linux":
        release = _read_os_release() if os_release is _UNSET else os_release
        return Environment(OperatingSystem.LINUX, _linux_distribution(release))
    if name == "Windows":
        return Environment(OperatingSystem.WINDOWS)
    return Environment(OperatingSystem.UNSUPPORTED)


def config_directory() -> Path:
    return detect_environment().config_directory()
