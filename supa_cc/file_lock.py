import os

try:
    import fcntl as _fcntl
except ImportError:  # pragma: no cover - exercised on Windows CI
    _fcntl = None

try:
    import msvcrt as _msvcrt
except ImportError:  # pragma: no cover - exercised on POSIX CI
    _msvcrt = None


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
    if os.name == "nt":
        _acquire_windows(descriptor)
    else:
        _acquire_posix(descriptor)


def release_file_lock(descriptor: int) -> None:
    if os.name == "nt":
        _release_windows(descriptor)
    else:
        _release_posix(descriptor)
