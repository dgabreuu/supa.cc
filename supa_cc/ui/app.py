from typing import Callable, Dict, Optional

from ..accounts import AccountService
from .render import UIRenderer
from .screens import TUIScreens
from .state import NavigationState, PageId


class TUIApp:
    def __init__(
        self,
        manager: Optional[AccountService] = None,
        renderer: Optional[UIRenderer] = None,
        screens: Optional[TUIScreens] = None,
        state: Optional[NavigationState] = None,
    ):
        self.state = state or NavigationState()
        self.renderer = renderer or UIRenderer()
        self.manager = manager or AccountService()
        self.screens = screens or TUIScreens(self.manager, self.renderer)
        self.routes: Dict[PageId, Callable[[NavigationState], None]] = {
            PageId.HOME: self.screens.home,
            PageId.ADD: self.screens.add_account,
            PageId.SWITCH: self.screens.switch_account,
            PageId.REMOVE: self.screens.remove_account,
        }

    def run(self) -> int:
        self.renderer.start_frame()
        while self.state.running:
            handler = self.routes.get(self.state.current_page)
            if handler is None:
                self.state.go_home()
                continue
            handler(self.state)

        self.renderer.show_goodbye()
        return self.state.exit_code
