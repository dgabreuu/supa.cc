from supa_cc.ui.screens import TUIScreens
from supa_cc.ui.state import NavigationState

from helpers import fake_pat


class FakePrompt:
    def __init__(self, value):
        self.value = value

    def ask(self):
        return self.value


class FakePrompts:
    def __init__(self, name, token):
        self.name = name
        self.token = token

    def text(self, *args, **kwargs):
        return FakePrompt(self.name)

    def password(self, *args, **kwargs):
        return FakePrompt(self.token)


class FakeManager:
    def add(self, name, token):
        raise ValueError(f"invalid token {token}")


def test_add_account_sanitizes_token_like_errors():
    token = fake_pat("secret_token")
    screens = TUIScreens(
        manager=FakeManager(),
        renderer=None,
        prompts=FakePrompts("work", token),
    )
    state = NavigationState()

    screens.add_account(state)

    assert token not in state.last_message.text
    assert state.last_message.text == "Erro: Erro de validação. Verifique os dados fornecidos."
