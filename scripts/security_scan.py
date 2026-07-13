"""High-confidence secret scanner that never prints matched values."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


MAX_SCANNED_BYTES = 4 * 1024 * 1024
_PATTERNS = (
    (
        "supabase_pat",
        re.compile(b"sbp" + b"_(?:oauth_)?[a-f0-9]{40}"),
    ),
    (
        "private_key",
        re.compile(
            b"-----BEGIN "
            b"(?:RSA |EC |OPENSSH |DSA )?"
            b"PRIVATE KEY-----"
        ),
    ),
    (
        "github_token",
        re.compile(b"gh" + b"[pousr]_[A-Za-z0-9]{36,255}"),
    ),
    (
        "aws_access_key",
        re.compile(b"AKIA" + b"[A-Z0-9]{16}"),
    ),
)
_SKIPPED_DIRECTORIES = {".git", ".venv", "venv", "dist", "build", "__pycache__"}


@dataclass(frozen=True)
class Finding:
    kind: str
    location: str

    def render(self) -> str:
        return f"{self.kind}: {self.location}"


def scan_bytes(data: bytes, location: str) -> list[Finding]:
    if len(data) > MAX_SCANNED_BYTES:
        return []
    return [
        Finding(kind=kind, location=location)
        for kind, pattern in _PATTERNS
        if pattern.search(data) is not None
    ]


def _iter_files(paths: Iterable[os.PathLike[str] | str]):
    for raw_path in paths:
        path = Path(raw_path)
        if path.is_dir():
            for child in path.rglob("*"):
                if child.is_file() and not any(
                    part in _SKIPPED_DIRECTORIES for part in child.parts
                ):
                    yield child
        elif path.is_file():
            yield path


def scan_paths(paths: Iterable[os.PathLike[str] | str]) -> list[Finding]:
    findings = []
    for path in _iter_files(paths):
        try:
            findings.extend(scan_bytes(path.read_bytes(), str(path)))
        except OSError:
            continue
    return findings


def tracked_paths(repository: os.PathLike[str] | str = ".") -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=repository,
        check=True,
        capture_output=True,
    )
    root = Path(repository)
    return [root / os.fsdecode(name) for name in result.stdout.split(b"\0") if name]


def worktree_paths(repository: os.PathLike[str] | str = ".") -> list[Path]:
    """Return tracked and non-ignored untracked files from the current worktree."""
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=repository,
        check=True,
        capture_output=True,
    )
    root = Path(repository)
    return [root / os.fsdecode(name) for name in result.stdout.split(b"\0") if name]


def scan_git_history(
    repository: os.PathLike[str] | str = ".",
    ignored_objects: set[str] | frozenset[str] = frozenset(),
) -> list[Finding]:
    repository = Path(repository)
    listed = subprocess.run(
        ["git", "rev-list", "--objects", "--all"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    findings = []
    seen = set()
    for line in listed.stdout.splitlines():
        object_id, _, object_path = line.partition(" ")
        if object_id in seen or object_id in ignored_objects:
            continue
        seen.add(object_id)
        object_type = subprocess.run(
            ["git", "cat-file", "-t", object_id],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if object_type != "blob":
            continue
        size = int(
            subprocess.run(
                ["git", "cat-file", "-s", object_id],
                cwd=repository,
                check=True,
                capture_output=True,
                text=True,
            ).stdout
        )
        if size > MAX_SCANNED_BYTES:
            continue
        data = subprocess.run(
            ["git", "cat-file", "blob", object_id],
            cwd=repository,
            check=True,
            capture_output=True,
        ).stdout
        location = f"git:{object_id[:12]}:{object_path or '<unnamed>'}"
        findings.extend(scan_bytes(data, location))
    return findings


def load_history_allowlist(repository: os.PathLike[str] | str = ".") -> set[str]:
    path = Path(repository) / ".security-scan-allowlist"
    if not path.exists():
        return set()
    ignored = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.partition("#")[0].strip().lower()
        if not line:
            continue
        if re.fullmatch(r"[a-f0-9]{40}", line) is None:
            raise ValueError("invalid object ID in security scan allowlist")
        ignored.add(line)
    return ignored


def _deduplicate(findings: Iterable[Finding]) -> list[Finding]:
    return sorted(set(findings), key=lambda finding: (finding.location, finding.kind))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tracked", action="store_true")
    parser.add_argument("--worktree", action="store_true")
    parser.add_argument("--history", action="store_true")
    parser.add_argument("--path", action="append", default=[])
    parser.add_argument("--repository", default=".")
    args = parser.parse_args(argv)

    scan_default = not (args.tracked or args.worktree or args.history or args.path)
    findings = []
    if args.tracked or scan_default:
        findings.extend(scan_paths(tracked_paths(args.repository)))
    if args.worktree:
        findings.extend(scan_paths(worktree_paths(args.repository)))
    if args.history or scan_default:
        findings.extend(
            scan_git_history(
                args.repository,
                ignored_objects=load_history_allowlist(args.repository),
            )
        )
    if args.path:
        findings.extend(scan_paths(args.path))

    findings = _deduplicate(findings)
    for finding in findings:
        print(finding.render())
    if findings:
        print(f"security scan failed with {len(findings)} finding(s)")
        return 1
    print("security scan passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
