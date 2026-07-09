from typing import Iterable

from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..models import Account
from .console import console as default_console
from .layout import create_message_panel
from .state import NavigationState, UIMessage
from .strings import UIStrings as Textos
from .theme import RICH_STYLES, SUPA_CC_BANNER


class UIRenderer:
    def __init__(self, console: Console = None):
        self.console = console or default_console

    def show_home(self, state: NavigationState, account_count: int) -> None:
        account_label = Textos.ACCOUNT_COUNT_ONE if account_count == 1 else Textos.ACCOUNT_COUNT_MANY
        body = Text()
        body.append(SUPA_CC_BANNER, style=RICH_STYLES["banner"])
        body.append(f"\n{Textos.APP_NAME}", style="bold white")
        body.append(f"\n{Textos.APP_DESCRIPTION}", style=RICH_STYLES["dim"])
        body.append(f"\n\n{account_count} {account_label}", style=RICH_STYLES["info"])

        self.console.print(
            Panel(
                Align.center(body),
                title=f"[bold {RICH_STYLES['border']}]{Textos.PANEL_TITLE}[/bold {RICH_STYLES['border']}]",
                subtitle=f"[{RICH_STYLES['subtitle']}]{Textos.APP_SUBTITLE}[/{RICH_STYLES['subtitle']}]",
                border_style=RICH_STYLES["border"],
                padding=(1, 2),
            )
        )

        if state.last_message:
            self.show_message(state.last_message)

    def show_message(self, message: UIMessage) -> None:
        panel = create_message_panel(message.text, message.level)
        self.console.print(panel)

    def show_accounts(self, accounts: Iterable[Account]) -> None:
        table = Table(title=Textos.TABLE_TITLE, border_style=RICH_STYLES["border"])
        table.add_column(Textos.TABLE_ACCOUNT, style="white")

        for account in accounts:
            table.add_row(account.name)

        self.console.print(table)

    def show_goodbye(self) -> None:
        self.console.print(
            Panel(
                Align.center(Text(Textos.MSG_GOODBYE, style=RICH_STYLES["highlight"])),
                border_style=RICH_STYLES["highlight"],
                padding=(1, 2),
            )
        )
