import re
import sys
import tarfile
import zipfile
from pathlib import Path, PurePosixPath


FORBIDDEN_COMPONENTS = {
    ".superpowers",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
}
FORBIDDEN_TEXT = (".superpowers", "docs/superpowers")
POLICY_FILES = (
    ".gitignore",
    "pyproject.toml",
    "scripts/inspect_artifacts.py",
    "tests/test_artifact_inspection.py",
    "tests/test_project_identity.py",
    "tests/test_publication_assets.py",
)
MAX_TEXT_MEMBER_BYTES = 1024 * 1024
LOCAL_PATH = re.compile(
    r"(?<![A-Za-z0-9:])/(?:home|Users|tmp|private/tmp|var/folders)/[^\s\"'<>]+"
)


class ArtifactInspectionError(ValueError):
    """Raised when a distribution artifact contains private or local data."""


def _check_size(name, size):
    if size > MAX_TEXT_MEMBER_BYTES:
        raise ArtifactInspectionError(f"text member is too large to inspect safely: {name}")


def _check_member(name, data):
    path = PurePosixPath(name)
    if (
        path.is_absolute()
        or ".." in path.parts
        or any(part in FORBIDDEN_COMPONENTS for part in path.parts)
        or name.endswith((".pyc", ".diff"))
        or "docs/superpowers" in name
    ):
        raise ArtifactInspectionError(f"forbidden member path: {name}")

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return
    if any(name == policy or name.endswith(f"/{policy}") for policy in POLICY_FILES):
        return
    if any(reference in text for reference in FORBIDDEN_TEXT) or LOCAL_PATH.search(text):
        raise ArtifactInspectionError(f"forbidden text in artifact member: {name}")


def inspect_artifacts(directory):
    directory = Path(directory)
    wheels = list(directory.glob("*.whl"))
    sdists = list(directory.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise ArtifactInspectionError(
            f"expected exactly one wheel and one sdist, found {len(wheels)} and {len(sdists)}"
        )

    with zipfile.ZipFile(wheels[0]) as archive:
        for info in archive.infolist():
            if not info.is_dir():
                _check_size(info.filename, info.file_size)
                _check_member(info.filename, archive.read(info))

    with tarfile.open(sdists[0], "r:gz") as archive:
        for member in archive.getmembers():
            if member.issym() or member.islnk():
                raise ArtifactInspectionError(f"tar links are forbidden: {member.name}")
            if member.isfile():
                _check_size(member.name, member.size)
                stream = archive.extractfile(member)
                _check_member(member.name, stream.read() if stream is not None else b"")
            else:
                _check_member(member.name, b"")

    return len(wheels), len(sdists)


if __name__ == "__main__":
    try:
        wheel_count, sdist_count = inspect_artifacts(sys.argv[1] if len(sys.argv) > 1 else "dist")
    except (ArtifactInspectionError, OSError, tarfile.TarError, zipfile.BadZipFile) as error:
        raise SystemExit(str(error)) from error
    print(f"inspected {wheel_count} wheel and {sdist_count} sdist")
