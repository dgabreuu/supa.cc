import hmac
import hashlib
import os
import platform
import uuid
from unittest.mock import Mock

import keyring
import pytest

from supa_cc.credentials import create_credential_store
from supa_cc.environment import detect_environment
from supa_cc.models import Account


pytestmark = pytest.mark.skipif(
    platform.system() != "Darwin"
    or os.environ.get("SUPA_CC_RUN_KEYCHAIN_SMOKE") != "1",
    reason=(
        "requires macOS and explicit SUPA_CC_RUN_KEYCHAIN_SMOKE=1 opt-in"
    ),
)


@pytest.mark.real_keychain
def test_disposable_macos_keychain_round_trip():
    unique = uuid.uuid4().hex
    service = f"supa.cc.tests.{unique}"
    account_name = f"smoke-{unique}"
    original_token = "sbp_" + hashlib.sha256(
        f"smoke:{unique}".encode("utf-8")
    ).hexdigest()[:40]
    updated_token = "sbp_" + hashlib.sha256(
        f"updated:{unique}".encode("utf-8")
    ).hexdigest()[:40]
    store = create_credential_store(
        detect_environment(system_name="Darwin"),
        service=service,
    )

    assert not isinstance(keyring.set_password, Mock)
    assert not isinstance(keyring.get_password, Mock)
    assert not isinstance(keyring.delete_password, Mock)
    assert service != "supa.cc.supabase.accounts.v2"
    assert store.service == service
    assert Account(name=account_name, token=original_token).validate_token()
    assert Account(name=account_name, token=updated_token).validate_token()
    primary_error = None
    try:
        store.set(Account(name=account_name, token=original_token))
        loaded = store.get(account_name)
        assert loaded is not None
        assert hmac.compare_digest(loaded, original_token)
        assert hmac.compare_digest(
            keyring.get_password(service, account_name), original_token
        )

        store.set(Account(name=account_name, token=updated_token))
        updated = store.get(account_name)
        assert updated is not None
        assert hmac.compare_digest(updated, updated_token)

        store.delete(account_name)
        assert store.get(account_name) is None
        assert keyring.get_password(service, account_name) is None
    except BaseException as error:
        primary_error = error
        raise
    finally:
        try:
            store.delete(account_name)
        except Exception as error:  # pragma: no cover - real backend only
            if primary_error is not None:
                primary_error.add_note(
                    "The isolated Keychain smoke cleanup also failed with "
                    f"{type(error).__name__}."
                )
            else:
                pytest.fail(
                    "Failed to clean up the isolated temporary Keychain smoke item: "
                    f"service={service}, account={account_name}, "
                    f"error={type(error).__name__}",
                    pytrace=False,
                )
