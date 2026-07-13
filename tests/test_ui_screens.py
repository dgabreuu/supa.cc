from unittest.mock import Mock

from supa_cc.accounts import AccountManager
from supa_cc.models import Account
from supa_cc.auth import (
    AccountIndexReadError,
    AccountTransactionError,
    AuthFailureCode,
    AuthResult,
    InvalidAccessTokenError,
)
from supa_cc.ui.screens import TUIScreens
from supa_cc.ui.state import MenuAction, NavigationState, PageId
from supa_cc.strings import UIStrings as Strings

from helpers import fake_pat


class FakeConsole:
    def __init__(self):
        self.lines = []

    def print(self, message, style=None):
        self.lines.append((message, style))


class FakeRenderer:
    def __init__(self):
        self.console = FakeConsole()
        self.home_paints = 0
        self.subpage_paints = []

    def paint_home(self, state, account_count, active_account=None):
        self.home_paints += 1

    def paint_subpage(self, state, title):
        self.subpage_paints.append(title)

    def show_goodbye(self):
        pass


class FakePrompt:
    def __init__(self, value):
        self.value = value

    def ask(self):
        return self.value


class SequencePrompts:
    def __init__(self, **queues):
        self.queues = {key: list(values) for key, values in queues.items()}
        self.select_calls = []

    def _next(self, kind):
        values = self.queues.get(kind, [])
        if not values:
            return FakePrompt(None)
        return FakePrompt(values.pop(0))

    def text(self, *args, **kwargs):
        return self._next("text")

    def password(self, *args, **kwargs):
        return self._next("password")

    def select(self, message, choices=None, **kwargs):
        self.select_calls.append(
            {"message": message, "choices": list(choices or []), "kwargs": kwargs}
        )
        return self._next("select")

    def confirm(self, *args, **kwargs):
        return self._next("confirm")


class FakeManager:
    def __init__(self, accounts=None, activate_result=None, active_name=None):
        self._accounts = list(accounts or [])
        self.activate_result = (
            AuthResult.success("Account activated in Supa.cc.")
            if activate_result is None
            else activate_result
        )
        self.activated = []
        self.added = []
        self.removed = []
        self.list_calls = 0
        self.active_name = active_name

    def add(self, name, token):
        self.added.append((name, token))
        self._accounts.append(Account(name=name, token=token))

    def list(self):
        self.list_calls += 1
        return list(self._accounts)

    def get_active_name(self):
        return self.active_name

    def set_active(self, name):
        self.activated.append(name)
        return self.activate_result

    def remove(self, name):
        self.removed.append(name)
        self._accounts = [a for a in self._accounts if a.name != name]


def test_home_opens_switch_page():
    screens = TUIScreens(
        manager=FakeManager(),
        renderer=FakeRenderer(),
        prompts=SequencePrompts(select=[MenuAction.SWITCH_ACCOUNT]),
    )
    state = NavigationState()

    screens.home(state)

    assert screens.renderer.home_paints == 1
    assert state.current_page == PageId.SWITCH


def test_home_exit_stops_app():
    screens = TUIScreens(
        manager=FakeManager(),
        renderer=FakeRenderer(),
        prompts=SequencePrompts(select=[MenuAction.EXIT]),
    )
    state = NavigationState()

    screens.home(state)

    assert state.running is False


def test_home_cancel_stops_app():
    screens = TUIScreens(
        manager=FakeManager(),
        renderer=FakeRenderer(),
        prompts=SequencePrompts(select=[None]),
    )
    state = NavigationState()

    screens.home(state)

    assert state.running is False


def test_home_select_uses_standard_pointer_without_default_selection():
    prompts = SequencePrompts(select=[MenuAction.EXIT])
    screens = TUIScreens(
        manager=FakeManager(),
        renderer=FakeRenderer(),
        prompts=prompts,
    )

    screens.home(NavigationState())

    kwargs = prompts.select_calls[0]["kwargs"]
    assert kwargs.get("default") is None
    assert kwargs.get("pointer") == "»"
    assert kwargs.get("use_indicator") is False


