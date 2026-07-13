from questionary import Choice, Separator
from questionary.prompts.common import InquirerControl
from supa_cc.ui.navigation import (
    BACK_ARROW,
    BACK_SPACING_LINES,
    DEFAULT_POINTER,
    choices_with_back,
)
from supa_cc.ui.state import MenuAction
from supa_cc.strings import UIStrings as Strings


def test_back_spacing_is_two_lines():
    assert BACK_SPACING_LINES == 2


def test_voltar_text_has_no_embedded_arrow():
    assert Strings.MENU_BACK == "Back"
    assert "←" not in Strings.MENU_BACK
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
    assert voltar.title == [("class:text", "← Back")]
    assert len(result) == 2 + BACK_SPACING_LINES + 1


def test_choices_with_back_only_voltar():
    result = choices_with_back([])

    assert len(result) == BACK_SPACING_LINES + 1
    assert result[BACK_SPACING_LINES].value == MenuAction.BACK


def test_questionary_renders_formatted_back_choice_with_spacing_and_selection():
    choices = choices_with_back([Choice(title="A", value="a")])
    control = InquirerControl(
        choices,
        pointer=DEFAULT_POINTER,
        use_indicator=False,
    )
    control.pointed_at = len(control.choices) - 1
    tokens = control._get_choice_tokens()
    rendered = "".join(text for _, text in tokens)

    assert control.get_pointed_at().value is MenuAction.BACK
    assert f"{BACK_ARROW} {Strings.MENU_BACK}" in rendered
    assert sum(style == "class:separator" for style, _ in tokens) == BACK_SPACING_LINES
    assert DEFAULT_POINTER in rendered  # Questionary may show its standard selected pointer.
    assert InquirerControl._get_choice_tokens.__module__.startswith("questionary.")
