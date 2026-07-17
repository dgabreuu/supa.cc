from typing import Any, List

import questionary
from prompt_toolkit.styles import Style as PTKStyle
from questionary import Choice

from ..accounts import AccountService
from ..auth import classify_local_failure
from .animations import loading
from .navigation import DEFAULT_POINTER, choices_with_back
from .render import UIRenderer
from .state import MenuAction, NavigationState, PageId
from ..strings import UIStrings as Strings
from .theme import QUESTIONARY_STYLE


MAIN_MENU_CHOICES = [
    Choice(title=Strings.MENU_ADD, value=MenuAction.ADD_ACCOUNT),
    Choice(title=Strings.MENU_SWITCH, value=MenuAction.SWITCH_ACCOUNT),
    Choice(title=Strings.MENU_REMOVE, value=MenuAction.REMOVE_ACCOUNT),
    Choice(title=Strings.MENU_EXIT, value=MenuAction.EXIT),
]

ACTION_TO_PAGE = {
    MenuAction.ADD_ACCOUNT: PageId.ADD,
    MenuAction.SWITCH_ACCOUNT: PageId.SWITCH,
    MenuAction.REMOVE_ACCOUNT: PageId.REMOVE,
}


class TUIScreens:
    def __init__(
        self,
        manager: AccountService,
        renderer: UIRenderer,
        prompts: Any = questionary,
        style: PTKStyle = QUESTIONARY_STYLE,
    ):
        self.manager = manager
        self.renderer = renderer
        self.prompts = prompts
        self.style = style

    def _ask(self, question: Any) -> Any:
        return question.ask()

    def _create_prompt(self, factory: Any, *args: Any, **kwargs: Any) -> Any:
        kwargs["erase_when_done"] = True
        return factory(*args, **kwargs)

    def _select(self, message: str, choices: List) -> Any:
        # No default: avoids "selected" highlight on first option.
        # Standard pointer for normal items; Back carries its arrow in its formatted title.
        return self._ask(
            self._create_prompt(
                self.prompts.select,
                message,
                choices=choices,
                style=self.style,
                pointer=DEFAULT_POINTER,
                use_indicator=False,
            )
        )

    def _text(self, message: str) -> Any:
        return self._ask(
            self._create_prompt(self.prompts.text, message, style=self.style)
        )

    def _password(self, message: str) -> Any:
        return self._ask(
            self._create_prompt(self.prompts.password, message, style=self.style)
        )

    def _confirm(self, message: str, default: bool = False) -> Any:
        return self._ask(
            self._create_prompt(
                self.prompts.confirm,
                message,
                default=default,
                style=self.style,
            )
        )

    def _account_choices(self, accounts: List) -> List:
        base = [Choice(title=account.name, value=account.name) for account in accounts]
        return choices_with_back(base)

    def _load_accounts(self, state: NavigationState):
        try:
            return self.manager.list()
        except Exception as error:
            result = classify_local_failure(error)
            state.set_message(result.message, "error")
            state.record_failure(result.exit_code)
            state.stop()
            self.renderer.paint_home(state, account_count=0)
            return None

    def home(self, state: NavigationState) -> None:
        accounts = self._load_accounts(state)
        if accounts is None:
            return
        try:
            active_account = self.manager.get_active_name()
        except AttributeError:
            active_account = None
        except Exception as error:
            result = classify_local_failure(error)
            state.set_message(result.message, "error")
            state.record_failure(result.exit_code)
            active_account = None
        self.renderer.paint_home(
            state,
            account_count=len(accounts),
            active_account=active_account,
        )
        action = self._select(Strings.MENU_TITLE, MAIN_MENU_CHOICES)

        if action is None or action == MenuAction.EXIT:
            state.stop()
            return

        page = ACTION_TO_PAGE.get(action)
        if page is None:
            state.set_message(Strings.MSG_UNKNOWN_OPTION, "error")
            return

        state.open(page)

    def add_account(self, state: NavigationState) -> None:
        self.renderer.paint_subpage(state, title=Strings.MENU_ADD)

        name = self._text(Strings.PROMPT_ACCOUNT_NAME)
        if name is None:
            state.go_home()
            return
        if not name.strip():
            state.set_message(Strings.MSG_ACCOUNT_REQUIRED, "warning")
            state.go_home()
            return

        token = self._password(Strings.PROMPT_ACCESS_TOKEN)
        if token is None:
            state.go_home()
            return
        if not token:
            state.set_message(Strings.MSG_TOKEN_REQUIRED, "warning")
            state.go_home()
            return

        name = name.strip()
        try:
            result = self.manager.add(name, token)
            if result.ok:
                state.set_message(Strings.MSG_ACCOUNT_ADDED.format(name), "success")
            else:
                state.set_message(result.message, "error")
                state.record_failure(result.exit_code)
        except Exception as error:
            result = classify_local_failure(error)
            state.set_message(result.message, "error")
            state.record_failure(result.exit_code)

        state.go_home()

    def switch_account(self, state: NavigationState) -> None:
        accounts = self._load_accounts(state)
        if accounts is None:
            state.go_home()
            return
        if not accounts:
            state.set_message(Strings.MSG_NO_ACCOUNTS_SWITCH, "warning")
            state.go_home()
            return

        self.renderer.paint_subpage(state, title=Strings.MENU_SWITCH)
        name = self._select(
            Strings.PROMPT_SELECT_ACCOUNT,
            self._account_choices(accounts),
        )

        if name is None or name == MenuAction.BACK:
            state.go_home()
            return

        try:
            with loading(Strings.LOADING_SWITCH_ACCOUNT, console=self.renderer.console):
                result = self.manager.set_active(
                    name,
                    token_provider=lambda _name: self._password(
                        Strings.PROMPT_RESTORE_ACCESS_TOKEN.format(name)
                    ),
                )
        except Exception as error:
            result = classify_local_failure(error, operation="switch")

        if result.ok:
            state.set_message(result.message, "success")
        else:
            state.set_message(result.message, "error")
            state.record_failure(result.exit_code)

        state.go_home()

    def remove_account(self, state: NavigationState) -> None:
        accounts = self._load_accounts(state)
        if accounts is None:
            state.go_home()
            return
        if not accounts:
            state.set_message(Strings.MSG_NO_ACCOUNTS_REMOVE, "warning")
            state.go_home()
            return

        self.renderer.paint_subpage(state, title=Strings.MENU_REMOVE)
        name = self._select(
            Strings.PROMPT_SELECT_REMOVE,
            self._account_choices(accounts),
        )

        if name is None or name == MenuAction.BACK:
            state.go_home()
            return

        confirmed = self._confirm(Strings.PROMPT_CONFIRM_REMOVE.format(name), default=False)
        if confirmed is None or not confirmed:
            state.go_home()
            return

        try:
            result = self.manager.remove(name)
        except Exception as error:
            result = classify_local_failure(error)
            state.set_message(result.message, "error")
            state.record_failure(result.exit_code)
        else:
            if not result.ok:
                state.set_message(result.message, "error")
                state.record_failure(result.exit_code)
                state.go_home()
                return
            state.set_message(Strings.MSG_ACCOUNT_REMOVED.format(name), "success")
        state.go_home()
