import hashlib
import subprocess

from scripts.security_scan import (
    scan_bytes,
    scan_git_history,
    scan_paths,
    worktree_paths,
)


def credential(value):
    body = hashlib.sha256(value.encode("utf-8")).hexdigest()[:40]
    return "sbp" + "_" + body


def test_scan_reports_only_finding_class_and_location(tmp_path):
    secret = credential("scanner-output")
    findings = scan_bytes(secret.encode("utf-8"), "fixture.txt")

    assert [(finding.kind, finding.location) for finding in findings] == [
        ("supabase_pat", "fixture.txt")
    ]
    assert secret not in repr(findings)
    assert secret not in "\n".join(finding.render() for finding in findings)


def test_scan_paths_finds_private_keys_without_returning_contents(tmp_path):
    private_key = b"-----BEGIN " + b"PRIVATE KEY-----\nprivate\n"
    path = tmp_path / "identity.pem"
    path.write_bytes(private_key)

    findings = scan_paths([path])

    assert [(finding.kind, finding.location) for finding in findings] == [
        ("private_key", str(path))
    ]
    assert "private\n" not in repr(findings)


def test_scan_git_history_visits_objects_not_present_in_head(tmp_path):
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    secret = credential("historical-object")
    tracked = repository / "tracked.txt"
    tracked.write_text(secret, encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=repository, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Supa.cc tests",
            "-c",
            "user.email=tests@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
        cwd=repository,
        check=True,
    )
    tracked.write_text("clean", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=repository, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Supa.cc tests",
            "-c",
            "user.email=tests@example.invalid",
            "commit",
            "-qm",
            "cleanup",
        ],
        cwd=repository,
        check=True,
    )

    findings = scan_git_history(repository)

    assert any(finding.kind == "supabase_pat" for finding in findings)
    assert secret not in repr(findings)

    historical_prefix = next(
        finding.location.split(":", 2)[1]
        for finding in findings
        if finding.kind == "supabase_pat"
    )
    historical_blob = subprocess.run(
        ["git", "rev-parse", historical_prefix],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert scan_git_history(repository, ignored_objects={historical_blob}) == []


def test_worktree_paths_include_untracked_nonignored_files(tmp_path):
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    (repository / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    (repository / "tracked.txt").write_text("tracked", encoding="utf-8")
    (repository / "untracked.txt").write_text("untracked", encoding="utf-8")
    (repository / "ignored.txt").write_text("ignored", encoding="utf-8")
    subprocess.run(["git", "add", ".gitignore", "tracked.txt"], cwd=repository, check=True)

    paths = {path.relative_to(repository).as_posix() for path in worktree_paths(repository)}

    assert paths == {".gitignore", "tracked.txt", "untracked.txt"}
