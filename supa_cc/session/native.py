import os
import tempfile
from enum import Enum
from pathlib import Path
from typing import Mapping, Optional

from ..auth import AuthFailureCode, AuthResult, is_valid_account_name
from ..supabase_cli import SupabaseCLI
from ..models import Account
from ..state import atomic_write_json, read_json, read_text, secure_remove


_OPERATION_PHASES = {
    "activate": frozenset(
        ("intent", "credential_backup", "native_login", "native_verified", "local_write", "verified", "rollback")
    ),
    "logout": frozenset(
        ("intent", "credential_backup", "native_verified", "local_write", "verified", "rollback")
    ),
    "account_add": frozenset(("intent", "credential_written", "index_committed")),
    "account_replace": frozenset(
        ("intent", "credential_backup", "credential_written", "index_committed")
    ),
    "account_remove": frozenset(("intent", "credential_backup", "index_committed")),
    "active_account_add": frozenset(
        ("intent", "index_committed", "native_login", "native_verified")
    ),
}
_JOURNAL_MAX_BYTES = 4096


class MutationState(str, Enum):
    NONE = "none"
    ATTEMPTED = "attempted"
    VERIFIED = "verified"
    UNCERTAIN = "uncertain"


def access_token_fallback_path(env=None, home=None) -> Path:
    values = os.environ if env is None else env
    root = (
        Path(values["SUPABASE_HOME"])
        if values.get("SUPABASE_HOME")
        else (Path.home() if home is None else Path(home)) / ".supabase"
    )
    return root / "access-token"


class SessionSyncJournal:
    def __init__(self, path: Path):
        self.path = Path(path)

    def read(self):
        try:
            payload = read_json(self.path, _JOURNAL_MAX_BYTES)
        except (OSError, ValueError, TypeError) as error:
            raise ValueError("The synchronization journal is invalid.") from error
        if payload is None:
            return None
        self._validate(payload)
        return payload

    def write(
        self,
        operation: str,
        target_account: Optional[str],
        previous_account: Optional[str],
        phase: str,
    ) -> None:
        payload = {
            "operation": operation,
            "target_account": target_account,
            "previous_account": previous_account,
            "phase": phase,
        }
        self._validate(payload)
        atomic_write_json(self.path, payload)

    def clear(self) -> None:
        secure_remove(self.path)

    @staticmethod
    def _validate(payload) -> None:
        if not isinstance(payload, dict) or set(payload) != {
            "operation", "target_account", "previous_account", "phase"
        }:
            raise ValueError("The synchronization journal is invalid.")
        phases = _OPERATION_PHASES.get(payload["operation"])
        if phases is None or payload["phase"] not in phases:
            raise ValueError("The synchronization journal is invalid.")
        for key in ("target_account", "previous_account"):
            value = payload[key]
            if value is not None and not is_valid_account_name(value):
                raise ValueError("The synchronization journal is invalid.")
        if payload["operation"] == "activate" and payload["target_account"] is None:
                raise ValueError("The synchronization journal is invalid.")
        if payload["operation"] == "logout" and (
            payload["target_account"] is not None
        ):
                raise ValueError("The synchronization journal is invalid.")
        if (payload["operation"].startswith("account_") or payload["operation"] == "active_account_add") and (
            payload["target_account"] is None
            or payload["previous_account"] is not None
        ):
            raise ValueError("The synchronization journal is invalid.")


