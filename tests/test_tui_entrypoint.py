import supa_cc.tui as tui
from supa_cc.__main__ import main
from supa_cc.auth import AccountIndexReadError

from helpers import click_runner


def test_run_starts_modular_tui_app(monkeypatch):
    calls = []

    class FakeApp:
        def run(self):
            calls.append("run")

    monkeypatch.setattr(tui, "TUIApp", lambda: FakeApp())

    tui.run()

    assert calls == ["run"]


def test_bare_startup_sanitizes_tui_construction_failure(monkeypatch):
    monkeypatch.setattr(
        "supa_cc.__main__._run_tui",
        lambda: (_ for _ in ()).throw(AccountIndexReadError("/private/path")),
    )

    result = click_runner().invoke(main, [])

    assert result.exit_code != 0
    assert "Unable to read the local account index." in result.stderr
    assert "/private/path" not in result.output
    assert "Traceback" not in result.output


def test_bare_startup_sanitizes_tui_runtime_failure(monkeypatch):
    monkeypatch.setattr(
        "supa_cc.__main__._run_tui",
        lambda: (_ for _ in ()).throw(RuntimeError("/private/runtime")),
    )

    result = click_runner().invoke(main, [])

    assert result.exit_code != 0
    assert "The local operation could not be completed." in result.stderr
    assert "/private/runtime" not in result.output
    assert "Traceback" not in result.output
