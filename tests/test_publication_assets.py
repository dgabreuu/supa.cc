from pathlib import Path
import re

import yaml
try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.9/3.10
    import tomli as tomllib



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


def test_publication_docs_keep_stable_installation_separate_from_development():
    installation = Path("docs/installation.md").read_text(encoding="utf-8")
    release = Path("docs/release.md").read_text(encoding="utf-8")

    assert "brew tap dgabreuu/supa-cc https://github.com/dgabreuu/supa.cc.git" in installation
    assert "brew install supa-cc" in installation
    assert "brew install --HEAD supa-cc" not in installation
    assert "brew --repo dgabreuu/supa-cc" in release
    assert "brew update-python-resources Formula/supa-cc.rb" in release
    assert "brew audit --strict supa-cc" in release
    assert "brew test supa-cc" in release
    assert "git status --short" in release


def test_docs_describe_supported_runtime_and_state_without_claiming_name_only_files():
    security = Path("docs/security.md").read_text(encoding="utf-8")
    normalized = security.lower()

    assert "2.109.1" in security
    assert "perfil oficial" in normalized
    assert "executável" in normalized
    assert "nenhum arquivo local contém" in normalized and "pat" in normalized
    for state in ("accounts.json", "active-account", "session-sync", ".lock"):
        assert state in security
    assert "backup" in normalized
    assert "mutation" in normalized or "mutaç" in normalized
    assert "somente nomes de contas" not in normalized
    assert "arquivos locais contêm somente nomes" not in normalized


def test_installation_uses_stable_release_channels():
    installation = Path("docs/installation.md").read_text(encoding="utf-8")

    assert "brew install supa-cc" in installation
    assert "supabase.com/docs/guides/local-development/cli/getting-started" in installation
    for command in ("install", "upgrade", "uninstall"):
        assert re.search(rf"(?m)^pipx {command} supa\.cc\s*$", installation)


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
    assert "python scripts/runtime_requirements.py runtime-requirements.txt" in workflow
    assert "pip-audit --requirement runtime-requirements.txt" in workflow
    assert "python -m build" in workflow
    assert "artifact" in workflow.lower()
    assert re.search(r"^jobs:", workflow, re.MULTILINE)
    assert "scripts/inspect_artifacts.py dist" in workflow
    assert "wheel-test/bin/supa.cc --version" in workflow
    assert "wheel-test/bin/supa.cc version" in workflow


