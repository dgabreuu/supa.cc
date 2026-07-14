import json
import inspect
import os
from pathlib import Path
from unittest.mock import Mock

import pytest
import supa_cc

from supa_cc.accounts import AccountService
from supa_cc.accounts.state import AccountState, StateRepository
from supa_cc.auth import (
    ActiveAccountInvalidError,
    AuthFailureCode,
    AuthResult,
)
from supa_cc.supabase_cli import SupabaseCLI as SupabaseConfig
from supa_cc.credentials import CredentialStoreStatus
from supa_cc.diagnostics import DiagnosticService
from supa_cc.diagnostic_collectors import collect_activation_consistency
import supa_cc.diagnostic_collectors as diagnostic_collectors
import supa_cc.diagnostic_renderers as diagnostic_renderers
import supa_cc.diagnostics as diagnostics_facade
from supa_cc.environment import detect_environment
from supa_cc.installation import installation_guidance
from supa_cc.account_store import KEYCHAIN_SERVICE
from supa_cc.native_session import NativeSessionSynchronizer, SessionSyncJournal

from helpers import fake_pat
from helpers import FakeCredentialStore


def _service(
    tmp_path,
    *,
    manager=None,
    env=None,
    supabase_path=None,
    signature_resolver=None,
    environment=None,
    credential_store=None,
):
    if manager is None:
        manager = Mock()
        manager.keychain = Mock()
        manager.active_store = Mock()
        manager.keychain.index_path = tmp_path / "accounts.json"
        manager.keychain.service = KEYCHAIN_SERVICE
        manager.active_store.read.return_value = None
        manager.config = SupabaseConfig(
            binary_resolver=lambda _: supabase_path
        )
        manager.sync_journal = SessionSyncJournal(
            tmp_path / "session-sync.json"
        )
        manager.native_session = NativeSessionSynchronizer(
            manager.config,
            env={} if env is None else env,
            supabase_home=tmp_path / ".supabase",
        )
    return DiagnosticService(
        manager=manager,
        env={} if env is None else env,
        launcher_path=tmp_path / "bin" / "supa.cc",
        python_executable=tmp_path / "venv" / "bin" / "python",
        telemetry_path=tmp_path / ".supabase",
        backend_resolver=lambda: "keyring.backends.macOS.Keyring",
        signature_resolver=signature_resolver or (
            lambda path: {"status": "signed", "identifier": Path(path).name}
        ),
        python_version="3.14.0",
        python_implementation="CPython",
        environment=environment
        or detect_environment(system_name="Darwin"),
        credential_store=credential_store,
    )


def test_default_doctor_is_read_only_and_never_reads_token_or_authenticates(tmp_path):
    manager = Mock()
    manager.keychain = Mock()
    manager.active_store = Mock()
    manager.keychain.index_path = tmp_path / "accounts.json"
    manager.keychain.service = KEYCHAIN_SERVICE
    manager.active_store.read.return_value = "work"
    manager.config = SupabaseConfig(binary_resolver=lambda _: None)
    manager.config.supabase_cli = str(tmp_path / "supabase")
    manager.get.side_effect = AssertionError("must not read Keychain")
    manager.validate_named_account.side_effect = AssertionError("must not validate")
    service = _service(tmp_path, manager=manager, env={"SUPABASE_ACCESS_TOKEN": fake_pat("env")})

    report = service.run()

    manager.get.assert_not_called()
    manager.validate_named_account.assert_not_called()
    assert report.environment["supabase_access_token_present"] is True
    assert fake_pat("env") not in report.to_json()
    assert report.active_account == {"selected": True, "indexed": False}
    assert report.keychain_service == KEYCHAIN_SERVICE

    report_with_account_but_not_live = service.run(account="work", live=False)
    manager.get.assert_not_called()
    manager.validate_named_account.assert_not_called()
    assert report_with_account_but_not_live.live_result is None


def test_versioned_doctor_reads_state_without_opening_native_credentials(tmp_path):
    repository = StateRepository(tmp_path / "state.json")
    repository.save(AccountState(aliases=("work",), confirmed_active="work"))
    credentials = FakeCredentialStore()
    credentials.get_error = AssertionError("must not open credential")
    cli = SupabaseConfig(binary_resolver=lambda _: None, base_environment={})
    manager = AccountService(
        state_repository=repository,
        credential_store=credentials,
        cli=cli,
        native_session=Mock(),
    )

    report = _service(tmp_path, manager=manager).run()

    assert credentials.operations == []
    assert report.index["state"] == "valid"
    assert report.index["account_count"] == 1
    assert report.active_account == {"selected": True, "indexed": True}


