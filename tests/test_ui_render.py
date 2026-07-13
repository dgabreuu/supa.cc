from supa_cc.ui.render import UIRenderer
from supa_cc.ui.state import NavigationState
from supa_cc.ui.theme import BANNER_MEDIUM, BANNER_COMPACT
from helpers import RecordingConsole

def test_stylized_banner_uses_project_name():
    expected = r"""
 ____
/ ___| _   _ _ __   __ _   ___ ___
\___ \| | | | '_ \ / _` | / __/ __|
 ___) | |_| | |_) | (_| || (_| (__
|____/ \__,_| .__/ \__,_(_)___\___|
            |_|
""".strip("\n")

    assert _normalize_banner(BANNER_MEDIUM) == expected


def _normalize_banner(banner: str) -> str:
    return "\n".join(line.rstrip() for line in banner.splitlines())


def test_home_screen_renders_medium_banner_in_wide_terminal():
    console = RecordingConsole(width=100, height=30)
    renderer = UIRenderer(console=console)
    state = NavigationState()
    state.set_message("Account switched", "success")

    renderer.show_home(state, account_count=2)

    output = console.export_text()
    assert "Supa.cc" in output
    assert "2 saved accounts" in output
    assert "Account switched" in output


def test_home_screen_renders_compact_banner_in_narrow_terminal():
    console = RecordingConsole(width=40, height=30)
    renderer = UIRenderer(console=console)
    state = NavigationState()

    renderer.show_home(state, account_count=1)

    output = console.export_text()
    assert "Supa.cc" in output
    assert "1 saved account" in output
    for line in BANNER_COMPACT.splitlines():
        assert line.strip() in output or line.lstrip() in output
