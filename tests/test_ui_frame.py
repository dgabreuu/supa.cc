from rich.console import Console

from supa_cc.ui.render import UIRenderer
from supa_cc.ui.state import NavigationState, PageId
from supa_cc.ui.strings import UIStrings as Textos


def test_paint_home_shows_message_without_esc_footer():
    console = Console(record=True, width=100)
    renderer = UIRenderer(console=console)
    state = NavigationState()
    state.set_message("ok", "success")

    renderer.paint_home(state, account_count=1)

    output = console.export_text()
    assert "Supa.cc" in output
    assert "1 conta salva" in output
    assert "ok" in output
    assert "esc = voltar" not in output
    assert "Esc:" not in output


def test_paint_subpage_shows_title_and_body_without_esc_footer():
    console = Console(record=True, width=100)
    renderer = UIRenderer(console=console)
    state = NavigationState()
    state.open(PageId.LIST)

    rendered = {"body": False}

    def body():
        rendered["body"] = True
        console.print("BODY_CONTENT")

    renderer.paint_subpage(state, title=Textos.MENU_LIST, render_body=body)

    output = console.export_text()
    assert Textos.MENU_LIST in output
    assert "BODY_CONTENT" in output
    assert "esc = voltar" not in output
    assert rendered["body"] is True
    assert "contas salvas" not in output
