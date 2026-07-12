try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on Python < 3.11
    import tomli as tomllib

from pathlib import Path

from supa_cc import __version__
import supa_cc.account_store as account_store
import supa_cc.supabase_cli as supabase_cli


def test_internal_modules_do_not_expose_stale_class_aliases():
    assert not hasattr(account_store, "AccountRepository")
    assert not hasattr(supabase_cli, "SupabaseConfig")


def load_project_metadata():
    with open("pyproject.toml", "rb") as pyproject_file:
        return tomllib.load(pyproject_file)["project"]


def load_pyproject():
    with open("pyproject.toml", "rb") as pyproject_file:
        return tomllib.load(pyproject_file)


def test_project_metadata_uses_supa_cc_identity():
    project = load_project_metadata()

    assert project["name"] == "supa.cc"
    assert project["scripts"] == {
        "supa.cc": "supa_cc.__main__:main",
    }


def test_source_version_is_0_3_0_while_formula_remains_on_stable_release():
    project = load_project_metadata()
    with open("Formula/supa-cc.rb", "r", encoding="utf-8") as formula_file:
        formula = formula_file.read()

    assert project["version"] == "0.3.0"
    assert __version__ == "0.3.0"
    assert (
        'url "https://github.com/dgabreuu/supa.cc/archive/refs/tags/v0.3.0.tar.gz"'
        in formula
    )
    assert (
        'sha256 "0b54c209831fef223d8bff3518c54310f3c89e7e4bde0e676f84dd5dd8c2acdd"'
        in formula
    )


def test_project_metadata_links_public_repository():
    project = load_project_metadata()

    assert project["urls"] == {
        "Homepage": "https://github.com/dgabreuu/supa.cc",
        "Repository": "https://github.com/dgabreuu/supa.cc.git",
        "Issues": "https://github.com/dgabreuu/supa.cc/issues",
        "Documentation": "https://github.com/dgabreuu/supa.cc/blob/main/docs/usage.md",
        "Changelog": "https://github.com/dgabreuu/supa.cc/blob/main/CHANGELOG.md",
    }


def test_python_39_test_dependency_includes_tomli():
    project = load_project_metadata()

    assert 'tomli>=2.0.0; python_version < "3.11"' in project["optional-dependencies"]["dev"]


def test_build_and_audit_dependencies_are_bounded_and_development_only():
    pyproject = load_pyproject()

    assert pyproject["build-system"]["requires"] == ["hatchling>=1.25,<2"]
    assert "pip-audit>=2.7,<3" in pyproject["project"]["optional-dependencies"]["dev"]
    assert "setuptools>=78.1.1" in pyproject["project"]["optional-dependencies"]["dev"]
    assert not any(
        dependency.startswith("pip-audit")
        for dependency in pyproject["project"]["dependencies"]
    )


def test_sdist_explicitly_excludes_private_and_local_artifacts():
    exclude = set(load_pyproject()["tool"]["hatch"]["build"]["targets"]["sdist"]["exclude"])

    required = {
        "/.superpowers",
        "/docs/superpowers",
        "/.pytest_cache",
        "/dist",
        "/build",
        "/.venv",
        "/venv",
    }
    assert required <= exclude


def test_project_metadata_declares_macos_and_linux_support():
    project = load_project_metadata()

    assert "Operating System :: MacOS" in project["classifiers"]
    assert "Operating System :: POSIX :: Linux" in project["classifiers"]
    assert "Linux" in project["description"]
    assert "linux" in project["keywords"]
    assert any(
        dependency.startswith("build")
        for dependency in project["optional-dependencies"]["dev"]
    )


def test_pytest_metadata_declares_opt_in_real_secret_service_marker():
    with open("pyproject.toml", "rb") as pyproject_file:
        pyproject = tomllib.load(pyproject_file)

    assert any(
        marker.startswith("real_secret_service:")
        for marker in pyproject["tool"]["pytest"]["ini_options"]["markers"]
    )


def test_license_uses_mit_with_supa_cc_attribution():
    with open("LICENSE", "r", encoding="utf-8") as license_file:
        license_text = license_file.read()

    assert license_text.startswith("MIT License")
    assert "Copyright (c) 2026 Supa.cc contributors" in license_text
    assert "Tradução" not in license_text
    assert license_text.rstrip().endswith("SOFTWARE.")
    assert not Path("docs/license-pt-BR.md").exists()
