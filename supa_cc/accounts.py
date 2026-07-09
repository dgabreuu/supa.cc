import re
from typing import List, Optional
from .models import Account
from .keychain import KeychainManager


_ACCOUNT_NAME_REGEX = re.compile(r"^[a-zA-Z0-9_-]+$")

class AccountManager:
    def __init__(self):
        self.keychain = KeychainManager()

    def add(self, name: str, token: str) -> Account:
        """Adiciona nova conta."""
        if not name or len(name) < 1 or len(name) > 50:
            raise ValueError("Nome da conta deve ter entre 1 e 50 caracteres.")
        if not _ACCOUNT_NAME_REGEX.match(name):
            raise ValueError(
                "Nome da conta contém caracteres inválidos. "
                "Use apenas letras, números, hífens e underscores."
            )
        account = Account(name=name, token=token)
        if not account.validate_token():
            raise ValueError("Token inválido. Deve começar com 'sbp_'")
        self.keychain.save_account(account)
        self._update_index_add(name)
        return account

    def list(self) -> List[Account]:
        """Lista todas as contas."""
        return self.keychain.list_accounts()

    def get(self, name: str) -> Optional[Account]:
        """Obtém conta por nome."""
        return self.keychain.get_account(name)

    def remove(self, name: str) -> None:
        """Remove conta."""
        self.keychain.delete_account(name)
        self._update_index_remove(name)

    def set_active(self, name: str) -> bool:
        """Ativa conta no Supabase CLI."""
        account = self.get(name)
        if not account:
            return False
        from .config import SupabaseConfig
        config = SupabaseConfig()
        return config.set_active_account(account)

    def _read_index_names(self) -> List[str]:
        """Lê nomes do índice sem criar objetos Account."""
        return self.keychain._read_index()

    def _update_index_add(self, name: str) -> None:
        """Adiciona nome ao índice."""
        names = self._read_index_names()
        if name not in names:
            names.append(name)
            self.keychain.update_index(names)

    def _update_index_remove(self, name: str) -> None:
        """Remove nome do índice."""
        names = [n for n in self._read_index_names() if n != name]
        self.keychain.update_index(names)
