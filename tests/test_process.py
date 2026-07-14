import os
import sys
from unittest.mock import Mock

import supa_cc.process as process_module
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


def test_windows_spawn_assigns_job_before_resuming_suspended_process(monkeypatch):
    events = []
    process = Mock()
    popen = Mock(return_value=process)

    def assign(candidate):
        assert candidate is process
        events.append("assigned")
        return Mock()

    def resume(candidate):
        assert candidate is process
        events.append("resumed")

    monkeypatch.setattr(process_module.os, "name", "nt")
    monkeypatch.setattr(process_module.subprocess, "Popen", popen)
    monkeypatch.setattr(process_module, "create_kill_on_close_job", assign)
    monkeypatch.setattr(process_module, "resume_suspended_process", resume)

    spawned, close_job = process_module._spawn_process(["safe"], {})

    assert spawned is process
    assert close_job is not None
    assert events == ["assigned", "resumed"]
    assert popen.call_args.kwargs["creationflags"] & 0x00000004
