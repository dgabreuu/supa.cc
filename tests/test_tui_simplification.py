import subprocess
import sys

from supa_cc.ui.animations import loading
from supa_cc.ui.screens import MAIN_MENU_CHOICES
from supa_cc.ui.state import MenuAction
from supa_cc.ui.theme import BANNER_COMPACT, get_banner


class RecordingConsole:
    def __init__(self):
        self.lines = []

    def print(self, text, style=None):
        self.lines.append((text, style))


def test_ui_import_graph_does_not_load_rich():
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import supa_cc.tui; "
                "print(','.join(sorted(name for name in sys.modules "
                "if name == 'rich' or name.startswith('rich.'))))"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert completed.stdout.strip() == ""


def test_home_menu_contains_only_actions_with_a_direct_effect():
    actions = [choice.value for choice in MAIN_MENU_CHOICES]

    assert actions == [
        MenuAction.ADD_ACCOUNT,
        MenuAction.SWITCH_ACCOUNT,
        MenuAction.REMOVE_ACCOUNT,
        MenuAction.EXIT,
    ]


def test_short_terminal_uses_compact_banner_even_when_wide():
    assert get_banner(width=100, height=15) == BANNER_COMPACT


def test_loading_prints_one_stable_status_line_without_spinner():
    console = RecordingConsole()

    with loading("Activating account… (up to 30s)", console=console):
        pass

    assert console.lines == [("Activating account… (up to 30s)", "status")]
