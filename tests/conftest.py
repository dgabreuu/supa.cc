import os
import platform
from unittest.mock import patch

import pytest

from helpers import FakeCredentialStore


@pytest.fixture(autouse=True)
def silence_security_keychain(request):
    """Evita acesso ao Keychain do host durante unit tests."""
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
        "supa_cc.keychain.create_credential_store",
        side_effect=lambda _environment, **_kwargs: FakeCredentialStore(),
    ):
        yield
