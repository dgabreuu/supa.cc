from supa_cc.models import Account

from helpers import fake_pat


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


def test_account_repr_does_not_expose_token():
    token = fake_pat("secret_token")
    account = Account(name="test", token=token)

    assert token not in repr(account)
