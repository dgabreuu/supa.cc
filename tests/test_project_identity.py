try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on Python < 3.11
    import tomli as tomllib


def test_project_metadata_uses_supa_cc_identity():
    with open("pyproject.toml", "rb") as pyproject_file:
        pyproject = tomllib.load(pyproject_file)

    assert pyproject["project"]["name"] == "supa.cc"
    assert pyproject["project"]["scripts"] == {
        "supa.cc": "supa_cc.__main__:main",
    }


def test_project_metadata_links_public_repository():
    with open("pyproject.toml", "rb") as pyproject_file:
        pyproject = tomllib.load(pyproject_file)

    assert pyproject["project"]["urls"] == {
        "Homepage": "https://github.com/dgabreuu/supa.cc",
        "Repository": "https://github.com/dgabreuu/supa.cc.git",
        "Issues": "https://github.com/dgabreuu/supa.cc/issues",
    }


def test_python_39_test_dependency_includes_tomli():
    with open("pyproject.toml", "rb") as pyproject_file:
        pyproject = tomllib.load(pyproject_file)

    assert 'tomli>=2.0.0; python_version < "3.11"' in pyproject["project"]["optional-dependencies"]["dev"]


def test_license_uses_mit_with_supa_cc_attribution():
    with open("LICENSE", "r", encoding="utf-8") as license_file:
        license_text = license_file.read()

    assert license_text.startswith("MIT License")
    assert "Copyright (c) 2026 Supa.cc contributors" in license_text
