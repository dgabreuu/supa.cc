from supa_cc.ui.layout import center_banner_lines, create_message_panel
from supa_cc.ui.theme import BANNER_COMPACT, BANNER_MEDIUM, get_banner


def test_get_banner_returns_medium_for_wide_terminal():
    banner = get_banner(width=80)
    assert banner == BANNER_MEDIUM


def test_get_banner_returns_compact_for_narrow_terminal():
    banner = get_banner(width=40)
    assert banner == BANNER_COMPACT


def test_center_banner_lines_makes_all_lines_same_width():
    centered = center_banner_lines(BANNER_MEDIUM)
    widths = {len(line) for line in centered.splitlines()}
    assert len(widths) == 1


def test_center_banner_lines_preserves_content():
    centered = center_banner_lines(BANNER_COMPACT)
    lines = centered.splitlines()
    assert len(lines) >= 4
    assert any(line.strip() for line in lines)
