import codecs
import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional, Sequence, Tuple

from .windows_job import create_kill_on_close_job, resume_suspended_process

OutputSink = Callable[[str], None]
STREAM_SAMPLE_LIMIT = 8192
STREAM_SAMPLE_SEPARATOR = "\n...[truncated]...\n"

class ProcessState(str, Enum):
    EXITED = "exited"
    NOT_FOUND = "not_found"
    PERMISSION_DENIED = "permission_denied"
    INVALID_ARGUMENT = "invalid_argument"
    LAUNCH_FAILED = "launch_failed"
    TIMED_OUT = "timed_out"
    OUTPUT_FAILED = "output_failed"


@dataclass(frozen=True)
class ProcessResult:
    state: ProcessState
    exit_code: int = 1
    stdout: str = ""
    stderr: str = ""


class _BoundedSample:
    def __init__(self, limit):
        self.limit = max(0, int(limit))
        content = max(0, self.limit - len(STREAM_SAMPLE_SEPARATOR))
        self.head_limit, self.tail_limit = content // 2, content - content // 2
        self.full = self.head = self.tail = ""
        self.truncated = False

    def add(self, text):
        if not self.limit or not text:
            return
        if not self.truncated and len(self.full) + len(text) <= self.limit:
            self.full += text
        elif not self.truncated:
            combined = self.full + text
            self.head = combined[:self.head_limit]
            self.tail = combined[-self.tail_limit:] if self.tail_limit else ""
            self.full, self.truncated = "", True
        elif self.tail_limit:
            self.tail = (self.tail + text)[-self.tail_limit:]

    @property
    def value(self):
        if not self.truncated:
            return self.full
        if self.limit < len(STREAM_SAMPLE_SEPARATOR):
            return self.tail[-self.limit:]
        return self.head + STREAM_SAMPLE_SEPARATOR + self.tail


def _terminate_process_group(process):
    if os.name == "posix":
        for sig, timeout in ((signal.SIGTERM, 0.2), (signal.SIGKILL, 1)):
            try:
                os.killpg(process.pid, sig)
            except (ProcessLookupError, PermissionError):
                pass
            try:
                process.wait(timeout=timeout)
            except (subprocess.TimeoutExpired, ProcessLookupError):
                pass
        return
    try:
        process.terminate()
        process.wait(timeout=0.2)
    except (subprocess.TimeoutExpired, ProcessLookupError):
        try:
            process.kill()
            process.wait(timeout=1)
        except (subprocess.TimeoutExpired, ProcessLookupError):
            pass


def _spawn_process(argv: Sequence[str], env: dict, pass_fds: Tuple[int, ...] = ()):
    options = {"pass_fds": pass_fds} if os.name == "posix" else {}
    if os.name == "nt":
        options["creationflags"] = 0x00000004  # CREATE_SUSPENDED
    process = subprocess.Popen(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        bufsize=0,
        start_new_session=(os.name == "posix"),
        **options,
    )
    close_windows_job = None
    if os.name == "nt":
        try:
            close_windows_job = create_kill_on_close_job(process)
            resume_suspended_process(process)
        except Exception:
            if close_windows_job is not None:
                try:
                    close_windows_job()
                except OSError:
                    pass
            _terminate_process_group(process)
            raise OSError("Unable to start a contained Windows process.") from None
    return process, close_windows_job


def run_process(argv: Sequence[str], env: dict, stdout_sink: OutputSink = lambda _chunk: None,
                 stderr_sink: OutputSink = lambda _chunk: None, sample_limit: int = STREAM_SAMPLE_LIMIT,
                 timeout_seconds: Optional[float] = None, pass_fds: Tuple[int, ...] = (),
                 pre_spawn_check: Optional[Callable[[], None]] = None) -> ProcessResult:
    try:
        if pre_spawn_check is not None:
            pre_spawn_check()
        process, close_windows_job = _spawn_process(argv, env, pass_fds)
    except FileNotFoundError:
        return ProcessResult(ProcessState.NOT_FOUND)
    except PermissionError:
        return ProcessResult(ProcessState.PERMISSION_DENIED)
    except ValueError:
        return ProcessResult(ProcessState.INVALID_ARGUMENT, exit_code=2)
    except OSError:
        return ProcessResult(ProcessState.LAUNCH_FAILED)

    def finalize(result):
        if close_windows_job is not None:
            try:
                close_windows_job()
            except OSError:
                return ProcessResult(
                    ProcessState.LAUNCH_FAILED,
                    stdout=result.stdout,
                    stderr=result.stderr,
                )
        return result

    samples = {"stdout": _BoundedSample(sample_limit), "stderr": _BoundedSample(sample_limit)}
    errors, failed = [], threading.Event()

    def drain(name, pipe, sink):
        decoder, available = codecs.getincrementaldecoder("utf-8")("replace"), True
        def publish(text):
            nonlocal available
            if not text:
                return
            samples[name].add(text)
            if available:
                try:
                    sink(text)
                except Exception as error:
                    if not errors:
                        errors.append(error)
                    available = False
                    failed.set()
        try:
            while True:
                chunk = os.read(pipe.fileno(), 4096)
                if not chunk:
                    break
                publish(decoder.decode(chunk))
            publish(decoder.decode(b"", final=True))
        except Exception as error:
            if not errors:
                errors.append(error)
            failed.set()
        finally:
            pipe.close()

    assert process.stdout is not None and process.stderr is not None
    threads = [threading.Thread(target=drain, args=(name, pipe, sink)) for name, pipe, sink in
               (("stdout", process.stdout, stdout_sink), ("stderr", process.stderr, stderr_sink))]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + timeout_seconds if timeout_seconds is not None else None
    reason = None
    try:
        while True:
            return_code = process.poll()
            if return_code is not None:
                break
            if failed.wait(0.02):
                reason = "reader"
            elif deadline is not None and time.monotonic() >= deadline:
                reason = "timeout"
            if reason:
                _terminate_process_group(process)
                return_code = process.poll()
                break
    except (KeyboardInterrupt, SystemExit):
        _terminate_process_group(process)
        for thread in threads:
            thread.join()
        if close_windows_job is not None:
            try:
                close_windows_job()
            except OSError:
                pass
        raise
    while any(thread.is_alive() for thread in threads):
        if failed.is_set() and reason is None:
            reason = "reader"
            _terminate_process_group(process)
        if deadline is not None and time.monotonic() >= deadline and reason is None:
            reason = "timeout"
            _terminate_process_group(process)
        for thread in threads:
            thread.join(0.02)
    stdout, stderr = samples["stdout"].value, samples["stderr"].value
    if reason == "timeout":
        return finalize(ProcessResult(ProcessState.TIMED_OUT, stdout=stdout, stderr=stderr))
    if errors:
        return finalize(ProcessResult(ProcessState.OUTPUT_FAILED, stdout=stdout, stderr=stderr))
    return finalize(ProcessResult(ProcessState.EXITED, exit_code=return_code, stdout=stdout, stderr=stderr))
