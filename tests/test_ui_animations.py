import pytest

from supa_cc.ui.animations import loading


class FakeConsole:
    def __init__(self):
        self.print_calls = []

    def print(self, message, style=None):
        self.print_calls.append((message, style))


def test_loading_context_wraps_call_and_returns_result():
    console = FakeConsole()

    with loading("Activating...", console=console) as status:
        result = status

    assert result is console
    assert console.print_calls == [("Activating...", "status")]


def test_loading_context_propagates_exception():
    console = FakeConsole()

    with pytest.raises(RuntimeError):
        with loading("Activating...", console=console):
            raise RuntimeError("fail")

    assert console.print_calls == [("Activating...", "status")]
