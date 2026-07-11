import inspect

import pytest
from keyring.errors import KeyringError, KeyringLocked, PasswordDeleteError

import supa_cc.credentials as credentials
from supa_cc.auth import (
    AuthFailureCode,
    CredentialPermissionDeniedError,
    CredentialReadError,
    classify_local_failure,
)
from supa_cc.credentials import (
    CredentialAccessError,
    CredentialPermissionDeniedError as StorePermissionDeniedError,
    CredentialStoreStatus,
    create_credential_store,
)
from supa_cc.environment import detect_environment
from supa_cc.models import Account

from helpers import fake_pat


class FakeKeyring:
    def __init__(self):
        self.passwords = {}
        self.calls = []
        self.get_error = None
        self.set_error = None
        self.delete_error = None
        self.read_back = None

    def get_password(self, service, name):
        self.calls.append(("get", service, name))
        if self.get_error is not None:
            raise self.get_error
        if self.read_back is not None:
            return self.read_back
        return self.passwords.get((service, name))

    def set_password(self, service, name, token):
        self.calls.append(("set", service, name, token))
        if self.set_error is not None:
            raise self.set_error
        self.passwords[(service, name)] = token

    def delete_password(self, service, name):
        self.calls.append(("delete", service, name))
        if self.delete_error is not None:
            raise self.delete_error
        self.passwords.pop((service, name), None)


@pytest.fixture
def fake_secret_service(monkeypatch):
    fake = FakeKeyring()
    monkeypatch.setattr(
        credentials,
        "_create_secret_service_backend",
        lambda: fake,
    )
    monkeypatch.setattr(
        credentials,
        "_probe_secret_service_provider",
        lambda: None,
    )
    return fake


def linux_environment():
    return detect_environment(system_name="Linux", os_release="ID=arch\n")


def test_linux_selects_only_secret_service_backend(fake_secret_service):
    store = create_credential_store(linux_environment())

    assert store.backend_name == "keyring.backends.SecretService.Keyring"
    assert store.status() == CredentialStoreStatus(
        backend_name="keyring.backends.SecretService.Keyring",
        available=True,
    )
    assert len(fake_secret_service.calls) == 1
    operation, service, name = fake_secret_service.calls[0]
    assert operation == "get"
    assert service != "supa.cc.supabase.accounts.v2"
    assert service.startswith("supa.cc.probe.")
    assert name.startswith("probe-")


def test_darwin_selects_only_macos_backend(monkeypatch):
    fake_macos_keyring = FakeKeyring()
    monkeypatch.setattr(
        credentials,
        "_create_macos_backend",
        lambda: fake_macos_keyring,
    )

    store = create_credential_store(detect_environment(system_name="Darwin"))

    assert store.backend_name == "keyring.backends.macOS.Keyring"


def test_linux_rejects_unavailable_secret_service(monkeypatch):
    monkeypatch.setattr(
        credentials,
        "_create_secret_service_backend",
        lambda: (_ for _ in ()).throw(RuntimeError("fake backend detail")),
    )

    with pytest.raises(CredentialAccessError) as raised:
        create_credential_store(
            detect_environment(system_name="Linux", os_release="ID=debian\n")
        )

    assert "fake backend detail" not in str(raised.value)


def test_credential_store_factory_has_no_backend_injection_parameters():
    assert list(inspect.signature(create_credential_store).parameters) == ["environment"]


def test_unavailable_provider_reports_safe_remediation(
    fake_secret_service, monkeypatch
):
    monkeypatch.setattr(
        credentials,
        "_probe_secret_service_provider",
        lambda: (_ for _ in ()).throw(RuntimeError("D-Bus provider detail")),
    )

    store = create_credential_store(linux_environment())

    status = store.status()

    assert status.available is False
    assert "D-Bus" in status.message
    assert "desbloqueie" in status.message
    assert "detail" not in status.message
    assert fake_secret_service.calls == []


