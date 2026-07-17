from contextlib import contextmanager

from .console import console as default_console
from .theme import OUTPUT_STYLES


@contextmanager
def loading(message: str, console=None):
    """Print a stable status line before a potentially slow operation."""
    target = console or default_console
    target.print(message, style=OUTPUT_STYLES["status"])
    yield target