def test_versioned_doctor_detects_plaintext_fallback_without_reading_it(tmp_path):
    repository = StateRepository(tmp_path / "state.json")
    repository.save(AccountState(aliases=("work",)))
    credentials = FakeCredentialStore()
    credentials.get_error = AssertionError("must not open credential")
    cli = SupabaseConfig(binary_resolver=lambda _: None, base_environment={})
    native_session = Mock()
    native_session.fallback_path = tmp_path / ".supabase" / "access-token"
    native_session.fallback_path.parent.mkdir()
    native_session.fallback_path.write_text("opaque", encoding="utf-8")
    manager = AccountService(
        state_repository=repository,
        credential_store=credentials,
        cli=cli,
        native_session=native_session,
    )

    report = _service(tmp_path, manager=manager).run()

    assert credentials.operations == []
    assert report.activation["plaintext_fallback_present"] is True
    assert report.activation["plaintext_fallback_state"] == "present"
    assert AuthFailureCode.PLAINTEXT_FALLBACK_BLOCKED.value in report.diagnostic_codes


def test_doctor_output_is_shareable_without_account_name_or_private_paths(tmp_path):
    manager = Mock()
    manager.keychain = Mock()
    manager.active_store = Mock()
    manager.keychain.index_path = tmp_path / "private-user" / "accounts.json"
    manager.keychain.service = KEYCHAIN_SERVICE
    manager.active_store.read.return_value = "private-account-name"
    manager.config = SupabaseConfig(binary_resolver=lambda _: None)
    manager.sync_journal = SessionSyncJournal(tmp_path / "session-sync.json")
    manager.native_session = NativeSessionSynchronizer(
        manager.config, env={}, supabase_home=tmp_path / ".supabase"
    )
    service = _service(tmp_path, manager=manager)

    payload = service.run().to_dict()
    rendered = json.dumps(payload)

    assert payload["active_account"] == {"selected": True, "indexed": False}
    assert payload["index"]["path"] == "<temp>/accounts.json"
    assert payload["runtime"]["launcher"]["path_relation"] == "same"
    assert payload["runtime"]["python"]["path_relation"] == "same"
    assert payload["supabase_cli"]["path_relation"] == "unavailable"
    assert "private-account-name" not in rendered
    assert str(tmp_path) not in rendered


def test_doctor_reports_effective_custom_keychain_service(tmp_path):
    manager = Mock()
    manager.keychain = Mock()
    manager.active_store = Mock()
    manager.keychain.index_path = tmp_path / "accounts.json"
    manager.keychain.service = "supa.cc.tests.doctor"
    manager.active_store.read.return_value = None
    manager.config = SupabaseConfig(binary_resolver=lambda _: None)

    report = _service(tmp_path, manager=manager).run()

    assert report.keychain_service == "supa.cc.tests.doctor"
    assert report.to_dict()["keychain"]["service"] == "supa.cc.tests.doctor"


def test_doctor_reports_the_effective_credential_store_namespace(tmp_path):
    manager = Mock()
    manager.keychain = Mock()
    manager.active_store = Mock()
    manager.keychain.index_path = tmp_path / "accounts.json"
    manager.keychain.service = "supa.cc.tests.requested"
    manager.keychain.credential_store.service = "supa.cc.tests.effective"
    manager.active_store.read.return_value = None
    manager.config = SupabaseConfig(binary_resolver=lambda _: None)

    report = _service(tmp_path, manager=manager).run()

    assert report.keychain_service == "supa.cc.tests.effective"


