import os
import stat
from contextlib import contextmanager
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


def _windows_file_identity(descriptor: int):
    import ctypes
    from ctypes import wintypes

    class FileInformation(ctypes.Structure):
        _fields_ = [
            ("attributes", wintypes.DWORD),
            ("creation_time", wintypes.FILETIME),
            ("access_time", wintypes.FILETIME),
            ("write_time", wintypes.FILETIME),
            ("volume_serial", wintypes.DWORD),
            ("size_high", wintypes.DWORD),
            ("size_low", wintypes.DWORD),
            ("links", wintypes.DWORD),
            ("file_index_high", wintypes.DWORD),
            ("file_index_low", wintypes.DWORD),
        ]

    if _msvcrt is None:
        raise OSError("Windows file identity is unavailable")
    information = FileInformation()
    handle = _msvcrt.get_osfhandle(descriptor)
    if not ctypes.windll.kernel32.GetFileInformationByHandle(
        wintypes.HANDLE(handle), ctypes.byref(information)
    ):
        raise ctypes.WinError()
    file_index = (information.file_index_high << 32) | information.file_index_low
    return information.volume_serial, file_index


def _same_file(descriptor, path, opened, current) -> bool:
    if not (_is_windows() and os.name == "nt"):
        return os.path.samestat(opened, current)
    current_descriptor = os.open(path, os.O_RDONLY)
    try:
        return _windows_file_identity(descriptor) == _windows_file_identity(
            current_descriptor
        )
    finally:
        os.close(current_descriptor)


def validate_lock_file(descriptor: int, path: Path) -> None:
    opened = os.fstat(descriptor)
    current = Path(path).lstat()
    unsafe_posix_metadata = not _is_windows() and (
        opened.st_uid != os.getuid()
        or stat.S_IMODE(opened.st_mode) != 0o600
        or current.st_uid != os.getuid()
        or stat.S_IMODE(current.st_mode) != 0o600
    )
    attributes = getattr(current, "st_file_attributes", 0)
    reparse_point = _is_windows() and isinstance(attributes, int) and bool(
        attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )
    link_counts = (getattr(opened, "st_nlink", 0), getattr(current, "st_nlink", 0))
    multiply_linked = _is_windows() and any(
        isinstance(count, int) and count > 1 for count in link_counts
    )
    if (
        not stat.S_ISREG(opened.st_mode)
        or not stat.S_ISREG(current.st_mode)
        or unsafe_posix_metadata
        or reparse_point
        or multiply_linked
        or not _same_file(descriptor, path, opened, current)
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


class LockReleaseError(OSError):
    """The lock body completed but releasing the lock failed."""


class LockCloseError(OSError):
    """The lock body completed but closing its descriptor failed."""


@contextmanager
def locked_file(
    path: Path,
    *,
    open_file=os.open,
    close_file=os.close,
    acquire=acquire_file_lock,
    release=release_file_lock,
    validate=validate_lock_file,
):
    """Open, validate, hold, and reliably finalize a private file lock."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not _is_windows():
        path.parent.chmod(0o700)
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    descriptor = open_file(path, flags, 0o600)
    locked = False
    body_error = None
    unlock_failed = False
    close_failed = False
    try:
        validate(descriptor, path)
        if not _is_windows():
            os.fchmod(descriptor, 0o600)
        acquire(descriptor)
        locked = True
        validate(descriptor, path)
        try:
            yield
        except BaseException as error:
            body_error = error
    finally:
        try:
            if locked:
                release(descriptor)
        except OSError:
            unlock_failed = True
        finally:
            try:
                close_file(descriptor)
            except OSError:
                close_failed = True
    if body_error is not None:
        raise body_error
    if unlock_failed:
        raise LockReleaseError()
    if close_failed:
        raise LockCloseError()
