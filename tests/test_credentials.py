import inspect

import pytest
from keyring.errors import KeyringError, KeyringLocked, PasswordDeleteError

import supa_cc.credentials as credentials
from supa_cc.auth import (
    AuthFailureCode,
    CredentialPermissionDeniedError,
    CredentialReadError,
    SecretServiceUnavailableError,
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
    priority = 5
    instances = []
    next_get_error = None

    def __init__(self):
        self.passwords = {}
        self.calls = []
        self.get_error = type(self).next_get_error
        self.set_error = None
        self.delete_error = None
        self.read_back = None
        type(self).instances.append(self)

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


class FakeSecretServiceKeyring(FakeKeyring):
    instances = []
    next_get_error = None


class FakeMacOSKeyring(FakeKeyring):
    instances = []
    next_get_error = None


@pytest.fixture
def fake_secret_service(monkeypatch):
    FakeSecretServiceKeyring.instances.clear()
    FakeSecretServiceKeyring.next_get_error = None
    monkeypatch.setattr(
        credentials.SecretService,
        "Keyring",
        FakeSecretServiceKeyring,
    )
    return FakeSecretServiceKeyring


def linux_environment():
    return detect_environment(system_name="Linux", os_release="ID=arch\n")


def test_linux_selects_only_secret_service_backend(fake_secret_service):
    store = create_credential_store(linux_environment())
    fake = fake_secret_service.instances[0]

    assert store.backend_name == "keyring.backends.SecretService.Keyring"
    assert isinstance(store._backend, credentials.SecretService.Keyring)
    assert store.status() == CredentialStoreStatus(
        backend_name="keyring.backends.SecretService.Keyring",
        available=True,
    )
    assert len(fake.calls) == 1
    operation, service, name = fake.calls[0]
    assert operation == "get"
    assert service != "supa.cc.supabase.accounts.v2"
    assert service.startswith("supa.cc.probe.")
    assert name.startswith("probe-")


def test_darwin_selects_only_macos_backend(monkeypatch):
    FakeMacOSKeyring.instances.clear()
    monkeypatch.setattr(
        credentials.macOS,
        "Keyring",
        FakeMacOSKeyring,
    )

    store = create_credential_store(detect_environment(system_name="Darwin"))
    fake = FakeMacOSKeyring.instances[0]
    account = Account(name="mac", token=fake_pat("mac-routing"))

    assert store.backend_name == "keyring.backends.macOS.Keyring"
    assert isinstance(store._backend, credentials.macOS.Keyring)
    assert store.status().available is True
    store.set(account)
    assert store.get(account.name) == account.token
    store.delete(account.name)
    assert fake.calls == [
        ("set", "supa.cc.supabase.accounts.v2", account.name, account.token),
        ("get", "supa.cc.supabase.accounts.v2", account.name),
        ("get", "supa.cc.supabase.accounts.v2", account.name),
        ("delete", "supa.cc.supabase.accounts.v2", account.name),
    ]


def test_linux_rejects_unavailable_secret_service(monkeypatch):
    class RaisingSecretServiceKeyring:
        def __init__(self):
            raise RuntimeError("fake backend detail")

    monkeypatch.setattr(
        credentials.SecretService,
        "Keyring",
        RaisingSecretServiceKeyring,
    )

    with pytest.raises(CredentialAccessError) as raised:
        create_credential_store(
            detect_environment(system_name="Linux", os_release="ID=debian\n")
        )

    assert "fake backend detail" not in str(raised.value)


def test_credential_store_factory_accepts_only_environment_and_service():
    assert list(inspect.signature(create_credential_store).parameters) == [
        "environment",
        "service",
    ]


class PlaintextBackend:
    def __init__(self):
        self.calls = []

    def get_password(self, *_args):
        self.calls.append("get")

    def set_password(self, *_args):
        self.calls.append("set")


class FailBackend(PlaintextBackend):
    pass


class AlternativeBackend(PlaintextBackend):
    pass


@pytest.mark.parametrize(
    "backend",
    [None, PlaintextBackend(), FailBackend(), AlternativeBackend()],
    ids=["null", "plaintext", "fail", "alternative"],
)
def test_linux_rejects_invalid_private_construction_results(monkeypatch, backend):
    monkeypatch.setattr(
        credentials,
        "_create_secret_service_backend",
        lambda: backend,
    )
    monkeypatch.setattr(
        credentials,
        "_probe_secret_service_provider",
        lambda: None,
    )

    with pytest.raises(CredentialAccessError):
        create_credential_store(linux_environment())

    assert backend is None or backend.calls == []


def test_linux_rejects_subclass_of_expected_backend_before_credential_writes(
    monkeypatch,
):
    class ExpectedSecretServiceKeyring(FakeKeyring):
        instances = []
        next_get_error = None

    class AlternativeSecretServiceKeyring(ExpectedSecretServiceKeyring):
        instances = []
        next_get_error = None

    backend = AlternativeSecretServiceKeyring()
    monkeypatch.setattr(
        credentials.SecretService,
        "Keyring",
        ExpectedSecretServiceKeyring,
    )
    monkeypatch.setattr(
        credentials,
        "_create_secret_service_backend",
        lambda: backend,
    )
    monkeypatch.setattr(
        credentials,
        "_probe_secret_service_provider",
        lambda: None,
    )

    with pytest.raises(CredentialAccessError):
        create_credential_store(linux_environment())

    assert backend.calls == []


def test_unavailable_provider_reports_safe_remediation(
    fake_secret_service, monkeypatch
):
    monkeypatch.setattr(
        credentials,
        "_probe_secret_service_provider",
        lambda: (_ for _ in ()).throw(RuntimeError("D-Bus provider detail")),
    )

    store = create_credential_store(linux_environment())
    fake = fake_secret_service.instances[0]

    status = store.status()

    assert status.available is False
    assert "D-Bus" in status.message
    assert "desbloqueie" in status.message
    assert "detail" not in status.message
    assert fake.calls == []


@pytest.mark.parametrize(
    "probe_error",
    [KeyringLocked("locked detail"), PermissionError("permission detail")],
    ids=["locked", "permission"],
)
def test_unavailable_collection_reports_safe_remediation(
    fake_secret_service, probe_error
):
    fake_secret_service.next_get_error = probe_error

    store = create_credential_store(linux_environment())
    fake = fake_secret_service.instances[0]

    status = store.status()

    assert status.available is False
    assert "D-Bus" in status.message
    assert "desbloqueie" in status.message
    assert "detail" not in status.message
    assert len(fake.calls) == 1
    assert fake.calls[0][1] != "supa.cc.supabase.accounts.v2"


def test_unavailable_store_blocks_writes_before_token_access(fake_secret_service):
    fake_secret_service.next_get_error = PermissionError("permission detail")
    store = create_credential_store(linux_environment())
    fake = fake_secret_service.instances[0]
    account = Account(name="work", token=fake_pat("unavailable"))

    with pytest.raises(CredentialAccessError) as raised:
        store.set(account)

    assert "D-Bus" in str(raised.value)
    assert account.token not in str(raised.value)
    assert [call[0] for call in fake.calls] == ["get"]


@pytest.mark.parametrize("operation", ["get", "set", "delete"])
def test_startup_probe_secret_service_unavailability_survives_classification(
    fake_secret_service, operation
):
    fake_secret_service.next_get_error = PermissionError("private probe detail")
    account = Account(name="work", token=fake_pat("startup-probe"))
    store = create_credential_store(linux_environment())
    fake = fake_secret_service.instances[0]

    with pytest.raises(SecretServiceUnavailableError) as raised:
        if operation == "get":
            store.get(account.name)
        elif operation == "set":
            store.set(account)
        else:
            store.delete(account.name)

    result = classify_local_failure(raised.value)
    expected_message = (
        "O Secret Service não está disponível. Verifique o D-Bus e desbloqueie "
        "o Secret Service."
    )

    assert result.code is AuthFailureCode.KEYCHAIN_READ_FAILED
    assert result.message == expected_message
    assert account.token not in str(raised.value)
    assert account.token not in result.message
    assert "private probe detail" not in result.message
    assert [call[0] for call in fake.calls] == ["get"]


def test_store_uses_the_selected_fake_for_every_operation(fake_secret_service):
    store = create_credential_store(linux_environment())
    fake = fake_secret_service.instances[0]
    account = Account(name="work", token=fake_pat("credential-store"))

    fake.calls.clear()
    store.set(account)
    assert store.get(account.name) == account.token
    store.delete(account.name)

    assert fake.calls == [
        ("set", "supa.cc.supabase.accounts.v2", account.name, account.token),
        ("get", "supa.cc.supabase.accounts.v2", account.name),
        ("get", "supa.cc.supabase.accounts.v2", account.name),
        ("delete", "supa.cc.supabase.accounts.v2", account.name),
    ]


def test_store_routes_operations_to_an_explicit_service(fake_secret_service):
    service = "supa.cc.tests.custom"
    store = create_credential_store(linux_environment(), service=service)
    fake = fake_secret_service.instances[0]
    account = Account(name="work", token=fake_pat("custom-service"))

    fake.calls.clear()
    store.set(account)
    assert store.get(account.name) == account.token
    store.delete(account.name)

    assert store.service == service
    assert fake.calls == [
        ("set", service, account.name, account.token),
        ("get", service, account.name),
        ("get", service, account.name),
        ("delete", service, account.name),
    ]


@pytest.mark.parametrize(
    "failure",
    [
        KeyringLocked("fake backend detail"),
        PermissionError("fake backend detail"),
        KeyringError("fake backend detail"),
    ],
    ids=["locked", "permission", "keyring"],
)
def test_store_normalizes_read_errors_without_backend_details(
    fake_secret_service, failure
):
    store = create_credential_store(linux_environment())
    fake = fake_secret_service.instances[0]
    fake.calls.clear()
    fake.get_error = failure

    with pytest.raises(CredentialAccessError) as raised:
        store.get("work")

    assert "fake backend detail" not in str(raised.value)


@pytest.mark.parametrize(
    "operation,failure",
    [
        ("get", KeyringError("D-Bus disconnected backend detail")),
        ("set", KeyringLocked("locked backend detail")),
        ("delete", PermissionError("permission backend detail")),
    ],
    ids=["get-disconnected", "set-locked", "delete-permission"],
)
def test_linux_post_probe_failures_keep_secret_service_remediation_public(
    fake_secret_service, operation, failure
):
    store = create_credential_store(linux_environment())
    fake = fake_secret_service.instances[0]
    account = Account(name="work", token=fake_pat("post-probe"))

    fake.calls.clear()
    setattr(fake, f"{operation}_error", failure)

    with pytest.raises(CredentialAccessError) as raised:
        if operation == "get":
            store.get(account.name)
        elif operation == "set":
            store.set(account)
        else:
            store.delete(account.name)

    result = classify_local_failure(raised.value)
    expected_message = (
        "O Secret Service não está disponível. Verifique o D-Bus e desbloqueie "
        "o Secret Service."
    )

    assert str(raised.value) == expected_message
    assert result.code is AuthFailureCode.KEYCHAIN_READ_FAILED
    assert result.message == expected_message
    assert "D-Bus" in result.message
    assert "desbloqueie" in result.message
    assert "backend detail" not in result.message
    assert account.token not in result.message


def test_macos_operation_failures_keep_neutral_credential_message(monkeypatch):
    FakeMacOSKeyring.instances.clear()
    monkeypatch.setattr(credentials.macOS, "Keyring", FakeMacOSKeyring)
    store = create_credential_store(detect_environment(system_name="Darwin"))
    fake = FakeMacOSKeyring.instances[0]
    fake.get_error = KeyringLocked("locked backend detail")

    with pytest.raises(StorePermissionDeniedError) as raised:
        store.get("work")

    result = classify_local_failure(raised.value)

    assert result.code is AuthFailureCode.KEYCHAIN_PERMISSION_DENIED
    assert result.message == "Acesso ao armazenamento de credenciais não autorizado."
    assert "D-Bus" not in result.message
    assert "backend detail" not in result.message


def test_store_tolerates_only_a_recognized_missing_delete(fake_secret_service):
    store = create_credential_store(linux_environment())
    fake = fake_secret_service.instances[0]
    fake.calls.clear()
    fake.delete_error = PasswordDeleteError("Item not found")

    store.delete("missing")


def test_store_rejects_read_back_mismatch_without_exposing_token(fake_secret_service):
    account = Account(name="work", token=fake_pat("expected-token"))
    store = create_credential_store(linux_environment())
    fake = fake_secret_service.instances[0]
    fake.calls.clear()
    fake.read_back = fake_pat("other-token")

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