def test_doctor_reports_verified_runtime_identity_and_homebrew_receipt(tmp_path):
    launcher_target = tmp_path / "venv" / "bin" / "supa-cc-real"
    launcher_target.parent.mkdir(parents=True)
    launcher_target.write_text("launcher", encoding="utf-8")
    launcher = tmp_path / "bin" / "supa.cc"
    launcher.parent.mkdir()
    launcher.symlink_to(launcher_target)

    python_target = tmp_path / "Cellar" / "python" / "3.14" / "bin" / "python3"
    python_target.parent.mkdir(parents=True)
    python_target.write_text("python", encoding="utf-8")
    python_link = tmp_path / "venv" / "bin" / "python"
    python_link.parent.mkdir(parents=True, exist_ok=True)
    python_link.symlink_to(python_target)

    prefix = tmp_path / "Cellar" / "supabase" / "2.109.1"
    binary = prefix / "bin" / "supabase-real"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    invoked = tmp_path / "homebrew" / "bin" / "supabase"
    invoked.parent.mkdir(parents=True)
    invoked.symlink_to(binary)
    (prefix / "INSTALL_RECEIPT.json").write_text(
        json.dumps({"source": {"versions": {"stable": "2.109.1"}}}),
        encoding="utf-8",
    )
    signatures = []

    def signature(path):
        signatures.append(str(path))
        return {"status": "signed", "identifier": Path(path).name}

    service = _service(
        tmp_path,
        supabase_path=str(invoked),
        signature_resolver=signature,
        environment=detect_environment(system_name="Darwin"),
    )
    service.launcher_path = launcher
    service.python_executable = python_link

    report = service.run()
    payload = report.to_dict()

    assert payload["runtime"]["supa_cc_version"] == supa_cc.__version__
    assert payload["runtime"]["launcher"] == {
        "invoked": "<temp>/supa.cc",
        "realpath": "<temp>/supa-cc-real",
        "path_relation": "symlinked",
        "signature": {"status": "signed", "identifier": "supa-cc-real"},
    }
    assert payload["runtime"]["python"]["invoked"] == "<temp>/python"
    assert payload["runtime"]["python"]["realpath"] == "<temp>/python3"
    assert payload["runtime"]["python"]["path_relation"] == "symlinked"
    assert payload["runtime"]["python"]["implementation"] == "CPython"
    assert payload["runtime"]["python"]["version"] == "3.14.0"
    assert payload["supabase_cli"]["invoked"] == "<temp>/supabase"
    assert payload["supabase_cli"]["realpath"] == "<temp>/supabase-real"
    assert payload["supabase_cli"]["path_relation"] == "symlinked"
    assert payload["supabase_cli"]["version"] == "2.109.1"
    assert payload["supabase_cli"]["provenance"] == "homebrew"
    assert payload["activation"] == {
        "mode": "native_session",
        "native_session": "managed",
        "profile": "unmanaged",
        "journal_present": False,
        "journal_state": "absent",
        "plaintext_fallback_present": False,
        "plaintext_fallback_state": "absent",
        "parent_override_present": False,
    }
    assert set(signatures) == {
        str(launcher_target),
        str(python_target),
        str(binary),
    }
    human = report.to_human()
    assert "<temp>/supa.cc -> <temp>/supa-cc-real" in human
    assert "<temp>/python -> <temp>/python3" in human
    assert "<temp>/supabase -> <temp>/supabase-real" in human
    assert str(tmp_path) not in human
    assert human.count("signature: signed") == 3
    assert "Activation: native_session" in human


def test_doctor_reports_sync_metadata_by_presence_without_reading_contents(tmp_path):
    manager = Mock()
    manager.keychain = Mock()
    manager.active_store = Mock()
    manager.keychain.index_path = tmp_path / "accounts.json"
    manager.keychain.service = KEYCHAIN_SERVICE
    manager.active_store.read.return_value = "work"
    manager.config = SupabaseConfig(binary_resolver=lambda _: None)
    manager.sync_journal = Mock()
    manager.sync_journal.path = tmp_path / "session-sync.json"
    manager.sync_journal.read.return_value = {
        "operation": "activate",
        "target_account": "work",
        "previous_account": None,
        "phase": "native_login",
    }
    manager.native_session = Mock()
    manager.native_session.fallback_path = tmp_path / ".supabase" / "access-token"
    manager.native_session.fallback_path.parent.mkdir()
    manager.sync_journal.path.write_text("private journal", encoding="utf-8")
    manager.native_session.fallback_path.write_text("private token", encoding="utf-8")
    manager.get.side_effect = AssertionError("must not read credential")

    report = _service(
        tmp_path,
        manager=manager,
        env={"SUPABASE_ACCESS_TOKEN": fake_pat("parent_override")},
    ).run()

    assert report.activation == {
        "mode": "native_session",
        "native_session": "managed",
        "profile": "unmanaged",
        "journal_present": True,
        "journal_state": "present",
        "plaintext_fallback_present": True,
        "plaintext_fallback_state": "present",
        "parent_override_present": True,
    }
    manager.sync_journal.read.assert_called_once_with()
    manager.get.assert_not_called()
    rendered = report.to_json()
    assert "private journal" not in rendered
    assert "private token" not in rendered


