from typing import List, Sequence, Union

from questionary import Choice, Separator
from questionary.constants import DEFAULT_SELECTED_POINTER

from ..strings import UIStrings as Strings
from .state import MenuAction

BACK_SPACING_LINES = 2
BACK_ARROW = "←"
DEFAULT_POINTER = DEFAULT_SELECTED_POINTER

BACK_CHOICE = Choice(
    title=[("class:text", f"{BACK_ARROW} {Strings.MENU_BACK}")],
    value=MenuAction.BACK,
)


def choices_with_back(
    choices: Sequence[Union[str, Choice, Separator]] = (),
) -> List[Union[Choice, Separator]]:
    """Append Back separated by blank lines."""
    result: List[Union[Choice, Separator]] = list(choices)
    for _ in range(BACK_SPACING_LINES):
        result.append(Separator(" "))
    result.append(BACK_CHOICE)
    return result