def test_windows_ci_runs_full_suite_without_claiming_real_vault_coverage():
    workflow = yaml.safe_load(Path(".github/workflows/ci.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["test-build"]["steps"]
    test_steps = [step for step in steps if "pytest" in step.get("run", "")]

    assert len(test_steps) == 1
    assert "python -m pytest\n" in test_steps[0]["run"]
    assert "tests/test_" not in test_steps[0]["run"]
    assert "SUPA_CC_RUN_WINDOWS_CREDENTIAL_MANAGER_SMOKE" not in test_steps[0]["run"]


def test_release_uses_the_same_audit_and_artifact_inspection_commands_as_ci():
    release = Path("docs/release.md").read_text(encoding="utf-8")

    assert "python scripts/runtime_requirements.py runtime-requirements.txt" in release
    assert "pip-audit --requirement runtime-requirements.txt" in release
    assert "scripts/inspect_artifacts.py dist" in release


def test_release_workflow_uses_published_release_and_least_privilege_oidc():
    path = Path(".github/workflows/release.yml")
    workflow_text = path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)
    trigger = workflow.get("on", workflow.get(True))

    assert trigger == {"release": {"types": ["published"]}}
    assert workflow["permissions"] == {}
    assert workflow["jobs"]["build"]["permissions"] == {"contents": "read"}
    publish = workflow["jobs"]["publish"]
    assert publish["permissions"] == {"id-token": "write"}
    assert "permissions" not in workflow["jobs"]["verify-pypi"]
    assert "secrets" not in workflow_text.lower()
    assert "password:" not in workflow_text.lower()


def test_release_workflow_rejects_draft_and_prerelease_before_build_or_publish():
    workflow = yaml.safe_load(Path(".github/workflows/release.yml").read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    stable_guard = "github.event.release.draft == false && github.event.release.prerelease == false"

    assert jobs["build"]["if"] == stable_guard
    for job_name in ("publish", "verify-pypi"):
        assert jobs[job_name]["if"] == "success()"

    validation = jobs["build"]["steps"][0]
    assert validation["name"] == "Require stable published release"
    assert validation["env"] == {
        "RELEASE_DRAFT": "${{ github.event.release.draft }}",
        "RELEASE_PRERELEASE": "${{ github.event.release.prerelease }}",
    }
    assert "RELEASE_DRAFT" in validation["run"]
    assert "RELEASE_PRERELEASE" in validation["run"]


def test_release_workflow_pins_only_reviewed_official_actions_by_sha():
    workflow_text = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)
    expected_actions = {
        "actions/checkout",
        "actions/setup-python",
        "actions/upload-artifact",
        "actions/download-artifact",
        "pypa/gh-action-pypi-publish",
    }
    uses = re.findall(
        r"^\s+(?:-\s+)?uses:\s+([^@\s]+)@([^\s#]+)\s+#\s+(.+)$",
        workflow_text,
        re.MULTILINE,
    )

    assert {repository for repository, _ref, _comment in uses} == expected_actions
    assert all(re.fullmatch(r"[0-9a-f]{40}", ref) for _repository, ref, _comment in uses)
    assert all(re.search(r"\bv\d", comment) for _repository, _ref, comment in uses)
    assert workflow_text.count("actions/checkout@") == 1
    assert any(
        step.get("uses", "").startswith("actions/checkout@")
        for step in workflow["jobs"]["build"]["steps"]
    )
    for job_name in ("publish", "verify-pypi"):
        assert not any(
            step.get("uses", "").startswith("actions/checkout@")
            for step in workflow["jobs"][job_name]["steps"]
        )


def test_release_workflow_builds_once_and_publishes_the_same_artifact():
    workflow_text = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)
    jobs = workflow["jobs"]

    assert workflow_text.count("python -m build") == 1
    assert workflow_text.count("actions/upload-artifact@") == 1
    assert workflow_text.count("actions/download-artifact@") == 1
    assert jobs["publish"]["needs"] == "build"
    assert jobs["verify-pypi"]["needs"] == "publish"
    assert jobs["verify-pypi"]["strategy"]["matrix"]["os"] == [
        "ubuntu-latest",
        "windows-latest",
    ]
    assert "pipx install supa.cc==0.3.0" in workflow_text


def test_pypi_metadata_has_explicit_markdown_and_public_links():
    metadata = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]

    assert metadata["readme"] == {
        "file": "README.md",
        "content-type": "text/markdown",
    }
    assert metadata["urls"]["Documentation"].endswith("/blob/main/docs/usage.md")
    assert metadata["urls"]["Changelog"].endswith("/blob/main/CHANGELOG.md")


def test_readme_links_render_from_pypi_without_repository_relative_targets():
    readme = Path("README.md").read_text(encoding="utf-8")
    targets = re.findall(r"!?(?:\[[^]]*\])\(([^)]+)\)", readme)

    assert targets
    assert all(target.startswith("https://") for target in targets)


def test_changelog_marks_0_3_0_as_prepared_and_only_claims_verified_scope():
    changelog = Path("CHANGELOG.md").read_text(encoding="utf-8")
    normalized = changelog.lower()

    heading = re.search(r"^##\s+\[?0\.3\.0\]?\s*[-:]\s*(.+)$", changelog, re.MULTILINE)
    assert heading
    assert "não lançad" in heading.group(1).lower()
    for expected in (
        "sessão nativa",
        "linux",
        "windows",
        "doctor",
        "segurança",
        "recuperação",
    ):
        assert expected in normalized
    assert "re-adicionar" not in normalized
    assert "readicionar" not in normalized
    assert "rollback para 0.2.0" not in normalized


def test_release_runbook_orders_pypi_verification_before_formula_and_copy_changes():
    release = Path("docs/release.md").read_text(encoding="utf-8")
    normalized = release.lower()

    concepts = (
        r"^##\s+\d+\..*validar.*candidat",
        r"^##\s+\d+\..*github release",
        r"^##\s+\d+\..*pypi",
        r"^##\s+\d+\..*pipx.*linux.*windows",
        r"^##\s+\d+\..*fórmula homebrew",
        r"^##\s+\d+\..*texto.*disponibilidade",
    )
    positions = [re.search(pattern, normalized, re.MULTILINE).start() for pattern in concepts]
    assert positions == sorted(positions)
    assert "v0.2.0" in Path("Formula/supa-cc.rb").read_text(encoding="utf-8")


