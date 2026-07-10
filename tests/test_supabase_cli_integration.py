import os
import threading
import time
from pathlib import Path

import pytest

from supa_cc.auth import AuthFailureCode
from supa_cc.config import SupabaseConfig
from supa_cc.models import Account

from helpers import fake_pat


def _fake_cli(tmp_path: Path, body: str, name: str = "supabase") -> Path:
    executable = tmp_path / name
    executable.write_text(
        "#!/usr/bin/env python3\n"
        "import os, subprocess, sys, time\n"
        + body
        + "\n",
        encoding="utf-8",
    )
    executable.chmod(0o700)
    return executable


@pytest.mark.parametrize(
    "body,expected",
    [
        ("print('ok')", AuthFailureCode.NONE),
        (
            "sys.stderr.write('HTTP 401 Unauthorized\\n'); sys.exit(9)",
            AuthFailureCode.TOKEN_REJECTED,
        ),
        (
            "sys.stderr.write('profile mismatch\\n'); sys.exit(8)",
            AuthFailureCode.PROFILE_MISMATCH,
        ),
    ],
)
def test_real_fake_cli_validation_classification(tmp_path, body, expected):
    executable = _fake_cli(tmp_path, body)
    config = SupabaseConfig(binary_resolver=lambda _: str(executable))

    result = config.validate_access_token(
        Account(name="work", token=fake_pat("integration"))
    )

    assert result.code is expected
    assert result.ok is (expected is AuthFailureCode.NONE)


def test_real_fake_cli_validation_timeout(tmp_path):
    executable = _fake_cli(tmp_path, "time.sleep(1)")
    config = SupabaseConfig(
        binary_resolver=lambda _: str(executable),
        validation_timeout_seconds=0.05,
    )

    result = config.validate_access_token(
        Account(name="work", token=fake_pat("timeout"))
    )

    assert result.ok is False
    assert result.code is AuthFailureCode.NETWORK_FAILURE


def test_real_fake_cli_missing_and_eperm(tmp_path):
    missing = SupabaseConfig(binary_resolver=lambda _: None)
    missing_result = missing.validate_access_token(
        Account(name="work", token=fake_pat("missing"))
    )

    executable = _fake_cli(tmp_path, "print('never')")
    executable.chmod(0o600)
    blocked = SupabaseConfig(binary_resolver=lambda _: str(executable))
    blocked_result = blocked.validate_access_token(
        Account(name="work", token=fake_pat("blocked"))
    )

    assert missing_result.code is AuthFailureCode.CLI_NOT_FOUND
    assert blocked_result.code is AuthFailureCode.ENVIRONMENT_BLOCKED


def test_streaming_emits_before_exit_and_redacts_token_split_across_chunks(tmp_path):
    executable = _fake_cli(
        tmp_path,
        """
token = os.environ['SUPABASE_ACCESS_TOKEN']
if token in sys.argv:
    sys.exit(91)
os.write(1, b'prompt> ')
time.sleep(1.5)
cut = len(token) // 2
os.write(1, token[:cut].encode())
time.sleep(0.03)
os.write(1, token[cut:].encode())
os.write(1, b' done\\n')
""",
    )
    token = fake_pat("split_stream_secret")
    config = SupabaseConfig(binary_resolver=lambda _: str(executable))
    chunks = []
    first_output = threading.Event()
    holder = {}

    def sink(chunk):
        chunks.append(chunk)
        first_output.set()

    def execute():
        holder["result"] = config.execute_authenticated_streaming(
            Account(name="work", token=token),
            ["projects", "list"],
            stdout_sink=sink,
            stderr_sink=lambda _chunk: None,
        )

    worker = threading.Thread(target=execute)
    worker.start()

    assert first_output.wait(timeout=1.0) is True
    assert worker.is_alive() is True
    worker.join(timeout=2)

    assert worker.is_alive() is False
    result = holder["result"]
    output = "".join(chunks)
    assert result.ok is True
    assert output.startswith("prompt> ")
    assert token not in output
    assert token not in result.stdout
    assert token not in repr(result)
    assert "[REDACTED]" in output


