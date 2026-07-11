from typing import Callable, List, Optional, Sequence, Tuple

from .auth import (
    ActiveAccountStore,
    ActiveAccountError,
    ActiveAccountInvalidError,
    ActiveAccountPermissionDeniedError,
    ActiveAccountReadError,
    ActiveAccountWriteError,
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


class AccountManager:
    def __init__(
        self,
        keychain: Optional[KeychainManager] = None,
        config: Optional[SupabaseConfig] = None,
        active_store: Optional[ActiveAccountStore] = None,
    ):
        environment = detect_environment()
        self.keychain = (
            keychain
            if keychain is not None
            else KeychainManager(environment=environment)
        )
        self.config = config if config is not None else SupabaseConfig()
        self.active_store = (
            active_store
            if active_store is not None
            else ActiveAccountStore(
                path=environment.config_directory() / "active-account"
            )
        )

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
        self.keychain.add_account(account)
        return account

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
        self.keychain.remove_account(name)

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
        """Valida a conta e persiste somente seu nome como seleção ativa."""
        validation = self.validate_named_account(name)
        if not validation.ok:
            return validation

        try:
            self.active_store.write(name)
        except PermissionError:
            return classify_local_failure(
                ActiveAccountPermissionDeniedError()
            )
        except OSError:
            return classify_local_failure(ActiveAccountWriteError())
        except ValueError:
            return classify_local_failure(ActiveAccountInvalidError())
        return AuthResult.success(
            f"Conta '{name}' ativada no Supa.cc. A sessão nativa independente "
            "da Supabase CLI não foi alterada; use 'supa.cc run -- ...'."
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
