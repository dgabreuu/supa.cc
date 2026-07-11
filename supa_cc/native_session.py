import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Mapping, Optional

from .auth import AuthFailureCode, AuthResult, is_valid_account_name
from .config import SupabaseConfig
from .models import Account


_OPERATIONS = frozenset(("activate", "logout"))
_PHASES = frozenset(
    (
        "intent",
        "credential_backup",
        "native_login",
        "native_verified",
        "local_write",
        "verified",
        "rollback",
    )
)
_LOGOUT_PHASES = _PHASES - {"credential_backup", "native_login"}


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
        descriptor = None
        try:
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(self.path, flags)
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.getuid()
                or stat.S_IMODE(metadata.st_mode) != 0o600
            ):
                raise ValueError("O journal de sincronização é inválido.")
            with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
                descriptor = None
                payload = json.load(stream)
        except FileNotFoundError:
            return None
        except (OSError, ValueError, TypeError) as error:
            raise ValueError("O journal de sincronização é inválido.") from error
        finally:
            if descriptor is not None:
                os.close(descriptor)
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
            directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            directory_descriptor = os.open(self.path.parent, directory_flags)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
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
            return
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        directory_descriptor = os.open(self.path.parent, directory_flags)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)

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
        if payload["operation"] == "activate" and payload["target_account"] is None:
            raise ValueError("O journal de sincronização é inválido.")
        if payload["operation"] == "logout" and (
            payload["target_account"] is not None
            or payload["phase"] not in _LOGOUT_PHASES
        ):
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
        try:
            fallback = self._fallback_metadata()
        except OSError:
            return self._fallback_failure()
        if fallback is not None:
            return self._fallback_failure()
        login = self.config.login_with_access_token(account)
        if not login.ok:
            return login
        try:
            fallback = self._fallback_metadata()
            if fallback is not None:
                self._remove_safe_fallback(fallback)
                return self._fallback_failure()
        except OSError:
            return self._cleanup_failure()
        verification = self.config.verify_persisted_session()
        if not verification.ok:
            return verification
        return AuthResult.success("Conta ativada e sessão nativa sincronizada.")

    def logout(self) -> AuthResult:
        verification = self.config.verify_persisted_session()
        if not verification.ok and verification.code is AuthFailureCode.TOKEN_MISSING:
            return AuthResult.success("Sessão nativa encerrada.")
        if not verification.ok:
            return verification
        result = self.config.logout_session()
        if not result.ok:
            return result
        verification = self.config.verify_persisted_session()
        if not verification.ok and verification.code is AuthFailureCode.TOKEN_MISSING:
            return AuthResult.success("Sessão nativa encerrada.")
        if not verification.ok:
            return self._uncertain_logout_failure()
        return self._uncertain_logout_failure()

    @staticmethod
    def _uncertain_logout_failure() -> AuthResult:
        return AuthResult.failure(
            AuthFailureCode.SYNC_PENDING,
            "O logout pode ter sido concluído, mas requer verificação antes de alterar o estado local.",
        )

    @staticmethod
    def _fallback_failure() -> AuthResult:
        return AuthResult.failure(
            AuthFailureCode.PLAINTEXT_FALLBACK_BLOCKED,
            "A Supabase CLI tentou usar um fallback de token em texto simples.",
        )

    def _fallback_metadata(self):
        try:
            return self.fallback_path.lstat()
        except FileNotFoundError:
            return None

    def _remove_safe_fallback(self, inspected) -> None:
        if not stat.S_ISREG(inspected.st_mode) or inspected.st_uid != os.getuid():
            raise OSError("fallback inseguro")

        descriptor = None
        try:
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(self.fallback_path, flags)
            opened = os.fstat(descriptor)
            current = self.fallback_path.lstat()
            identities = {
                (inspected.st_dev, inspected.st_ino),
                (opened.st_dev, opened.st_ino),
                (current.st_dev, current.st_ino),
            }
            if (
                len(identities) != 1
                or not stat.S_ISREG(opened.st_mode)
                or opened.st_uid != os.getuid()
                or not stat.S_ISREG(current.st_mode)
                or current.st_uid != os.getuid()
            ):
                raise OSError("fallback substituído")
            self.fallback_path.unlink()
        finally:
            if descriptor is not None:
                os.close(descriptor)

    @staticmethod
    def _cleanup_failure() -> AuthResult:
        return AuthResult.failure(
            AuthFailureCode.SYNC_ROLLBACK_FAILED,
            "O fallback inseguro não pôde ser removido com segurança.",
        )