def test_activation_collector_reports_read_only_consistency_findings(tmp_path):
    journal = SessionSyncJournal(tmp_path / "session-sync.json")
    journal.write("activate", "work", None, "native_login")
    native_session = NativeSessionSynchronizer(
        Mock(), env={"SUPABASE_HOME": str(tmp_path / "custom-home")}
    )
    native_session.fallback_path.parent.mkdir()
    native_session.fallback_path.write_text("private token", encoding="utf-8")
    profile_path = native_session.fallback_path.parent / "profile"
    profile_path.write_text(
        "other", encoding="utf-8"
    )
    profile_path.chmod(0o600)

    activation, codes = collect_activation_consistency(
        journal=journal,
        native_session=native_session,
        env={},
    )

    assert activation["journal_state"] == "present"
    assert activation["plaintext_fallback_state"] == "present"
    assert activation["profile"] == "unsupported"
    assert AuthFailureCode.SYNC_PENDING.value in codes
    assert AuthFailureCode.PLAINTEXT_FALLBACK_BLOCKED.value in codes
    assert AuthFailureCode.PROFILE_MISMATCH.value in codes


def test_profile_inspection_failure_is_not_reported_as_profile_mismatch(
    tmp_path, monkeypatch
):
    native_session = NativeSessionSynchronizer(
        Mock(), env={}, supabase_home=tmp_path / ".supabase"
    )
    monkeypatch.setattr(
        diagnostic_collectors,
        "read_text",
        Mock(side_effect=PermissionError("private path")),
    )

    activation, codes = collect_activation_consistency(
        SessionSyncJournal(tmp_path / "journal.json"), native_session, {}
    )

    assert activation["profile"] == "inaccessible"
    assert AuthFailureCode.ENVIRONMENT_BLOCKED.value in codes
    assert AuthFailureCode.PROFILE_MISMATCH.value not in codes


def test_rendering_implementation_lives_outside_collectors():
    collector_source = "\n".join(
        inspect.getsource(report_class)
        for report_class in diagnostic_collectors.DoctorReport.__mro__
        if report_class.__module__ == diagnostic_collectors.__name__
    )
    renderer_source = inspect.getsource(diagnostic_renderers)

    assert "Supa.cc doctor" not in collector_source
    assert '"keychain"' not in collector_source
    assert "Supa.cc doctor" in renderer_source
    assert '"keychain"' in renderer_source


def test_diagnostics_facade_reexports_collector_service_directly():
    assert diagnostics_facade.DiagnosticService is diagnostic_collectors.DiagnosticService


def test_doctor_reports_active_account_absent_from_valid_index(tmp_path):
    manager = Mock()
    manager.keychain = Mock()
    manager.active_store = Mock()
    manager.keychain.index_path = tmp_path / "accounts.json"
    manager.keychain.index_path.write_text(
        '{"accounts": ["personal"]}', encoding="utf-8"
    )
    manager.keychain.index_path.chmod(0o600)
    manager.keychain.service = KEYCHAIN_SERVICE
    manager.active_store.read.return_value = "work"
    manager.config = SupabaseConfig(binary_resolver=lambda _: None)
    manager.sync_journal = SessionSyncJournal(tmp_path / "session-sync.json")
    manager.native_session = NativeSessionSynchronizer(
        manager.config, env={}, supabase_home=tmp_path / ".supabase"
    )

    report = _service(tmp_path, manager=manager).run()

    assert AuthFailureCode.ACTIVE_ACCOUNT_MISSING.value in report.diagnostic_codes
    assert report.ok is False


