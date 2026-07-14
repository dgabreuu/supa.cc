from ..strings import UIStrings as Strings
from .console import console as default_console
from .layout import center_banner_lines, clear_screen, create_header, create_message
from .state import NavigationState, UIMessage
from .theme import OUTPUT_STYLES, get_banner


class UIRenderer:
    def __init__(self, console=None):
        self.console = console or default_console
        self._frame_started = False
        self._frame_line_count = 0

    def clear(self) -> None:
        clear_screen(self.console)

    def start_frame(self) -> None:
        if self._frame_started:
            return

        self.clear()
        banner = center_banner_lines(
            get_banner(self.console.width, self.console.height)
        )
        self.console.print(banner, style=OUTPUT_STYLES["banner"])
        self.console.print(
            f"{Strings.APP_NAME} · {Strings.APP_DESCRIPTION}",
            style=OUTPUT_STYLES["title"],
        )
        self._frame_line_count = len(banner.splitlines()) + 1
        self._frame_started = True

    def _clear_dynamic_region(self) -> None:
        self.start_frame()
        self.console.clear_below(self._frame_line_count)

    def paint_home(
        self,
        state: NavigationState,
        account_count: int,
        active_account=None,
    ) -> None:
        self._clear_dynamic_region()
        self.show_home(state, account_count, active_account=active_account)

    def paint_subpage(self, state: NavigationState, title: str) -> None:
        self._clear_dynamic_region()
        self.console.print(
            create_header(title),
            style=OUTPUT_STYLES["title"],
        )

    def show_home(
        self,
        state: NavigationState,
        account_count: int,
        active_account=None,
    ) -> None:
        self.start_frame()
        account_label = (
            Strings.ACCOUNT_COUNT_ONE
            if account_count == 1
            else Strings.ACCOUNT_COUNT_MANY
        )
        active = active_account or Strings.ACTIVE_ACCOUNT_NONE
        self.console.print(
            f"{account_count} {account_label} · {Strings.ACTIVE_ACCOUNT}: {active}",
            style=OUTPUT_STYLES["info"],
        )
        if state.last_message:
            self.show_message(state.last_message)

    def show_message(self, message: UIMessage) -> None:
        self.console.print(
            create_message(message.text, message.level),
            style=OUTPUT_STYLES.get(message.level, OUTPUT_STYLES["info"]),
        )

    def show_goodbye(self) -> None:
        self.console.print(
            Strings.MSG_GOODBYE,
            style=OUTPUT_STYLES["highlight"],
        )
