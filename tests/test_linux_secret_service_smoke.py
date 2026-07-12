import hmac
import os
import platform
from types import SimpleNamespace
from uuid import uuid4

import pytest

from helpers import fake_pat
from supa_cc.auth import CredentialAccessError
from supa_cc.credentials import create_credential_store
from supa_cc.environment import detect_environment
from supa_cc.models import Account


@pytest.mark.real_secret_service
@pytest.mark.skipif(
    os.environ.get("SUPA_CC_REAL_SECRET_SERVICE") != "1",
    reason="requires explicit SUPA_CC_REAL_SECRET_SERVICE=1 opt-in",
)
def test_secret_service_round_trip_uses_an_isolated_entry():
    if platform.system() != "Linux":
        pytest.skip("requires Linux")

    unique = uuid4().hex
    service = f"supa.cc.tests.{unique}"
    account_name = f"smoke-{unique}"
    token = fake_pat("secret-service")

    try:
        store = create_credential_store(
            detect_environment(system_name="Linux", os_release="ID=fedora\n"),
            service=service,
        )
    except CredentialAccessError:
        pytest.skip("Secret Service is unavailable")

    if not store.status().available:
        pytest.skip("Secret Service is unavailable")

    try:
        store.set(Account(name=account_name, token=token))
        loaded = store.get(account_name)
        assert loaded is not None
        assert hmac.compare_digest(loaded, token)
    finally:
        try:
            store.delete(account_name)
        except Exception as error:  # pragma: no cover - real backend only
            pytest.fail(
                "Failed to clean up the isolated Secret Service smoke entry: "
                f"{type(error).__name__}",
                pytrace=False,
            )


def test_secret_service_smoke_skips_off_linux_without_constructing_store(
    monkeypatch,
):
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        "test_linux_secret_service_smoke.create_credential_store",
        lambda *_args, **_kwargs: pytest.fail("credential store was constructed"),
    )

    with pytest.raises(pytest.skip.Exception, match="requires Linux"):
        test_secret_service_round_trip_uses_an_isolated_entry()


def test_secret_service_smoke_skips_when_service_is_unavailable(monkeypatch):
    store = SimpleNamespace(
        status=lambda: SimpleNamespace(available=False),
    )
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(
        "test_linux_secret_service_smoke.create_credential_store",
        lambda *_args, **_kwargs: store,
    )

    with pytest.raises(pytest.skip.Exception, match="Secret Service is unavailable"):
        test_secret_service_round_trip_uses_an_isolated_entry()
