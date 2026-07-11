import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional

import keyring
import supa_cc

from .accounts import AccountManager
from .auth import (
    ActiveAccountError,
    AuthFailureCode,
    AuthResult,
    classify_local_failure,
    sanitize_sensitive_text,
)
from .keychain import (
    KEYCHAIN_SERVICE,
    AccountIndexInvalidError,
    AccountIndexReadError,
    safe_load_json_index,
)


BackendResolver = Callable[[], str]
SignatureResolver = Callable[[Path], Dict[str, str]]


def _sanitize_structure(value):
    if isinstance(value, str):
        return sanitize_sensitive_text(value)
    if isinstance(value, dict):
        return {
            str(key): _sanitize_structure(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_structure(item) for item in value]
    return value


def _default_backend_name() -> str:
    backend = keyring.get_keyring()
    backend_type = type(backend)
    return f"{backend_type.__module__}.{backend_type.__name__}"


def _safe_invoked_path(value: object) -> str:
    text = str(value) if value is not None else ""
    if not text:
        return ""
    resolved = shutil.which(text) if os.path.sep not in text else None
    return os.path.abspath(resolved or text)


def _safe_realpath(value: object) -> str:
    invoked = _safe_invoked_path(value)
    return os.path.realpath(invoked) if invoked else ""


def _path_writable(path: Path) -> bool:
    candidate = path
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate.exists() and os.access(candidate, os.W_OK)


def _read_json(path: Path) -> Optional[dict]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _metadata_ancestors(path: Path, limit: int = 8):
    current = path.parent
    for _ in range(limit):
        yield current
        if current == current.parent:
            return
        current = current.parent


def _verified_cli_metadata(path: Path) -> Dict[str, str]:
    for parent in _metadata_ancestors(path):
        receipt = _read_json(parent / "INSTALL_RECEIPT.json")
        if receipt is None:
            continue
        source = receipt.get("source")
        source = source if isinstance(source, dict) else {}
        versions = source.get("versions")
        versions = versions if isinstance(versions, dict) else {}
        version = (
            versions.get("stable")
            or source.get("version")
            or receipt.get("version")
        )
        if isinstance(version, str) and version:
            return {"version": version, "provenance": "homebrew"}

    for parent in _metadata_ancestors(path):
        package = _read_json(parent / "package.json")
        if package is None:
            continue
        name = package.get("name")
        version = package.get("version")
        if name in {"supabase", "@supabase/cli"} and isinstance(
            version, str
        ) and version:
            return {"version": version, "provenance": "node"}
    return {"version": "unknown", "provenance": "unknown"}


def _default_signature_resolver(path: Path) -> Dict[str, str]:
    codesign = Path("/usr/bin/codesign")
    if not path.exists() or not codesign.exists():
        return {"status": "unknown"}
    try:
        completed = subprocess.run(
            [str(codesign), "-dvv", str(path)],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
            env={"LC_ALL": "C"},
        )
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return {"status": "unknown"}
    output = f"{completed.stdout or ''}\n{completed.stderr or ''}"
    if completed.returncode != 0:
        return {"status": "unsigned"}
    identity = {"status": "signed"}
    for line in output.splitlines():
        if line.startswith("Identifier="):
            identity["identifier"] = line.partition("=")[2]
        elif line.startswith("TeamIdentifier="):
            identity["team_identifier"] = line.partition("=")[2]
        elif line == "Signature=adhoc":
            identity["status"] = "ad_hoc"
    return identity


def _safe_signature(
    resolver: SignatureResolver,
    path: Path,
) -> Dict[str, str]:
    try:
        identity = resolver(path)
    except Exception:
        return {"status": "unknown"}
    return identity if isinstance(identity, dict) else {"status": "unknown"}


def _supabase_identity(
    invoked: Optional[str],
    realpath: Optional[str],
    signature_resolver: SignatureResolver,
) -> Dict[str, object]:
    if realpath is None:
        return {
            "invoked": invoked,
            "realpath": None,
            "version": "unknown",
            "provenance": "unknown",
            "signature": {"status": "unknown"},
        }
    metadata = _verified_cli_metadata(Path(realpath))
    return {
        "invoked": invoked,
        "realpath": realpath,
        **metadata,
        "signature": _safe_signature(signature_resolver, Path(realpath)),
    }


@dataclass(frozen=True)
class DoctorReport:
    ok: bool
    exit_code: int
    runtime: Dict[str, object] = field(repr=False)
    supabase_cli: Dict[str, object] = field(repr=False)
    keychain_service: str
    keychain_backend: str
    index: Dict[str, object]
    active_account: Optional[str]
    environment: Dict[str, object] = field(repr=False)
    diagnostic_codes: List[str]
    live_result: Optional[AuthResult] = field(default=None, repr=False)
    activation: Dict[str, str] = field(
        default_factory=lambda: {
            "mode": "environment_only",
            "native_session": "unmanaged",
            "profile": "unmanaged",
        }
    )

    def to_dict(self) -> Dict[str, object]:
        live = None
        if self.live_result is not None:
            live = {
                "ok": self.live_result.ok,
                "code": self.live_result.code.value,
                "message": sanitize_sensitive_text(self.live_result.message),
                "exit_code": self.live_result.exit_code,
            }
        report = {
            "ok": self.ok,
            "exit_code": self.exit_code,
            "runtime": self.runtime,
            "supabase_cli": self.supabase_cli,
            "keychain": {
                "service": self.keychain_service,
                "backend": self.keychain_backend,
            },
            "index": self.index,
            "active_account": self.active_account,
            "environment": self.environment,
            "diagnostic_codes": self.diagnostic_codes,
            "activation": self.activation,
            "live": live,
        }
        return _sanitize_structure(report)

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
        )

    def to_human(self) -> str:
        cli_path = (
            self.supabase_cli.get("realpath")
            or self.supabase_cli.get("path")
            or "não encontrada"
        )
        cli_version = self.supabase_cli.get("version") or "unknown"
        provenance = self.supabase_cli.get("provenance") or "unknown"
        launcher = self.runtime.get("launcher")
        launcher_invoked = (
            launcher.get("invoked") if isinstance(launcher, dict) else launcher
        )
        launcher_realpath = (
            launcher.get("realpath") if isinstance(launcher, dict) else launcher
        )
        launcher_signature = (
            launcher.get("signature")
            if isinstance(launcher, dict)
            else None
        )
        python = self.runtime.get("python")
        python_invoked = (
            python.get("invoked")
            if isinstance(python, dict)
            else self.runtime.get("python_executable")
        )
        python_realpath = (
            python.get("realpath")
            if isinstance(python, dict)
            else self.runtime.get("python_realpath")
        )
        python_signature = (
            python.get("signature") if isinstance(python, dict) else None
        )
        cli_invoked = self.supabase_cli.get("invoked")
        cli_realpath = self.supabase_cli.get("realpath") or cli_path
        cli_signature = self.supabase_cli.get("signature")

        def identity_line(label, invoked, realpath, signature):
            status = (
                signature.get("status", "unknown")
                if isinstance(signature, dict)
                else "unknown"
            )
            return (
                f"{label}: {invoked or 'não identificado'} -> "
                f"{realpath or 'não identificado'} (assinatura: {status})"
            )
        active = self.active_account or "não selecionada"
        diagnostics = ", ".join(self.diagnostic_codes) or "none"
        lines = [
            "Supa.cc doctor",
            f"Supa.cc versão: {self.runtime.get('supa_cc_version') or 'unknown'}",
            identity_line(
                "Supa.cc launcher",
                launcher_invoked,
                launcher_realpath,
                launcher_signature,
            ),
            identity_line(
                "Python",
                python_invoked,
                python_realpath,
                python_signature,
            ),
            identity_line(
                "Supabase CLI",
                cli_invoked or cli_path,
                cli_realpath,
                cli_signature,
            ),
            f"Versão da Supabase CLI: {cli_version}",
            f"Proveniência: {provenance}",
            f"Keychain backend: {self.keychain_backend}",
            f"Keychain service: {self.keychain_service}",
            f"Índice: {self.index.get('state')} ({self.index.get('account_count', 0)} contas)",
            f"Conta ativa: {active}",
            "SUPABASE_ACCESS_TOKEN no ambiente: "
            + (
                "presente"
                if self.environment.get("supabase_access_token_present")
                else "ausente"
            ),
            f"Diagnósticos: {diagnostics}",
            "Ativação: environment_only (sessão nativa e perfil não gerenciados)",
        ]
        if self.live_result is not None:
            lines.append(
                "Validação live: "
                f"{self.live_result.code.value} - "
                f"{sanitize_sensitive_text(self.live_result.message)}"
            )
        return sanitize_sensitive_text("\n".join(lines))


