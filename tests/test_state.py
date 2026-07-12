import os
import stat

import pytest

from supa_cc.state import atomic_write_text, read_text, secure_remove


def _private_file(path, contents="state\n"):
    path.write_text(contents, encoding="utf-8")
    path.chmod(0o600)


@pytest.mark.parametrize("unsafe_kind", ["symlink", "directory", "permissive"])
def test_read_text_rejects_unsafe_final_file(tmp_path, unsafe_kind):
    path = tmp_path / "state"
    if unsafe_kind == "symlink":
        target = tmp_path / "target"
        _private_file(target)
        path.symlink_to(target)
    elif unsafe_kind == "directory":
        path.mkdir()
    else:
        path.write_text("state\n", encoding="utf-8")
        path.chmod(0o644)

    with pytest.raises(OSError):
        read_text(path, max_bytes=32)


def test_read_text_rejects_wrong_owner(tmp_path, monkeypatch):
    path = tmp_path / "state"
    _private_file(path)
    original_fstat = os.fstat

    def wrong_owner(descriptor):
        metadata = list(original_fstat(descriptor))
        metadata[4] = os.getuid() + 1
        return os.stat_result(metadata)

    monkeypatch.setattr(os, "fstat", wrong_owner)

    with pytest.raises(OSError):
        read_text(path, max_bytes=32)


def test_read_text_rejects_oversized_content(tmp_path):
    path = tmp_path / "state"
    _private_file(path, "x" * 33)

    with pytest.raises(OSError):
        read_text(path, max_bytes=32)


def test_atomic_write_text_fsyncs_file_and_directory(tmp_path, monkeypatch):
    path = tmp_path / "private" / "state"
    synced = []
    original_fsync = os.fsync

    def record_fsync(descriptor):
        synced.append(stat.S_ISDIR(os.fstat(descriptor).st_mode))
        original_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", record_fsync)

    atomic_write_text(path, "state\n")

    assert synced == [False, True]
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_secure_remove_fsyncs_directory(tmp_path, monkeypatch):
    path = tmp_path / "state"
    _private_file(path)
    directory_fsyncs = 0
    original_fsync = os.fsync

    def record_fsync(descriptor):
        nonlocal directory_fsyncs
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            directory_fsyncs += 1
        original_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", record_fsync)

    secure_remove(path)

    assert directory_fsyncs == 1
    assert not path.exists()
