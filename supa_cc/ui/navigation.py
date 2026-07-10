from typing import Any, List, Optional, Sequence, Union

from questionary import Choice, Separator
from questionary.constants import DEFAULT_SELECTED_POINTER, INDICATOR_SELECTED, INDICATOR_UNSELECTED
from questionary.prompts.common import InquirerControl

from .state import MenuAction
from .strings import UIStrings as Textos

BACK_SPACING_LINES = 2
BACK_ARROW = "←"
DEFAULT_POINTER = DEFAULT_SELECTED_POINTER

BACK_CHOICE = Choice(title=Textos.MENU_BACK, value=MenuAction.BACK)

_PATCHED = False


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


def _is_back_choice(choice: Choice) -> bool:
    return getattr(choice, "value", None) == MenuAction.BACK


def _supa_get_choice_tokens(self: InquirerControl):
    """Render choices: standard » pointer for items; permanent ← for Voltar only."""
    tokens = []
    pointer = self.pointer
    pointer_length = len(pointer) if pointer is not None else 1

    def append(index: int, choice: Choice) -> None:
        selected = choice.value in self.selected_options
        pointed = index == self.pointed_at

        if _is_back_choice(choice):
            # ← always in the indicator column; never show »
            arrow_style = "class:pointer" if pointed else "class:text"
            tokens.append((arrow_style, f" {BACK_ARROW} "))
            if pointed:
                tokens.append(("[SetCursorPosition]", ""))
                tokens.append(("class:highlighted", Textos.MENU_BACK))
            else:
                tokens.append(("class:text", Textos.MENU_BACK))
            tokens.append(("", "\n"))
            return

        if pointed:
            if pointer is not None:
                tokens.append(("class:pointer", " {} ".format(pointer)))
            else:
                tokens.append(("class:text", " " * 3))
            tokens.append(("[SetCursorPosition]", ""))
        else:
            tokens.append(("class:text", " " * (2 + pointer_length)))

        if isinstance(choice, Separator):
            tokens.append(("class:separator", "{}".format(choice.title)))
        elif choice.disabled:
            if isinstance(choice.title, list):
                tokens.append(
                    ("class:selected" if selected else "class:disabled", "- ")
                )
                tokens.extend(choice.title)
            else:
                tokens.append(
                    (
                        "class:selected" if selected else "class:disabled",
                        "- {}".format(choice.title),
                    )
                )
            tokens.append(
                (
                    "class:selected" if selected else "class:disabled",
                    "{}".format(
                        ""
                        if isinstance(choice.disabled, bool)
                        else " ({})".format(choice.disabled)
                    ),
                )
            )
        else:
            shortcut = choice.get_shortcut_title() if self.use_shortcuts else ""

            if selected:
                indicator = (INDICATOR_SELECTED + " ") if self.use_indicator else ""
                tokens.append(("class:selected", "{}".format(indicator)))
            else:
                indicator = (INDICATOR_UNSELECTED + " ") if self.use_indicator else ""
                tokens.append(("class:text", "{}".format(indicator)))

            if isinstance(choice.title, list):
                tokens.extend(choice.title)
            elif selected:
                tokens.append(
                    ("class:selected", "{}{}".format(shortcut, choice.title))
                )
            elif pointed:
                tokens.append(
                    ("class:highlighted", "{}{}".format(shortcut, choice.title))
                )
            else:
                tokens.append(("class:text", "{}{}".format(shortcut, choice.title)))

        tokens.append(("", "\n"))

    for i, c in enumerate(self.filtered_choices):
        append(i, c)

    current = self.get_pointed_at()

    if self.show_selected:
        answer = current.get_shortcut_title() if self.use_shortcuts else ""
        answer += (
            current.title if isinstance(current.title, str) else current.title[0][1]
        )
        tokens.append(("class:text", "  Answer: {}".format(answer)))

    show_description = self.show_description and current.description is not None
    if show_description:
        tokens.append(
            ("class:text", "  Description: {}".format(current.description))
        )

    if not (self.show_selected or show_description):
        tokens.pop()

    return tokens


def install_back_aware_renderer() -> None:
    """Patch questionary so Voltar always shows ←; other options keep »."""
    global _PATCHED
    if _PATCHED:
        return
    InquirerControl._get_choice_tokens = _supa_get_choice_tokens  # type: ignore[method-assign]
    _PATCHED = True


install_back_aware_renderer()
