import re
from typing import Optional


ACCESS_TOKEN_PREFIX = "sbp_"
ACCESS_TOKEN_BODY_CHARACTERS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._~-"
)
_PAT_CANDIDATE_REGEX = re.compile(
    r"sbp_(?:oauth_)?[a-f0-9]{40}",
    re.ASCII,
)
REDACTED = "[REDACTED]"


def is_valid_access_token(token: object) -> bool:
    return (
        isinstance(token, str)
        and _PAT_CANDIDATE_REGEX.fullmatch(token) is not None
    )


def is_access_token_body_character(value: str) -> bool:
    return len(value) == 1 and value in ACCESS_TOKEN_BODY_CHARACTERS


def sanitize_sensitive_text(value: object, secret: Optional[str] = None) -> str:
    text = "" if value is None else str(value)
    if secret:
        text = text.replace(secret, REDACTED)
    return _PAT_CANDIDATE_REGEX.sub(REDACTED, text)


def contains_pat(value: object) -> bool:
    return _PAT_CANDIDATE_REGEX.search(str(value)) is not None
