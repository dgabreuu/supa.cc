from .console import console as default_console


def clear_screen(console=None) -> None:
    (console or default_console).clear()


def center_banner_lines(banner: str) -> str:
    lines = banner.splitlines()
    if not lines:
        return banner
    max_width = max(len(line) for line in lines)
    return "\n".join(line.ljust(max_width) for line in lines)


def create_header(title: str, subtitle: str = "") -> str:
    return f"{title}\n{subtitle}" if subtitle else title


def create_message(text: str, level: str = "info") -> str:
    icons = {"success": "✓ ", "error": "✗ ", "warning": "⚠ ", "info": "ℹ "}
    return f"{icons.get(level, '')}{text}"
