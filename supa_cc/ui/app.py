from typing import Callable, Dict, Optional

from ..accounts import AccountManager
from .render import UIRenderer
from .screens import TUIScreens
from .state import MenuAction, NavigationState
from .strings import UIStrings as Textos


class TUIApp:
    def __init__(
        self,
        manager: Optional[AccountManager] = None,
        renderer: Optional[UIRenderer] = None,
        screens: Optional[TUIScreens] = None,
        state: Optional[NavigationState] = None,
    ):
        self.state = state or NavigationState()
        self.renderer = renderer or UIRenderer()
        self.manager = manager or AccountManager()
        self.screens = screens or TUIScreens(self.manager, self.renderer)
        self.routes: Dict[MenuAction, Callable[[NavigationState], None]] = {
            MenuAction.ADD_ACCOUNT: self.screens.add_account,
            MenuAction.LIST_ACCOUNTS: self.screens.list_accounts,
            MenuAction.SWITCH_ACCOUNT: self.screens.switch_account,
            MenuAction.REMOVE_ACCOUNT: self.screens.remove_account,
        }

    def run(self) -> None:
        while self.state.running:
            action = self.screens.main_menu(self.state)
            if action is None or action == MenuAction.EXIT:
                self.state.stop()
                break

            self.state.last_action = action
            handler = self.routes.get(action)
            if handler is None:
                self.state.set_message(Textos.MSG_UNKNOWN_OPTION, "error")
                continue

            handler(self.state)

        self.renderer.show_goodbye()
