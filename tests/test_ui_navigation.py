from questionary import Choice, Separator
from questionary.prompts.common import InquirerControl

from supa_cc.ui.navigation import (
    BACK_ARROW,
    BACK_SPACING_LINES,
    DEFAULT_POINTER,
    choices_with_back,
    first_selectable_value,
)
from supa_cc.ui.state import MenuAction
from supa_cc.ui.strings import UIStrings as Textos


def test_back_spacing_is_two_lines():
    assert BACK_SPACING_LINES == 2


def test_voltar_text_has_no_embedded_arrow():
    assert Textos.MENU_BACK == "Voltar"
    assert "←" not in Textos.MENU_BACK
    assert BACK_ARROW == "←"
    assert DEFAULT_POINTER == "»"


def test_choices_with_back_separates_voltar_by_two_lines():
    base = [Choice(title="A", value="a"), Choice(title="B", value="b")]

    result = choices_with_back(base)

    assert result[0].value == "a"
    assert result[1].value == "b"

    spacing = result[2 : 2 + BACK_SPACING_LINES]
    assert len(spacing) == 2
    assert all(isinstance(item, Separator) for item in spacing)

    voltar = result[2 + BACK_SPACING_LINES]
    assert isinstance(voltar, Choice)
    assert voltar.value == MenuAction.BACK
    assert voltar.title == "Voltar"
    assert len(result) == 2 + BACK_SPACING_LINES + 1


def test_choices_with_back_only_voltar():
    result = choices_with_back([])

    assert len(result) == BACK_SPACING_LINES + 1
    assert result[BACK_SPACING_LINES].value == MenuAction.BACK


def test_first_selectable_value_skips_separators():
    choices = choices_with_back([Choice(title="A", value="a"), Choice(title="B", value="b")])
    assert first_selectable_value(choices) == "a"


def test_first_selectable_value_with_only_back():
    choices = choices_with_back([])
    assert first_selectable_value(choices) == MenuAction.BACK


def test_renderer_always_shows_arrow_for_voltar_without_standard_pointer():
    choices = choices_with_back([Choice(title="A", value="a")])
    control = InquirerControl(choices, pointer=DEFAULT_POINTER, use_indicator=False)
    # Point at first option (A)
    control.pointed_at = 0
    tokens = control._get_choice_tokens()
    text = "".join(part for _, part in tokens if part)

    assert "»" in text  # standard pointer on A
    assert BACK_ARROW in text  # ← always on Voltar
    assert "Voltar" in text

    # Point at Voltar
    control.pointed_at = len(control.choices) - 1
    tokens = control._get_choice_tokens()
    rendered = [(style, part) for style, part in tokens]

    # No » next to Voltar when focused
    voltar_chunks = []
    capture = False
    for style, part in rendered:
        if BACK_ARROW in part:
            capture = True
        if capture:
            voltar_chunks.append((style, part))
            if "Voltar" in part:
                break

    joined = "".join(part for _, part in voltar_chunks)
    assert BACK_ARROW in joined
    assert "»" not in joined
    assert any(style == "class:highlighted" and "Voltar" in part for style, part in voltar_chunks)
