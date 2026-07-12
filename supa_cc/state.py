import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any, Optional


def ensure_parent(path: Path) -> Path:
    parent = Path(path).parent
    parent.mkdir(parents=True, exist_ok=True)
    parent.chmod(0o700)
    return parent


def _validate_file(descriptor: int, max_bytes: Optional[int] = None):
    metadata = os.fstat(descriptor)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or (max_bytes is not None and metadata.st_size > max_bytes)
    ):
        raise OSError("unsafe state file")
    return metadata


def read_text(path: Path, max_bytes: int) -> Optional[str]:
    descriptor = None
    try:
        descriptor = os.open(
            Path(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        )
        _validate_file(descriptor, max_bytes)
        contents = os.read(descriptor, max_bytes + 1)
        if len(contents) > max_bytes:
            raise OSError("state file is too large")
        try:
            return contents.decode("utf-8")
        except UnicodeDecodeError as error:
            raise OSError("state file is not UTF-8") from error
    except FileNotFoundError:
        return None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def read_json(path: Path, max_bytes: int) -> Optional[Any]:
    contents = read_text(path, max_bytes)
    return None if contents is None else json.loads(contents)


def _fsync_directory(parent: Path) -> None:
    descriptor = os.open(
        parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write_text(path: Path, contents: str) -> None:
    path = Path(path)
    parent = ensure_parent(path)
    descriptor = None
    temporary_path = None
    try:
        descriptor, temporary_path = tempfile.mkstemp(
            prefix=f".{path.name}.", dir=parent
        )
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = None
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
        _fsync_directory(parent)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary_path is not None:
            try:
                os.unlink(temporary_path)
            except FileNotFoundError:
                pass


def atomic_write_json(path: Path, payload: Any, *, indent=None) -> None:
    contents = json.dumps(payload, indent=indent, sort_keys=indent is None)
    atomic_write_text(path, f"{contents}\n")


def secure_remove(path: Path) -> None:
    path = Path(path)
    descriptor = None
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        opened = _validate_file(descriptor)
        current = path.lstat()
        if (
            not stat.S_ISREG(current.st_mode)
            or current.st_uid != os.getuid()
            or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino)
        ):
            raise OSError("unsafe state file")
        path.unlink()
    except FileNotFoundError:
        return
    finally:
        if descriptor is not None:
            os.close(descriptor)
    _fsync_directory(path.parent)
