import pytest

from supa_cc.auth import is_valid_access_token
from supa_cc.models import Account

from helpers import fake_oauth_pat, fake_pat


def test_account_creation():
    account = Account(name="test", token=fake_pat("test123"))
    assert account.name == "test"
    assert account.token == fake_pat("test123")


def test_account_validate_token_valid():
    account = Account(name="test", token=fake_pat("valid_token_here"))
    assert account.validate_token() is True


def test_account_validate_token_invalid():
    account = Account(name="test", token="invalid_token")
    assert account.validate_token() is False

    account2 = Account(name="test", token="sbp" + "_")
    assert account2.validate_token() is False


@pytest.mark.parametrize(
    "token",
    [
        fake_pat("ascii_pat_sbp"),
        fake_oauth_pat("ascii_pat_oauth"),
    ],
)
def test_access_token_contract_accepts_ascii_pat(token):
    assert is_valid_access_token(token) is True
    assert Account(name="work", token=token).validate_token() is True


@pytest.mark.parametrize(
    "token",
    [
        fake_pat("bypass_short")[:-1],
        fake_pat("bypass_long") + "a",
        fake_pat("bypass_upper")[:4] + fake_pat("bypass_upper")[4:].upper(),
        fake_pat("bypass_bad_char")[:-1] + "g",
        "sbp_OAUTH_" + fake_pat("bypass_oauth_case")[4:],
        " " + fake_pat("bypass_leading_space"),
        fake_pat("bypass_trailing_space") + " ",
        fake_pat("bypass_newline") + "\n",
        fake_pat("bypass_null") + "\x00",
    ],
)
def test_access_token_contract_rejects_bypasses(token):
    assert is_valid_access_token(token) is False
    assert Account(name="work", token=token).validate_token() is False


def test_account_repr_does_not_expose_token():
    token = fake_pat("secret_token")
    account = Account(name="test", token=token)

    assert token not in repr(account)
