from supa_cc.ui.render import UIRenderer
from supa_cc.ui.state import NavigationState, PageId
from supa_cc.strings import UIStrings as Strings
from helpers import RecordingConsole


def test_paint_home_shows_message_without_esc_footer():
    console = RecordingConsole(width=100, height=30)
    renderer = UIRenderer(console=console)
    state = NavigationState()
    state.set_message("ok", "success")

    renderer.paint_home(state, account_count=1)

    output = console.export_text()
    assert "Supa.cc" in output
    assert "1 saved account" in output
    assert "ok" in output
    assert "esc = back" not in output
    assert "Esc:" not in output


def test_paint_subpage_shows_title_without_esc_footer():
    console = RecordingConsole(width=100, height=30)
    renderer = UIRenderer(console=console)
    state = NavigationState()
    state.open(PageId.SWITCH)

    renderer.paint_subpage(state, title=Strings.MENU_SWITCH)

    output = console.export_text()
    assert Strings.MENU_SWITCH in output
    assert "esc = back" not in output
    assert "saved accounts" not in output