@pytest.mark.parametrize(
    "probe_error",
    [KeyringLocked("locked detail"), PermissionError("permission detail")],
    ids=["locked", "permission"],
)
def test_unavailable_collection_reports_safe_remediation(
    fake_secret_service, probe_error
):
    fake_secret_service.get_error = probe_error

    store = create_credential_store(linux_environment())

    status = store.status()

    assert status.available is False
    assert "D-Bus" in status.message
    assert "desbloqueie" in status.message
    assert "detail" not in status.message
    assert len(fake_secret_service.calls) == 1
    assert fake_secret_service.calls[0][1] != "supa.cc.supabase.accounts.v2"


def test_unavailable_store_blocks_writes_before_token_access(fake_secret_service):
    fake_secret_service.get_error = PermissionError("permission detail")
    store = create_credential_store(linux_environment())
    account = Account(name="work", token=fake_pat("unavailable"))

    with pytest.raises(CredentialAccessError) as raised:
        store.set(account)

    assert "D-Bus" in str(raised.value)
    assert account.token not in str(raised.value)
    assert [call[0] for call in fake_secret_service.calls] == ["get"]


def test_store_uses_the_selected_fake_for_every_operation(fake_secret_service):
    store = create_credential_store(linux_environment())
    account = Account(name="work", token=fake_pat("credential-store"))

    fake_secret_service.calls.clear()
    store.set(account)
    assert store.get(account.name) == account.token
    store.delete(account.name)

    assert fake_secret_service.calls == [
        ("set", "supa.cc.supabase.accounts.v2", account.name, account.token),
        ("get", "supa.cc.supabase.accounts.v2", account.name),
        ("get", "supa.cc.supabase.accounts.v2", account.name),
        ("delete", "supa.cc.supabase.accounts.v2", account.name),
    ]


@pytest.mark.parametrize(
    "failure,expected_exception",
    [
        (KeyringLocked("fake backend detail"), StorePermissionDeniedError),
        (PermissionError("fake backend detail"), StorePermissionDeniedError),
        (KeyringError("fake backend detail"), CredentialReadError),
    ],
    ids=["locked", "permission", "keyring"],
)
def test_store_normalizes_read_errors_without_backend_details(
    fake_secret_service, failure, expected_exception
):
    store = create_credential_store(linux_environment())
    fake_secret_service.calls.clear()
    fake_secret_service.get_error = failure

    with pytest.raises(expected_exception) as raised:
        store.get("work")

    assert "fake backend detail" not in str(raised.value)


def test_store_tolerates_only_a_recognized_missing_delete(fake_secret_service):
    store = create_credential_store(linux_environment())
    fake_secret_service.calls.clear()
    fake_secret_service.delete_error = PasswordDeleteError("Item not found")

    store.delete("missing")


def test_store_rejects_read_back_mismatch_without_exposing_token(fake_secret_service):
    account = Account(name="work", token=fake_pat("expected-token"))
    store = create_credential_store(linux_environment())
    fake_secret_service.calls.clear()
    fake_secret_service.read_back = fake_pat("other-token")

    with pytest.raises(CredentialReadError) as raised:
        store.set(account)

    assert account.token not in str(raised.value)


@pytest.mark.parametrize(
    "failure,expected_code",
    [
        (CredentialAccessError("fake backend detail"), AuthFailureCode.KEYCHAIN_READ_FAILED),
        (CredentialPermissionDeniedError("fake backend detail"), AuthFailureCode.KEYCHAIN_PERMISSION_DENIED),
        (CredentialReadError("fake backend detail"), AuthFailureCode.KEYCHAIN_READ_FAILED),
    ],
)
def test_neutral_credential_errors_keep_failure_codes_and_safe_messages(
    failure, expected_code
):
    result = classify_local_failure(failure)

    assert result.code is expected_code
    assert "armazenamento de credenciais" in result.message
    assert "Keychain" not in result.message
    assert "fake backend detail" not in result.message
