import stat
from pathlib import Path

import pytest

import supa_cc.auth as auth
from supa_cc.auth import (
    ActiveAccountStore,
    ActiveAccountInvalidError,
    ActiveAccountPermissionDeniedError,
    ActiveAccountReadError,
    ActiveAccountWriteError,
    AccountIndexInvalidError,
    AccountIndexReadError,
    AccountTransactionError,
    AuthFailureCode,
    AuthResult,
    CommandResult,
    contains_pat,
    sanitize_sensitive_text,
    classify_local_failure,
)

from helpers import fake_oauth_pat, fake_pat


def test_auth_failure_code_covers_activation_failures():
    assert {code.name for code in AuthFailureCode} >= {
        "NONE",
        "TOKEN_MISSING",
        "TOKEN_FORMAT_INVALID",
        "TOKEN_REJECTED",
        "KEYCHAIN_PERMISSION_DENIED",
        "KEYCHAIN_READ_FAILED",
        "CLI_NOT_FOUND",
        "CLI_INCOMPATIBLE",
        "API_AUTH_FAILED",
        "NETWORK_FAILURE",
        "ENVIRONMENT_BLOCKED",
        "PROFILE_MISMATCH",
        "COMMAND_FAILED",
    }


@pytest.mark.parametrize(
    "name,expected",
    [
        ("work", True),
        ("work_2-test", True),
        ("", False),
        ("a" * 51, False),
        ("work account", False),
        ("work\n", False),
    ],
)
def test_shared_account_name_validator(name, expected):
    assert auth.is_valid_account_name(name) is expected


@pytest.mark.parametrize(
    "name",
    [
        fake_pat("account_namespace"),
        "sbp_account_like",
        "acct_" + fake_pat("embedded"),
    ],
)
def test_account_names_cannot_overlap_pat_namespace(name):
    assert auth.is_valid_account_name(name) is False


def test_auth_result_factories_are_typed_and_keep_messages_out_of_repr():
    token = "sbp_example_token_that_must_not_be_rendered"

    success = AuthResult.success("Conta validada.")
    failure = AuthResult.failure(
        AuthFailureCode.TOKEN_REJECTED,
        token,
        exit_code=1,
    )

    assert success == AuthResult(
        ok=True,
        code=AuthFailureCode.NONE,
        message="Conta validada.",
        exit_code=0,
    )
    assert failure.ok is False
    assert failure.code is AuthFailureCode.TOKEN_REJECTED
    assert failure.exit_code == 1
    assert token not in repr(failure)


def test_auth_result_requires_callers_to_read_ok_explicitly():
    result = AuthResult.failure(
        AuthFailureCode.COMMAND_FAILED,
        "Falha segura.",
    )

    with pytest.raises(TypeError, match=r"\.ok"):
        bool(result)


def test_command_result_hides_message_and_streams_from_repr_and_failure_is_nonzero():
    token = "sbp_command_secret"
    result = CommandResult.failure(
        AuthFailureCode.COMMAND_FAILED,
        token,
        exit_code=0,
        stdout=token,
        stderr=token,
    )

    assert result.ok is False
    assert result.exit_code == 1
    assert token not in repr(result)
    with pytest.raises(TypeError, match=r"\.ok"):
        bool(result)


def test_detection_and_sanitization_share_access_token_contract():
    token = fake_pat("shared_contract")
    rendered = sanitize_sensitive_text(f"before {token} after")

    assert contains_pat(token) is True
    assert token not in rendered
    assert rendered == "before [REDACTED] after"


@pytest.mark.parametrize(
    "token",
    [
        fake_pat("suffix_candidate"),
        fake_oauth_pat("suffix_candidate_oauth"),
    ],
)
def test_candidate_detection_and_redaction_block_hex_suffix_bypass(token):
    bypass = f"prefix_{token}deadbeef"

    assert auth.is_valid_access_token(f"{token}deadbeef") is False
    assert contains_pat(bypass) is True
    rendered = sanitize_sensitive_text(bypass)
    assert token not in rendered
    assert "[REDACTED]" in rendered


def test_account_name_rejects_embedded_pat_with_hex_suffix():
    name = "x" + fake_pat("name_suffix") + "f"

    assert len(name) <= 50
    assert auth.is_valid_account_name(name) is False


@pytest.mark.parametrize(
    "invalid",
    [
        "sbp_short",
        fake_pat("invalid_upper")[:4] + fake_pat("invalid_upper")[4:].upper(),
        fake_pat("invalid_bad_char")[:-1] + "g",
    ],
)
def test_invalid_pat_shapes_are_not_treated_as_valid_tokens(invalid):
    assert contains_pat(invalid) is False


def test_candidate_detection_is_conservative_for_valid_pat_with_trailing_newline():
    value = fake_pat("newline_candidate") + "\n"

    assert auth.is_valid_access_token(value) is False
    assert contains_pat(value) is True
    assert fake_pat("newline_candidate") not in sanitize_sensitive_text(value)


