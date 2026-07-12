import os
import stat
from pathlib import Path

try:
    import fcntl as _fcntl
except ImportError:  # pragma: no cover - exercised on Windows CI
    _fcntl = None

try:
    import msvcrt as _msvcrt
except ImportError:  # pragma: no cover - exercised on POSIX CI
    _msvcrt = None


def _is_windows() -> bool:
    return os.name == "nt"


def validate_lock_file(descriptor: int, path: Path) -> None:
    opened = os.fstat(descriptor)
    current = Path(path).lstat()
    unsafe_posix_metadata = not _is_windows() and (
        opened.st_uid != os.getuid()
        or stat.S_IMODE(opened.st_mode) != 0o600
        or current.st_uid != os.getuid()
        or stat.S_IMODE(current.st_mode) != 0o600
    )
    reparse_point = _is_windows() and bool(
        getattr(current, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )
    multiply_linked = _is_windows() and (
        getattr(opened, "st_nlink", 1) != 1 or getattr(current, "st_nlink", 1) != 1
    )
    if (
        not stat.S_ISREG(opened.st_mode)
        or not stat.S_ISREG(current.st_mode)
        or unsafe_posix_metadata
        or reparse_point
        or multiply_linked
        or not os.path.samestat(opened, current)
    ):
        raise OSError("unsafe lock file")


def _acquire_posix(descriptor: int) -> None:
    if _fcntl is None:
        raise OSError("POSIX file locking is unavailable")
    _fcntl.flock(descriptor, _fcntl.LOCK_EX)


def _release_posix(descriptor: int) -> None:
    if _fcntl is None:
        raise OSError("POSIX file locking is unavailable")
    _fcntl.flock(descriptor, _fcntl.LOCK_UN)


def _acquire_windows(descriptor: int) -> None:
    if _msvcrt is None:
        raise OSError("Windows file locking is unavailable")
    if os.fstat(descriptor).st_size == 0:
        os.lseek(descriptor, 0, os.SEEK_SET)
        os.write(descriptor, b"\0")
    os.lseek(descriptor, 0, os.SEEK_SET)
    _msvcrt.locking(descriptor, _msvcrt.LK_LOCK, 1)


def _release_windows(descriptor: int) -> None:
    if _msvcrt is None:
        raise OSError("Windows file locking is unavailable")
    os.lseek(descriptor, 0, os.SEEK_SET)
    _msvcrt.locking(descriptor, _msvcrt.LK_UNLCK, 1)


def acquire_file_lock(descriptor: int) -> None:
    if _is_windows():
        _acquire_windows(descriptor)
    else:
        _acquire_posix(descriptor)


def release_file_lock(descriptor: int) -> None:
    if _is_windows():
        _release_windows(descriptor)
    else:
        _release_posix(descriptor)
