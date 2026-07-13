import os
import platform
from unittest.mock import patch

import pytest

from helpers import FakeCredentialStore
from supa_cc.auth import contains_pat


def pytest_make_parametrize_id(config, val, argname):
    """Keep credential-shaped values out of collected node IDs and caches."""
    del config
    if isinstance(val, str) and contains_pat(val):
        return f"{argname}-credential"
    return None


@pytest.fixture(autouse=True)
def isolate_user_state(tmp_path, monkeypatch):
    """Route every unit-test state path to a disposable per-test home."""
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("APPDATA", str(home / "AppData" / "Roaming"))


@pytest.fixture(autouse=True)
def silence_security_keychain(request):
    """Prevent unit tests from reaching the host credential store."""
    if request.node.get_closest_marker("real_keychain") is not None:
        if (
            platform.system() != "Darwin"
            or os.environ.get("SUPA_CC_RUN_KEYCHAIN_SMOKE") != "1"
        ):
            pytest.skip(
                "real Keychain access requires macOS and explicit opt-in"
            )
        yield
        return

    if request.node.get_closest_marker("real_secret_service") is not None:
        yield
        return

    with patch(
        "supa_cc.accounts.store.create_credential_store",
        side_effect=lambda _environment, **_kwargs: FakeCredentialStore(),
    ):
        yield
