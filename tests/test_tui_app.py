from supa_cc.ui.app import TUIApp
from supa_cc.ui.state import MenuAction, NavigationState


class FakeRenderer:
    def __init__(self):
        self.goodbye_calls = 0

    def show_goodbye(self):
        self.goodbye_calls += 1


class FakeScreens:
    def __init__(self, actions):
        self.actions = list(actions)
        self.calls = []

    def main_menu(self, state):
        self.calls.append("main_menu")
        return self.actions.pop(0)

    def add_account(self, state):
        self.calls.append("add_account")
        state.set_message("Account added", "success")

    def list_accounts(self, state):
        self.calls.append("list_accounts")
        state.set_message("Accounts listed", "info")

    def switch_account(self, state):
        self.calls.append("switch_account")
        state.set_message("Account switched", "success")

    def remove_account(self, state):
        self.calls.append("remove_account")
        state.set_message("Account removed", "success")


def test_run_returns_to_main_menu_after_action_until_exit():
    screens = FakeScreens([MenuAction.LIST_ACCOUNTS, MenuAction.EXIT])
    renderer = FakeRenderer()
    state = NavigationState()
    app = TUIApp(screens=screens, renderer=renderer, state=state)

    app.run()

    assert screens.calls == ["main_menu", "list_accounts", "main_menu"]
    assert state.running is False
    assert state.last_message.text == "Accounts listed"
    assert renderer.goodbye_calls == 1


def test_run_exits_when_main_menu_is_cancelled():
    screens = FakeScreens([None])
    renderer = FakeRenderer()
    state = NavigationState()
    app = TUIApp(screens=screens, renderer=renderer, state=state)

    app.run()

    assert screens.calls == ["main_menu"]
    assert state.running is False
    assert renderer.goodbye_calls == 1