def test_troubleshooting_doctor_language_is_credential_store_neutral():
    troubleshooting = Path("docs/troubleshooting.md").read_text(encoding="utf-8")
    normalized = troubleshooting.lower()

    assert "armazenamento de credenciais" in normalized
    assert "configur" in normalized
    assert "não" in normalized and ("test" in normalized or "verific" in normalized)


def test_public_docs_do_not_claim_default_doctor_probes_credential_availability():
    skill = Path("SKILL.md").read_text(encoding="utf-8")
    troubleshooting = Path("docs/troubleshooting.md").read_text(encoding="utf-8")

    for contents in (skill, troubleshooting):
        normalized = contents.lower()
        assert "doctor" in normalized
        assert "não" in normalized
        assert "credencial" in normalized
        assert "live" in normalized


def test_obsolete_private_implementation_documents_are_removed():
    obsolete = [
        Path(".superpowers/sdd/native-sync-task-3-report.md"),
        *Path("docs/superpowers").glob("**/*linux-support*"),
        *Path("docs/superpowers").glob("**/*native-cli-session-sync*"),
    ]
    assert not any(path.exists() for path in obsolete)


def test_public_docs_cover_linux_installation_and_credential_requirements():
    installation = Path("docs/installation.md").read_text(encoding="utf-8")
    skill = Path("SKILL.md").read_text(encoding="utf-8")
    agents = Path("AGENTS.md").read_text(encoding="utf-8")

    for distribution in ("Debian", "Ubuntu", "Arch", "Fedora"):
        assert distribution in installation
    for detail in ("pipx", "Secret Service", "D-Bus", "XDG_CONFIG_HOME", "supa.cc doctor"):
        assert detail in installation
    for detail in ("headless", "plaintext", "keyrings.alt"):
        assert detail in installation.lower()
    assert "Secret Service" in skill and "Secret Service" in agents


def test_public_docs_keep_installation_routes_and_credential_flow_platform_specific():
    installation = Path("docs/installation.md").read_text(encoding="utf-8")
    skill = Path("SKILL.md").read_text(encoding="utf-8")

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
    surfaces = {
        path: Path(path).read_text(encoding="utf-8")
        for path in (
            "SKILL.md",
            "AGENTS.md",
            "docs/installation.md",
            "docs/usage.md",
            "docs/security.md",
            "docs/troubleshooting.md",
            "CONTRIBUTING.md",
        )
    }
    contradictions = (
        "supa.cc add <name> --token",
        "supa.cc add <nome> --token",
        "supabase login --name",
        "repair automático",
        "credential repair is automatic",
        "memoizes both loaded tokens and missing",
        "ativa a conta informada no supabase cli",
    )
    default_doctor_reads_secrets = re.compile(
        r"\b(?:supa\.cc\s+)?doctor(?:\s+--json)?\s+"
        r"(?:abre|l[eê]|consulta|sonda|testa|verifica|opens?|reads?|probes?|checks?)\s+"
        r"(?:o\s+|a\s+|os\s+|as\s+)?"
        r"(?:pat|token|credencia\w*|backend|armazenamento)",
        re.IGNORECASE,
    )

    for path, document in surfaces.items():
        normalized = document.lower()
        for contradiction in contradictions:
            assert contradiction not in normalized, f"contradiction in {path}: {contradiction}"
        assert not default_doctor_reads_secrets.search(document), (
            f"{path} claims default doctor opens or probes credentials"
        )

    skill = surfaces["SKILL.md"]
    usage = surfaces["docs/usage.md"]
    security = surfaces["docs/security.md"]
    assert "supa.cc run --" in usage and "prompt oculto" in usage.lower()
    assert "doctor --json" in usage and "--account <nome> --live" in usage
    live_access = re.compile(
        r"(?:somente|apenas|exige|required|only)?.{0,100}"
        r"(?:--account\s+<[^>]+>.{0,20}--live|--live.{0,30}--account)"
        r".{0,120}(?:abre|l[eê]|opens?|reads?).{0,40}(?:pat|token|credencia)",
        re.IGNORECASE | re.DOTALL,
    )
    for path, document in (
        ("docs/usage.md", usage),
        ("docs/security.md", security),
    ):
        assert live_access.search(document), (
            f"{path} must state that only account live mode reads a credential"
        )
    for detail in (
        "SUPABASE_ACCESS_TOKEN",
        "supa.cc.supabase.accounts.v2",
        "active-account",
        "plaintext",
        "logout",
        "journal",
        "concorr",
        "login",
        "projects list",
    ):
        assert detail.lower() in security.lower()
    assert "precedência" in security.lower() or "override" in security.lower()
    assert "sbp_oauth_" in skill and "[0-9a-f]{40}" in skill


