import os
import platform
from uuid import uuid4

import pytest

from supa_cc.credentials import create_credential_store
from supa_cc.environment import detect_environment
from supa_cc.models import Account

from helpers import fake_pat


pytestmark = pytest.mark.real_windows_credential_manager


def test_real_windows_credential_manager_round_trip():
    if platform.system() != "Windows":
        pytest.skip("Windows Credential Manager smoke test requires Windows")
    if os.environ.get("SUPA_CC_RUN_WINDOWS_CREDENTIAL_MANAGER_SMOKE") != "1":
        pytest.skip("real Windows Credential Manager access requires explicit opt-in")

    suffix = uuid4().hex
    store = create_credential_store(
        detect_environment(), service=f"supa.cc.tests.{suffix}"
    )
    account = Account(name=f"smoke-{suffix}", token=fake_pat(suffix))
    try:
        store.set(account)
        assert store.matches(account.name, account.token)
    finally:
        store.delete(account.name)
