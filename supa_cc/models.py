from dataclasses import dataclass, field

from .auth import is_valid_access_token


@dataclass
class Account:
    name: str
    token: str = field(repr=False)

    def validate_token(self) -> bool:
        """Validate the Supabase token format."""
        return is_valid_access_token(self.token)


@dataclass(frozen=True)
class AccountSummary:
    name: str
