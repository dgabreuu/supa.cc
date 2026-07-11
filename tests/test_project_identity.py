try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on Python < 3.11
    import tomli as tomllib


def load_project_metadata():
    with open("pyproject.toml", "rb") as pyproject_file:
        return tomllib.load(pyproject_file)["project"]


def test_project_metadata_uses_supa_cc_identity():
    project = load_project_metadata()

    assert project["name"] == "supa.cc"
    assert project["scripts"] == {
        "supa.cc": "supa_cc.__main__:main",
    }


def test_project_metadata_links_public_repository():
    project = load_project_metadata()

    assert project["urls"] == {
        "Homepage": "https://github.com/dgabreuu/supa.cc",
        "Repository": "https://github.com/dgabreuu/supa.cc.git",
        "Issues": "https://github.com/dgabreuu/supa.cc/issues",
    }


def test_python_39_test_dependency_includes_tomli():
    project = load_project_metadata()

    assert 'tomli>=2.0.0; python_version < "3.11"' in project["optional-dependencies"]["dev"]


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
