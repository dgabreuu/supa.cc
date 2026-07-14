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

from .accounts import AccountService
from .accounts.state import StateInvalidError, StateReadError
from .auth import (
    ActiveAccountError,
    AccountIndexInvalidError,
    AccountIndexReadError,
    AuthFailureCode,
    AuthResult,
    classify_local_failure,
)
from .account_store import KEYCHAIN_SERVICE, safe_load_json_index
from .credentials import CredentialStoreStatus
from .environment import Environment, OperatingSystem, detect_environment
from .installation import detect_installation_channel, installation_guidance
from .native_session import access_token_fallback_path
from .state import read_text
from .diagnostic_renderers import render_human, render_json, report_to_dict


BackendResolver = Callable[[], str]
SignatureResolver = Callable[[Path], Dict[str, str]]


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


def _path_relation(invoked: object, realpath: object) -> str:
    if not invoked or not realpath:
        return "unavailable"
    if os.path.normcase(os.path.abspath(str(invoked))) == os.path.normcase(
        os.path.abspath(str(realpath))
    ):
        return "same"
    return "symlinked"


def _public_path(value: object) -> Optional[str]:
    if value is None:
        return None
    text = str(value)
    if not text:
        return ""
    path = Path(text)
    if not path.is_absolute():
        return f"<local-path>/{path.name}"

    normalized = os.path.normcase(os.path.abspath(text))
    home = os.path.normcase(os.path.abspath(os.path.expanduser("~")))
    if normalized == home or normalized.startswith(home + os.path.sep):
        relative = os.path.relpath(normalized, home)
        return "~" if relative == "." else f"~/{relative.replace(os.path.sep, '/')}"

    temporary_prefixes = (
        "/tmp",
        "/private/tmp",
        "/var/folders",
        "/private/var/folders",
    )
    if any(
        normalized == prefix or normalized.startswith(prefix + os.path.sep)
        for prefix in temporary_prefixes
    ):
        return f"<temp>/{path.name}"

    public_prefixes = (
        "/usr",
        "/bin",
        "/sbin",
        "/opt",
        "/Applications",
        "/Library",
        "/System",
    )
    if any(
        normalized == os.path.normcase(prefix)
        or normalized.startswith(os.path.normcase(prefix) + os.path.sep)
        for prefix in public_prefixes
    ):
        return text
    return f"<local-path>/{path.name}"


def _path_writable(path: Path) -> bool:
    candidate = path
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate.exists() and os.access(candidate, os.W_OK)


def _metadata_path_state(owner: object, attribute: str) -> str:
    path = getattr(owner, attribute, None)
    try:
        Path(os.fspath(path)).lstat()
    except FileNotFoundError:
        return "absent"
    except (TypeError, ValueError, OSError):
        return "inaccessible"
    return "present"


def collect_activation_consistency(journal, native_session, env):
    journal_state = _metadata_path_state(journal, "path")
    fallback_state = _metadata_path_state(native_session, "fallback_path")
    codes = []
    if journal_state == "present":
        try:
            pending = journal.read()
        except (OSError, TypeError, ValueError):
            pending = True
        if pending:
            codes.append(AuthFailureCode.SYNC_PENDING.value)
    if fallback_state == "present":
        codes.append(AuthFailureCode.PLAINTEXT_FALLBACK_BLOCKED.value)
    if "inaccessible" in (journal_state, fallback_state):
        codes.append(AuthFailureCode.ENVIRONMENT_BLOCKED.value)

    profile = "unmanaged"
    fallback_path = getattr(native_session, "fallback_path", None)
    if fallback_path is not None:
        try:
            value = read_text(Path(fallback_path).parent / "profile", 64)
            if value is not None:
                profile = "supabase" if value.strip() == "supabase" else "unsupported"
        except (OSError, TypeError, UnicodeError, ValueError):
            profile = "inaccessible"
            codes.append(AuthFailureCode.ENVIRONMENT_BLOCKED.value)
        if profile == "unsupported":
            codes.append(AuthFailureCode.PROFILE_MISMATCH.value)
    return {
        "mode": "native_session",
        "native_session": "managed",
        "profile": profile,
        "journal_present": journal_state == "present",
        "journal_state": journal_state,
        "plaintext_fallback_present": fallback_state == "present",
        "plaintext_fallback_state": fallback_state,
        "parent_override_present": "SUPABASE_ACCESS_TOKEN" in env,
    }, codes


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
    environment: Environment,
) -> Dict[str, object]:
    signature = (
        _safe_signature(signature_resolver, Path(realpath))
        if environment.operating_system is OperatingSystem.MACOS and realpath
        else {"status": "not_applicable"}
    )
    if realpath is None:
        return {
            "invoked": _public_path(invoked),
            "realpath": None,
            "path_relation": "unavailable",
            "version": "unknown",
            "provenance": "unknown",
            "signature": signature,
        }
    metadata = _verified_cli_metadata(Path(realpath))
    return {
        "invoked": _public_path(invoked),
        "realpath": _public_path(realpath),
        "path_relation": _path_relation(invoked, realpath),
        **metadata,
        "signature": signature,
    }