class NativeSessionSynchronizer:
    def __init__(
        self,
        config: SupabaseCLI,
        env: Optional[Mapping[str, str]] = None,
        supabase_home: Optional[Path] = None,
    ):
        self.config = config
        self.env = os.environ if env is None else env
        self.fallback_path = (
            Path(supabase_home) / "access-token"
            if supabase_home is not None
            else access_token_fallback_path(self.env)
        )
        self.mutation_state = MutationState.NONE

    def preflight(self) -> AuthResult:
        self.mutation_state = MutationState.NONE
        if "SUPABASE_ACCESS_TOKEN" in self.env:
            return AuthResult.failure(
                AuthFailureCode.ENVIRONMENT_BLOCKED,
                "Remove SUPABASE_ACCESS_TOKEN from the environment before synchronizing.",
            )
        try:
            if self._fallback_metadata() is not None:
                return self._fallback_failure()
        except OSError:
            return self._fallback_failure()
        try:
            profile_path = self.fallback_path.parent / "profile"
            profile = read_text(profile_path, 64)
            if profile is None:
                profile = "supabase"
            if profile.strip() != "supabase":
                return self._profile_failure()
        except (OSError, UnicodeError, ValueError):
            return self._profile_failure()
        cli = self.config.preflight()
        return cli

    def activate(self, account: Account) -> AuthResult:
        preflight = self.preflight()
        if preflight.ok is False:
            return preflight
        return self._activate_preflighted(account)

    def _activate_preflighted(self, account: Account) -> AuthResult:
        with tempfile.TemporaryDirectory(prefix="supa-cc-native-") as directory:
            controlled_home = Path(directory)
            controlled_home.chmod(0o700)
            (controlled_home / "access-token").mkdir(mode=0o700)
            self.mutation_state = MutationState.ATTEMPTED
            login = self.config.login_with_access_token(
                account, supabase_home=controlled_home, profile="supabase"
            )
            if not login.ok:
                return login
            verification = self.config.verify_persisted_session(
                supabase_home=controlled_home, profile="supabase"
            )
            if not verification.ok:
                self.mutation_state = MutationState.UNCERTAIN
                if verification.code in {
                    AuthFailureCode.TOKEN_MISSING,
                    AuthFailureCode.TOKEN_REJECTED,
                    AuthFailureCode.API_AUTH_FAILED,
                }:
                    return AuthResult.failure(
                        AuthFailureCode.NATIVE_VERIFICATION_FAILED,
                        "The Supabase CLI could not recover its persisted session.",
                        exit_code=verification.exit_code,
                    )
                return verification
            self.mutation_state = MutationState.VERIFIED
            return AuthResult.success("Account activated and native session synchronized.")

    def logout(self) -> AuthResult:
        preflight = self.preflight()
        if preflight.ok is False:
            return preflight
        return self._logout_preflighted()

    def _logout_preflighted(self) -> AuthResult:
        with tempfile.TemporaryDirectory(prefix="supa-cc-native-") as directory:
            controlled_home = Path(directory)
            controlled_home.chmod(0o700)
            (controlled_home / "access-token").mkdir(mode=0o700)
            return self._logout_controlled(controlled_home)

    def _logout_controlled(self, controlled_home: Path) -> AuthResult:
        verification = self.config.verify_persisted_session(
            supabase_home=controlled_home, profile="supabase"
        )
        if not verification.ok and verification.code is AuthFailureCode.TOKEN_MISSING:
            return AuthResult.success("Native session ended.")
        if not verification.ok:
            return verification
        self.mutation_state = MutationState.ATTEMPTED
        try:
            result = self.config.logout_session(
                supabase_home=controlled_home, profile="supabase"
            )
        except (OSError, ValueError):
            self.mutation_state = MutationState.UNCERTAIN
            return self._uncertain_logout_failure()
        if not result.ok:
            self.mutation_state = MutationState.UNCERTAIN
            return result
        try:
            verification = self.config.verify_persisted_session(
                supabase_home=controlled_home, profile="supabase"
            )
        except (OSError, ValueError):
            self.mutation_state = MutationState.UNCERTAIN
            return self._uncertain_logout_failure()
        if not verification.ok and verification.code is AuthFailureCode.TOKEN_MISSING:
            self.mutation_state = MutationState.VERIFIED
            return AuthResult.success("Native session ended.")
        if not verification.ok:
            self.mutation_state = MutationState.UNCERTAIN
            return self._uncertain_logout_failure()
        self.mutation_state = MutationState.UNCERTAIN
        return self._uncertain_logout_failure()

    @staticmethod
    def _profile_failure() -> AuthResult:
        return AuthResult.failure(
            AuthFailureCode.PROFILE_MISMATCH,
            "Use only the official 'supabase' profile before synchronizing.",
        )

    @staticmethod
    def _uncertain_logout_failure() -> AuthResult:
        return AuthResult.failure(
            AuthFailureCode.SYNC_PENDING,
            "Logout may have completed, but verification is required before changing local state.",
        )

    @staticmethod
    def _fallback_failure() -> AuthResult:
        return AuthResult.failure(
            AuthFailureCode.PLAINTEXT_FALLBACK_BLOCKED,
            "The Supabase CLI attempted to use a plaintext token fallback.",
        )

    def _fallback_metadata(self):
        try:
            return self.fallback_path.lstat()
        except FileNotFoundError:
            return None
