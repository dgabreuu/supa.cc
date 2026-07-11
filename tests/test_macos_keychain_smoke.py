import hmac
import hashlib
import os
import platform
import uuid
from unittest.mock import Mock

import keyring
import pytest

from supa_cc.keychain import KEYCHAIN_SERVICE, KeychainManager
from supa_cc.models import Account


pytestmark = pytest.mark.skipif(
    platform.system() != "Darwin"
    or os.environ.get("SUPA_CC_RUN_KEYCHAIN_SMOKE") != "1",
    reason=(
        "requires macOS and explicit SUPA_CC_RUN_KEYCHAIN_SMOKE=1 opt-in"
    ),
)


@pytest.mark.real_keychain
def test_disposable_macos_keychain_round_trip(tmp_path):
    unique = uuid.uuid4().hex
    service = f"supa.cc.tests.{unique}"
    account_name = f"smoke-{unique}"
    original_token = "sbp_" + hashlib.sha256(
        f"smoke:{unique}".encode("utf-8")
    ).hexdigest()[:40]
    updated_token = "sbp_" + hashlib.sha256(
        f"updated:{unique}".encode("utf-8")
    ).hexdigest()[:40]
    manager = KeychainManager(
        index_path=tmp_path / "accounts.json",
        service=service,
        cache_ttl_seconds=0,
    )

    assert not isinstance(keyring.set_password, Mock)
    assert not isinstance(keyring.get_password, Mock)
    assert not isinstance(keyring.delete_password, Mock)
    assert service != KEYCHAIN_SERVICE
    assert manager.credential_store.service == service
    assert Account(name=account_name, token=original_token).validate_token()
    assert Account(name=account_name, token=updated_token).validate_token()
    try:
        manager.add_account(
            Account(name=account_name, token=original_token)
        )
        loaded = manager.get_account(account_name)
        assert loaded is not None
        assert hmac.compare_digest(loaded.token, original_token)
        assert hmac.compare_digest(
            keyring.get_password(service, account_name), original_token
        )

        manager.add_account(
            Account(name=account_name, token=updated_token)
        )
        updated = manager.get_account(account_name)
        assert updated is not None
        assert hmac.compare_digest(updated.token, updated_token)

        manager.remove_account(account_name)
        assert manager.get_account(account_name) is None
        assert keyring.get_password(service, account_name) is None
    finally:
        try:
            manager.delete_account(account_name)
        except Exception as error:  # pragma: no cover - real backend only
            pytest.fail(
                "Falha ao limpar o item temporário isolado do smoke Keychain: "
                f"service={service}, account={account_name}, "
                f"error={type(error).__name__}",
                pytrace=False,
            )
