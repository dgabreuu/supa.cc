from unittest.mock import Mock, patch

from supa_cc import tui
from supa_cc.auth import AccountIndexReadError
from supa_cc.ui.app import TUIApp
from supa_cc.ui.state import MenuAction, NavigationState, PageId


class FakeRenderer:
    def __init__(self):
        self.goodbye_calls = 0
        self.start_frame_calls = 0
        self.home_paints = 0
        self.subpage_paints = []

    def start_frame(self):
        self.start_frame_calls += 1

    def paint_home(self, state, account_count, active_account=None):
        self.home_paints += 1

    def paint_subpage(self, state, title):
        self.subpage_paints.append(title)

    def show_goodbye(self):
        self.goodbye_calls += 1


class FakeScreens:
    def __init__(self, script):
        """script: list of callables(state) executed in order per home/page visit."""
        self.script = list(script)
        self.calls = []

    def home(self, state):
        self.calls.append("home")
        self.script.pop(0)(state)

    def add_account(self, state):
        self.calls.append("add_account")
        self.script.pop(0)(state)

    def switch_account(self, state):
        self.calls.append("switch_account")
        self.script.pop(0)(state)

    def remove_account(self, state):
        self.calls.append("remove_account")
        self.script.pop(0)(state)


def test_run_routes_home_to_switch_and_back_until_exit():
    def open_switch(state):
        state.open(PageId.SWITCH)

    def back_home(state):
        state.go_home()

    def exit_app(state):
        state.stop()

    screens = FakeScreens([open_switch, back_home, exit_app])
    renderer = FakeRenderer()
    state = NavigationState()
    app = TUIApp(screens=screens, renderer=renderer, state=state)

    exit_code = app.run()

    assert screens.calls == ["home", "switch_account", "home"]
    assert state.running is False
    assert renderer.start_frame_calls == 1
    assert renderer.goodbye_calls == 1
    assert exit_code == 0


def test_run_exits_when_home_stops():
    def exit_app(state):
        state.stop()

    screens = FakeScreens([exit_app])
    renderer = FakeRenderer()
    state = NavigationState()
    app = TUIApp(screens=screens, renderer=renderer, state=state)

    exit_code = app.run()

    assert screens.calls == ["home"]
    assert state.running is False
    assert renderer.goodbye_calls == 1
    assert exit_code == 0


def test_run_opens_add_page_from_home():
    def open_add(state):
        state.open(PageId.ADD)

    def finish_add(state):
        state.set_message("Account added", "success")
        state.go_home()

    def exit_app(state):
        state.stop()

    screens = FakeScreens([open_add, finish_add, exit_app])
    renderer = FakeRenderer()
    state = NavigationState()
    app = TUIApp(screens=screens, renderer=renderer, state=state)

    app.run()

    assert screens.calls == ["home", "add_account", "home"]
    assert state.last_message.text == "Account added"


def test_run_preserves_nonzero_exit_after_later_success_and_goodbye():
    def fail_then_continue(state):
        state.record_failure(9)
        state.open(PageId.SWITCH)

    def recover(state):
        state.go_home()

    def exit_app(state):
        state.stop()

    screens = FakeScreens([fail_then_continue, recover, exit_app])
    renderer = FakeRenderer()
    state = NavigationState()
    app = TUIApp(screens=screens, renderer=renderer, state=state)

    exit_code = app.run()

    assert exit_code == 9
    assert renderer.goodbye_calls == 1


def test_real_screens_paint_classified_failure_before_goodbye_from_subpage():
    events = []

    class FailingManager:
        def list(self):
            raise AccountIndexReadError("private")

    class OrderedRenderer(FakeRenderer):
        def paint_home(self, state, account_count, active_account=None):
            events.append(("paint", state.last_message.text))

        def show_goodbye(self):
            events.append(("goodbye", None))

    state = NavigationState(current_page=PageId.SWITCH)
    app = TUIApp(
        manager=FailingManager(),
        renderer=OrderedRenderer(),
        state=state,
    )

    exit_code = app.run()

    assert exit_code != 0
    assert events == [
        ("paint", "Unable to read the local account index."),
        ("goodbye", None),
    ]


def test_tui_entrypoint_returns_app_exit_code():
    app = Mock()
    app.run.return_value = 6
    with patch("supa_cc.tui.TUIApp", return_value=app):
        assert tui.run() == 6
