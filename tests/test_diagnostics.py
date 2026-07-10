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
from supa_cc.diagnostics import DiagnosticService
from supa_cc.keychain import KEYCHAIN_SERVICE

from helpers import fake_pat


def _service(
    tmp_path,
    *,
    manager=None,
    env=None,
    supabase_path=None,
    signature_resolver=None,
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
