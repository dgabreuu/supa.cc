import os
import json
import hashlib
import threading
import time
import subprocess
import sys
from pathlib import Path

import pytest

from supa_cc.auth import AuthFailureCode
from supa_cc.accounts import AccountService
from supa_cc.accounts.state import AccountState, StateRepository, StateTransition
from supa_cc.supabase_cli import SupabaseCLI as SupabaseConfig
from supa_cc.models import Account
from supa_cc.native_session import NativeSessionSynchronizer

from helpers import FakeCredentialStore, fake_pat


def _fake_cli(tmp_path: Path, body: str, name: str = "supabase") -> Path:
    script = tmp_path / (name + ".py" if os.name == "nt" else name)
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import os, subprocess, sys, time\n"
        + body
        + "\n",
        encoding="utf-8",
    )
    script.chmod(0o700)
    if os.name != "nt":
        return script
    executable = tmp_path / (name + ".cmd")
    executable.write_text(
        f'@"{sys.executable}" "%~dp0{name}.py" %*\r\n', encoding="utf-8"
    )
    return executable


def _stateful_fake_cli(tmp_path: Path) -> tuple[Path, Path, Path]:
    state_path = tmp_path / "fake-cli-state.json"
    control_path = tmp_path / "fake-cli-control.json"
    control_path.write_text("{}", encoding="utf-8")
    executable = _fake_cli(
        tmp_path,
        """
import hashlib, json
from pathlib import Path

state_path = Path(os.environ['FAKE_SUPABASE_STATE'])
control_path = Path(os.environ['FAKE_SUPABASE_CONTROL'])
raw_args = sys.argv[1:]
if raw_args == ['--version']:
    print('2.109.1')
    sys.exit(0)
profile = os.environ.get('SUPABASE_PROFILE', 'supabase')
args = list(raw_args)
if '--profile' in args:
    index = args.index('--profile')
    if index + 1 >= len(args):
        sys.exit(2)
    profile = args[index + 1]
    del args[index:index + 2]
if profile != 'supabase':
    sys.stderr.write('profile mismatch\\n')
    sys.exit(8)
state = json.loads(state_path.read_text()) if state_path.exists() else {'events': []}
control = json.loads(control_path.read_text())
token = os.environ.get('SUPABASE_ACCESS_TOKEN')
fingerprint = hashlib.sha256(token.encode()).hexdigest() if token else None
event = {'argv': args, 'has_access_token': token is not None}
state['events'].append(event)
state['last_profile'] = profile

if args == ['login']:
    if not token or control.get('fail_login_fingerprint') == fingerprint:
        state_path.write_text(json.dumps(state))
        sys.exit(1)
    state['session_fingerprint'] = fingerprint
    if control.get('force_plaintext_fallback'):
        fallback = Path(os.environ['SUPABASE_HOME']) / 'access-token'
        fallback.parent.mkdir(parents=True, exist_ok=True)
        fallback.write_text('synthetic-fallback')
elif args == ['logout', '--yes']:
    state.pop('session_fingerprint', None)
    state.pop('legacy_session_fingerprint', None)
    fallback = Path(os.environ['SUPABASE_HOME']) / 'access-token'
    if fallback.exists():
        if fallback.is_dir():
            fallback.rmdir()
        else:
            fallback.unlink()
elif args == ['projects', 'list']:
    effective = (
        fingerprint
        or state.get('session_fingerprint')
        or state.get('legacy_session_fingerprint')
    )
    if not effective:
        state_path.write_text(json.dumps(state))
        sys.stderr.write('access token not provided\\n')
        sys.exit(1)
    if not token and control.get('fail_verify_fingerprint') == effective:
        state_path.write_text(json.dumps(state))
        sys.stderr.write('HTTP 401 Unauthorized\\n')
        sys.exit(1)
    sys.stdout.write('fingerprint=' + effective + '\\n')
else:
    state_path.write_text(json.dumps(state))
    sys.exit(2)

state_path.write_text(json.dumps(state))
""",
    )
    return executable, state_path, control_path


