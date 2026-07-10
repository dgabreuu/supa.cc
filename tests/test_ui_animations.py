import pytest

from supa_cc.ui.animations import loading


class FakeConsole:
    def __init__(self):
        self.is_terminal = True
        self.status_calls = []
        self.entered = 0
        self.exited = 0

    def status(self, message, spinner="dots", spinner_style=""):
        self.status_calls.append(message)
        return self

    def __enter__(self):
        self.entered += 1
        return self

    def __exit__(self, *args):
        self.exited += 1
        return False


def test_loading_context_wraps_call_and_returns_result():
    console = FakeConsole()

    with loading("Ativando...", console=console) as spinner:
        result = spinner

    assert console.entered == 1
    assert console.exited == 1
    assert "Ativando..." in console.status_calls[0]


def test_loading_context_propagates_exception():
    console = FakeConsole()

    with pytest.raises(RuntimeError):
        with loading("Ativando...", console=console):
            raise RuntimeError("fail")

    assert console.exited == 1
