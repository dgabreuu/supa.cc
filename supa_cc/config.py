import os
import subprocess
from .models import Account


class SupabaseConfig:
    def __init__(self):
        self.supabase_cli = "supabase"

    def is_installed(self) -> bool:
        """Verifica se Supabase CLI está instalado."""
        try:
            subprocess.run(
                [self.supabase_cli, "--version"],
                capture_output=True,
                check=True
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def set_active_account(self, account: Account) -> bool:
        """Ativa conta via supabase login.

        O token é passado via variável de ambiente SUPABASE_ACCESS_TOKEN
        para evitar exposição em ps, logs de processo e histórico de shell.
        """
        try:
            env = os.environ.copy()
            env["SUPABASE_ACCESS_TOKEN"] = account.token
            subprocess.run(
                [
                    self.supabase_cli,
                    "login",
                    "--name", account.name
                ],
                capture_output=True,
                text=True,
                check=True,
                env=env
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
