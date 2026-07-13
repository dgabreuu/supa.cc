import shutil
import sys

import questionary


class TerminalConsole:
    """Small output adapter backed by Questionary/prompt-toolkit."""

    def __init__(self, printer=None, width=None, height=None, is_terminal=None):
        size = shutil.get_terminal_size(fallback=(80, 24))
        self.width = width if width is not None else size.columns
        self.height = height if height is not None else size.lines
        self.is_terminal = (
            sys.stdout.isatty() if is_terminal is None else is_terminal
        )
        self._printer = printer or questionary.print

    def print(self, text="", style=None):
        self._printer(str(text), style=style)

    def clear(self):
        if self.is_terminal:
            self.print("\033[2J\033[H")


console = TerminalConsole()