def test_active_account_store_writes_only_name_with_private_permissions(tmp_path):
    path = tmp_path / "supa.cc" / "active-account"
    store = ActiveAccountStore(path=path)

    store.write("work")

    assert path.read_text(encoding="utf-8") == "work\n"
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert store.read() == "work"


def test_active_account_store_restricts_existing_permissions(tmp_path):
    path = tmp_path / "supa.cc" / "active-account"
    path.parent.mkdir(mode=0o755)
    path.write_text("old\n", encoding="utf-8")
    path.chmod(0o644)
    store = ActiveAccountStore(path=path)

    store.write("new")

    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert store.read() == "new"


def test_active_account_store_replaces_symlink_without_touching_target(tmp_path):
    path = tmp_path / "supa.cc" / "active-account"
    path.parent.mkdir()
    target = tmp_path / "unrelated"
    target.write_text("keep-me\n", encoding="utf-8")
    path.symlink_to(target)
    store = ActiveAccountStore(path=path)

    store.write("work")

    assert target.read_text(encoding="utf-8") == "keep-me\n"
    assert path.is_symlink() is False
    assert path.read_text(encoding="utf-8") == "work\n"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    "operation",
    ["fsync", "replace"],
)
def test_active_account_store_preserves_previous_value_on_write_failure(
    tmp_path, operation
):
    path = tmp_path / "supa.cc" / "active-account"
    path.parent.mkdir()
    path.write_text("old\n", encoding="utf-8")
    store = ActiveAccountStore(path=path)

    with pytest.MonkeyPatch.context() as monkeypatch:
        def fail(*_args, **_kwargs):
            raise OSError("write failed")

        monkeypatch.setattr(f"supa_cc.auth.os.{operation}", fail)
        with pytest.raises(OSError, match="write failed"):
            store.write("new")

    assert path.read_text(encoding="utf-8") == "old\n"
    assert list(path.parent.glob(".active-account.*")) == []


@pytest.mark.parametrize(
    "contents",
    ["", "\n", "../work\n", "work account\n", " work\n", "work \n", "work\n\n"],
)
def test_active_account_store_classifies_empty_or_unsafe_names(tmp_path, contents):
    path = tmp_path / "active-account"
    path.write_text(contents, encoding="utf-8")

    with pytest.raises(ActiveAccountInvalidError):
        ActiveAccountStore(path=path).read()


def test_active_account_store_returns_none_when_missing(tmp_path):
    assert ActiveAccountStore(path=tmp_path / "missing").read() is None


@pytest.mark.parametrize(
    "failure,expected_exception",
    [
        (PermissionError("private path"), ActiveAccountPermissionDeniedError),
        (OSError("private path"), ActiveAccountReadError),
    ],
)
def test_active_account_store_distinguishes_read_failures(
    tmp_path, monkeypatch, failure, expected_exception
):
    path = tmp_path / "active-account"
    path.write_text("work\n", encoding="utf-8")
    monkeypatch.setattr(Path, "read_text", lambda *_args, **_kwargs: (_ for _ in ()).throw(failure))

    with pytest.raises(expected_exception) as raised:
        ActiveAccountStore(path=path).read()

    assert "private" not in str(raised.value)


def test_active_account_store_rejects_invalid_contents_with_domain_error(tmp_path):
    path = tmp_path / "active-account"
    path.write_text("../unsafe\n", encoding="utf-8")

    with pytest.raises(ActiveAccountInvalidError):
        ActiveAccountStore(path=path).read()


@pytest.mark.parametrize(
    "failure,expected",
    [
        (AccountIndexInvalidError("secret"), AuthFailureCode.INDEX_INVALID),
        (AccountIndexReadError("secret"), AuthFailureCode.INDEX_READ_FAILED),
        (
            AccountTransactionError("secret"),
            AuthFailureCode.ACCOUNT_TRANSACTION_FAILED,
        ),
        (
            ActiveAccountPermissionDeniedError("secret"),
            AuthFailureCode.ACTIVE_ACCOUNT_PERMISSION_DENIED,
        ),
        (
            ActiveAccountReadError("secret"),
            AuthFailureCode.ACTIVE_ACCOUNT_READ_FAILED,
        ),
        (
            ActiveAccountWriteError("secret"),
            AuthFailureCode.ACTIVE_ACCOUNT_WRITE_FAILED,
        ),
        (
            ActiveAccountInvalidError("secret"),
            AuthFailureCode.ACTIVE_ACCOUNT_INVALID,
        ),
        (RuntimeError("secret"), AuthFailureCode.COMMAND_FAILED),
    ],
)
def test_local_failure_classifier_never_exposes_exception_details(failure, expected):
    result = classify_local_failure(failure)

    assert result.ok is False
    assert result.code is expected
    assert "secret" not in result.message


@pytest.mark.parametrize("name", ["", "../work", "work account", "a" * 51])
def test_active_account_store_rejects_unsafe_names(tmp_path, name):
    store = ActiveAccountStore(path=tmp_path / "active-account")

    with pytest.raises(ValueError, match="nome de conta"):
        store.write(name)
