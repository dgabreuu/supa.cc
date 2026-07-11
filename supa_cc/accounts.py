import fcntl
import os
import stat
from contextlib import contextmanager
from typing import Callable, Iterator, List, Optional, Sequence, Tuple

from .auth import (
    ActiveAccountStore,
    ActiveAccountError,
    ActiveAccountInvalidError,
    ActiveAccountPermissionDeniedError,
    ActiveAccountReadError,
    ActiveAccountWriteError,
    AccountTransactionError,
    AuthFailureCode,
    AuthResult,
    CommandResult,
    CredentialAccessError,
    InvalidAccessTokenError,
    InvalidAccountNameError,
    classify_local_failure,
    is_valid_account_name,
)
from .config import SupabaseConfig
from .environment import detect_environment
from .models import Account
from .keychain import KeychainManager
from .native_session import NativeSessionSynchronizer, SessionSyncJournal


class _SyncUnlockError(OSError):
    pass


class _SyncCloseError(OSError):
    pass


class AccountManager:
    def __init__(
        self,
        keychain: Optional[KeychainManager] = None,
        config: Optional[SupabaseConfig] = None,
        active_store: Optional[ActiveAccountStore] = None,
        native_session: Optional[NativeSessionSynchronizer] = None,
        sync_journal: Optional[SessionSyncJournal] = None,
    ):
        environment = detect_environment()
        self.keychain = (
            keychain
            if keychain is not None
            else KeychainManager(environment=environment)
        )
        self.config = config if config is not None else SupabaseConfig()
        config_directory = environment.config_directory()
        self.active_store = (
            active_store
            if active_store is not None
            else ActiveAccountStore(
                path=config_directory / "active-account"
            )
        )
        self.sync_journal = (
            sync_journal
            if sync_journal is not None
            else SessionSyncJournal(config_directory / "session-sync.json")
        )
        self.native_session = (
            native_session
            if native_session is not None
            else NativeSessionSynchronizer(self.config, journal=self.sync_journal)
        )
        self._sync_lock_path = self.sync_journal.path.with_name(".session-sync.lock")

    @contextmanager
    def _sync_lock(self) -> Iterator[None]:
        self._sync_lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._sync_lock_path.parent.chmod(0o700)
        flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(self._sync_lock_path, flags, 0o600)
        locked = False
        body_error = None
        unlock_failed = False
        close_failed = False
        try:
            opened = os.fstat(descriptor)
            current = self._sync_lock_path.lstat()
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_uid != os.getuid()
                or stat.S_IMODE(opened.st_mode) != 0o600
                or not stat.S_ISREG(current.st_mode)
                or current.st_uid != os.getuid()
                or stat.S_IMODE(current.st_mode) != 0o600
                or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino)
            ):
                raise ValueError("O lock de sincronização é inválido.")
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            locked = True
            current = self._sync_lock_path.lstat()
            if (
                not stat.S_ISREG(current.st_mode)
                or current.st_uid != os.getuid()
                or stat.S_IMODE(current.st_mode) != 0o600
                or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino)
            ):
                raise ValueError("O lock de sincronização é inválido.")
            try:
                yield
            except BaseException as error:
                body_error = error
        finally:
            try:
                if locked:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
            except OSError:
                unlock_failed = True
            finally:
                try:
                    os.close(descriptor)
                except OSError:
                    close_failed = True
        if body_error is not None:
            raise body_error
        if unlock_failed:
            raise _SyncUnlockError()
        if close_failed:
            raise _SyncCloseError()

    def _run_with_sync_lock(self, operation: Callable[[], AuthResult]) -> AuthResult:
        result = None
        try:
            with self._sync_lock():
                result = operation()
            return result
        except _SyncCloseError:
            if result is not None:
                return result
            return self._pending_sync_failure()
        except _SyncUnlockError:
            try:
                pending = self.sync_journal.read() is not None
            except (OSError, ValueError):
                pending = True
            if pending:
                return self._pending_sync_failure()
            return AuthResult.failure(
                AuthFailureCode.ENVIRONMENT_BLOCKED,
                "A operação foi concluída, mas o lock de sincronização não pôde ser finalizado.",
            )
        except (OSError, ValueError):
            return self._pending_sync_failure()

    def add(self, name: str, token: str) -> Account:
        """Adiciona nova conta."""
        if not name or len(name) < 1 or len(name) > 50:
            raise InvalidAccountNameError(
                "Nome da conta deve ter entre 1 e 50 caracteres."
            )
        if not is_valid_account_name(name):
            raise InvalidAccountNameError(
                "Nome da conta contém caracteres inválidos. "
                "Use apenas letras, números, hífens e underscores."
            )
        account = Account(name=name, token=token)
        if not account.validate_token():
            raise InvalidAccessTokenError(
                "Token inválido: o valor não atende ao formato PAT Supabase."
            )
        try:
            with self._sync_lock():
                self._add_locked(account)
        except AccountTransactionError:
            raise
        except OSError:
            raise
        except Exception:
            raise AccountTransactionError(
                "Não foi possível atualizar a conta ativa com segurança."
            ) from None
        return account

    def _add_locked(self, account: Account) -> None:
        recovery = self._recover_pending_sync_locked()
        if not recovery.ok:
            raise AccountTransactionError(recovery.message)
        try:
            active_name = self.active_store.read()
        except ActiveAccountError:
            raise AccountTransactionError(
                "Não foi possível confirmar a conta ativa com segurança."
            ) from None
        if active_name != account.name:
            self.keychain.add_account(account)
            return
        self._replace_active_account(account)

    def _replace_active_account(self, account: Account) -> None:
        previous = self.keychain.get_account(account.name)
        if previous is None:
            self.keychain.add_account(account)
            return
        try:
            self.sync_journal.write("activate", account.name, account.name, "intent")
            self.keychain.create_account_backup(account.name)
            self.sync_journal.write(
                "activate", account.name, account.name, "credential_backup"
            )
            self.keychain.add_account(account)
            self.sync_journal.write(
                "activate", account.name, account.name, "native_login"
            )
            activation = self.native_session.activate(account)
        except Exception:
            activation = self._pending_sync_failure()
        if not activation.ok:
            rollback = self._rollback_active_replacement(account.name)
            if not rollback.ok:
                raise AccountTransactionError(rollback.message)
            raise AccountTransactionError(
                "A conta ativa não pôde ser sincronizada; a sessão anterior foi restaurada."
            )
        try:
            self.sync_journal.write(
                "activate", account.name, account.name, "native_verified"
            )
            self.sync_journal.write("activate", account.name, account.name, "verified")
            self.keychain.delete_account_backup(account.name)
            self.sync_journal.clear()
        except Exception:
            raise AccountTransactionError(self._pending_sync_failure().message) from None

    def _rollback_active_replacement(self, name: str) -> AuthResult:
        try:
            self.sync_journal.write("activate", name, name, "rollback")
            self.keychain.restore_account_backup(name)
            previous = self.keychain.read_account_backup(name)
            if previous is None:
                return self._pending_sync_failure()
            activation = self.native_session.activate(previous)
            if not activation.ok:
                return AuthResult.failure(
                    AuthFailureCode.SYNC_ROLLBACK_FAILED,
                    "A sincronização falhou e a sessão anterior não pôde ser restaurada.",
                )
            self.active_store.write(name)
            self.keychain.delete_account_backup(name)
            self.sync_journal.clear()
        except Exception:
            return AuthResult.failure(
                AuthFailureCode.SYNC_ROLLBACK_FAILED,
                "A sincronização falhou e a sessão anterior não pôde ser restaurada.",
            )
        return AuthResult.success("A credencial e a sessão anteriores foram restauradas.")

    def list(self) -> List[Account]:
        """Lista todas as contas."""
        return self.keychain.list_accounts()

    def get(self, name: str) -> Optional[Account]:
        """Obtém conta por nome."""
        return self.keychain.get_account(name)

    def remove(self, name: str) -> None:
        """Remove conta."""
        if not is_valid_account_name(name):
            raise InvalidAccountNameError("Nome de conta inválido.")
        try:
            with self._sync_lock():
                self._remove_locked(name)
        except (AccountTransactionError, OSError):
            raise
        except Exception:
            raise AccountTransactionError(
                "Não foi possível remover a conta ativa com segurança."
            ) from None

    def _remove_locked(self, name: str) -> None:
        recovery = self._recover_pending_sync_locked()
        if not recovery.ok:
            raise AccountTransactionError(recovery.message)
        try:
            active_name = self.active_store.read()
        except ActiveAccountError:
            raise AccountTransactionError(
                "Não foi possível confirmar a conta ativa com segurança."
            ) from None
        if active_name != name:
            self.keychain.remove_account(name)
            return
        self._remove_active_account(name)

    def _remove_active_account(self, name: str) -> None:
        self.sync_journal.write("logout", None, name, "intent")
        try:
            logout = self.native_session.logout()
        except (OSError, ValueError):
            logout = self._pending_sync_failure()
        if not logout.ok:
            if logout.code is AuthFailureCode.SYNC_PENDING:
                raise AccountTransactionError(logout.message)
            try:
                self.sync_journal.clear()
            except (OSError, ValueError):
                raise AccountTransactionError(self._pending_sync_failure().message) from None
            raise AccountTransactionError("A sessão nativa não pôde ser encerrada.")
        self.sync_journal.write("logout", None, name, "native_verified")
        self.active_store.clear()
        self.sync_journal.write("logout", None, name, "local_write")
        self.keychain.remove_account(name)
        self.sync_journal.write("logout", None, name, "verified")
        self.sync_journal.clear()

    def _load_account_for_auth(
        self, name: str
    ) -> Tuple[Optional[Account], Optional[AuthResult]]:
        try:
            account = self.get(name)
        except CredentialAccessError as error:
            return None, classify_local_failure(error)

        if not account:
            return None, AuthResult.failure(
                AuthFailureCode.TOKEN_MISSING,
                "Token não encontrado para a conta selecionada.",
            )
        if not account.validate_token():
            return None, AuthResult.failure(
                AuthFailureCode.TOKEN_FORMAT_INVALID,
                "O token armazenado tem formato inválido.",
            )
        return account, None

    def validate_named_account(self, name: str) -> AuthResult:
        """Lê uma credencial uma vez e faz uma validação read-only."""
        if not is_valid_account_name(name):
            return AuthResult.failure(
                AuthFailureCode.ACCOUNT_REQUIRED,
                "Informe um nome de conta válido.",
                exit_code=2,
            )
        account, failure = self._load_account_for_auth(name)
        if failure is not None:
            return failure
        assert account is not None
        return self.config.validate_access_token(account)

    def set_active(self, name: str) -> AuthResult:
        """Sincroniza a sessão nativa antes de confirmar a seleção local."""
        if not is_valid_account_name(name):
            return AuthResult.failure(
                AuthFailureCode.ACCOUNT_REQUIRED,
                "Informe um nome de conta válido.",
                exit_code=2,
            )
        return self._run_with_sync_lock(lambda: self._set_active_locked(name))

    def _set_active_locked(self, name: str) -> AuthResult:
        recovery = self._recover_pending_sync_locked()
        if not recovery.ok:
            return recovery

        account, failure = self._load_account_for_auth(name)
        if failure is not None:
            return failure
        assert account is not None
        validation = self.config.validate_access_token(account)
        if not validation.ok:
            return validation
        try:
            previous_name = self.active_store.read()
        except ActiveAccountError as error:
            return classify_local_failure(error)

        try:
            self.sync_journal.write("activate", name, previous_name, "intent")
            self.sync_journal.write("activate", name, previous_name, "native_login")
        except (OSError, ValueError):
            return self._pending_sync_failure()
        try:
            activation = self.native_session.activate(account)
        except (OSError, ValueError):
            activation = self._pending_sync_failure()
        if not activation.ok:
            return self._compensate(name, previous_name, activation)

        try:
            self.sync_journal.write("activate", name, previous_name, "native_verified")
            self.sync_journal.write("activate", name, previous_name, "local_write")
        except (OSError, ValueError):
            return self._pending_sync_failure()
        try:
            self.active_store.write(name)
        except PermissionError:
            failure = classify_local_failure(ActiveAccountPermissionDeniedError())
            return self._compensate(name, previous_name, failure)
        except OSError:
            failure = classify_local_failure(ActiveAccountWriteError())
            return self._compensate(name, previous_name, failure)
        except ValueError:
            failure = classify_local_failure(ActiveAccountInvalidError())
            return self._compensate(name, previous_name, failure)

        try:
            self.sync_journal.write("activate", name, previous_name, "verified")
            self.sync_journal.clear()
        except (OSError, ValueError):
            return self._pending_sync_failure()
        return AuthResult.success(
            f"Conta '{name}' ativada e sessão nativa sincronizada."
        )

    def _compensate(
        self, target_name: str, previous_name: Optional[str], failure: AuthResult
    ) -> AuthResult:
        journal_failed = False
        try:
            self.sync_journal.write("activate", target_name, previous_name, "rollback")
        except (OSError, ValueError):
            journal_failed = True
        if previous_name is None:
            try:
                compensation = self.native_session.logout()
            except (OSError, ValueError):
                compensation = self._pending_sync_failure()
            if compensation.ok:
                try:
                    self.active_store.clear()
                except ActiveAccountError:
                    compensation = AuthResult.failure(
                        AuthFailureCode.SYNC_ROLLBACK_FAILED,
                        "A seleção anterior não pôde ser restaurada.",
                    )
        else:
            previous, load_failure = self._load_account_for_auth(previous_name)
            if load_failure is not None:
                compensation = load_failure
            else:
                assert previous is not None
                try:
                    compensation = self.native_session.activate(previous)
                except (OSError, ValueError):
                    compensation = self._pending_sync_failure()
                if compensation.ok:
                    try:
                        self.active_store.write(previous_name)
                    except (ActiveAccountError, OSError, ValueError):
                        compensation = AuthResult.failure(
                            AuthFailureCode.SYNC_ROLLBACK_FAILED,
                            "A seleção anterior não pôde ser restaurada.",
                        )
        if compensation.ok and not journal_failed:
            try:
                self.sync_journal.clear()
            except (OSError, ValueError):
                journal_failed = True
            else:
                return failure
        return AuthResult.failure(
            AuthFailureCode.SYNC_ROLLBACK_FAILED,
            "A sincronização falhou e a sessão anterior não pôde ser restaurada.",
        )

    def recover_pending_sync(self) -> AuthResult:
        return self._run_with_sync_lock(self._recover_pending_sync_locked)

    def _recover_pending_sync_locked(self) -> AuthResult:
        try:
            payload = self.sync_journal.read()
        except (OSError, ValueError):
            return self._pending_sync_failure()
        if payload is None:
            return AuthResult.success("Nenhuma sincronização pendente.")
        if payload["operation"] == "logout":
            return self._recover_logout(payload)
        if payload["operation"] != "activate":
            return self._pending_sync_failure()

        phase = payload["phase"]
        if payload["target_account"] == payload["previous_account"]:
            try:
                backup = self.keychain.read_account_backup(payload["target_account"])
            except Exception:
                return self._pending_sync_failure()
            if phase == "verified":
                try:
                    self.keychain.delete_account_backup(payload["target_account"])
                    self.sync_journal.clear()
                except Exception:
                    return self._pending_sync_failure()
                return AuthResult.success("Atualização pendente confirmada.")
            if backup is not None:
                return self._rollback_active_replacement(payload["target_account"])
            if phase == "intent":
                try:
                    self.sync_journal.clear()
                except (OSError, ValueError):
                    return self._pending_sync_failure()
                return AuthResult.success("Atualização pendente cancelada.")
        if phase == "verified":
            try:
                self.sync_journal.clear()
            except (OSError, ValueError):
                return self._pending_sync_failure()
            return AuthResult.success("Sincronização pendente confirmada.")
        if phase in ("intent", "native_login", "rollback"):
            result = self._recover_compensation(payload["previous_account"])
        else:
            result = self._recover_activation(payload["target_account"])
        if result.ok:
            try:
                self.sync_journal.clear()
            except (OSError, ValueError):
                return self._pending_sync_failure()
        return result

    def _recover_logout(self, payload) -> AuthResult:
        if payload["phase"] == "verified":
            try:
                self.sync_journal.clear()
            except (OSError, ValueError):
                return self._pending_sync_failure()
            return AuthResult.success("Remoção pendente confirmada.")
        if payload["phase"] == "intent":
            try:
                logout = self.native_session.logout()
            except (OSError, ValueError):
                return self._pending_sync_failure()
            if not logout.ok:
                return self._pending_sync_failure()
        try:
            self.active_store.clear()
            previous_name = payload["previous_account"]
            if previous_name is not None:
                self.keychain.remove_account(previous_name)
            self.sync_journal.clear()
        except (ActiveAccountError, OSError, ValueError):
            return self._pending_sync_failure()
        return AuthResult.success("Remoção pendente concluída.")

    def _recover_activation(self, name: str) -> AuthResult:
        account, failure = self._load_account_for_auth(name)
        if failure is not None:
            return self._pending_sync_failure()
        assert account is not None
        activation = self.native_session.activate(account)
        if not activation.ok:
            return self._pending_sync_failure()
        try:
            self.active_store.write(name)
        except (ActiveAccountError, OSError, ValueError):
            return self._pending_sync_failure()
        return AuthResult.success("Sincronização pendente concluída.")

    def _recover_compensation(self, previous_name: Optional[str]) -> AuthResult:
        if previous_name is None:
            compensation = self.native_session.logout()
            if compensation.ok:
                try:
                    self.active_store.clear()
                except ActiveAccountError:
                    return self._pending_sync_failure()
            return compensation if compensation.ok else self._pending_sync_failure()
        account, failure = self._load_account_for_auth(previous_name)
        if failure is not None:
            return self._pending_sync_failure()
        assert account is not None
        compensation = self.native_session.activate(account)
        if not compensation.ok:
            return self._pending_sync_failure()
        try:
            self.active_store.write(previous_name)
        except (ActiveAccountError, OSError, ValueError):
            return self._pending_sync_failure()
        return AuthResult.success("Sincronização anterior restaurada.")

    @staticmethod
    def _pending_sync_failure() -> AuthResult:
        return AuthResult.failure(
            AuthFailureCode.SYNC_PENDING,
            "Há uma sincronização de sessão pendente que requer recuperação.",
        )

    def run_active(
        self,
        arguments: Sequence[str],
        stdout_sink: Optional[Callable[[str], None]] = None,
        stderr_sink: Optional[Callable[[str], None]] = None,
    ) -> CommandResult:
        """Executa a CLI com a credencial da conta selecionada, sem persistir PAT."""
        try:
            name = self.active_store.read()
        except ActiveAccountError as error:
            failure = classify_local_failure(error)
            return CommandResult.failure(
                failure.code,
                failure.message,
                exit_code=failure.exit_code,
            )
        if name is None:
            return CommandResult.failure(
                AuthFailureCode.ACTIVE_ACCOUNT_MISSING,
                "Nenhuma conta ativa foi selecionada. Execute 'supa.cc switch <conta>'.",
            )

        account, failure = self._load_account_for_auth(name)
        if failure is not None:
            return CommandResult.failure(
                failure.code,
                failure.message,
                exit_code=failure.exit_code,
            )
        assert account is not None
        return self.config.execute_authenticated_streaming(
            account,
            arguments,
            stdout_sink=stdout_sink or (lambda _chunk: None),
            stderr_sink=stderr_sink or (lambda _chunk: None),
        )
