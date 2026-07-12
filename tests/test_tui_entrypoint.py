import supa_cc.tui as tui
from click.testing import CliRunner

from supa_cc.__main__ import main
from supa_cc.auth import AccountIndexReadError


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
        "supa_cc.__main__.run_tui",
        lambda: (_ for _ in ()).throw(AccountIndexReadError("/private/path")),
    )

    result = CliRunner().invoke(main, [])

    assert result.exit_code != 0
    assert "Não foi possível ler o índice local de contas." in result.stderr
    assert "/private/path" not in result.output
    assert "Traceback" not in result.output


def test_bare_startup_sanitizes_tui_runtime_failure(monkeypatch):
    monkeypatch.setattr(
        "supa_cc.__main__.run_tui",
        lambda: (_ for _ in ()).throw(RuntimeError("/private/runtime")),
    )

    result = CliRunner().invoke(main, [])

    assert result.exit_code != 0
    assert "A operação local não pôde ser concluída." in result.stderr
    assert "/private/runtime" not in result.output
    assert "Traceback" not in result.output
