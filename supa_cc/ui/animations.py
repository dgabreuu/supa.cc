from contextlib import contextmanager
from typing import Generator, Optional

from rich.console import Console

from .console import console as default_console
from .theme import COLOR_PRIMARY


@contextmanager
def loading(
    message: str,
    console: Optional[Console] = None,
) -> Generator[Optional[Console], None, None]:
    """Context manager discreto de status/loading estilo hacking/dados.

    Usa o spinner nativo do Rich com a cor principal #00D388.
    Desligado automaticamente em consoles sem terminal (testes/CI).
    """
    target = console or default_console
    if not target.is_terminal:
        yield None
        return

    with target.status(
        message,
        spinner="dots",
        spinner_style=COLOR_PRIMARY,
    ) as status:
        yield status
