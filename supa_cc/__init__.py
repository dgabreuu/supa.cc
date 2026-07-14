"""Supa.cc - CLI for managing Supabase accounts."""

import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def _source_tree_version():
    """Prefer the adjacent source metadata when running an editable checkout."""
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    try:
        project = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]
    except (OSError, KeyError, TypeError, ValueError, tomllib.TOMLDecodeError):
        return None
    if project.get("name") != "supa.cc":
        return None
    declared = project.get("version")
    return declared if isinstance(declared, str) and declared else None


try:
    _installed_version = version("supa.cc")
except PackageNotFoundError:
    _installed_version = None

__version__ = _source_tree_version() or _installed_version or "0+unknown"
