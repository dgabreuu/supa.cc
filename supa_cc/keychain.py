import json
import os
from pathlib import Path
import keyring
from keyring.errors import PasswordDeleteError
from typing import List, Optional
from .models import Account


KEYCHAIN_SERVICE = "supa.cc.supabase.accounts"
LEGACY_SUPAKILLER_KEYCHAIN_SERVICE = "supakiller.supabase.accounts"
LEGACY_KEYCHAIN_SERVICE = "sbc.supabase.accounts"
DEFAULT_INDEX_PATH = Path.home() / ".config" / "supa.cc" / "accounts.json"
LEGACY_SUPAKILLER_INDEX_PATH = Path.home() / ".config" / "supakiller" / "accounts.json"
LEGACY_INDEX_PATH = Path.home() / ".config" / "sbc" / "accounts.json"
_MACOS_KEYCHAIN_ITEM_NOT_FOUND = "-25300"


def _is_missing_keychain_item(error: PasswordDeleteError) -> bool:
    message = str(error).lower()
    return _MACOS_KEYCHAIN_ITEM_NOT_FOUND in message or "item not found" in message


def safe_load_json_index(path: Path) -> Optional[List[str]]:
    """Carrega lista de nomes de um arquivo JSON de índice.

    Retorna None se o arquivo não existir ou for inválido.
    Retorna lista vazia se o arquivo existir mas não tiver contas.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    accounts = data.get("accounts", []) if isinstance(data, dict) else []
    if not isinstance(accounts, list):
        return None
    return [name for name in accounts if isinstance(name, str) and name]


class KeychainManager:
    def __init__(self, index_path: Optional[Path] = None):
        self.index_path = Path(index_path) if index_path else DEFAULT_INDEX_PATH

    def _ensure_initialized(self) -> None:
        if not self.index_path.exists():
            self._read_index()

    def _migrate_legacy_data(self) -> bool:
        """Migra dados legados para o namespace atual se necessário."""
        if self.index_path.exists():
            return False

        legacy_names = []
        copied_names = set()
        legacy_names.extend(
            self._copy_legacy_index_tokens(
                LEGACY_SUPAKILLER_INDEX_PATH,
                LEGACY_SUPAKILLER_KEYCHAIN_SERVICE,
                copied_names,
            )
        )
        legacy_names.extend(
            self._copy_legacy_index_tokens(
                LEGACY_INDEX_PATH,
                LEGACY_KEYCHAIN_SERVICE,
                copied_names,
            )
        )
        legacy_names.extend(self._read_legacy_keychain_index(copied_names))

        if not legacy_names:
            return False

        self.update_index(legacy_names)
        return True

    def _copy_legacy_index_tokens(
        self,
        legacy_index_path: Path,
        legacy_service: str,
        copied_names: set,
    ) -> List[str]:
        if not legacy_index_path.exists():
            return []

        legacy_names = safe_load_json_index(legacy_index_path)
        if legacy_names is None or not legacy_names:
            return []

        self._copy_legacy_tokens(legacy_names, legacy_service, copied_names)
        return legacy_names

    def _copy_legacy_tokens(self, legacy_names: List[str], legacy_service: str, copied_names: set) -> None:
        for name in legacy_names:
            if name in copied_names:
                continue
            try:
                token = keyring.get_password(legacy_service, name)
                if token:
                    keyring.set_password(KEYCHAIN_SERVICE, name, token)
                    copied_names.add(name)
            except Exception:
                continue

    def save_account(self, account: Account) -> None:
        """Salva conta no Keychain."""
        self._ensure_initialized()
        keyring.set_password(KEYCHAIN_SERVICE, account.name, account.token)

    def get_account(self, name: str) -> Optional[Account]:
        """Recupera conta do Keychain."""
        self._ensure_initialized()
        token = keyring.get_password(KEYCHAIN_SERVICE, name)
        if token:
            return Account(name=name, token=token)
        return None

    def list_accounts(self) -> List[Account]:
        """Lista contas sem recuperar tokens do Keychain."""
        return [Account(name=name, token="") for name in self._read_index()]

    def delete_account(self, name: str) -> None:
        """Remove conta do Keychain."""
        self._ensure_initialized()
        try:
            keyring.delete_password(KEYCHAIN_SERVICE, name)
        except PasswordDeleteError as exc:
            if _is_missing_keychain_item(exc):
                return
            raise

    def update_index(self, names: List[str]) -> None:
        """Atualiza índice de contas com permissões atômicas."""
        unique_names = []
        for name in names:
            if name and name not in unique_names:
                unique_names.append(name)

        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.index_path.parent.chmod(0o700)

        data = json.dumps({"accounts": unique_names}, indent=2)
        # Cria arquivo com permissões restritas de forma atômica
        fd = os.open(
            self.index_path,
            os.O_CREAT | os.O_WRONLY | os.O_TRUNC,
            0o600
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(data)
        except Exception:
            os.close(fd)
            raise

    def _read_index(self) -> List[str]:
        if self.index_path.exists():
            return self._read_file_index()

        if self._migrate_legacy_data():
            return self._read_file_index()

        legacy_names = self._read_legacy_keychain_index()
        self.update_index(legacy_names)
        return legacy_names

    def _read_file_index(self) -> List[str]:
        names = safe_load_json_index(self.index_path)
        if names is None:
            self.update_index([])
            return []
        return names

    def _read_legacy_keychain_index(self, copied_names: Optional[set] = None) -> List[str]:
        try:
            from keyring.backends.macOS import Keyring

            backend = Keyring()
            index = backend.get_password(LEGACY_KEYCHAIN_SERVICE, "__index__")
        except Exception:
            return []

        if not index:
            return []
        names = [name for name in index.split(",") if name]
        self._copy_legacy_tokens(names, LEGACY_KEYCHAIN_SERVICE, copied_names or set())
        return names
