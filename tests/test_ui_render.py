from rich.console import Console

from supa_cc.models import Account
from supa_cc.ui.render import UIRenderer
from supa_cc.ui.state import NavigationState
from supa_cc.ui.theme import SUPA_CC_BANNER

from helpers import fake_pat


def test_stylized_banner_uses_project_name():
    expected = r"""
 ____
/ ___| _   _ _ __   __ _   ___ ___
\___ \| | | | '_ \ / _` | / __/ __|
 ___) | |_| | |_) | (_| || (_| (__
|____/ \__,_| .__/ \__,_(_)___\___|
            |_|
""".strip("\n")

    assert _normalize_banner(SUPA_CC_BANNER) == expected


def _normalize_banner(banner: str) -> str:
    return "\n".join(line.rstrip() for line in banner.splitlines())


def test_home_screen_renders_banner_title_and_status_message():
    console = Console(record=True, width=100)
    renderer = UIRenderer(console=console)
    state = NavigationState()
    state.set_message("Account switched", "success")

    renderer.show_home(state, account_count=2)

    output = console.export_text()
    assert "Supa.cc" in output
    assert "2 contas salvas" in output
    assert "Account switched" in output


def test_accounts_table_renders_account_names():
    console = Console(record=True, width=100)
    renderer = UIRenderer(console=console)
    accounts = [
        Account(name="example_alpha", token=fake_pat("token_alpha")),
        Account(name="example_beta", token=fake_pat("token_beta")),
    ]

    renderer.show_accounts(accounts)

    output = console.export_text()
    assert "example_alpha" in output
    assert "example_beta" in output
