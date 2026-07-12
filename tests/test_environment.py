from pathlib import Path

from supa_cc.environment import (
    LinuxDistribution,
    OperatingSystem,
    detect_environment,
)


def test_detect_environment_recognizes_supported_linux_id():
    environment = detect_environment(
        system_name="Linux",
        os_release='ID="ubuntu"\nID_LIKE="debian"\n',
    )

    assert environment.operating_system is OperatingSystem.LINUX
    assert environment.distribution is LinuxDistribution.UBUNTU
    assert environment.is_supported


def test_detect_environment_uses_supported_id_like_family():
    environment = detect_environment(
        system_name="Linux", os_release="ID=pop\nID_LIKE=ubuntu debian\n"
    )

    assert environment.distribution is LinuxDistribution.UBUNTU
    assert environment.is_supported


def test_detect_environment_marks_missing_or_malformed_linux_release_unknown():
    missing = detect_environment(system_name="Linux", os_release=None)
    malformed = detect_environment(system_name="Linux", os_release="not-a-value")

    assert missing.distribution is LinuxDistribution.UNKNOWN
    assert malformed.distribution is LinuxDistribution.UNKNOWN
    assert missing.is_supported is False
    assert malformed.is_supported is False


def test_detect_environment_marks_other_operating_systems_unsupported():
    environment = detect_environment(system_name="Windows")

    assert environment.operating_system is OperatingSystem.UNSUPPORTED
    assert environment.distribution is None
    assert environment.is_supported is False


def test_linux_config_directory_honors_xdg_config_home(tmp_path):
    environment = detect_environment(
        system_name="Linux", os_release="ID=fedora\n"
    )

    assert environment.config_directory({"XDG_CONFIG_HOME": str(tmp_path)}) == (
        tmp_path / "supa.cc"
    )


def test_linux_config_directory_falls_back_to_home_when_xdg_is_empty(tmp_path):
    environment = detect_environment(system_name="Linux", os_release="ID=arch\n")

    assert environment.config_directory(
        {"XDG_CONFIG_HOME": ""}, home=tmp_path
    ) == (tmp_path / ".config" / "supa.cc")


def test_linux_config_directory_ignores_relative_xdg_config_home(tmp_path):
    environment = detect_environment(system_name="Linux", os_release="ID=arch\n")

    assert environment.config_directory(
        {"XDG_CONFIG_HOME": "relative/config"}, home=tmp_path
    ) == (tmp_path / ".config" / "supa.cc")


def test_macos_config_directory_preserves_existing_default(tmp_path):
    environment = detect_environment(system_name="Darwin")

    assert environment.config_directory({}, home=tmp_path) == (
        tmp_path / ".config" / "supa.cc"
    )
