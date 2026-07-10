from pathlib import Path


REPO_URL = "https://github.com/dgabreuu/supa.cc.git"
TARBALL_URL = "https://github.com/dgabreuu/supa.cc/archive/refs/tags/v0.1.1.tar.gz"
TARBALL_SHA256 = "a4204159444e34612247c664acb5707536464724b20fe582a6bc4933c9bffe42"


def test_readme_uses_public_repository_url():
    readme = Path("README.md").read_text(encoding="utf-8")

    placeholder_org = "your" + "-" + "org"
    assert f"github.com/{placeholder_org}" not in readme
    assert REPO_URL in readme


def test_homebrew_formula_is_present_with_public_metadata():
    formula = Path("Formula/supa-cc.rb").read_text(encoding="utf-8")

    assert "class SupaCc < Formula" in formula
    assert 'homepage "https://github.com/dgabreuu/supa.cc"' in formula
    assert f'url "{TARBALL_URL}"' in formula
    assert f'sha256 "{TARBALL_SHA256}"' in formula
    assert f'head "{REPO_URL}", branch: "main"' in formula
    assert "depends_on :macos" in formula
    assert 'depends_on "python@3.13"' in formula
    assert 'depends_on "supabase"' in formula
    assert 'depends_on "supabase/tap/supabase"' not in formula
    assert 'resource "click" do' in formula
    assert 'resource "jaraco-classes" do' in formula
    assert 'resource "jaraco-context" do' in formula
    assert 'resource "jaraco-functools" do' in formula
    assert 'resource "markdown-it-py" do' in formula
    assert 'resource "more-itertools" do' in formula
    assert 'resource "questionary" do' in formula
    assert 'resource "rich" do' in formula
    assert 'shell_output("#{bin}/supa.cc --version")' in formula


def test_publication_docs_cover_installation_and_release():
    installation = Path("docs/installation.md").read_text(encoding="utf-8")
    release = Path("docs/release.md").read_text(encoding="utf-8")

    assert "brew tap dgabreuu/supa-cc https://github.com/dgabreuu/supa.cc.git" in installation
    assert "brew install supa-cc" in installation
    assert "brew install --HEAD supa-cc" in installation
    assert "brew --repo dgabreuu/supa-cc" in release
    assert "brew update-python-resources Formula/supa-cc.rb" in release
    assert "brew audit --strict supa-cc" in release
    assert "brew test supa-cc" in release
    assert "git status --short" in release


def test_public_authentication_contract_is_safe_and_current():
    readme = Path("README.md").read_text(encoding="utf-8")
    skill = Path("SKILL.md").read_text(encoding="utf-8")
    installation = Path("docs/installation.md").read_text(encoding="utf-8")
    docs = "\n".join((readme, skill, installation))
    normalized = docs.lower()

    assert "supa.cc add <name> --token" not in normalized
    assert "supa.cc add <nome> --token" not in normalized
    assert "supabase login --name" not in normalized
    assert "repair automático" not in normalized
    assert "credential repair is automatic" not in normalized
    assert "memoizes both loaded tokens and missing" not in normalized
    assert "ativa a conta informada no supabase cli" not in normalized

    assert "supa.cc run --" in docs
    assert "supa.cc doctor" in docs
    assert "doctor --json" in docs
    assert "--account <nome> --live" in docs or "--account <name> --live" in docs
    assert "SUPABASE_ACCESS_TOKEN" in docs
    assert "supa.cc.supabase.accounts.v2" in docs
    assert "active-account" in docs
    assert "não altera a sessão nativa" in normalized or "does not own or alter" in normalized
    assert "prompt oculto" in normalized or "hidden prompt" in normalized
    assert "sbp_oauth_" in docs
    assert "[0-9a-f]{40}" in docs
    assert "40 lowercase hexadecimal" in normalized or "40 caracteres hexadecimais minúsculos" in normalized


def test_public_docs_describe_the_opt_in_keychain_smoke_safely():
    readme = Path("README.md").read_text(encoding="utf-8")
    skill = Path("SKILL.md").read_text(encoding="utf-8")
    docs = "\n".join((readme, skill))

    command = (
        "SUPA_CC_RUN_KEYCHAIN_SMOKE=1 .venv/bin/pytest -q "
        "tests/test_macos_keychain_smoke.py"
    )
    assert command in docs
    assert "supa.cc.tests.<uuid>" in docs
    assert "smoke-<uuid>" in docs
    assert "finally" in docs
    assert "consentimento explícito" in docs or "explicit consent" in docs
    assert (
        "nunca acessa o serviço canônico do Supa.cc" in docs
        or "never accesses the canonical Supa.cc service" in docs
    )
    assert (
        ("nunca acessa" in docs and "Supabase CLI" in docs)
        or ("never accesses" in docs and "Supabase CLI" in docs)
    )
