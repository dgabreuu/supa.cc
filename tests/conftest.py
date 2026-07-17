import os
import platform
from unittest.mock import patch

import pytest

from helpers import FakeCredentialStore
from supa_cc.auth import contains_pat


NATIVE_CREDENTIAL_ACCESS = {
    "real_keychain": ("Darwin", "SUPA_CC_RUN_KEYCHAIN_SMOKE"),
    "real_secret_service": ("Linux", "SUPA_CC_REAL_SECRET_SERVICE"),
    "real_windows_credential_manager": (
        "Windows",
        "SUPA_CC_RUN_WINDOWS_CREDENTIAL_MANAGER_SMOKE",
    ),
}


def _native_credential_access_allowed(request):
    for marker, (expected_system, opt_in) in NATIVE_CREDENTIAL_ACCESS.items():
        if request.node.get_closest_marker(marker) is None:
            continue
        if platform.system() != expected_system:
            pytest.skip(f"{marker} requires {expected_system}")
        if os.environ.get(opt_in) != "1":
            pytest.skip(f"{marker} requires explicit {opt_in}=1 opt-in")
        return True
    return False


def _fake_credential_store(*_args, **_kwargs):
    return FakeCredentialStore()


def pytest_make_parametrize_id(config, val, argname):
    """Keep credential-shaped values out of collected node IDs and caches."""
    del config
    if isinstance(val, str) and contains_pat(val):
        return f"{argname}-credential"
    return None


@pytest.fixture(autouse=True)
def isolate_user_state(tmp_path, monkeypatch, request):
    """Route every unit-test state path to a disposable per-test home."""
    if _native_credential_access_allowed(request):
        yield
        return
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("APPDATA", str(home / "AppData" / "Roaming"))
    yield


@pytest.fixture(autouse=True)
def silence_security_keychain(request):
    """Prevent unit tests from reaching the host credential store."""
    if _native_credential_access_allowed(request):
        yield
        return

    with patch(
        "supa_cc.accounts.store.create_credential_store",
        side_effect=_fake_credential_store,
    ), patch(
        "supa_cc.accounts.service.create_credential_store",
        side_effect=_fake_credential_store,
    ):
        yield
