from dataclasses import dataclass
from enum import Enum
from typing import Optional


class MenuAction(Enum):
    ADD_ACCOUNT = "add_account"
    LIST_ACCOUNTS = "list_accounts"
    SWITCH_ACCOUNT = "switch_account"
    REMOVE_ACCOUNT = "remove_account"
    EXIT = "exit"


@dataclass
class UIMessage:
    text: str
    level: str = "info"


@dataclass
class NavigationState:
    running: bool = True
    last_action: Optional[MenuAction] = None
    last_message: Optional[UIMessage] = None

    def stop(self) -> None:
        self.running = False

    def set_message(self, text: str, level: str = "info") -> None:
        self.last_message = UIMessage(text=text, level=level)
