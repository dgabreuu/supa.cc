from supa_cc.ui.theme import COLOR_PRIMARY, QUESTIONARY_STYLE, RICH_STYLES


def test_primary_color_is_brand_green():
    assert COLOR_PRIMARY == "#00D388"


def test_rich_styles_use_primary_color_for_highlight_error_banner():
    assert "#00D388" in RICH_STYLES["error"]
    assert "#00D388" in RICH_STYLES["highlight"]
    assert "#00D388" in RICH_STYLES["banner"]


def test_questionary_style_uses_primary_color():
    style_dict = {name: value for name, value in QUESTIONARY_STYLE.style_rules}
    assert "#00D388" in style_dict["qmark"]
    assert "#00D388" in style_dict["pointer"]
    assert "#00D388" in style_dict["highlighted"]
