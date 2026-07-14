from supa_cc.environment import detect_environment
from supa_cc.installation import (
    InstallationChannel,
    detect_installation_channel,
    installation_guidance,
)


class FakeDistribution:
    def __init__(self, direct_url=None, installer=None):
        self.direct_url = direct_url
        self.installer = installer

    def read_text(self, name):
        if name == "direct_url.json":
            return self.direct_url
        if name == "INSTALLER":
            return self.installer
        return None


def test_detects_editable_and_vcs_installations_without_subprocesses():
    editable = FakeDistribution(
        '{"url":"file:///safe/source","dir_info":{"editable":true}}', "pip"
    )
    vcs = FakeDistribution(
        '{"url":"https://example.invalid/repository.git","vcs_info":{"vcs":"git"}}',
        "pip",
    )

    assert detect_installation_channel(distribution=editable) is InstallationChannel.EDITABLE
    assert detect_installation_channel(distribution=vcs) is InstallationChannel.VCS


def test_editable_metadata_takes_precedence_over_pipx_runtime():
    editable = FakeDistribution(
        '{"url":"file:///safe/source","dir_info":{"editable":true}}', "pip"
    )

    assert detect_installation_channel(
        distribution=editable,
        executable="/safe/pipx/venvs/supa-cc/bin/python",
    ) is InstallationChannel.EDITABLE


def test_local_wheel_metadata_is_reported_without_exposing_its_path():
    wheel = FakeDistribution(
        '{"url":"file:///private/location/supa_cc-0.5.0.dev1.whl",'
        '"archive_info":{"hash":"sha256=safe"}}',
        "pip",
    )

    assert detect_installation_channel(
        distribution=wheel,
        executable="/safe/pipx/venvs/supa-cc/bin/python",
    ) is InstallationChannel.WHEEL


def test_detects_homebrew_from_runtime_prefix():
    channel = detect_installation_channel(
        distribution=FakeDistribution(installer="pip"),
        executable="/opt/homebrew/Cellar/supa-cc/0.5.0/libexec/bin/python",
    )

    assert channel is InstallationChannel.HOMEBREW


def test_macos_editable_update_guidance_does_not_recommend_brew_upgrade():
    guidance = installation_guidance(
        detect_environment(system_name="Darwin"),
        channel=InstallationChannel.EDITABLE,
    )

    assert "pipx install --force" in guidance.update_hint
    assert "brew upgrade" not in guidance.update_hint
