import pytest
from keyring.errors import KeyringError, KeyringLocked, PasswordDeleteError

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
    credential_store_test_double = True

    def __init__(self, backend_name="keyring.backends.SecretService.Keyring"):
        self.credential_store_backend_name = backend_name
        self.passwords = {}
        self.calls = []
        self.probe_calls = 0
        self.probe_error = None
        self.get_error = None
        self.set_error = None
        self.delete_error = None
        self.read_back = None

    def credential_store_probe(self):
        self.probe_calls += 1
        if self.probe_error is not None:
            raise self.probe_error

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
def fake_secret_service():
    return FakeKeyring()


def linux_environment():
    return detect_environment(system_name="Linux", os_release="ID=arch\n")


def test_linux_selects_only_secret_service_backend(fake_secret_service):
    store = create_credential_store(
        linux_environment(),
        secret_service_factory=lambda: fake_secret_service,
    )

    assert store.backend_name == "keyring.backends.SecretService.Keyring"
    assert store.status() == CredentialStoreStatus(
        backend_name="keyring.backends.SecretService.Keyring",
        available=True,
    )


def test_darwin_selects_only_macos_backend():
    fake_macos_keyring = FakeKeyring("keyring.backends.macOS.Keyring")

    store = create_credential_store(
        detect_environment(system_name="Darwin"),
        macos_factory=lambda: fake_macos_keyring,
    )

    assert store.backend_name == "keyring.backends.macOS.Keyring"


def test_linux_rejects_unavailable_secret_service():
    with pytest.raises(CredentialAccessError) as raised:
        create_credential_store(
            detect_environment(system_name="Linux", os_release="ID=debian\n"),
            secret_service_factory=lambda: (_ for _ in ()).throw(
                RuntimeError("fake backend detail")
            ),
        )

    assert "fake backend detail" not in str(raised.value)


class UnsafeKeyring:
    def __init__(self):
        self.calls = []

    def get_password(self, *_args):
        self.calls.append("get")

    def set_password(self, *_args):
        self.calls.append("set")

    def delete_password(self, *_args):
        self.calls.append("delete")


class PlaintextKeyring(UnsafeKeyring):
    pass


class FailKeyring(UnsafeKeyring):
    pass


class AlternativeKeyring(UnsafeKeyring):
    pass


@pytest.mark.parametrize(
    "backend",
    [None, PlaintextKeyring(), FailKeyring(), AlternativeKeyring()],
    ids=["null", "plaintext", "fail", "alternative"],
)
def test_linux_rejects_insecure_backends_before_credential_operations(backend):
    with pytest.raises(CredentialAccessError):
        create_credential_store(
            linux_environment(),
            secret_service_factory=lambda: backend,
        )

    assert backend is None or backend.calls == []


@pytest.mark.parametrize(
    "probe_error",
    [RuntimeError("D-Bus provider detail"), KeyringLocked("locked detail")],
    ids=["provider", "locked"],
)
def test_unavailable_secret_service_reports_safe_remediation(
    fake_secret_service, probe_error
):
    fake_secret_service.probe_error = probe_error

    store = create_credential_store(
        linux_environment(),
        secret_service_factory=lambda: fake_secret_service,
    )

    status = store.status()

    assert status.available is False
    assert "D-Bus" in status.message
    assert "desbloqueie" in status.message
    assert "detail" not in status.message
    assert fake_secret_service.probe_calls == 1
    assert fake_secret_service.calls == []


def test_unavailable_store_blocks_credential_operations(fake_secret_service):
    fake_secret_service.probe_error = RuntimeError("D-Bus provider detail")
    store = create_credential_store(
        linux_environment(),
        secret_service_factory=lambda: fake_secret_service,
    )
    account = Account(name="work", token=fake_pat("unavailable"))

    for operation in (
        lambda: store.get(account.name),
        lambda: store.set(account),
        lambda: store.delete(account.name),
    ):
        with pytest.raises(CredentialAccessError) as raised:
            operation()
        assert "D-Bus" in str(raised.value)
        assert "detail" not in str(raised.value)

    assert fake_secret_service.calls == []


def test_store_uses_the_selected_fake_for_every_operation(fake_secret_service):
    store = create_credential_store(
        linux_environment(),
        secret_service_factory=lambda: fake_secret_service,
    )
    account = Account(name="work", token=fake_pat("credential-store"))

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
    fake_secret_service.get_error = failure
    store = create_credential_store(
        linux_environment(),
        secret_service_factory=lambda: fake_secret_service,
    )

    with pytest.raises(expected_exception) as raised:
        store.get("work")

    assert "fake backend detail" not in str(raised.value)


def test_store_tolerates_only_a_recognized_missing_delete(fake_secret_service):
    fake_secret_service.delete_error = PasswordDeleteError("Item not found")
    store = create_credential_store(
        linux_environment(),
        secret_service_factory=lambda: fake_secret_service,
    )

    store.delete("missing")


def test_store_rejects_read_back_mismatch_without_exposing_token(fake_secret_service):
    account = Account(name="work", token=fake_pat("expected-token"))
    fake_secret_service.read_back = fake_pat("other-token")
    store = create_credential_store(
        linux_environment(),
        secret_service_factory=lambda: fake_secret_service,
    )

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
