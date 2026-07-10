from dataclasses import dataclass, field

from .auth import is_valid_access_token


@dataclass
class Account:
    name: str
    token: str = field(repr=False)

    def validate_token(self) -> bool:
        """Valida formato do token Supabase."""
        return is_valid_access_token(self.token)
