from supa_cc.ui.console import TerminalConsole


class RecordingOutput:
    def __init__(self):
        self.events = []

    def erase_screen(self):
        self.events.append(("erase_screen",))

    def cursor_goto(self, row=0, column=0):
        self.events.append(("cursor_goto", row, column))

    def cursor_down(self, amount):
        self.events.append(("cursor_down", amount))

    def erase_down(self):
        self.events.append(("erase_down",))

    def flush(self):
        self.events.append(("flush",))


def test_clear_uses_terminal_output_without_printing_control_sequences():
    printed = []
    output = RecordingOutput()
    console = TerminalConsole(
        printer=lambda text, style=None: printed.append((text, style)),
        output=output,
        is_terminal=True,
    )

    console.clear()

    assert printed == []
    assert output.events == [
        ("erase_screen",),
        ("cursor_goto", 0, 0),
        ("flush",),
    ]


def test_clear_below_returns_to_frame_anchor_and_erases_dynamic_region():
    output = RecordingOutput()
    console = TerminalConsole(output=output, is_terminal=True)

    console.clear_below(line_count=7)

    assert output.events == [
        ("cursor_goto", 0, 0),
        ("cursor_down", 7),
        ("erase_down",),
        ("flush",),
    ]


def test_terminal_controls_are_noops_outside_a_terminal():
    output = RecordingOutput()
    console = TerminalConsole(output=output, is_terminal=False)

    console.clear()
    console.clear_below(line_count=7)

    assert output.events == []
