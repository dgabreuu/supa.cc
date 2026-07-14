import pytest

from supa_cc.accounts.state import (
    StateConflictError,
    StateInvalidError,
    StateReadError,
    StateWriteError,
)
from supa_cc.auth import AuthFailureCode, classify_local_failure


@pytest.mark.parametrize(
    ("error", "code", "phase"),
    [
        (StateInvalidError("private"), AuthFailureCode.STATE_INVALID, "read_state"),
        (StateConflictError("private"), AuthFailureCode.STATE_INVALID, "migrate_state"),
        (StateReadError("private"), AuthFailureCode.STATE_READ_FAILED, "read_state"),
        (StateWriteError("private"), AuthFailureCode.STATE_WRITE_FAILED, "write_state"),
        (OSError("private path"), AuthFailureCode.ENVIRONMENT_BLOCKED, "local_io"),
    ],
)
def test_local_infrastructure_failures_are_typed_and_sanitized(error, code, phase):
    result = classify_local_failure(error, operation="switch")

    assert result.code is code
    assert result.operation == "switch"
    assert result.phase == phase
    assert "private" not in result.message
    assert "The local operation could not be completed" not in result.message


def test_unexpected_failure_exposes_only_safe_exception_type():
    result = classify_local_failure(RuntimeError("secret contents"), operation="add")

    assert result.code is AuthFailureCode.UNEXPECTED_LOCAL_FAILURE
    assert result.operation == "add"
    assert result.phase == "unexpected"
    assert result.recoverability == "retryable"
    assert "RuntimeError" in result.message
    assert "secret contents" not in result.message
