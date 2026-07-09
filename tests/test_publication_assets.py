from pathlib import Path


REPO_URL = "https://github.com/dgabreuu/supa.cc.git"


def test_readme_uses_public_repository_url():
    readme = Path("README.md").read_text(encoding="utf-8")

    placeholder_org = "your" + "-" + "org"
    assert f"github.com/{placeholder_org}" not in readme
    assert REPO_URL in readme


def test_homebrew_formula_is_present_with_public_metadata():
    formula = Path("Formula/supa-cc.rb").read_text(encoding="utf-8")

    assert "class SupaCc < Formula" in formula
    assert 'homepage "https://github.com/dgabreuu/supa.cc"' in formula
    assert f'head "{REPO_URL}", branch: "main"' in formula
    assert "depends_on :macos" in formula
    assert 'depends_on "python@3.13"' in formula
    assert 'depends_on "supabase/tap/supabase"' in formula
    assert 'resource "click" do' in formula
    assert 'resource "questionary" do' in formula
    assert 'resource "rich" do' in formula
    assert 'shell_output("#{bin}/supa.cc --version")' in formula


def test_publication_docs_cover_installation_and_release():
    installation = Path("docs/installation.md").read_text(encoding="utf-8")
    release = Path("docs/release.md").read_text(encoding="utf-8")

    assert "brew tap dgabreuu/supa-cc https://github.com/dgabreuu/supa.cc.git" in installation
    assert "brew install --HEAD supa-cc" in installation
    assert "brew install supa-cc" in installation
    assert "brew --repo dgabreuu/supa-cc" in release
    assert "brew update-python-resources Formula/supa-cc.rb" in release
    assert "brew audit --strict supa-cc" in release
    assert "brew test supa-cc" in release
    assert "git status --short" in release
