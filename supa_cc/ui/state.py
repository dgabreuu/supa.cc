from dataclasses import dataclass
from enum import Enum
from typing import Optional


class PageId(Enum):
    HOME = "home"
    ADD = "add"
    LIST = "list"
    SWITCH = "switch"
    REMOVE = "remove"


class MenuAction(Enum):
    ADD_ACCOUNT = "add_account"
    LIST_ACCOUNTS = "list_accounts"
    SWITCH_ACCOUNT = "switch_account"
    REMOVE_ACCOUNT = "remove_account"
    BACK = "back"
    EXIT = "exit"


@dataclass
class UIMessage:
    text: str
    level: str = "info"


@dataclass
class NavigationState:
    running: bool = True
    current_page: PageId = PageId.HOME
    last_action: Optional[MenuAction] = None
    last_message: Optional[UIMessage] = None
    exit_code: int = 0

    def stop(self) -> None:
        self.running = False

    def record_failure(self, exit_code: int = 1) -> None:
        code = exit_code if 1 <= int(exit_code) <= 255 else 1
        if self.exit_code == 0:
            self.exit_code = code

    def open(self, page: PageId) -> None:
        self.current_page = page

    def go_home(self) -> None:
        self.current_page = PageId.HOME

    def set_message(self, text: str, level: str = "info") -> None:
        self.last_message = UIMessage(text=text, level=level)

    def clear_message(self) -> None:
        self.last_message = None
