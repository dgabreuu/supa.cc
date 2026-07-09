from typing import Any, List

import questionary
from prompt_toolkit.styles import Style as PTKStyle
from questionary import Choice

from ..accounts import AccountManager
from .render import UIRenderer
from .state import MenuAction, NavigationState
from .strings import UIStrings as Textos
from .theme import QUESTIONARY_STYLE


MAIN_MENU_CHOICES = [
    Choice(title=Textos.MENU_ADD, value=MenuAction.ADD_ACCOUNT),
    Choice(title=Textos.MENU_LIST, value=MenuAction.LIST_ACCOUNTS),
    Choice(title=Textos.MENU_SWITCH, value=MenuAction.SWITCH_ACCOUNT),
    Choice(title=Textos.MENU_REMOVE, value=MenuAction.REMOVE_ACCOUNT),
    Choice(title=Textos.MENU_EXIT, value=MenuAction.EXIT),
]


class TUIScreens:
    def __init__(
        self,
        manager: AccountManager,
        renderer: UIRenderer,
        prompts: Any = questionary,
        style: PTKStyle = QUESTIONARY_STYLE,
    ):
        self.manager = manager
        self.renderer = renderer
        self.prompts = prompts
        self.style = style

    def _account_choices(self) -> List[Choice]:
        """Cria lista de choices a partir das contas cadastradas."""
        return [Choice(title=account.name, value=account.name) for account in self.manager.list()]

    def main_menu(self, state: NavigationState) -> Any:
        accounts = self.manager.list()
        self.renderer.show_home(state, account_count=len(accounts))
        return self.prompts.select(
            Textos.MENU_TITLE, choices=MAIN_MENU_CHOICES, style=self.style
        ).ask()

    def add_account(self, state: NavigationState) -> None:
        name = self.prompts.text(Textos.PROMPT_ACCOUNT_NAME, style=self.style).ask()
        if name is None or not name.strip():
            state.set_message(Textos.MSG_ACCOUNT_REQUIRED, "warning")
            return

        token = self.prompts.password(Textos.PROMPT_ACCESS_TOKEN, style=self.style).ask()
        if token is None or not token.strip():
            state.set_message(Textos.MSG_TOKEN_REQUIRED, "warning")
            return

        name = name.strip()
        try:
            self.manager.add(name, token.strip())
            state.set_message(Textos.MSG_ACCOUNT_ADDED.format(name), "success")
        except ValueError as error:
            message = str(error)
            if "sbp_" in message:
                message = "Erro de validação. Verifique os dados fornecidos."
            state.set_message(f"Erro: {message}", "error")

    def list_accounts(self, state: NavigationState) -> None:
        accounts = self.manager.list()
        if not accounts:
            state.set_message(Textos.MSG_NO_ACCOUNTS, "warning")
            return

        self.renderer.show_accounts(accounts)
        suffix = Textos.ACCOUNT_SUFFIX_ONE if len(accounts) == 1 else Textos.ACCOUNT_SUFFIX_MANY
        state.set_message(Textos.MSG_LISTED_ACCOUNTS.format(len(accounts), suffix), "info")

    def switch_account(self, state: NavigationState) -> None:
        accounts = self.manager.list()
        if not accounts:
            state.set_message(Textos.MSG_NO_ACCOUNTS_SWITCH, "warning")
            return

        name = self.prompts.select(
            Textos.PROMPT_SELECT_ACCOUNT, choices=self._account_choices(), style=self.style
        ).ask()
        if name is None:
            state.set_message(Textos.MSG_SWITCH_CANCELLED, "warning")
            return

        if self.manager.set_active(name):
            state.set_message(
                Textos.MSG_ACCOUNT_ACTIVATED.format(name),
                "success",
            )
        else:
            state.set_message(Textos.MSG_ACTIVATE_FAILED.format(name), "error")

    def remove_account(self, state: NavigationState) -> None:
        accounts = self.manager.list()
        if not accounts:
            state.set_message(Textos.MSG_NO_ACCOUNTS_REMOVE, "warning")
            return

        name = self.prompts.select(
            Textos.PROMPT_SELECT_REMOVE, choices=self._account_choices(), style=self.style
        ).ask()
        if name is None:
            state.set_message(Textos.MSG_REMOVE_CANCELLED, "warning")
            return

        confirmed = self.prompts.confirm(
            Textos.PROMPT_CONFIRM_REMOVE.format(name), default=False, style=self.style
        ).ask()
        if not confirmed:
            state.set_message(Textos.MSG_REMOVE_CANCELLED, "warning")
            return

        self.manager.remove(name)
        state.set_message(Textos.MSG_ACCOUNT_REMOVED.format(name), "success")