class DiagnosticService:
    def __init__(
        self,
        manager: Optional[AccountManager] = None,
        env: Optional[Mapping[str, str]] = None,
        launcher_path: Optional[Path] = None,
        python_executable: Optional[Path] = None,
        telemetry_path: Optional[Path] = None,
        backend_resolver: Optional[BackendResolver] = None,
        signature_resolver: Optional[SignatureResolver] = None,
        python_version: Optional[str] = None,
        python_implementation: Optional[str] = None,
    ):
        self.manager = manager if manager is not None else AccountManager()
        self.env = os.environ if env is None else env
        self.launcher_path = launcher_path or Path(sys.argv[0])
        self.python_executable = python_executable or Path(sys.executable)
        self.telemetry_path = telemetry_path or (Path.home() / ".supabase")
        self.backend_resolver = backend_resolver or _default_backend_name
        self.signature_resolver = (
            signature_resolver or _default_signature_resolver
        )
        self.python_version = python_version or platform.python_version()
        self.python_implementation = (
            python_implementation or platform.python_implementation()
        )

    def run(
        self,
        account: Optional[str] = None,
        live: bool = False,
    ) -> DoctorReport:
        codes: List[str] = []
        ok = True
        exit_code = 0

        try:
            names = safe_load_json_index(self.manager.keychain.index_path)
            index_state = "missing" if names is None else "valid"
            account_count = 0 if names is None else len(names)
        except AccountIndexInvalidError:
            index_state = "invalid"
            account_count = 0
            codes.append(AuthFailureCode.INDEX_INVALID.value)
            ok = False
            exit_code = 1
        except AccountIndexReadError:
            index_state = "unreadable"
            account_count = 0
            codes.append(AuthFailureCode.INDEX_READ_FAILED.value)
            ok = False
            exit_code = 1

        try:
            backend = self.backend_resolver()
        except Exception:
            backend = "indisponível"
            codes.append(AuthFailureCode.KEYCHAIN_READ_FAILED.value)
            ok = False
            exit_code = 1

        cli_identity = _supabase_identity(
            self.manager.config.supabase_cli_invoked,
            self.manager.config.supabase_cli,
            self.signature_resolver,
        )
        if cli_identity["realpath"] is None:
            codes.append(AuthFailureCode.CLI_NOT_FOUND.value)
            ok = False
            exit_code = 1

        telemetry_exists = self.telemetry_path.exists()
        telemetry_writable = _path_writable(self.telemetry_path)
        if not telemetry_writable:
            codes.append(AuthFailureCode.ENVIRONMENT_BLOCKED.value)
            ok = False
            exit_code = 1

        live_result = None
        if live:
            if not account:
                live_result = AuthResult.failure(
                    AuthFailureCode.ACCOUNT_REQUIRED,
                    "Informe --account <nome> ao usar --live.",
                    exit_code=2,
                )
            else:
                live_result = self.manager.validate_named_account(account)
            if not live_result.ok:
                ok = False
                exit_code = live_result.exit_code or 1
                if live_result.code.value not in codes:
                    codes.append(live_result.code.value)

        launcher_invoked = _safe_invoked_path(self.launcher_path)
        launcher_realpath = _safe_realpath(self.launcher_path)
        python_invoked = _safe_invoked_path(self.python_executable)
        python_realpath = _safe_realpath(self.python_executable)
        runtime = {
            "supa_cc_version": supa_cc.__version__,
            "launcher": {
                "invoked": launcher_invoked,
                "realpath": launcher_realpath,
                "signature": _safe_signature(
                    self.signature_resolver,
                    Path(launcher_realpath),
                ),
            },
            "python": {
                "invoked": python_invoked,
                "realpath": python_realpath,
                "implementation": self.python_implementation,
                "version": self.python_version,
                "signature": _safe_signature(
                    self.signature_resolver,
                    Path(python_realpath),
                ),
            },
        }
        index = {
            "path": str(self.manager.keychain.index_path),
            "state": index_state,
            "account_count": account_count,
        }
        environment = {
            "supabase_access_token_present": "SUPABASE_ACCESS_TOKEN" in self.env,
            "telemetry_directory_exists": telemetry_exists,
            "telemetry_directory_writable": telemetry_writable,
        }
        active_account = None
        try:
            active_account = self.manager.active_store.read()
        except ActiveAccountError as error:
            active_failure = classify_local_failure(error)
            codes.append(active_failure.code.value)
            ok = False
            exit_code = exit_code or active_failure.exit_code

        credential_service = getattr(
            getattr(self.manager.keychain, "credential_store", None),
            "service",
            None,
        )
        keychain_service = credential_service
        if not isinstance(keychain_service, str):
            keychain_service = getattr(self.manager.keychain, "service", None)
        if not isinstance(keychain_service, str):
            keychain_service = KEYCHAIN_SERVICE

        return DoctorReport(
            ok=ok,
            exit_code=exit_code,
            runtime=runtime,
            supabase_cli=cli_identity,
            keychain_service=keychain_service,
            keychain_backend=backend,
            index=index,
            active_account=active_account,
            environment=environment,
            diagnostic_codes=codes,
            live_result=live_result,
        )
