import questionary


COLOR_BLACK = "#000000"
COLOR_DARK_GRAY = "#1A1A1A"
COLOR_MEDIUM_GRAY = "#4A4A4A"
COLOR_GRAY = "#808080"
COLOR_LIGHT_GRAY = "#B0B0B0"
COLOR_WHITE = "#FFFFFF"
COLOR_PRIMARY = "#00D388"

OUTPUT_STYLES = {
    "title": f"fg:{COLOR_WHITE} bold",
    "subtitle": f"fg:{COLOR_LIGHT_GRAY} bold",
    "success": f"fg:{COLOR_WHITE} bold",
    "error": f"fg:{COLOR_PRIMARY} bold",
    "warning": f"fg:{COLOR_LIGHT_GRAY} bold",
    "info": f"fg:{COLOR_GRAY}",
    "highlight": f"fg:{COLOR_PRIMARY} bold",
    "banner": f"fg:{COLOR_PRIMARY} bold",
    "status": f"fg:{COLOR_LIGHT_GRAY}",
}

BANNER_MEDIUM = r"""
 ____
/ ___| _   _ _ __   __ _   ___ ___
\___ \| | | | '_ \ / _` | / __/ __|
 ___) | |_| | |_) | (_| || (_| (__
|____/ \__,_| .__/ \__,_(_)___\___|
            |_|
""".strip("\n")

BANNER_COMPACT = r"""
 _   _
| | | | _ __   __ _   __ _   _
| |_| || '_ \ / _` | / _` | | |
 \___/ | .__/ \__, | \__,_| |_|
       |_|    |___/
""".strip("\n")

BANNER_WIDTH_THRESHOLD = 60
BANNER_HEIGHT_THRESHOLD = 22


def get_banner(width: int, height: int = 24) -> str:
    if width >= BANNER_WIDTH_THRESHOLD and height >= BANNER_HEIGHT_THRESHOLD:
        return BANNER_MEDIUM
    return BANNER_COMPACT


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
