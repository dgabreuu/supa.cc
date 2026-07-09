import supa_cc.tui as tui


def test_run_starts_modular_tui_app(monkeypatch):
    calls = []

    class FakeApp:
        def run(self):
            calls.append("run")

    monkeypatch.setattr(tui, "TUIApp", lambda: FakeApp())

    tui.run()

    assert calls == ["run"]
