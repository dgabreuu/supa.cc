from dataclasses import dataclass, field


@dataclass
class Account:
    name: str
    token: str = field(repr=False)

    def validate_token(self) -> bool:
        """Valida formato do token Supabase."""
        return self.token.startswith("sbp_") and len(self.token) > 10
