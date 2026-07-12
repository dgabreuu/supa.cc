import io
import tarfile
import zipfile

import pytest

from scripts.inspect_artifacts import ArtifactInspectionError, inspect_artifacts


def write_artifacts(path, text="https://example.com/home/project"):
    wheel = path / "example-1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("example/__init__.py", text)

    sdist = path / "example-1.0.tar.gz"
    payload = text.encode()
    info = tarfile.TarInfo("example-1.0/README.md")
    info.size = len(payload)
    with tarfile.open(sdist, "w:gz") as archive:
        archive.addfile(info, io.BytesIO(payload))


def test_inspection_accepts_one_clean_wheel_and_sdist_with_urls(tmp_path):
    write_artifacts(tmp_path)

    assert inspect_artifacts(tmp_path) == (1, 1)


def test_inspection_requires_exactly_one_wheel_and_one_sdist(tmp_path):
    write_artifacts(tmp_path)
    (tmp_path / "extra.whl").write_bytes(b"")

    with pytest.raises(ArtifactInspectionError, match="exactly one wheel"):
        inspect_artifacts(tmp_path)


@pytest.mark.parametrize(
    "text",
    (
        "internal notes: .superpowers/sdd/report.md",
        "generated from /home/developer/project",
        "generated from /Users/developer/project",
        "generated from /tmp/private-build/project",
        "generated from /private/tmp/private-build/project",
        "generated from /var/folders/ab/private-build/project",
    ),
)
def test_inspection_rejects_private_references_and_local_absolute_paths(tmp_path, text):
    write_artifacts(tmp_path, text)

    with pytest.raises(ArtifactInspectionError, match="forbidden text"):
        inspect_artifacts(tmp_path)


def test_inspection_rejects_forbidden_archive_member_paths(tmp_path):
    write_artifacts(tmp_path)
    wheel = next(tmp_path.glob("*.whl"))
    with zipfile.ZipFile(wheel, "a") as archive:
        archive.writestr("example/.pytest_cache/state", "clean")

    with pytest.raises(ArtifactInspectionError, match="forbidden member"):
        inspect_artifacts(tmp_path)


def test_inspection_allows_scanner_policy_literals_only_in_policy_files(tmp_path):
    write_artifacts(tmp_path)
    wheel = next(tmp_path.glob("*.whl"))
    with zipfile.ZipFile(wheel, "a") as archive:
        archive.writestr(
            "example-1.0/scripts/inspect_artifacts.py",
            "forbidden = '.superpowers'; sample = '/Users/developer/project'",
        )

    assert inspect_artifacts(tmp_path) == (1, 1)


@pytest.mark.parametrize(
    ("link_type", "target"),
    (
        (tarfile.SYMTYPE, "/tmp/private-target"),
        (tarfile.SYMTYPE, "../../private-target"),
        (tarfile.LNKTYPE, "/tmp/private-target"),
        (tarfile.LNKTYPE, "../../private-target"),
    ),
)
def test_inspection_rejects_all_tar_links(tmp_path, link_type, target):
    write_artifacts(tmp_path)
    sdist = next(tmp_path.glob("*.tar.gz"))
    sdist.unlink()
    with tarfile.open(sdist, "w:gz") as archive:
        payload = b"clean"
        regular = tarfile.TarInfo("example-1.0/README.md")
        regular.size = len(payload)
        archive.addfile(regular, io.BytesIO(payload))
        link = tarfile.TarInfo("example-1.0/link")
        link.type = link_type
        link.linkname = target
        archive.addfile(link)

    with pytest.raises(ArtifactInspectionError, match="links are forbidden"):
        inspect_artifacts(tmp_path)


def test_inspection_rejects_oversized_text_members_before_reading(tmp_path):
    write_artifacts(tmp_path, "x" * (1024 * 1024 + 1))

    with pytest.raises(ArtifactInspectionError, match="text member is too large"):
        inspect_artifacts(tmp_path)
