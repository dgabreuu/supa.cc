import os
from pathlib import Path
from types import SimpleNamespace

import conftest
import pytest

from helpers import FakeCredentialStore, fake_pat
from supa_cc.accounts.service import AccountService


NATIVE_ACCESS_CASES = (
    ("real_keychain", "Darwin", "SUPA_CC_RUN_KEYCHAIN_SMOKE"),
    ("real_secret_service", "Linux", "SUPA_CC_REAL_SECRET_SERVICE"),
    (
        "real_windows_credential_manager",
        "Windows",
        "SUPA_CC_RUN_WINDOWS_CREDENTIAL_MANAGER_SMOKE",
    ),
)


def _request_with_marker(marker):
    node = SimpleNamespace(
        get_closest_marker=lambda candidate: (
            object() if candidate == marker else None
        )
    )
    return SimpleNamespace(node=node)


def test_unit_tests_use_a_disposable_home(tmp_path):
    home = Path(os.environ["HOME"])

    assert home == tmp_path / "home"
    assert Path(os.environ["XDG_CONFIG_HOME"]) == home / ".config"
    assert Path(os.environ["APPDATA"]) == home / "AppData" / "Roaming"


def test_unit_tests_use_a_fake_credential_store_by_default():
    service = AccountService()

    assert isinstance(service.credential_store, FakeCredentialStore)


@pytest.mark.parametrize("marker,expected_system,opt_in", NATIVE_ACCESS_CASES)
def test_native_store_marker_requires_the_expected_system(
    monkeypatch, marker, expected_system, opt_in
):
    request = _request_with_marker(marker)
    monkeypatch.setattr(conftest.platform, "system", lambda: "Unsupported")
    monkeypatch.setenv(opt_in, "1")

    with pytest.raises(pytest.skip.Exception, match=expected_system):
        conftest._native_credential_access_allowed(request)


@pytest.mark.parametrize("marker,expected_system,opt_in", NATIVE_ACCESS_CASES)
def test_native_store_marker_requires_explicit_opt_in(
    monkeypatch, marker, expected_system, opt_in
):
    request = _request_with_marker(marker)
    monkeypatch.setattr(conftest.platform, "system", lambda: expected_system)
    monkeypatch.delenv(opt_in, raising=False)

    with pytest.raises(pytest.skip.Exception, match=opt_in):
        conftest._native_credential_access_allowed(request)


@pytest.mark.parametrize("marker,expected_system,opt_in", NATIVE_ACCESS_CASES)
def test_native_store_bypass_requires_system_and_opt_in(
    monkeypatch, marker, expected_system, opt_in
):
    request = _request_with_marker(marker)
    monkeypatch.setattr(conftest.platform, "system", lambda: expected_system)
    monkeypatch.setenv(opt_in, "1")

    assert conftest._native_credential_access_allowed(request)


@pytest.mark.parametrize("credential", [fake_pat("pytest-node-id")])
def test_credential_shaped_parameters_are_not_exposed_in_node_ids(
    request, credential
):
    assert credential not in request.node.nodeid
