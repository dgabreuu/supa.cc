import json
import os
from pathlib import Path
from unittest.mock import Mock

import supa_cc

from supa_cc.accounts import AccountManager
from supa_cc.auth import (
    ActiveAccountInvalidError,
    AuthFailureCode,
    AuthResult,
)
from supa_cc.config import SupabaseConfig
from supa_cc.credentials import CredentialStoreStatus
from supa_cc.diagnostics import DiagnosticService
from supa_cc.environment import detect_environment
from supa_cc.installation import installation_guidance
from supa_cc.keychain import KEYCHAIN_SERVICE

from helpers import fake_pat


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
        manager = Mock(spec=AccountManager)
        manager.keychain = Mock()
        manager.active_store = Mock()
        manager.keychain.index_path = tmp_path / "accounts.json"
        manager.keychain.service = KEYCHAIN_SERVICE
        manager.active_store.read.return_value = None
        manager.config = SupabaseConfig(
            binary_resolver=lambda _: supabase_path
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
    manager = Mock(spec=AccountManager)
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
    assert report.active_account == "work"
    assert report.keychain_service == KEYCHAIN_SERVICE

    report_with_account_but_not_live = service.run(account="work", live=False)
    manager.get.assert_not_called()
    manager.validate_named_account.assert_not_called()
    assert report_with_account_but_not_live.live_result is None


def test_doctor_reports_effective_custom_keychain_service(tmp_path):
    manager = Mock(spec=AccountManager)
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
    manager = Mock(spec=AccountManager)
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
        "invoked": str(launcher),
        "realpath": str(launcher_target),
        "signature": {"status": "signed", "identifier": "supa-cc-real"},
    }
    assert payload["runtime"]["python"]["invoked"] == str(python_link)
    assert payload["runtime"]["python"]["realpath"] == str(python_target)
    assert payload["runtime"]["python"]["implementation"] == "CPython"
    assert payload["runtime"]["python"]["version"] == "3.14.0"
    assert payload["supabase_cli"]["invoked"] == str(invoked)
    assert payload["supabase_cli"]["realpath"] == str(binary)
    assert payload["supabase_cli"]["version"] == "2.109.1"
    assert payload["supabase_cli"]["provenance"] == "homebrew"
    assert payload["activation"] == {
        "mode": "environment_only",
        "native_session": "unmanaged",
        "profile": "unmanaged",
    }
    assert set(signatures) == {
        str(launcher_target),
        str(python_target),
        str(binary),
    }
    human = report.to_human()
    assert f"{launcher} -> {launcher_target}" in human
    assert f"{python_link} -> {python_target}" in human
    assert f"{invoked} -> {binary}" in human
    assert human.count("assinatura: signed") == 3


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
    assert report.exit_code != 0


def test_doctor_maps_invalid_active_store_without_calling_it_missing(tmp_path):
    manager = Mock(spec=AccountManager)
    manager.keychain = Mock()
    manager.active_store = Mock()
    manager.keychain.index_path = tmp_path / "accounts.json"
    manager.active_store.read.side_effect = ActiveAccountInvalidError("private")
    manager.config = SupabaseConfig(binary_resolver=lambda _: None)

    report = _service(tmp_path, manager=manager).run()

    assert report.ok is False
    assert report.active_account is None
    assert AuthFailureCode.ACTIVE_ACCOUNT_INVALID.value in report.diagnostic_codes
    assert AuthFailureCode.ACTIVE_ACCOUNT_MISSING.value not in report.diagnostic_codes


def test_live_doctor_reads_and_validates_selected_account_once(tmp_path):
    manager = Mock(spec=AccountManager)
    manager.keychain = Mock()
    manager.active_store = Mock()
    manager.keychain.index_path = tmp_path / "accounts.json"
    manager.active_store.read.return_value = "work"
    manager.config = SupabaseConfig(binary_resolver=lambda _: None)
    manager.config.supabase_cli = str(tmp_path / "supabase")
    manager.validate_named_account.return_value = AuthResult.success(
        "Conta autenticada pela API da Supabase."
    )
    service = _service(tmp_path, manager=manager)

    report = service.run(account="work", live=True)

    assert report.ok is True
    manager.validate_named_account.assert_called_once_with("work")
    manager.get.assert_not_called()
    assert report.live_result.ok is True


def test_doctor_json_contains_no_environment_or_validation_secret(tmp_path):
    token = fake_pat("doctor_json_secret")
    manager = Mock(spec=AccountManager)
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

    assert "Sistema operacional: macos" in human
    assert "Distribuição Linux" not in human
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

    assert "Sistema operacional: linux" in human
    assert "Distribuição Linux: ubuntu" in human
    assert "Remediação: Instale os pré-requisitos indicados" in human
    assert "Secret Service" in human
    assert "keychain" not in human.lower()


def test_doctor_blocks_unknown_linux_without_constructing_account_manager(
    tmp_path, monkeypatch
):
    environment = detect_environment(system_name="Linux", os_release="ID=custom\n")
    token = fake_pat("blocked_doctor")
    monkeypatch.setattr(
        "supa_cc.diagnostics.AccountManager",
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
    environment = detect_environment(system_name="Windows")
    monkeypatch.setattr(
        "supa_cc.diagnostics.AccountManager",
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
