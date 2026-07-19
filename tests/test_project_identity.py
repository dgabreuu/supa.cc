import tomllib

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


def test_project_metadata_declares_english_as_the_only_natural_language():
    project = load_project_metadata()

    assert [
        classifier
        for classifier in project["classifiers"]
        if classifier.startswith("Natural Language ::")
    ] == ["Natural Language :: English"]


def test_source_uses_release_version_and_verified_stable_formula():
    project = load_project_metadata()
    with open("Formula/supa-cc.rb", "r", encoding="utf-8") as formula_file:
        formula = formula_file.read()

    assert project["version"] == "0.5.7"
    assert __version__ == "0.5.7"
    assert (
        'url "https://github.com/dgabreuu/supa.cc/archive/refs/tags/v0.5.6.tar.gz"'
        in formula
    )
    assert (
        'sha256 "36974301065a3e402c3f69d387b0e172792b88704b0efb75e903c0a4177c942a"'
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


def test_runtime_requires_supported_python_without_tomli_backport():
    project = load_project_metadata()

    assert project["requires-python"] == ">=3.11"
    assert not any(
        dependency.startswith("tomli")
        for dependency in project["optional-dependencies"]["dev"]
    )
    assert "Programming Language :: Python :: 3.9" not in project["classifiers"]
    assert "Programming Language :: Python :: 3.11" in project["classifiers"]


def test_runtime_dependencies_exclude_rich_and_its_transitive_stack():
    dependencies = load_project_metadata()["dependencies"]

    assert dependencies == [
        "questionary>=2.0.0",
        "keyring>=24.0.0",
        "click>=8.0.0",
    ]


def test_agent_conventions_match_supported_runtime_dependencies():
    agents = Path("AGENTS.md").read_text(encoding="utf-8")

    assert "Python 3.11+" in agents
    assert "Python 3.9+" not in agents
    assert "`click`, `questionary`, and `keyring`" in agents
    assert "`rich`" not in agents.lower()


def test_build_and_audit_dependencies_are_bounded_and_development_only():
    pyproject = load_pyproject()

    assert pyproject["build-system"]["requires"] == ["hatchling>=1.25,<2"]
    assert "pip-audit>=2.7,<3" in pyproject["project"]["optional-dependencies"]["dev"]
    assert "setuptools>=83.0.0" in pyproject["project"]["optional-dependencies"]["dev"]
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
        "/tests",
        "/assets",
        "/scripts",
        "/Formula",
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
    assert "Translation" not in license_text
    assert license_text.rstrip().endswith("SOFTWARE.")
    assert not Path("docs/license-pt-BR.md").exists()