@dataclass(frozen=True)
class _DoctorReportFields:
    ok: bool
    exit_code: int
    runtime: Dict[str, object] = field(repr=False)
    supabase_cli: Dict[str, object] = field(repr=False)
    keychain_service: str
    keychain_backend: str
    index: Dict[str, object]
    active_account: Dict[str, bool]
    environment: Dict[str, object] = field(repr=False)
    diagnostic_codes: List[str]
    credentials: Dict[str, object] = field(default_factory=dict, repr=False)
    live_result: Optional[AuthResult] = field(default=None, repr=False)
    activation: Dict[str, object] = field(
        default_factory=lambda: {
            "mode": "native_session",
            "native_session": "managed",
            "profile": "unmanaged",
            "journal_present": False,
            "journal_state": "absent",
            "plaintext_fallback_present": False,
            "plaintext_fallback_state": "absent",
            "parent_override_present": False,
        }
    )

class DoctorReport(_DoctorReportFields):
    def to_dict(self) -> Dict[str, object]:
        return report_to_dict(self)

    def to_json(self) -> str:
        return render_json(self.to_dict())

    def to_human(self) -> str:
        return render_human(self)


class DiagnosticService:
    def __init__(
        self,
        manager: Optional[object] = None,
        env: Optional[Mapping[str, str]] = None,
        launcher_path: Optional[Path] = None,
        python_executable: Optional[Path] = None,
        telemetry_path: Optional[Path] = None,
        backend_resolver: Optional[BackendResolver] = None,
        signature_resolver: Optional[SignatureResolver] = None,
        python_version: Optional[str] = None,
        python_implementation: Optional[str] = None,
        environment: Optional[Environment] = None,
        credential_store=None,
    ):
        self.environment = environment or detect_environment()
        self._manager = manager
        self.env = os.environ if env is None else env
        self.launcher_path = launcher_path or Path(sys.argv[0])
        self.python_executable = python_executable or Path(sys.executable)
        self.telemetry_path = telemetry_path or access_token_fallback_path(
            self.env
        ).parent
        self.backend_resolver = backend_resolver or _default_backend_name
        self.signature_resolver = (
            signature_resolver or _default_signature_resolver
        )
        self.python_version = python_version or platform.python_version()
        self.python_implementation = (
            python_implementation or platform.python_implementation()
        )
        self.credential_store = credential_store

    def _get_manager(self):
        if self._manager is None:
            self._manager = AccountService()
        return self._manager

    def _environment_blocked_report(self) -> DoctorReport:
        guidance = installation_guidance(self.environment)
        launcher_invoked = _safe_invoked_path(self.launcher_path)
        launcher_realpath = _safe_realpath(self.launcher_path)
        python_invoked = _safe_invoked_path(self.python_executable)
        python_realpath = _safe_realpath(self.python_executable)
        runtime = {
            "supa_cc_version": supa_cc.__version__,
            "installation_channel": detect_installation_channel().value,
            "operating_system": self.environment.operating_system.value,
            "linux_distribution": (
                self.environment.distribution.value
                if self.environment.distribution is not None
                else None
            ),
            "launcher": {
                "invoked": _public_path(launcher_invoked),
                "realpath": _public_path(launcher_realpath),
                "path_relation": _path_relation(launcher_invoked, launcher_realpath),
                "signature": {"status": "not_applicable"},
            },
            "python": {
                "invoked": _public_path(python_invoked),
                "realpath": _public_path(python_realpath),
                "path_relation": _path_relation(python_invoked, python_realpath),
                "implementation": self.python_implementation,
                "version": self.python_version,
                "signature": {"status": "not_applicable"},
            },
        }
        return DoctorReport(
            ok=False,
            exit_code=1,
            runtime=runtime,
            supabase_cli={
                "invoked": None,
                "realpath": None,
                "version": "unknown",
                "provenance": "unknown",
                "signature": {"status": "not_applicable"},
            },
            keychain_service=KEYCHAIN_SERVICE,
            keychain_backend="unavailable",
            credentials={
                "service": KEYCHAIN_SERVICE,
                "backend": "unavailable",
                "available": False,
                "status": "unavailable",
                "message": "The credential store is unavailable in this environment.",
                "remediation": guidance.remediation,
            },
            index={
                "path": _public_path(
                    self.environment.config_directory() / "state.json"
                ),
                "state": "not_checked",
                "account_count": 0,
            },
            active_account={"selected": False, "indexed": False},
            environment={
                "supabase_access_token_present": "SUPABASE_ACCESS_TOKEN" in self.env,
                "telemetry_directory_exists": self.telemetry_path.exists(),
                "telemetry_directory_writable": _path_writable(self.telemetry_path),
            },
            diagnostic_codes=[AuthFailureCode.ENVIRONMENT_BLOCKED.value],
            activation={
                "mode": "native_session",
                "native_session": "managed",
                "profile": "unmanaged",
                "journal_present": False,
                "journal_state": "absent",
                "plaintext_fallback_present": False,
                "plaintext_fallback_state": "absent",
                "parent_override_present": "SUPABASE_ACCESS_TOKEN" in self.env,
            },
        )

    def run(
        self,
        account: Optional[str] = None,
        live: bool = False,
    ) -> DoctorReport:
        if not self.environment.is_supported:
            return self._environment_blocked_report()

        manager = self._get_manager()
        uses_versioned_state = isinstance(manager, AccountService)
        codes: List[str] = []
        ok = True
        exit_code = 0
        names = None
        account_state = None

        try:
            if uses_versioned_state:
                account_state = manager.state_repository.load()
                names = list(account_state.aliases)
                index_state = "valid"
                account_count = len(names)
                index_path = manager.state_repository.path
            else:
                names = safe_load_json_index(manager.keychain.index_path)
                index_state = "missing" if names is None else "valid"
                account_count = 0 if names is None else len(names)
                index_path = manager.keychain.index_path
        except (AccountIndexInvalidError, StateInvalidError) as error:
            failure = classify_local_failure(error, operation="doctor")
            index_state = "invalid"
            account_count = 0
            index_path = (
                manager.state_repository.path
                if uses_versioned_state
                else manager.keychain.index_path
            )
            codes.append(failure.code.value)
            ok = False
            exit_code = 1
        except (AccountIndexReadError, StateReadError) as error:
            index_state = "unreadable"
            account_count = 0
            index_path = (
                manager.state_repository.path
                if uses_versioned_state
                else manager.keychain.index_path
            )
            codes.append(
                classify_local_failure(error, operation="doctor").code.value
            )
            ok = False
            exit_code = 1

        credential_store = self.credential_store
        if credential_store is None:
            credential_store = (
                getattr(manager, "credential_store", None)
                if uses_versioned_state
                else getattr(manager.keychain, "credential_store", None)
            )
        credential_status = None
        if credential_store is not None:
            try:
                status = credential_store.status()
            except Exception:
                status = None
            if isinstance(status, CredentialStoreStatus):
                credential_status = status

        if credential_status is not None:
            backend = credential_status.backend_name
        else:
            try:
                backend = self.backend_resolver()
            except Exception:
                backend = "unavailable"
                codes.append(AuthFailureCode.KEYCHAIN_READ_FAILED.value)
                ok = False
                exit_code = 1

        cli = manager.cli if uses_versioned_state else manager.config
        cli_identity = _supabase_identity(
            cli.supabase_cli_invoked,
            cli.supabase_cli,
            self.signature_resolver,
            self.environment,
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
                    "Provide --account <name> when using --live.",
                    exit_code=2,
                )
            else:
                live_result = manager.validate_named_account(account)
            if not live_result.ok:
                ok = False
                exit_code = live_result.exit_code or 1
                if live_result.code.value not in codes:
                    codes.append(live_result.code.value)

        launcher_invoked = _safe_invoked_path(self.launcher_path)
        launcher_realpath = _safe_realpath(self.launcher_path)
        python_invoked = _safe_invoked_path(self.python_executable)
        python_realpath = _safe_realpath(self.python_executable)
        signature = lambda path: (
            _safe_signature(self.signature_resolver, path)
            if self.environment.operating_system is OperatingSystem.MACOS
            else {"status": "not_applicable"}
        )
        runtime = {
            "supa_cc_version": supa_cc.__version__,
            "installation_channel": detect_installation_channel().value,
            "operating_system": self.environment.operating_system.value,
            "linux_distribution": (
                self.environment.distribution.value
                if self.environment.distribution is not None
                else None
            ),
            "launcher": {
                "invoked": _public_path(launcher_invoked),
                "realpath": _public_path(launcher_realpath),
                "path_relation": _path_relation(launcher_invoked, launcher_realpath),
                "signature": signature(Path(launcher_realpath)),
            },
            "python": {
                "invoked": _public_path(python_invoked),
                "realpath": _public_path(python_realpath),
                "path_relation": _path_relation(python_invoked, python_realpath),
                "implementation": self.python_implementation,
                "version": self.python_version,
                "signature": signature(Path(python_realpath)),
            },
        }
        index = {
            "path": _public_path(index_path),
            "state": index_state,
            "account_count": account_count,
        }
        environment = {
            "supabase_access_token_present": "SUPABASE_ACCESS_TOKEN" in self.env,
            "telemetry_directory_exists": telemetry_exists,
            "telemetry_directory_writable": telemetry_writable,
        }
        if uses_versioned_state:
            pending = (
                account_state.pending_transition
                if account_state is not None
                else None
            )
            fallback_state = _metadata_path_state(
                manager.native_session, "fallback_path"
            )
            fallback_present = fallback_state == "present"
            activation = {
                "mode": "native_session",
                "native_session": "managed",
                "profile": "supabase",
                "journal_present": pending is not None,
                "journal_state": "pending" if pending is not None else "absent",
                "plaintext_fallback_present": fallback_present,
                "plaintext_fallback_state": fallback_state,
                "parent_override_present": "SUPABASE_ACCESS_TOKEN" in self.env,
            }
            consistency_codes = (
                [AuthFailureCode.SYNC_PENDING.value] if pending is not None else []
            )
            if fallback_present:
                consistency_codes.append(
                    AuthFailureCode.PLAINTEXT_FALLBACK_BLOCKED.value
                )
            elif fallback_state == "inaccessible":
                consistency_codes.append(AuthFailureCode.ENVIRONMENT_BLOCKED.value)
        else:
            activation, consistency_codes = collect_activation_consistency(
                getattr(manager, "sync_journal", None),
                getattr(manager, "native_session", None),
                self.env,
            )
        for code in consistency_codes:
            if code not in codes:
                codes.append(code)
        if consistency_codes:
            ok = False
            exit_code = exit_code or 1
        active_account = None
        try:
            active_account = (
                None if account_state is None else account_state.confirmed_active
            ) if uses_versioned_state else manager.active_store.read()
        except ActiveAccountError as error:
            active_failure = classify_local_failure(error)
            codes.append(active_failure.code.value)
            ok = False
            exit_code = exit_code or active_failure.exit_code
        if (
            active_account is not None
            and names is not None
            and active_account not in names
        ):
            if AuthFailureCode.ACTIVE_ACCOUNT_MISSING.value not in codes:
                codes.append(AuthFailureCode.ACTIVE_ACCOUNT_MISSING.value)
            ok = False
            exit_code = exit_code or 1

        credential_service = getattr(credential_store, "service", None)
        keychain_service = credential_service
        if not isinstance(keychain_service, str) and not uses_versioned_state:
            keychain_service = getattr(manager.keychain, "service", None)
        if not isinstance(keychain_service, str):
            keychain_service = KEYCHAIN_SERVICE

        guidance = installation_guidance(self.environment)
        credentials = {
            "service": keychain_service,
            "backend": backend,
            "configured": True,
            "available": (
                credential_status.available
                if credential_status is not None
                else True
            ),
            "status": (
                "available"
                if credential_status is None or credential_status.available
                else "unavailable"
            ),
            "live_probed": (
                credential_status.live_probed
                if credential_status is not None
                else False
            ),
            "availability": (
                "available" if credential_status.available else "unavailable"
            )
            if credential_status is not None and credential_status.live_probed
            else "unverified",
            "message": credential_status.message if credential_status else "",
            "remediation": guidance.remediation,
        }
        if credential_status is not None and not credential_status.available:
            codes.append(AuthFailureCode.KEYCHAIN_READ_FAILED.value)
            ok = False
            exit_code = exit_code or 1

        return DoctorReport(
            ok=ok,
            exit_code=exit_code,
            runtime=runtime,
            supabase_cli=cli_identity,
            keychain_service=keychain_service,
            keychain_backend=backend,
            credentials=credentials,
            index=index,
            active_account={
                "selected": active_account is not None,
                "indexed": (
                    active_account is not None
                    and names is not None
                    and active_account in names
                ),
            },
            environment=environment,
            diagnostic_codes=codes,
            live_result=live_result,
            activation=activation,
        )