def test_doctor_uses_supabase_home_for_native_session_diagnostics(tmp_path):
    custom_home = tmp_path / "custom-supabase-home"
    service = DiagnosticService(
        env={"SUPABASE_HOME": str(custom_home)},
        launcher_path=tmp_path / "supa.cc",
        python_executable=tmp_path / "python",
        environment=detect_environment(system_name="Darwin"),
    )
    manager = Mock()
    manager.keychain = Mock()
    manager.keychain.index_path = tmp_path / "accounts.json"
    manager.keychain.service = KEYCHAIN_SERVICE
    manager.active_store = Mock()
    manager.active_store.read.return_value = None
    manager.config = SupabaseConfig(binary_resolver=lambda _: None)
    manager.sync_journal = SessionSyncJournal(tmp_path / "journal.json")
    manager.native_session = NativeSessionSynchronizer(manager.config, env=service.env)
    service._manager = manager

    report = service.run()

    assert report.environment["telemetry_directory_exists"] is False
    assert manager.native_session.fallback_path == custom_home / "access-token"


@pytest.mark.parametrize(
    "metadata,error",
    [
        ("journal", PermissionError("private journal path and backend detail")),
        ("journal", OSError("private journal inspection detail")),
        ("fallback", PermissionError("private fallback path and backend detail")),
        ("fallback", OSError("private fallback inspection detail")),
    ],
)
def test_doctor_reports_inaccessible_sync_metadata_without_reading_secrets(
    tmp_path, monkeypatch, metadata, error
):
    manager = Mock()
    manager.keychain = Mock()
    manager.active_store = Mock()
    manager.keychain.index_path = tmp_path / "accounts.json"
    manager.keychain.service = KEYCHAIN_SERVICE
    manager.active_store.read.return_value = "work"
    manager.config = SupabaseConfig(binary_resolver=lambda _: None)
    supabase = tmp_path / "supabase"
    supabase.write_text("safe", encoding="utf-8")
    manager.config.supabase_cli_invoked = str(supabase)
    manager.config.supabase_cli = str(supabase)
    manager.sync_journal = Mock()
    manager.sync_journal.path = tmp_path / "private-journal-location"
    manager.sync_journal.read.side_effect = AssertionError("must not read journal")
    manager.native_session = Mock()
    manager.native_session.fallback_path = tmp_path / "private-fallback-location"
    manager.get.side_effect = AssertionError("must not read credential")
    inspected = (
        manager.sync_journal.path
        if metadata == "journal"
        else manager.native_session.fallback_path
    )
    original_lstat = Path.lstat

    def fail_selected_path(path):
        if path == inspected:
            raise error
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", fail_selected_path)

    report = _service(tmp_path, manager=manager).run()
    payload = report.to_dict()
    human = report.to_human()

    state_key = (
        "journal_state" if metadata == "journal" else "plaintext_fallback_state"
    )
    assert report.ok is False
    assert report.exit_code != 0
    assert payload["activation"][state_key] == "inaccessible"
    assert AuthFailureCode.ENVIRONMENT_BLOCKED.value in payload["diagnostic_codes"]
    assert "inaccessible" in human
    manager.sync_journal.read.assert_not_called()
    manager.get.assert_not_called()
    rendered = report.to_json() + human
    assert str(inspected) not in rendered
    assert str(error) not in rendered


def test_doctor_does_not_trust_fake_cellar_path_without_receipt(tmp_path):
    binary = tmp_path / "Cellar" / "supabase" / "9.9.9" / "bin" / "supabase"
    binary.parent.mkdir(parents=True)
    binary.write_text("fake", encoding="utf-8")

    payload = _service(tmp_path, supabase_path=str(binary)).run().to_dict()

    assert payload["supabase_cli"]["version"] == "unknown"
    assert payload["supabase_cli"]["provenance"] == "unknown"


def test_doctor_reads_node_package_metadata_without_executing_cli(tmp_path):
    package = tmp_path / "node_modules" / "supabase"
    binary = package / "bin" / "supabase"
    binary.parent.mkdir(parents=True)
    binary.write_text("fake", encoding="utf-8")
    (package / "package.json").write_text(
        json.dumps({"name": "supabase", "version": "2.98.2"}),
        encoding="utf-8",
    )

    payload = _service(tmp_path, supabase_path=str(binary)).run().to_dict()

    assert payload["supabase_cli"]["version"] == "2.98.2"
    assert payload["supabase_cli"]["provenance"] == "node"


def test_doctor_classifies_invalid_index_without_overwriting_it(tmp_path):
    index = tmp_path / "accounts.json"
    index.write_text("not-json", encoding="utf-8")
    index.chmod(0o600)
    service = _service(tmp_path)

    report = service.run()

    assert report.ok is False
    assert report.exit_code != 0
    assert report.index["state"] == "invalid"
    assert AuthFailureCode.INDEX_INVALID.value in report.diagnostic_codes
    assert index.read_text(encoding="utf-8") == "not-json"


