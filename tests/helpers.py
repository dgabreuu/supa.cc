import hashlib


def fake_pat(value: str = "valid_token") -> str:
    body = hashlib.sha256(value.encode("utf-8")).hexdigest()[:40]
    return "sbp" + "_" + body


def fake_oauth_pat(value: str = "valid_token") -> str:
    body = hashlib.sha256(value.encode("utf-8")).hexdigest()[:40]
    return "sbp" + "_oauth_" + body
