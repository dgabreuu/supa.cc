from typing import Optional

from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from .console import console as default_console
from .theme import RICH_STYLES


def clear_screen(console: Optional[Console] = None) -> None:
    """Limpa a tela do terminal antes de renderizar o frame estável."""
    target = console or default_console
    target.clear()


def center_banner_lines(banner: str) -> str:
    """Pad banner lines to the same width so Align.center works horizontally."""
    lines = banner.splitlines()
    if not lines:
        return banner
    max_width = max(len(line) for line in lines)
    return "\n".join(line.ljust(max_width) for line in lines)


def create_header(title: str, subtitle: str = "") -> Panel:
    """Cria painel de cabeçalho estilizado."""
    content = Text()
    content.append(title, style=RICH_STYLES["title"])
    if subtitle:
        content.append(f"\n{subtitle}", style=RICH_STYLES["subtitle"])
    return Panel(
        Align.center(content),
        border_style=RICH_STYLES["border"],
        padding=(1, 2),
    )


def create_message_panel(text: str, level: str = "info") -> Panel:
    """Cria painel de mensagem com estilo apropriado."""
    style = RICH_STYLES.get(level, RICH_STYLES["info"])
    icons = {
        "success": "✓ ",
        "error": "✗ ",
        "warning": "⚠ ",
        "info": "ℹ ",
    }
    icon = icons.get(level, "")
    content = Text(f"{icon}{text}", style=style)
    return Panel(content, border_style=style, padding=(1, 2))