def test_live_doctor_requires_explicit_account(tmp_path):
    service = _service(tmp_path)

    report = service.run(live=True)

    assert report.ok is False
    assert report.live_result.code is AuthFailureCode.ACCOUNT_REQUIRED
    assert report.live_result.message == "Provide --account <name> when using --live."
    assert report.exit_code != 0


def test_doctor_maps_invalid_active_store_without_calling_it_missing(tmp_path):
    manager = Mock()
    manager.keychain = Mock()
    manager.active_store = Mock()
    manager.keychain.index_path = tmp_path / "accounts.json"
    manager.active_store.read.side_effect = ActiveAccountInvalidError("private")
    manager.config = SupabaseConfig(binary_resolver=lambda _: None)

    report = _service(tmp_path, manager=manager).run()

    assert report.ok is False
    assert report.active_account == {"selected": False, "indexed": False}
    assert AuthFailureCode.ACTIVE_ACCOUNT_INVALID.value in report.diagnostic_codes
    assert AuthFailureCode.ACTIVE_ACCOUNT_MISSING.value not in report.diagnostic_codes


def test_live_doctor_reads_and_validates_selected_account_once(tmp_path):
    manager = Mock()
    manager.keychain = Mock()
    manager.active_store = Mock()
    manager.keychain.index_path = tmp_path / "accounts.json"
    manager.active_store.read.return_value = "work"
    manager.config = SupabaseConfig(binary_resolver=lambda _: None)
    manager.config.supabase_cli = str(tmp_path / "supabase")
    manager.sync_journal = SessionSyncJournal(
        tmp_path / "session-sync.json"
    )
    manager.native_session = NativeSessionSynchronizer(
        manager.config, env={}, supabase_home=tmp_path / ".supabase"
    )
    manager.validate_named_account.return_value = AuthResult.success(
        "Account authenticated by the Supabase API."
    )
    service = _service(tmp_path, manager=manager)

    report = service.run(account="work", live=True)

    assert report.ok is True
    manager.validate_named_account.assert_called_once_with("work")
    manager.get.assert_not_called()
    assert report.live_result.ok is True


def test_doctor_json_contains_no_environment_or_validation_secret(tmp_path):
    token = fake_pat("doctor_json_secret")
    manager = Mock()
    manager.keychain = Mock()
    manager.active_store = Mock()
    manager.keychain.index_path = tmp_path / "accounts.json"
    manager.active_store.read.return_value = "work"
    manager.config = SupabaseConfig(binary_resolver=lambda _: None)
    manager.validate_named_account.return_value = AuthResult.failure(
        AuthFailureCode.TOKEN_REJECTED,
        f"unsafe {token}",
    )
    service = _service(
        tmp_path,
        manager=manager,
        env={"SUPABASE_ACCESS_TOKEN": token, "OTHER_SECRET": token},
    )

    report = service.run(account="work", live=True)
    rendered = report.to_json()
    payload = json.loads(rendered)

    assert token not in rendered
    assert "OTHER_SECRET" not in rendered
    assert payload["environment"] == {
        "supabase_access_token_present": True,
        "telemetry_directory_exists": False,
        "telemetry_directory_writable": True,
    }
    assert payload["live"]["code"] == AuthFailureCode.TOKEN_REJECTED.value
    assert payload["live"]["message"] == "unsafe [REDACTED]"


def test_macos_doctor_human_output_reports_operating_system(tmp_path):
    report = _service(
        tmp_path,
        environment=detect_environment(system_name="Darwin"),
    ).run()

    human = report.to_human()

    assert "Operating system: macos" in human
    assert "Linux distribution" not in human
    assert "keychain" not in human.lower()


