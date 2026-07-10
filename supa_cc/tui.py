from .ui.app import TUIApp


def run() -> int:
    """Entrypoint para a aplicação TUI."""
    app = TUIApp()
    return app.run()