def test_add_account_success_returns_home_with_message():
    token = fake_pat("token")
    manager = FakeManager()
    screens = TUIScreens(
        manager=manager,
        renderer=FakeRenderer(),
        prompts=SequencePrompts(text=["work"], password=[token]),
    )
    state = NavigationState()
    state.open(PageId.ADD)

    screens.add_account(state)

    assert manager.added == [("work", token)]
    assert state.current_page == PageId.HOME
    assert state.last_message.text == "Account 'work' added."
    assert state.last_message.level == "success"
    assert screens.renderer.subpage_paints == [Strings.MENU_ADD]


def test_add_account_does_not_strip_token_whitespace_before_validation():
    token = f" {fake_pat('whitespace')} "
    manager = FakeManager()
    screens = TUIScreens(
        manager=manager,
        renderer=FakeRenderer(),
        prompts=SequencePrompts(text=["work"], password=[token]),
    )
    state = NavigationState()
    state.open(PageId.ADD)

    screens.add_account(state)

    assert manager.added == [("work", token)]


def test_add_account_with_whitespace_pat_is_rejected_by_real_contract():
    token = f" {fake_pat('whitespace_contract')} "
    keychain = Mock()
    manager = AccountManager(keychain=keychain)
    screens = TUIScreens(
        manager=manager,
        renderer=FakeRenderer(),
        prompts=SequencePrompts(text=["work"], password=[token]),
    )
    state = NavigationState()
    state.open(PageId.ADD)

    screens.add_account(state)

    assert state.last_message.level == "error"
    assert "Invalid token" in state.last_message.text
    keychain.add_account.assert_not_called()


def test_add_account_cancel_returns_home_without_error_message():
    screens = TUIScreens(
        manager=FakeManager(),
        renderer=FakeRenderer(),
        prompts=SequencePrompts(text=[None]),
    )
    state = NavigationState()
    state.open(PageId.ADD)

    screens.add_account(state)

    assert state.current_page == PageId.HOME
    assert state.last_message is None


def test_switch_account_success_returns_home():
    account = Account(name="work", token=fake_pat("token"))
    message = (
        "Account 'work' activated and native session synchronized."
    )
    manager = FakeManager(
        accounts=[account], activate_result=AuthResult.success(message)
    )
    prompts = SequencePrompts(select=["work"])
    screens = TUIScreens(
        manager=manager,
        renderer=FakeRenderer(),
        prompts=prompts,
    )
    state = NavigationState()
    state.open(PageId.SWITCH)

    screens.switch_account(state)

    assert manager.activated == ["work"]
    assert state.current_page == PageId.HOME
    assert state.last_message.text == message
    assert state.last_message.level == "success"
    assert prompts.select_calls[0]["kwargs"].get("default") is None
    assert prompts.select_calls[0]["kwargs"].get("pointer") == "»"
    assert manager.list_calls == 1


def test_switch_account_cancel_returns_home():
    account = Account(name="work", token=fake_pat("token"))
    screens = TUIScreens(
        manager=FakeManager(accounts=[account]),
        renderer=FakeRenderer(),
        prompts=SequencePrompts(select=[None]),
    )
    state = NavigationState()
    state.open(PageId.SWITCH)

    screens.switch_account(state)

    assert state.current_page == PageId.HOME
    assert state.last_message is None


def test_switch_account_failure_uses_same_typed_message_as_cli():
    account = Account(name="work", token=fake_pat("token"))
    failure = AuthResult.failure(
        AuthFailureCode.TOKEN_REJECTED,
        "The token was rejected by the Supabase API.",
        exit_code=9,
    )
    manager = FakeManager(accounts=[account], activate_result=failure)
    screens = TUIScreens(
        manager=manager,
        renderer=FakeRenderer(),
        prompts=SequencePrompts(select=["work"]),
    )
    state = NavigationState()
    state.open(PageId.SWITCH)

    screens.switch_account(state)

    assert state.current_page == PageId.HOME
    assert state.last_message.text == failure.message
    assert state.last_message.level == "error"


