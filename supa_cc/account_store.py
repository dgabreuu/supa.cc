"""Compatibility facade for the account-store feature module."""

import os

from .accounts.store import (
    KEYCHAIN_SERVICE,
    AccountStore,
    safe_load_json_index,
)

__all__ = ["KEYCHAIN_SERVICE", "AccountStore", "safe_load_json_index"]
