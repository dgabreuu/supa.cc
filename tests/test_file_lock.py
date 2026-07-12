import os
from unittest.mock import Mock

import pytest

import supa_cc.file_lock as file_lock


def test_posix_lock_uses_exclusive_flock(monkeypatch):
    backend = Mock(LOCK_EX=2, LOCK_UN=8)
    monkeypatch.setattr(file_lock, "_fcntl", backend)

    file_lock._acquire_posix(7)
    file_lock._release_posix(7)

    assert backend.flock.call_args_list == [
        ((7, backend.LOCK_EX),),
        ((7, backend.LOCK_UN),),
    ]


def test_windows_lock_reserves_and_locks_first_byte(monkeypatch):
    backend = Mock(LK_LOCK=1, LK_UNLCK=0)
    monkeypatch.setattr(file_lock, "_msvcrt", backend)
    monkeypatch.setattr(file_lock.os, "fstat", Mock(return_value=Mock(st_size=0)))
    write = Mock(return_value=1)
    seek = Mock(return_value=0)
    monkeypatch.setattr(file_lock.os, "write", write)
    monkeypatch.setattr(file_lock.os, "lseek", seek)

    file_lock._acquire_windows(9)
    file_lock._release_windows(9)

    write.assert_called_once_with(9, b"\0")
    assert seek.call_count == 3
    assert backend.locking.call_args_list == [
        ((9, backend.LK_LOCK, 1),),
        ((9, backend.LK_UNLCK, 1),),
    ]


def test_windows_lock_rejects_link_before_writing_target(tmp_path, monkeypatch):
    target = tmp_path / "target"
    target.write_bytes(b"")
    link = tmp_path / "lock"
    link.symlink_to(target)
    descriptor = os.open(link, os.O_RDWR)
    write = Mock(wraps=os.write)
    monkeypatch.setattr(file_lock, "_is_windows", lambda: True)
    monkeypatch.setattr(file_lock.os, "write", write)

    try:
        with pytest.raises(OSError, match="unsafe lock file"):
            file_lock.validate_lock_file(descriptor, link)
    finally:
        os.close(descriptor)

    write.assert_not_called()
    assert target.read_bytes() == b""