def test_public_docs_describe_the_opt_in_keychain_smoke_safely():
    contributing = Path("CONTRIBUTING.md").read_text(encoding="utf-8")
    docs = contributing

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


def test_public_support_and_security_surfaces_are_safe_and_official():
    security = Path("SECURITY.md").read_text(encoding="utf-8")
    contributing = Path("CONTRIBUTING.md").read_text(encoding="utf-8")
    assert "https://github.com/dgabreuu/supa.cc/issues" in contributing
    assert "https://github.com/dgabreuu/supa.cc/security/advisories/new" in security
    assert "não abra uma issue pública" in security.lower()
    assert "python 3.9" in contributing.lower()
    assert 'python3 -m pip install -e ".[dev]"' in contributing
    assert 'py -m pip install -e ".[dev]"' in contributing
    assert "python3 -m pytest" in contributing
    assert "py -m pytest" in contributing
    assert "pat" in security.lower() and "dump" in security.lower()
    assert "pat" in contributing.lower() and "dump" in contributing.lower()


def _load_issue_form(filename):
    path = Path(".github/ISSUE_TEMPLATE", filename)
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _fields_by_id(form):
    return {field["id"]: field for field in form["body"] if "id" in field}


def _assert_safety_contract(form):
    fields = _fields_by_id(form)
    safety = fields["safety"]
    assert safety["type"] == "checkboxes"
    assert safety["attributes"]["options"][0]["required"] is True
    public_copy = "\n".join(
        field.get("attributes", {}).get("value", "") for field in form["body"]
    ).lower()
    assert "pat" in public_copy
    assert "credencia" in public_copy and "dump" in public_copy
    assert any(term in public_copy for term in ("nunca", "não inclua", "do not"))


def test_bug_and_install_forms_collect_required_reproduction_context():
    filenames = ("bug_report.yml", "install_problem.yml")
    required_fields = {
        "os": "input",
        "supa_cc_version": "input",
        "python_version": "input",
        "supabase_cli_version": "input",
        "installation_method": "dropdown",
        "reproduction": "textarea",
        "expected": "textarea",
        "actual": "textarea",
    }

    for filename in filenames:
        form = _load_issue_form(filename)
        fields = _fields_by_id(form)
        assert form.get("name") and form.get("description")
        for field_id, field_type in required_fields.items():
            assert fields[field_id]["type"] == field_type
            assert fields[field_id]["validations"]["required"] is True
        assert fields["doctor"]["type"] == "textarea"
        assert fields["doctor"].get("validations", {}).get("required", False) is False
        assert "supa.cc doctor --json" in fields["doctor"]["attributes"]["label"]
        _assert_safety_contract(form)


def test_feature_form_requires_only_problem_proposal_and_safety_acceptance():
    form = _load_issue_form("feature_request.yml")
    fields = _fields_by_id(form)

    assert form.get("name") and form.get("description")
    assert set(fields) == {"problem", "proposal", "safety"}
    assert fields["problem"]["type"] == "textarea"
    assert fields["proposal"]["type"] == "textarea"
    assert fields["problem"]["validations"]["required"] is True
    assert fields["proposal"]["validations"]["required"] is True
    _assert_safety_contract(form)


def test_issue_template_config_disables_blank_issues_and_uses_official_routes():
    config = _load_issue_form("config.yml")

    assert config["blank_issues_enabled"] is False
    assert [link["url"] for link in config["contact_links"]] == [
        "https://github.com/dgabreuu/supa.cc/issues",
        "https://github.com/dgabreuu/supa.cc/security/advisories/new",
    ]


def test_issue_form_validation_dependency_is_declared():
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]

    assert any(
        re.match(r"pyyaml(?:\[.*\])?\s*[<>=!~]", dependency, re.IGNORECASE)
        for dependency in project["optional-dependencies"]["dev"]
    )
