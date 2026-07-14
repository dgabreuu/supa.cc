"""Public account-management feature."""

from .service import AccountService

# The historical public name now resolves to the single runtime service.
AccountManager = AccountService

__all__ = ["AccountManager", "AccountService"]