def test_linux_doctor_reports_distribution_and_unavailable_credential_store(
    tmp_path,
):
    credential_store = Mock()
    credential_store.service = "supa.cc.tests.credentials"
    credential_store.status.return_value = CredentialStoreStatus(
        backend_name="keyring.backends.SecretService.Keyring",
        available=False,
        message="credential store unavailable",
    )
    signature_resolver = Mock(return_value={"status": "signed"})
    service = _service(
        tmp_path,
        signature_resolver=signature_resolver,
        environment=detect_environment(
            system_name="Linux", os_release="ID=ubuntu\n"
        ),
        credential_store=credential_store,
    )

    report = service.run()

    assert report.runtime["operating_system"] == "linux"
    assert report.runtime["linux_distribution"] == "ubuntu"
    assert report.credentials["available"] is False
    assert report.credentials["remediation"]
    assert AuthFailureCode.KEYCHAIN_READ_FAILED.value in report.diagnostic_codes
    assert report.to_dict()["keychain"]["backend"] == (
        "keyring.backends.SecretService.Keyring"
    )
    assert "keychain" not in report.to_human().lower()
    signature_resolver.assert_not_called()


def test_default_doctor_preserves_legacy_status_but_marks_availability_unverified(
    tmp_path,
):
    credential_store = Mock()
    credential_store.service = "supa.cc.tests.credentials"
    credential_store.status.return_value = CredentialStoreStatus(
        backend_name="keyring.backends.SecretService.Keyring",
        available=True,
        live_probed=False,
    )

    report = _service(
        tmp_path,
        environment=detect_environment(
            system_name="Linux", os_release="ID=ubuntu\n"
        ),
        credential_store=credential_store,
    ).run()

    assert report.credentials["status"] == "available"
    assert report.credentials["live_probed"] is False
    assert report.credentials["configured"] is True
    assert report.credentials["availability"] == "unverified"
    human = report.to_human().lower()
    assert "configured" in human
    assert "not verified" in human
    assert "(available)" not in human
    assert "(available)" not in human
    credential_store.probe.assert_not_called()


def test_linux_doctor_human_output_reports_distribution_and_remediation(
    tmp_path,
):
    credential_store = Mock()
    credential_store.status.return_value = CredentialStoreStatus(
        backend_name="keyring.backends.SecretService.Keyring",
        available=False,
        message="credential store unavailable",
    )
    report = _service(
        tmp_path,
        environment=detect_environment(
            system_name="Linux", os_release="ID=ubuntu\n"
        ),
        credential_store=credential_store,
    ).run()

    human = report.to_human()

    assert "Operating system: linux" in human
    assert "Linux distribution: ubuntu" in human
    assert "Remediation: Install the listed prerequisites" in human
    assert "Secret Service" in human
    assert "keychain" not in human.lower()


def test_doctor_blocks_unknown_linux_without_constructing_account_manager(
    tmp_path, monkeypatch
):
    environment = detect_environment(system_name="Linux", os_release="ID=custom\n")
    token = fake_pat("blocked_doctor")
    monkeypatch.setattr(
        "supa_cc.diagnostic_collectors.AccountService",
        Mock(side_effect=AssertionError("must not construct manager")),
    )

    report = DiagnosticService(
        env={"SUPABASE_ACCESS_TOKEN": token},
        launcher_path=tmp_path / "supa.cc",
        python_executable=tmp_path / "python",
        telemetry_path=tmp_path / ".supabase",
        environment=environment,
    ).run()

    assert report.ok is False
    assert report.runtime["operating_system"] == "linux"
    assert report.runtime["linux_distribution"] == "unknown"
    assert report.credentials["available"] is False
    assert report.credentials["status"] == "unavailable"
    assert report.credentials["remediation"] == installation_guidance(environment).remediation
    assert report.diagnostic_codes == [AuthFailureCode.ENVIRONMENT_BLOCKED.value]
    assert token not in report.to_json()


def test_doctor_blocks_unsupported_os_without_constructing_account_manager(
    tmp_path, monkeypatch
):
    environment = detect_environment(system_name="FreeBSD")
    monkeypatch.setattr(
        "supa_cc.diagnostic_collectors.AccountService",
        Mock(side_effect=AssertionError("must not construct manager")),
    )

    report = DiagnosticService(
        launcher_path=tmp_path / "supa.cc",
        python_executable=tmp_path / "python",
        telemetry_path=tmp_path / ".supabase",
        environment=environment,
    ).run()

    assert report.ok is False
    assert report.runtime["operating_system"] == "unsupported"
    assert report.runtime["linux_distribution"] is None
    assert report.credentials["available"] is False
    assert report.credentials["remediation"] == installation_guidance(environment).remediation
    assert report.diagnostic_codes == [AuthFailureCode.ENVIRONMENT_BLOCKED.value]