def test_streaming_sample_is_bounded_and_classifies_tail(tmp_path):
    executable = _fake_cli(
        tmp_path,
        "os.write(1, b'x' * 50000); "
        "sys.stderr.write('HTTP 401 Unauthorized\\n'); sys.exit(23)",
    )
    config = SupabaseConfig(binary_resolver=lambda _: str(executable))
    streamed = 0

    def sink(chunk):
        nonlocal streamed
        streamed += len(chunk)

    result = config.execute_authenticated_streaming(
        Account(name="work", token=fake_pat("bounded_sample")),
        ["projects", "list"],
        stdout_sink=sink,
        stderr_sink=lambda _chunk: None,
        sample_limit=128,
    )

    assert streamed == 50000
    assert len(result.stdout) <= 128
    assert len(result.stderr) <= 128
    assert result.code is AuthFailureCode.TOKEN_REJECTED
    assert result.exit_code == 23


def test_streaming_classifies_401_seen_only_in_truncated_middle_with_precedence(tmp_path):
    executable = _fake_cli(
        tmp_path,
        "sys.stderr.write('permission denied\\n'); sys.stderr.flush(); "
        "os.write(1, b'x' * 20000); "
        "os.write(1, b'HTTP 401 Unauthorized'); "
        "os.write(1, b'y' * 20000); sys.exit(19)",
    )
    config = SupabaseConfig(binary_resolver=lambda _: str(executable))

    result = config.execute_authenticated_streaming(
        Account(name="work", token=fake_pat("middle_401")),
        ["projects", "list"],
        stdout_sink=lambda _chunk: None,
        stderr_sink=lambda _chunk: None,
        sample_limit=128,
    )

    assert result.code is AuthFailureCode.TOKEN_REJECTED
    assert "401" not in result.stdout
    assert "...[truncated]..." in result.stdout


def test_streaming_does_not_invent_401_across_sample_gap(tmp_path):
    executable = _fake_cli(
        tmp_path,
        "os.write(1, b'40'); os.write(1, b'x' * 20000); "
        "os.write(1, b'1'); sys.exit(18)",
    )
    config = SupabaseConfig(binary_resolver=lambda _: str(executable))

    result = config.execute_authenticated_streaming(
        Account(name="work", token=fake_pat("no_artificial_401")),
        ["projects", "list"],
        stdout_sink=lambda _chunk: None,
        stderr_sink=lambda _chunk: None,
        sample_limit=64,
    )

    assert result.code is AuthFailureCode.COMMAND_FAILED
    assert "...[truncated]..." in result.stdout


def test_streaming_detects_marker_split_between_real_chunks(tmp_path):
    executable = _fake_cli(
        tmp_path,
        "os.write(2, b'HTTP 40'); time.sleep(0.03); "
        "os.write(2, b'1 Unauthorized'); sys.exit(17)",
    )
    config = SupabaseConfig(binary_resolver=lambda _: str(executable))

    result = config.execute_authenticated_streaming(
        Account(name="work", token=fake_pat("split_marker")),
        ["projects", "list"],
        stdout_sink=lambda _chunk: None,
        stderr_sink=lambda _chunk: None,
    )

    assert result.code is AuthFailureCode.TOKEN_REJECTED


def test_broken_sink_terminates_long_running_child_without_orphan(tmp_path):
    executable = _fake_cli(
        tmp_path,
        "os.write(1, f'pid={os.getpid()}\\n'.encode()); time.sleep(10)",
    )
    config = SupabaseConfig(binary_resolver=lambda _: str(executable))
    child_pid = []

    def broken_sink(chunk):
        if chunk.startswith("pid="):
            child_pid.append(int(chunk.partition("=")[2]))
        raise BrokenPipeError("closed")

    started = time.monotonic()
    result = config.execute_authenticated_streaming(
        Account(name="work", token=fake_pat("broken_sink")),
        ["projects", "list"],
        stdout_sink=broken_sink,
        stderr_sink=lambda _chunk: None,
    )
    elapsed = time.monotonic() - started

    assert elapsed < 2
    assert result.ok is False
    assert result.code is AuthFailureCode.COMMAND_FAILED
    assert child_pid
    with pytest.raises(ProcessLookupError):
        os.kill(child_pid[0], 0)


def test_validation_output_is_bounded_and_not_emitted(tmp_path):
    executable = _fake_cli(tmp_path, "os.write(1, b'x' * 1000000)")
    config = SupabaseConfig(binary_resolver=lambda _: str(executable))

    result = config.execute_authenticated(
        Account(name="work", token=fake_pat("bounded_validation")),
        ["projects", "list"],
        timeout_seconds=1,
    )

    assert result.ok is True
    assert len(result.stdout) <= 8192
    assert "...[truncated]..." in result.stdout


