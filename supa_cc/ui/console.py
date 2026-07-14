import shutil
import sys

import questionary
from prompt_toolkit.output.defaults import create_output


class TerminalConsole:
    """Small output adapter backed by Questionary/prompt-toolkit."""

    def __init__(
        self,
        printer=None,
        output=None,
        width=None,
        height=None,
        is_terminal=None,
    ):
        size = shutil.get_terminal_size(fallback=(80, 24))
        self.width = width if width is not None else size.columns
        self.height = height if height is not None else size.lines
        self.is_terminal = (
            sys.stdout.isatty() if is_terminal is None else is_terminal
        )
        self._printer = printer or questionary.print
        self._output = output if output is not None else create_output()

    def print(self, text="", style=None):
        self._printer(str(text), style=style)

    def clear(self):
        if not self.is_terminal:
            return
        self._output.erase_screen()
        self._output.cursor_goto(0, 0)
        self._output.flush()

    def clear_below(self, line_count):
        if not self.is_terminal:
            return
        self._output.cursor_goto(0, 0)
        self._output.cursor_down(line_count)
        self._output.erase_down()
        self._output.flush()


console = TerminalConsole()
