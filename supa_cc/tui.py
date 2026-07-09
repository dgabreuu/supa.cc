from .ui.app import TUIApp


def run() -> None:
    """Entrypoint para a aplicação TUI."""
    app = TUIApp()
    app.run()