def test_remove_account_success_returns_home():
    account = Account(name="work", token=fake_pat("token"))
    manager = FakeManager(accounts=[account])
    screens = TUIScreens(
        manager=manager,
        renderer=FakeRenderer(),
        prompts=SequencePrompts(select=["work"], confirm=[True]),
    )
    state = NavigationState()
    state.open(PageId.REMOVE)

    screens.remove_account(state)

    assert manager.removed == ["work"]
    assert state.current_page == PageId.HOME
    assert state.last_message.text == "Account 'work' removed."
    assert manager.list_calls == 1


def test_add_account_sanitizes_token_like_errors():
    token = fake_pat("secret_token")

    class FailingManager(FakeManager):
        def add(self, name, token):
            raise ValueError(f"invalid token {token}")

    screens = TUIScreens(
        manager=FailingManager(),
        renderer=FakeRenderer(),
        prompts=SequencePrompts(text=["work"], password=[token]),
    )
    state = NavigationState()
    state.open(PageId.ADD)

    screens.add_account(state)

    assert token not in state.last_message.text
    assert state.last_message.text == "The local operation could not be completed."
    assert state.current_page == PageId.HOME


def test_add_account_reports_invalid_token_format_clearly():
    class FailingManager(FakeManager):
        def add(self, name, token):
            raise InvalidAccessTokenError("private token detail")

    screens = TUIScreens(
        manager=FailingManager(),
        renderer=FakeRenderer(),
        prompts=SequencePrompts(
            text=["work"], password=[fake_pat("invalid_format")]
        ),
    )
    state = NavigationState()
    state.open(PageId.ADD)

    screens.add_account(state)

    assert state.last_message.level == "error"
    assert "Invalid token: provide a Supabase PAT" in state.last_message.text
    assert "private token detail" not in state.last_message.text


def test_home_maps_index_read_failure_without_traceback():
    class FailingManager(FakeManager):
        def list(self):
            raise AccountIndexReadError("private index detail")

    screens = TUIScreens(
        manager=FailingManager(),
        renderer=FakeRenderer(),
        prompts=SequencePrompts(),
    )
    state = NavigationState()

    screens.home(state)

    assert state.last_message.level == "error"
    assert "Unable to read the local account index." == state.last_message.text
    assert "private" not in state.last_message.text
    assert state.running is False


def test_remove_maps_transaction_failure_without_traceback():
    account = Account(name="work", token=fake_pat("token"))

    class FailingManager(FakeManager):
        def remove(self, name):
            raise AccountTransactionError("private transaction detail")

    screens = TUIScreens(
        manager=FailingManager(accounts=[account]),
        renderer=FakeRenderer(),
        prompts=SequencePrompts(select=["work"], confirm=[True]),
    )
    state = NavigationState()
    state.open(PageId.REMOVE)

    screens.remove_account(state)

    assert state.last_message.level == "error"
    assert "could not be completed safely" in state.last_message.text
    assert "private" not in state.last_message.text


def test_remove_rejects_pat_like_name_without_echoing_or_keychain_mutation():
    token_like_name = fake_pat("remove_tui_namespace")
    keychain = Mock()
    keychain.list_accounts.return_value = [
        Account(name=token_like_name, token="")
    ]
    manager = AccountManager(keychain=keychain)
    screens = TUIScreens(
        manager=manager,
        renderer=FakeRenderer(),
        prompts=SequencePrompts(
            select=[token_like_name],
            confirm=[True],
        ),
    )
    state = NavigationState(current_page=PageId.REMOVE)

    screens.remove_account(state)

    assert state.last_message.level == "error"
    assert token_like_name not in state.last_message.text
    assert "Invalid account name" in state.last_message.text
    assert state.exit_code != 0
    keychain.remove_account.assert_not_called()
