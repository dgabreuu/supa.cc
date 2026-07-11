import json
import os
import tempfile
from pathlib import Path
from typing import Mapping, Optional

from .auth import AuthFailureCode, AuthResult, is_valid_account_name
from .config import SupabaseConfig
from .models import Account


_OPERATIONS = frozenset(("activate", "logout"))
_PHASES = frozenset(
    ("intent", "native_login", "native_verified", "local_write", "verified", "rollback")
)


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
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError, TypeError) as error:
            raise ValueError("O journal de sincronização é inválido.") from error
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
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.parent.chmod(0o700)
        descriptor = None
        temporary_path = None
        try:
            descriptor, temporary_path = tempfile.mkstemp(
                prefix=f".{self.path.name}.", dir=self.path.parent
            )
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                descriptor = None
                json.dump(payload, stream, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, self.path)
            temporary_path = None
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if temporary_path is not None:
                try:
                    os.unlink(temporary_path)
                except FileNotFoundError:
                    pass

    def clear(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass

    @staticmethod
    def _validate(payload) -> None:
        if not isinstance(payload, dict) or set(payload) != {
            "operation", "target_account", "previous_account", "phase"
        }:
            raise ValueError("O journal de sincronização é inválido.")
        if payload["operation"] not in _OPERATIONS or payload["phase"] not in _PHASES:
            raise ValueError("O journal de sincronização é inválido.")
        for key in ("target_account", "previous_account"):
            value = payload[key]
            if value is not None and not is_valid_account_name(value):
                raise ValueError("O journal de sincronização é inválido.")


class NativeSessionSynchronizer:
    def __init__(
        self,
        config: SupabaseConfig,
        env: Optional[Mapping[str, str]] = None,
        supabase_home: Optional[Path] = None,
        journal: Optional[SessionSyncJournal] = None,
    ):
        self.config = config
        self.env = os.environ if env is None else env
        self.fallback_path = (
            Path(supabase_home) / "access-token"
            if supabase_home is not None
            else access_token_fallback_path(self.env)
        )
        self.journal = journal

    def activate(self, account: Account) -> AuthResult:
        if self.env.get("SUPABASE_ACCESS_TOKEN"):
            return AuthResult.failure(
                AuthFailureCode.ENVIRONMENT_BLOCKED,
                "Remova SUPABASE_ACCESS_TOKEN do ambiente antes de sincronizar.",
            )
        if self.fallback_path.exists():
            return self._fallback_failure()
        login = self.config.login_with_access_token(account)
        if not login.ok:
            return login
        if self.fallback_path.exists():
            try:
                self.fallback_path.unlink()
            except OSError:
                pass
            return self._fallback_failure()
        verification = self.config.verify_persisted_session()
        if not verification.ok:
            return verification
        return AuthResult.success("Conta ativada e sessão nativa sincronizada.")

    def logout(self) -> AuthResult:
        result = self.config.logout_session()
        if not result.ok:
            return result
        verification = self.config.verify_persisted_session()
        if not verification.ok and verification.code is AuthFailureCode.TOKEN_MISSING:
            return AuthResult.success("Sessão nativa encerrada.")
        return AuthResult.failure(
            AuthFailureCode.NATIVE_VERIFICATION_FAILED,
            "Não foi possível confirmar o encerramento da sessão nativa.",
        )

    @staticmethod
    def _fallback_failure() -> AuthResult:
        return AuthResult.failure(
            AuthFailureCode.PLAINTEXT_FALLBACK_BLOCKED,
            "A Supabase CLI tentou usar um fallback de token em texto simples.",
        )
