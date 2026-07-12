from typing import Any, List, Sequence, Union

from questionary import Choice, Separator
from questionary.constants import DEFAULT_SELECTED_POINTER

from ..strings import UIStrings as Textos
from .state import MenuAction

BACK_SPACING_LINES = 2
BACK_ARROW = "←"
DEFAULT_POINTER = DEFAULT_SELECTED_POINTER

BACK_CHOICE = Choice(
    title=[("class:text", f"{BACK_ARROW} {Textos.MENU_BACK}")],
    value=MenuAction.BACK,
)


def first_selectable_value(
    choices: Sequence[Union[str, Choice, Separator]],
) -> Any:
    """Return value of the first non-separator, non-disabled choice."""
    for choice in choices:
        if isinstance(choice, Separator):
            continue
        if isinstance(choice, Choice):
            if choice.disabled:
                continue
            return choice.value
        return choice
    return None


def choices_with_back(
    choices: Sequence[Union[str, Choice, Separator]] = (),
) -> List[Union[Choice, Separator]]:
    """Append Voltar separated by blank lines."""
    result: List[Union[Choice, Separator]] = list(choices)
    for _ in range(BACK_SPACING_LINES):
        result.append(Separator(" "))
    result.append(BACK_CHOICE)
    return result