def _integration_manager(tmp_path, monkeypatch):
    executable, state_path, control_path = _stateful_fake_cli(tmp_path)
    supabase_home = tmp_path / "supabase-home"
    monkeypatch.setenv("FAKE_SUPABASE_STATE", str(state_path))
    monkeypatch.setenv("FAKE_SUPABASE_CONTROL", str(control_path))
    monkeypatch.setenv("SUPABASE_HOME", str(supabase_home))
    monkeypatch.delenv("SUPABASE_ACCESS_TOKEN", raising=False)
    config = SupabaseConfig(binary_resolver=lambda _: str(executable))
    manager = AccountService(
        state_repository=StateRepository(tmp_path / "config" / "state.json"),
        credential_store=FakeCredentialStore(),
        cli=config,
        native_session=NativeSessionSynchronizer(
            config, env={}, supabase_home=supabase_home,
        ),
    )
    return manager, config, state_path, control_path, supabase_home


def _fake_state(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _set_fake_control(path, **values):
    path.write_text(json.dumps(values), encoding="utf-8")


def test_native_sync_first_selection_switch_and_direct_command(tmp_path, monkeypatch):
    manager, config, state_path, _, _ = _integration_manager(tmp_path, monkeypatch)
    work_token = fake_pat("native-work")
    personal_token = fake_pat("native-personal")
    manager.add("work", work_token)
    manager.add("personal", personal_token)

    assert manager.set_active("work").ok
    assert manager.set_active("personal").ok
    executable = config.supabase_cli_invoked
    direct = subprocess.run(
        [executable, "projects", "list"], capture_output=True, text=True, check=False,
        env={key: value for key, value in os.environ.items() if key != "SUPABASE_ACCESS_TOKEN"},
    )

    state = _fake_state(state_path)
    work_fingerprint = hashlib.sha256(work_token.encode()).hexdigest()
    personal_fingerprint = hashlib.sha256(personal_token.encode()).hexdigest()
    assert direct.returncode == 0
    assert direct.stdout == f"fingerprint={personal_fingerprint}\n"
    assert manager.get_active_name() == "personal"
    assert state["session_fingerprint"] == personal_fingerprint
    assert state["session_fingerprint"] != work_fingerprint
    login_events = [event for event in state["events"] if event["argv"] == ["login"]]
    assert len(login_events) == 2
    assert all(work_token not in event["argv"] for event in state["events"])
    assert all(personal_token not in event["argv"] for event in state["events"])
    persisted_checks = [
        event
        for event in state["events"]
        if event["argv"] == ["projects", "list"] and not event["has_access_token"]
    ]
    # Each switch inspects the previous session and verifies the newly persisted
    # session; the final event is the direct CLI command above.
    assert len(persisted_checks) == 5
    assert state["events"][-1] == {"argv": ["projects", "list"], "has_access_token": False}


def test_native_sync_replaces_conflicting_legacy_session_through_public_logout(
    tmp_path, monkeypatch
):
    manager, config, state_path, _, _ = _integration_manager(tmp_path, monkeypatch)
    legacy_fingerprint = hashlib.sha256(b"synthetic-legacy-session").hexdigest()
    state_path.write_text(
        json.dumps(
            {
                "events": [],
                "legacy_session_fingerprint": legacy_fingerprint,
            }
        ),
        encoding="utf-8",
    )
    selected_token = fake_pat("opaque-current-session")
    manager.add("work", selected_token)

    result = manager.set_active("work")
    direct = subprocess.run(
        [config.supabase_cli_invoked, "projects", "list"],
        capture_output=True,
        text=True,
        check=False,
        env={
            key: value
            for key, value in os.environ.items()
            if key != "SUPABASE_ACCESS_TOKEN"
        },
    )

    state = _fake_state(state_path)
    selected_fingerprint = hashlib.sha256(selected_token.encode()).hexdigest()
    assert result.ok
    assert direct.returncode == 0
    assert state["session_fingerprint"] == selected_fingerprint
    assert "legacy_session_fingerprint" not in state
    assert direct.stdout == f"fingerprint={selected_fingerprint}\n"


def test_native_sync_failed_switch_rolls_back_previous_session(tmp_path, monkeypatch):
    manager, _, state_path, control_path, _ = _integration_manager(tmp_path, monkeypatch)
    old_token = fake_pat("rollback-old")
    target_token = fake_pat("rollback-target")
    manager.add("old", old_token)
    manager.add("target", target_token)
    assert manager.set_active("old").ok
    _set_fake_control(
        control_path,
        fail_verify_fingerprint=hashlib.sha256(target_token.encode()).hexdigest(),
    )

    result = manager.set_active("target")

    state = _fake_state(state_path)
    assert not result.ok
    assert manager.get_active_name() == "old"
    assert state["session_fingerprint"] == hashlib.sha256(old_token.encode()).hexdigest()
    assert [event["argv"] for event in state["events"]].count(["login"]) == 3
    assert manager.state_repository.load().pending_transition is None


def test_native_sync_active_removal_logs_out_and_clears_selection(tmp_path, monkeypatch):
    manager, _, state_path, _, _ = _integration_manager(tmp_path, monkeypatch)
    manager.add("work", fake_pat("remove-active"))
    assert manager.set_active("work").ok

    manager.remove("work")

    state = _fake_state(state_path)
    assert manager.get_active_name() is None
    assert manager.get("work") is None
    assert "session_fingerprint" not in state
    assert ["logout", "--yes"] in [event["argv"] for event in state["events"]]


def test_native_sync_crash_recovery_completes_verified_activation(tmp_path, monkeypatch):
    manager, _, state_path, _, _ = _integration_manager(tmp_path, monkeypatch)
    manager.add("old", fake_pat("recovery-old"))
    manager.add("target", fake_pat("recovery-target"))
    assert manager.set_active("old").ok
    target = manager.get("target")
    assert target is not None
    assert manager.native_session.activate(target).ok
    state = manager.state_repository.load()
    manager.state_repository.save(
        AccountState(
            aliases=state.aliases,
            confirmed_active="old",
            pending_transition=StateTransition(
                "switch", "target", "old", "verified"
            ),
        )
    )

    result = manager.recover_pending_sync()

    assert result.ok
    assert manager.get_active_name() == "target"
    assert manager.state_repository.load().pending_transition is None
    assert _fake_state(state_path)["events"][-1] == {
        "argv": ["projects", "list"],
        "has_access_token": False,
    }


def test_native_sync_blocks_and_removes_forced_plaintext_fallback(tmp_path, monkeypatch):
    manager, _, state_path, control_path, supabase_home = _integration_manager(
        tmp_path, monkeypatch
    )
    token = fake_pat("forced-plaintext")
    manager.add("work", token)
    _set_fake_control(control_path, force_plaintext_fallback=True)

    result = manager.set_active("work")

    assert result.code is AuthFailureCode.SYNC_ROLLBACK_FAILED
    assert manager.get_active_name() is None
    assert not (supabase_home / "access-token").exists()
    state = _fake_state(state_path)
    assert token not in state_path.read_text(encoding="utf-8")
    assert all(token not in event["argv"] for event in state["events"])


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
time.sleep(0.05)
cut = len(token) // 2
os.write(1, token[:cut].encode())
time.sleep(0.005)
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

    assert first_output.wait(timeout=3.0) is True
    assert worker.is_alive() is True
    worker.join(timeout=3)

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
        "os.write(2, b'HTTP 40'); time.sleep(0.005); "
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
        time.sleep(0.03)
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
    assert elapsed >= 0.02
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
            timeout_seconds=1.0,
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
