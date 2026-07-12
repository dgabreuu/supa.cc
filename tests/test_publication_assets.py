from pathlib import Path
import re



REPO_URL = "https://github.com/dgabreuu/supa.cc.git"
TARBALL_URL = "https://github.com/dgabreuu/supa.cc/archive/refs/tags/v0.2.0.tar.gz"
TARBALL_SHA256 = "61ffeb04b5c157f71a5e14fdd7a740757d9ac77655c39476feb04ea02ceaf054"


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


def test_docs_describe_supported_runtime_and_state_without_claiming_name_only_files():
    paths = ("README.md", "SKILL.md", "docs/installation.md", "AGENTS.md")
    docs = "\n".join(Path(path).read_text(encoding="utf-8") for path in paths)
    normalized = docs.lower()

    assert "2.109.1" in docs
    assert "perfil oficial" in normalized
    assert "executável" in normalized and "confiança" in normalized
    assert "nenhum arquivo local contém" in normalized and "pat" in normalized
    for state in ("accounts.json", "active-account", "session-sync", ".lock"):
        assert state in docs
    assert "backup" in normalized
    assert "mutation" in normalized or "mutaç" in normalized
    assert "somente nomes de contas" not in normalized
    assert "arquivos locais contêm somente nomes" not in normalized


def test_installation_uses_release_channels_not_nonexistent_pypi_package():
    installation = Path("docs/installation.md").read_text(encoding="utf-8")
    normalized = installation.lower()

    assert "git+https://github.com/dgabreuu/supa.cc.git" in installation
    assert "brew install supa-cc" in installation
    assert "supabase.com/docs/guides/local-development/cli/getting-started" in installation
    assert not re.search(r"pipx\s+(?:install|upgrade)\s+supa[.-]cc(?:\s|$)", normalized)


def test_release_keeps_formula_stable_until_clean_0_3_0_tag_build():
    release = Path("docs/release.md").read_text(encoding="utf-8")
    normalized = release.lower()

    assert "v0.2.0" in Path("Formula/supa-cc.rb").read_text(encoding="utf-8")
    assert "v0.3.0" in release
    assert "depois que a tag" in normalized or "após a tag" in normalized
    assert "checkout limpo" in normalized
    assert "brew test supa-cc" in release


def test_ci_has_least_privilege_cross_platform_build_and_security_jobs():
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert re.search(r"permissions:\s*\n\s+contents: read", workflow)
    assert "ubuntu-latest" in workflow and "macos-latest" in workflow
    assert '"3.9"' in workflow and '"3.x"' in workflow
    assert "fedora" in workflow.lower() and "archlinux" in workflow.lower()
    assert "pip check" in workflow
    assert "pip-audit --skip-editable" in workflow
    assert "python -m build" in workflow
    assert "artifact" in workflow.lower()
    assert re.search(r"^jobs:", workflow, re.MULTILINE)
    assert "scripts/inspect_artifacts.py dist" in workflow
    assert "wheel-test/bin/supa.cc --version" in workflow
    assert "wheel-test/bin/supa.cc version" in workflow


def test_release_uses_the_same_audit_and_artifact_inspection_commands_as_ci():
    release = Path("docs/release.md").read_text(encoding="utf-8")

    assert "pip-audit --skip-editable" in release
    assert "scripts/inspect_artifacts.py dist" in release


def test_readme_doctor_language_is_credential_store_neutral():
    readme = Path("README.md").read_text(encoding="utf-8")
    doctor = readme.split("## Diagnóstico", 1)[1].split("## Modelo de segurança", 1)[0]

    assert "armazenamento de credenciais" in doctor
    assert "Keychain" not in doctor
    assert "configurado" in doctor
    assert "não testa" in doctor or "não verifica" in doctor


def test_public_docs_do_not_claim_default_doctor_probes_credential_availability():
    readme = Path("README.md").read_text(encoding="utf-8")
    skill = Path("SKILL.md").read_text(encoding="utf-8")
    installation = Path("docs/installation.md").read_text(encoding="utf-8")

    for contents in (readme, skill, installation):
        assert "configurado, mas não verificado" in contents


def test_obsolete_private_implementation_documents_are_removed():
    obsolete = [
        Path(".superpowers/sdd/native-sync-task-3-report.md"),
        *Path("docs/superpowers").glob("**/*linux-support*"),
        *Path("docs/superpowers").glob("**/*native-cli-session-sync*"),
    ]
    assert not any(path.exists() for path in obsolete)


def test_public_docs_cover_linux_installation_and_credential_requirements():
    readme = Path("README.md").read_text(encoding="utf-8")
    installation = Path("docs/installation.md").read_text(encoding="utf-8")
    skill = Path("SKILL.md").read_text(encoding="utf-8")
    agents = Path("AGENTS.md").read_text(encoding="utf-8")
    docs = "\n".join((readme, installation, skill, agents))
    normalized = docs.lower()

    for distribution in ("Debian", "Ubuntu", "Arch", "Fedora"):
        assert distribution in installation
    assert "pipx" in docs
    assert "Secret Service" in docs
    assert "D-Bus" in docs
    assert "XDG_CONFIG_HOME" in docs
    assert "supa.cc doctor" in docs
    assert "headless" in normalized
    assert "plaintext" in normalized
    assert "keyrings.alt" in normalized


def test_public_docs_keep_installation_routes_and_credential_flow_platform_specific():
    readme = Path("README.md").read_text(encoding="utf-8")
    installation = Path("docs/installation.md").read_text(encoding="utf-8")
    skill = Path("SKILL.md").read_text(encoding="utf-8")

    assert "Homebrew (somente macOS)" in readme
    assert "Linux (somente pipx)" in readme
    assert "Homebrew (somente macOS)" in installation
    assert "Linux (somente pipx)" in installation
    assert "macOS: Keychain service supa.cc.supabase.accounts.v2" in skill
    assert "Linux: Secret Service supa.cc.supabase.accounts.v2" in skill
    assert "plaintext" in skill.lower()


def test_release_docs_build_and_validate_linux_artifacts():
    release = Path("docs/release.md").read_text(encoding="utf-8")

    assert "python3 -m build" in release
    assert "dist/" in release
    assert "Linux" in release
    assert "python3 -m pytest" in release


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
    assert "supabase projects list" in docs
    assert "opcional" in normalized or "optional" in normalized
    assert "override" in normalized
    assert "fallback" in normalized and "plaintext" in normalized
    assert "logout" in normalized
    assert "credenciais auxiliares" in normalized or "auxiliary credentials" in normalized
    assert "journal" in normalized
    assert "concorr" in normalized or "concurr" in normalized
    assert "login" in normalized and "logout" in normalized and "projects list" in normalized
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
