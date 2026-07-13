from .ui.app import TUIApp


def run() -> int:
    """Entry point for the TUI application."""
    app = TUIApp()
    return app.run()