def test_normal_completion_waits_for_slow_sink_and_preserves_complete_output(tmp_path):
    executable = _fake_cli(tmp_path, "os.write(1, b'complete-output')")
    config = SupabaseConfig(binary_resolver=lambda _: str(executable))
    chunks = []

    def slow_sink(chunk):
        time.sleep(1.5)
        chunks.append(chunk)

    started = time.monotonic()
    result = config.execute_authenticated_streaming(
        Account(name="work", token=fake_pat("slow_sink")),
        ["projects", "list"],
        stdout_sink=slow_sink,
        stderr_sink=lambda _chunk: None,
    )
    elapsed = time.monotonic() - started

    assert result.ok is True
    assert elapsed >= 1.4
    assert "".join(chunks) == "complete-output"


def _wait_for_pids_to_exit(pids, timeout=2.0):
    deadline = time.monotonic() + timeout
    remaining = set(pids)
    while remaining and time.monotonic() < deadline:
        for pid in list(remaining):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                remaining.remove(pid)
        if remaining:
            time.sleep(0.02)
    return remaining


def _cleanup_pids(pids):
    for pid in pids:
        try:
            os.kill(pid, 9)
        except ProcessLookupError:
            pass


def test_broken_sink_kills_process_group_including_grandchild(tmp_path):
    executable = _fake_cli(
        tmp_path,
        "grandchild = subprocess.Popen([sys.executable, '-c', "
        "'import time; time.sleep(30)']); "
        "os.write(1, f'parent={os.getpid()} child={grandchild.pid}\\n'.encode()); "
        "time.sleep(30)",
    )
    config = SupabaseConfig(binary_resolver=lambda _: str(executable))
    pids = []

    def broken_sink(chunk):
        fields = dict(part.split("=") for part in chunk.split())
        pids.extend([int(fields["parent"]), int(fields["child"])])
        raise BrokenPipeError("closed")

    try:
        started = time.monotonic()
        result = config.execute_authenticated_streaming(
            Account(name="work", token=fake_pat("group_broken")),
            ["projects", "list"],
            stdout_sink=broken_sink,
            stderr_sink=lambda _chunk: None,
        )
        elapsed = time.monotonic() - started

        assert elapsed < 2
        assert result.code is AuthFailureCode.COMMAND_FAILED
        assert len(pids) == 2
        assert _wait_for_pids_to_exit(pids) == set()
    finally:
        _cleanup_pids(pids)


def test_validation_timeout_kills_process_group_including_grandchild(tmp_path):
    executable = _fake_cli(
        tmp_path,
        "grandchild = subprocess.Popen([sys.executable, '-c', "
        "'import time; time.sleep(30)']); "
        "os.write(1, f'parent={os.getpid()} child={grandchild.pid}\\n'.encode()); "
        "time.sleep(30)",
    )
    config = SupabaseConfig(binary_resolver=lambda _: str(executable))
    pids = []
    try:
        result = config.execute_authenticated(
            Account(name="work", token=fake_pat("group_timeout")),
            ["projects", "list"],
            timeout_seconds=0.2,
        )
        fields = dict(part.split("=") for part in result.stdout.split())
        pids.extend([int(fields["parent"]), int(fields["child"])])

        assert result.code is AuthFailureCode.NETWORK_FAILURE
        assert _wait_for_pids_to_exit(pids) == set()
    finally:
        _cleanup_pids(pids)


def test_streaming_inherits_stdin(tmp_path):
    executable = _fake_cli(
        tmp_path,
        "data = sys.stdin.readline(); sys.stdout.write('stdin=' + data)",
    )
    config = SupabaseConfig(binary_resolver=lambda _: str(executable))
    chunks = []
    read_fd, write_fd = os.pipe()
    previous_stdin = os.dup(0)
    try:
        os.write(write_fd, b"hello-child\n")
        os.close(write_fd)
        os.dup2(read_fd, 0)
        result = config.execute_authenticated_streaming(
            Account(name="work", token=fake_pat("stdin_inherited")),
            ["projects", "list"],
            stdout_sink=chunks.append,
            stderr_sink=lambda _chunk: None,
        )
    finally:
        os.dup2(previous_stdin, 0)
        os.close(previous_stdin)
        os.close(read_fd)

    assert result.ok is True
    assert "".join(chunks) == "stdin=hello-child\n"
