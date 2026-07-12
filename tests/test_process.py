import os
import sys

from supa_cc.process import ProcessState, run_process


def test_process_runner_returns_neutral_failure_state():
    result = run_process(
        [sys.executable, "-c", "import sys; sys.stderr.write('401 Unauthorized'); sys.exit(7)"],
        os.environ.copy(),
    )

    assert result.state is ProcessState.EXITED
    assert result.exit_code == 7
    assert result.stderr == "401 Unauthorized"
    assert not hasattr(result, "code")


def test_process_runner_does_not_redact_application_specific_output():
    result = run_process(
        [sys.executable, "-c", "print('sbp_' + 'a' * 40)"],
        os.environ.copy(),
    )

    assert result.stdout == "sbp_" + "a" * 40 + "\n"


def test_process_runner_reports_launch_failure_neutrally():
    result = run_process(["/definitely/missing"], os.environ.copy())

    assert result.state is ProcessState.NOT_FOUND
    assert result.exit_code == 1
