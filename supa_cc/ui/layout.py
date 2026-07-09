from typing import Optional

from rich.align import Align
from rich.panel import Panel
from rich.text import Text

from .console import console as default_console
from .theme import RICH_STYLES


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


def create_footer(text: str) -> Text:
    """Cria texto de rodapé estilizado."""
    return Text(text, style=RICH_STYLES["dim"], justify="center")


def create_divider(width: Optional[int] = None) -> Text:
    """Cria linha divisória estilizada."""
    divider_width = width or default_console.width
    return Text("─" * divider_width, style=RICH_STYLES["border"])


def spacer(lines: int = 1) -> Text:
    """Cria espaçamento vertical."""
    return Text("\n" * lines)


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
