import ctypes
import os
from types import SimpleNamespace
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


def test_windows_lock_accepts_unknown_legacy_link_count(tmp_path, monkeypatch):
    lock_path = tmp_path / "lock"
    lock_path.write_bytes(b"\0")
    descriptor = os.open(lock_path, os.O_RDWR)
    opened = os.fstat(descriptor)
    current = lock_path.lstat()

    def legacy_metadata(metadata):
        values = list(metadata)
        values[3] = 0
        return os.stat_result(values)

    monkeypatch.setattr(file_lock, "_is_windows", lambda: True)
    monkeypatch.setattr(file_lock.os, "fstat", lambda _fd: legacy_metadata(opened))
    monkeypatch.setattr(
        type(lock_path), "lstat", lambda _path: legacy_metadata(current)
    )
    try:
        file_lock.validate_lock_file(descriptor, lock_path)
    finally:
        os.close(descriptor)


def test_windows_file_identity_rejects_path_replacement(monkeypatch):
    monkeypatch.setattr(file_lock, "_is_windows", lambda: True)
    monkeypatch.setattr(file_lock.os, "name", "nt")
    monkeypatch.setattr(
        file_lock, "_windows_file_identity", Mock(side_effect=[(7, 11), (7, 12)])
    )
    monkeypatch.setattr(file_lock.os, "open", Mock(return_value=9))
    close = Mock()
    monkeypatch.setattr(file_lock.os, "close", close)

    assert file_lock._same_file(8, "lock", Mock(), Mock()) is False
    close.assert_called_once_with(9)


def test_windows_file_identity_reads_native_volume_and_file_index(monkeypatch):
    backend = Mock()
    backend.get_osfhandle.return_value = 123

    def get_information(handle, pointer):
        assert handle.value == 123
        information = pointer._obj
        information.volume_serial = 7
        information.file_index_high = 2
        information.file_index_low = 3
        return 1

    kernel32 = Mock(GetFileInformationByHandle=Mock(side_effect=get_information))
    monkeypatch.setattr(file_lock, "_msvcrt", backend)
    monkeypatch.setattr(
        ctypes, "windll", SimpleNamespace(kernel32=kernel32), raising=False
    )

    assert file_lock._windows_file_identity(8) == (7, (2 << 32) | 3)


def test_windows_same_file_accepts_matching_native_identities(monkeypatch):
    monkeypatch.setattr(file_lock, "_is_windows", lambda: True)
    monkeypatch.setattr(file_lock.os, "name", "nt")
    identity = Mock(side_effect=[(7, 11), (7, 11)])
    monkeypatch.setattr(file_lock, "_windows_file_identity", identity)
    monkeypatch.setattr(file_lock.os, "open", Mock(return_value=9))
    close = Mock()
    monkeypatch.setattr(file_lock.os, "close", close)

    assert file_lock._same_file(8, "lock", Mock(), Mock()) is True
    assert identity.call_args_list == [((8,),), ((9,),)]
    close.assert_called_once_with(9)


def test_locked_file_closes_descriptor_when_unlock_fails(tmp_path):
    path = tmp_path / "shared.lock"
    close = Mock(wraps=os.close)

    with pytest.raises(file_lock.LockReleaseError):
        with file_lock.locked_file(
            path,
            release=Mock(side_effect=OSError("private unlock detail")),
            close_file=close,
        ):
            pass

    close.assert_called_once()


def test_locked_file_preserves_body_error_over_cleanup_failure(tmp_path):
    path = tmp_path / "shared.lock"
    close = Mock(wraps=os.close)

    with pytest.raises(ValueError, match="body failure"):
        with file_lock.locked_file(
            path,
            release=Mock(side_effect=OSError("private unlock detail")),
            close_file=close,
        ):
            raise ValueError("body failure")

    close.assert_called_once()
