import questionary

# Paleta de cores: escala de cinza + verde principal #00D388
COLOR_BLACK = "#000000"
COLOR_DARK_GRAY = "#1A1A1A"
COLOR_MEDIUM_GRAY = "#4A4A4A"
COLOR_GRAY = "#808080"
COLOR_LIGHT_GRAY = "#B0B0B0"
COLOR_WHITE = "#FFFFFF"
COLOR_PRIMARY = "#00D388"

# Estilos Rich centralizados
RICH_STYLES = {
    "title": f"bold {COLOR_WHITE}",
    "subtitle": f"bold {COLOR_LIGHT_GRAY}",
    "success": f"bold {COLOR_WHITE}",
    "error": f"bold {COLOR_PRIMARY}",
    "warning": f"bold {COLOR_LIGHT_GRAY}",
    "info": f"bold {COLOR_GRAY}",
    "border": COLOR_MEDIUM_GRAY,
    "highlight": f"bold {COLOR_PRIMARY}",
    "active": COLOR_WHITE,
    "inactive": COLOR_GRAY,
    "dim": COLOR_GRAY,
    "banner": f"bold {COLOR_PRIMARY}",
}

# Banner Supa.cc — médio (terminais >= 60 cols)
BANNER_MEDIUM = r"""
 ____
/ ___| _   _ _ __   __ _   ___ ___
\___ \| | | | '_ \ / _` | / __/ __|
 ___) | |_| | |_) | (_| || (_| (__
|____/ \__,_| .__/ \__,_(_)___\___|
            |_|
""".strip("\n")

# Banner Supa.cc — compacto (terminais < 60 cols)
BANNER_COMPACT = r"""
 _   _
| | | | _ __   __ _   __ _   _
| |_| || '_ \ / _` | / _` | | |
 \___/ | .__/ \__, | \__,_| |_|
       |_|    |___/
""".strip("\n")

BANNER_WIDTH_THRESHOLD = 60


def get_banner(width: int) -> str:
    """Retorna banner adequado à largura do terminal."""
    return BANNER_MEDIUM if width >= BANNER_WIDTH_THRESHOLD else BANNER_COMPACT

# Estilo Questionary com paleta cinza + verde principal #00D388
QUESTIONARY_STYLE = questionary.Style(
    [
        ("qmark", f"fg:{COLOR_PRIMARY} bold"),
        ("question", "bold"),
        ("answer", f"fg:{COLOR_WHITE} bold"),
        ("pointer", f"fg:{COLOR_PRIMARY} bold"),
        ("highlighted", f"fg:{COLOR_PRIMARY} bold"),
        ("selected", f"fg:{COLOR_WHITE}"),
        ("separator", f"fg:{COLOR_GRAY}"),
        ("instruction", f"fg:{COLOR_GRAY}"),
        ("text", ""),
        ("disabled", f"fg:{COLOR_GRAY} italic"),
    ]
)
