from pathlib import Path
import re

import yaml
import tomllib



REPO_URL = "https://github.com/dgabreuu/supa.cc.git"
PACKAGE_VERSION = "0.5.4"
STABLE_FORMULA_VERSION = "0.5.4"
TARBALL_URL = (
    "https://github.com/dgabreuu/supa.cc/archive/refs/tags/"
    f"v{STABLE_FORMULA_VERSION}.tar.gz"
)
TARBALL_SHA256 = "ac98e4c7c4a39fe0ded8684fac5fca7c3c4c38314ed6c2ce66ccde30481ca47f"
HOMEBREW_TAP = "dgabreuu/supa-cc"
HOMEBREW_FORMULA = f"{HOMEBREW_TAP}/supa-cc"
HOMEBREW_TAP_COMMAND = f"brew tap {HOMEBREW_TAP} {REPO_URL}"
HOMEBREW_SUPABASE_INSTALL_COMMAND = "brew install supabase/tap/supabase"
HOMEBREW_INSTALL_COMMAND = f"brew install {HOMEBREW_FORMULA}"


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
    assert 'resource "more-itertools" do' in formula
    assert 'resource "questionary" do' in formula
    for retired_resource in ("markdown-it-py", "mdurl", "pygments", "rich"):
        assert f'resource "{retired_resource}" do' not in formula
    assert 'shell_output("#{bin}/supa.cc --version")' in formula


def test_publication_docs_keep_stable_installation_separate_from_development():
    installation = Path("docs/installation.md").read_text(encoding="utf-8")
    release = Path("docs/release.md").read_text(encoding="utf-8")

    assert HOMEBREW_TAP_COMMAND in installation
    assert HOMEBREW_INSTALL_COMMAND in installation
    assert "brew install supa-cc" not in installation
    assert "brew install --HEAD supa-cc" not in installation
    assert "brew --repo dgabreuu/supa-cc" in release
    assert "brew install supabase/tap/supabase" in release
    assert "brew trust --formula dgabreuu/supa-cc/supa-cc" in release
    assert "brew trust supabase/tap" not in release
    assert (
        "brew update-python-resources --ignore-main-package-cooldown "
        "Formula/supa-cc.rb"
    ) in release
    assert "brew audit --strict --formula dgabreuu/supa-cc/supa-cc" in release
    assert "brew test dgabreuu/supa-cc/supa-cc" in release
    assert "git status --short" in release


def test_docs_describe_supported_runtime_and_state_without_claiming_name_only_files():
    security = Path("docs/security.md").read_text(encoding="utf-8")
    normalized = security.lower()

    assert "2.109.1" in security
    assert "official `supabase` profile" in normalized
    assert "executable" in normalized
    assert "no local file contains" in normalized and "pat" in normalized
    for state in ("accounts.json", "active-account", "session-sync", ".lock"):
        assert state in security
    assert "pending transition" in normalized
    assert "mutation" in normalized
    assert "only account names" not in normalized
    assert "local files contain only names" not in normalized


def test_installation_uses_stable_release_channels():
    installation = Path("docs/installation.md").read_text(encoding="utf-8")

    assert HOMEBREW_INSTALL_COMMAND in installation
    assert "brew install supa-cc" not in installation
    assert "supabase.com/docs/guides/local-development/cli/getting-started" in installation
    for command in ("install", "upgrade", "uninstall"):
        assert re.search(rf"(?m)^pipx {command} supa\.cc\s*$", installation)


def test_release_formula_uses_verified_0_5_4_tag():
    release = Path("docs/release.md").read_text(encoding="utf-8")
    formula = Path("Formula/supa-cc.rb").read_text(encoding="utf-8")

    assert "v0.5.4" in formula
    assert "v0.5.0" not in formula
    assert "v0.4.2" not in formula
    assert "v0.3.0" not in formula
    assert "brew test dgabreuu/supa-cc/supa-cc" in release


def test_public_homebrew_flow_uses_formula_scoped_trust():
    installation = Path("docs/installation.md").read_text(encoding="utf-8")
    troubleshooting = Path("docs/troubleshooting.md").read_text(encoding="utf-8")

    for document in (installation,):
        assert HOMEBREW_TAP_COMMAND in document
        assert HOMEBREW_SUPABASE_INSTALL_COMMAND in document
        assert HOMEBREW_INSTALL_COMMAND in document
        assert (
            document.index(HOMEBREW_TAP_COMMAND)
            < document.index(HOMEBREW_SUPABASE_INSTALL_COMMAND)
            < document.index(HOMEBREW_INSTALL_COMMAND)
        )
        assert "brew install supa-cc" not in document
        assert "brew trust dgabreuu/supa-cc" not in document
        assert "HOMEBREW_NO_REQUIRE_TAP_TRUST" not in document

    assert HOMEBREW_SUPABASE_INSTALL_COMMAND in troubleshooting
    assert HOMEBREW_INSTALL_COMMAND in troubleshooting
    assert "brew trust --formula dgabreuu/supa-cc/supa-cc" in troubleshooting
    assert "brew trust dgabreuu/supa-cc" not in troubleshooting
    assert "brew trust supabase/tap" not in troubleshooting
    assert "HOMEBREW_NO_REQUIRE_TAP_TRUST" not in troubleshooting


def test_manual_install_channels_are_explicitly_labeled_as_fallbacks():
    installation = Path("docs/installation.md").read_text(encoding="utf-8")

    macos = installation[installation.index("### Homebrew (macOS only)") :]
    linux = installation[installation.index("### Linux (pipx only)") :]
    windows = installation[installation.index("### Windows (pipx only)") :]

    assert "advanced fallback" in macos.lower()
    assert "manual fallback" in macos.lower()
    assert "manual `pipx` fallback" in linux
    assert "manual `pipx` fallback" in windows


def test_homebrew_workflow_is_manual_read_only_macos_validation():
    path = Path(".github/workflows/homebrew.yml")
    workflow_text = path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)
    trigger = workflow.get("on", workflow.get(True))

    assert trigger == {"workflow_dispatch": None}
    assert workflow["permissions"] == {}
    validate = workflow["jobs"]["validate"]
    assert validate["runs-on"] == "macos-latest"
    assert validate["permissions"] == {"contents": "read"}
    assert "secrets" not in workflow_text.lower()
    assert "id-token" not in workflow_text.lower()
    for permission in ("write", "packages:", "deployments:"):
        assert permission not in workflow_text.lower()


def test_homebrew_workflow_refreshes_metadata_once_before_registering_tap():
    workflow_text = Path(".github/workflows/homebrew.yml").read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)
    steps = workflow["jobs"]["validate"]["steps"]
    command_lines = [
        line.strip()
        for step in steps
        for line in step.get("run", "").splitlines()
        if line.strip()
    ]
    update_commands = [
        line
        for line in command_lines
        if line == "brew update" or line.startswith("brew update ")
    ]

    assert steps[0] == {"name": "Update Homebrew metadata", "run": "brew update"}
    assert update_commands == ["brew update"]
    assert command_lines.index("brew update") < command_lines.index(
        "brew tap dgabreuu/supa-cc https://github.com/dgabreuu/supa.cc.git"
    )


def test_homebrew_workflow_validates_committed_formula_without_publishing():
    workflow_text = Path(".github/workflows/homebrew.yml").read_text(encoding="utf-8")

    for command in (
        "brew tap dgabreuu/supa-cc https://github.com/dgabreuu/supa.cc.git",
        'tap_repo="$(brew --repo dgabreuu/supa-cc)"',
        'test "$(git -C "$tap_repo" rev-parse HEAD)" = "$GITHUB_SHA"',
        "brew trust --formula supabase/tap/supabase",
        "brew trust --formula dgabreuu/supa-cc/supa-cc",
        "brew install --yes supabase/tap/supabase",
        "brew install --yes dgabreuu/supa-cc/supa-cc",
        'formula="$tap_repo/Formula/supa-cc.rb"',
        'brew update-python-resources --ignore-main-package-cooldown "$formula"',
        'git -C "$tap_repo" diff --exit-code -- Formula/supa-cc.rb',
        "brew audit --strict --formula dgabreuu/supa-cc/supa-cc",
        "supa.cc --version",
        "supa.cc version",
        "brew test dgabreuu/supa-cc/supa-cc",
    ):
        assert command in workflow_text
    sha_guard = workflow_text.index('test "$(git -C "$tap_repo" rev-parse HEAD)" = "$GITHUB_SHA"')
    supabase_trust = workflow_text.index("brew trust --formula supabase/tap/supabase")
    formula_trust = workflow_text.index("brew trust --formula dgabreuu/supa-cc/supa-cc")
    supabase_install = workflow_text.index("brew install --yes supabase/tap/supabase")
    install = workflow_text.index("brew install --yes dgabreuu/supa-cc/supa-cc")
    resource_update = workflow_text.index(
        'brew update-python-resources --ignore-main-package-cooldown "$formula"'
    )
    assert sha_guard < supabase_trust < formula_trust < supabase_install < install < resource_update
    assert "brew trust dgabreuu/supa-cc" not in workflow_text
    assert "brew trust supabase/tap" not in workflow_text
    assert "HOMEBREW_NO_REQUIRE_TAP_TRUST" not in workflow_text
    assert 'brew audit --strict --formula "$formula"' not in workflow_text
    assert 'brew install "$formula"' not in workflow_text
    assert STABLE_FORMULA_VERSION in workflow_text
    for prohibited in (
        "actions/checkout",
        "git commit",
        "git push",
        "gh release",
        "upload-artifact",
    ):
        assert prohibited not in workflow_text


def test_homebrew_workflow_requires_supported_supabase_cli_before_supa_cc_checks():
    workflow_text = Path(".github/workflows/homebrew.yml").read_text(encoding="utf-8")

    install = workflow_text.index("brew install --yes dgabreuu/supa-cc/supa-cc")
    supabase_check = workflow_text.index("supabase --version")
    supa_cc_check = workflow_text.index("supa.cc --version")

    assert install < supabase_check < supa_cc_check
    assert 'minimum_version="2.109.1"' in workflow_text
    assert "Gem::Version" in workflow_text
    assert 'puts "Installed Supabase CLI version: #{installed}"' in workflow_text
    assert "abort" in workflow_text
    assert "permissions: {}" in workflow_text
    assert "contents: read" in workflow_text
    assert "secrets" not in workflow_text.lower()
    assert "id-token" not in workflow_text.lower()


def test_ci_has_least_privilege_cross_platform_build_and_security_jobs():
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert re.search(r"permissions:\s*\n\s+contents: read", workflow)
    assert "ubuntu-latest" in workflow and "macos-latest" in workflow
    assert '"3.11"' in workflow and '"3.x"' in workflow
    assert '"3.9"' not in workflow
    assert "fedora" in workflow.lower() and "archlinux" in workflow.lower()
    assert "fedora@sha256:" in workflow
    assert "archlinux@sha256:" in workflow
    assert "fedora:latest" not in workflow
    assert "archlinux:latest" not in workflow
    assert "pip check" in workflow
    assert "python scripts/runtime_requirements.py runtime-requirements.txt" in workflow
    assert "pip-audit --requirement runtime-requirements.txt" in workflow
    assert "pip-audit --skip-editable" in workflow
    assert "--ignore-vuln" not in workflow
    assert "pip>=26.1.2" in workflow
    assert "persist-credentials: false" in workflow
    assert "python scripts/security_scan.py --tracked --history" in workflow
    assert "python -m pytest --cache-clear --collect-only -q" in workflow
    assert "python scripts/security_scan.py --path .pytest_cache" in workflow
    assert "actions/checkout@v4" not in workflow
    assert "actions/setup-python@v5" not in workflow
    assert "actions/upload-artifact@v4" not in workflow
    assert "PYSEC-2022-43012" not in workflow
    assert "PYSEC-2025-49" not in workflow
    assert "PYSEC-2026-1918" not in workflow
    assert "python -m build" in workflow
    assert "artifact" in workflow.lower()
    assert re.search(r"^jobs:", workflow, re.MULTILINE)
    assert "scripts/inspect_artifacts.py dist" in workflow
    assert "wheel-test/bin/supa.cc --version" in workflow
    assert "wheel-test/bin/supa.cc version" in workflow


def test_ci_validates_public_installers_with_native_shells():
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "bash -n install.sh" in workflow
    assert "bash install.sh --dry-run --yes" in workflow
    assert "System.Management.Automation.Language.Parser" in workflow
    assert ".\\install.ps1 -DryRun -Yes" in workflow


def test_windows_ci_runs_full_suite_without_claiming_real_vault_coverage():
    workflow = yaml.safe_load(Path(".github/workflows/ci.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["test-build"]["steps"]
    test_steps = [step for step in steps if "pytest" in step.get("run", "")]

    assert len(test_steps) == 2
    windows_steps = [
        step for step in test_steps if step.get("if") == "runner.os == 'Windows'"
    ]
    assert len(windows_steps) == 1
    assert "python -m pytest\n" in windows_steps[0]["run"]
    assert "tests/test_" not in windows_steps[0]["run"]
    assert "SUPA_CC_RUN_WINDOWS_CREDENTIAL_MANAGER_SMOKE" not in windows_steps[0]["run"]


def test_release_uses_the_same_audit_and_artifact_inspection_commands_as_ci():
    release = Path("docs/release.md").read_text(encoding="utf-8")

    assert "python3 scripts/runtime_requirements.py runtime-requirements.txt" in release
    assert "pip-audit --requirement runtime-requirements.txt" in release
    assert "pip-audit --skip-editable" in release
    assert "scripts/inspect_artifacts.py dist" in release
    assert "python3 scripts/security_scan.py --tracked --history" in release
    assert "python3 -m pytest --cache-clear --collect-only -q" in release
    assert "python3 scripts/security_scan.py --path .pytest_cache" in release
    assert "--ignore-vuln" not in release


def test_release_workflow_uses_published_release_and_least_privilege_oidc():
    path = Path(".github/workflows/release.yml")
    workflow_text = path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)
    trigger = workflow.get("on", workflow.get(True))

    assert trigger["release"] == {"types": ["published"]}
    assert "workflow_dispatch" in trigger
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
    stable_guard = "github.event_name == 'workflow_dispatch' || (github.event.release.draft == false && github.event.release.prerelease == false)"

    assert jobs["build"]["if"] == stable_guard
    for job_name in ("publish", "verify-pypi"):
        assert jobs[job_name]["if"] == "success()"

    validation = jobs["build"]["steps"][0]
    assert validation["name"] == "Require stable published release"
    assert validation["if"] == "github.event_name == 'release'"
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
    assert f"pipx install supa.cc=={PACKAGE_VERSION}" in workflow_text


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


def test_changelog_marks_0_3_0_as_released_and_only_claims_verified_scope():
    changelog = Path("CHANGELOG.md").read_text(encoding="utf-8")
    normalized = changelog.lower()

    heading = re.search(r"^##\s+\[?0\.3\.0\]?\s*[-:]\s*(.+)$", changelog, re.MULTILINE)
    assert heading
    assert heading.group(1) == "2026-07-12"
    assert (
        "[0.3.0]: https://github.com/dgabreuu/supa.cc/compare/v0.2.0...v0.3.0"
        in changelog
    )
    for expected in (
        "native session",
        "linux",
        "windows",
        "doctor",
        "security",
        "recovery",
    ):
        assert expected in normalized
    assert "re-adicionar" not in normalized
    assert "readicionar" not in normalized
    assert "rollback para 0.2.0" not in normalized


def test_changelog_marks_0_4_0_as_released():
    changelog = Path("CHANGELOG.md").read_text(encoding="utf-8")

    heading = re.search(r"^##\s+\[?0\.4\.0\]?\s*[-:]\s*(.+)$", changelog, re.MULTILINE)
    assert heading
    assert heading.group(1) == "2026-07-13"
    assert (
        "[0.4.0]: https://github.com/dgabreuu/supa.cc/compare/v0.3.0...v0.4.0"
        in changelog
    )
    assert "## [0.4.0] - Unreleased" not in changelog


def test_changelog_records_0_4_2_publication():
    changelog = Path("CHANGELOG.md").read_text(encoding="utf-8")

    assert "## [0.4.2] - 2026-07-14" in changelog
    assert "Interactive sessions keep" in changelog
    assert (
        "[0.4.2]: https://github.com/dgabreuu/supa.cc/compare/v0.4.1...v0.4.2"
        in changelog
    )


def test_changelog_records_0_5_0_release_candidate():
    changelog = Path("CHANGELOG.md").read_text(encoding="utf-8")

    assert "## [0.5.0] - 2026-07-15" in changelog
    assert "versioned, secret-free state document" in changelog
    assert (
        "[0.5.0]: https://github.com/dgabreuu/supa.cc/compare/v0.4.2...v0.5.0"
        in changelog
    )


def test_changelog_records_0_5_2_windows_bootstrap_fix():
    changelog = Path("CHANGELOG.md").read_text(encoding="utf-8")

    assert "## [0.5.2] - 2026-07-15" in changelog
    assert "PowerShell bootstrap runs now return success" in changelog
    assert (
        "[0.5.2]: https://github.com/dgabreuu/supa.cc/compare/v0.5.1...v0.5.2"
        in changelog
    )


def test_changelog_records_0_5_3_tui_fix_and_unreleased_comparison():
    changelog = Path("CHANGELOG.md").read_text(encoding="utf-8")

    assert "## [0.5.3] - 2026-07-17" in changelog
    assert "The TUI resolves semantic loading styles" in changelog
    assert (
        "[0.5.3]: https://github.com/dgabreuu/supa.cc/compare/v0.5.2...v0.5.3"
        in changelog
    )
    assert (
        "[0.5.4]: https://github.com/dgabreuu/supa.cc/compare/v0.5.3...v0.5.4"
        in changelog
    )


def test_changelog_records_0_5_4_publication_metadata_correction():
    changelog = Path("CHANGELOG.md").read_text(encoding="utf-8")

    assert "## [0.5.4] - 2026-07-17" in changelog
    assert "published package metadata and immutable bootstrap references" in changelog
    assert (
        "[Unreleased]: https://github.com/dgabreuu/supa.cc/compare/v0.5.4...HEAD"
        in changelog
    )


def test_release_runbook_orders_pypi_verification_before_formula_and_copy_changes():
    release = Path("docs/release.md").read_text(encoding="utf-8")
    normalized = release.lower()

    concepts = (
        r"^##\s+\d+\..*validate.*candidate",
        r"^##\s+\d+\..*github release",
        r"^##\s+\d+\..*pypi",
        r"^##\s+\d+\..*pipx.*linux.*windows",
        r"^##\s+\d+\..*homebrew formula",
        r"^##\s+\d+\..*availability documentation",
    )
    positions = [re.search(pattern, normalized, re.MULTILINE).start() for pattern in concepts]
    assert positions == sorted(positions)
    assert "v0.5.4" in Path("Formula/supa-cc.rb").read_text(encoding="utf-8")


def test_troubleshooting_doctor_language_is_credential_store_neutral():
    troubleshooting = Path("docs/troubleshooting.md").read_text(encoding="utf-8")
    normalized = troubleshooting.lower()

    assert "credential-store" in normalized
    assert "configur" in normalized
    assert "does not" in normalized and ("test" in normalized or "verif" in normalized)


def test_public_docs_do_not_claim_default_doctor_probes_credential_availability():
    skill = Path("SKILL.md").read_text(encoding="utf-8")
    troubleshooting = Path("docs/troubleshooting.md").read_text(encoding="utf-8")

    for contents in (skill, troubleshooting):
        normalized = contents.lower()
        assert "doctor" in normalized
        assert "does not" in normalized or "do not" in normalized
        assert "credential" in normalized
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

    assert "Homebrew (macOS only)" in installation
    assert "Linux (pipx only)" in installation
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
        "automatic credential repair",
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
    assert "supa.cc run --" in usage and "hidden prompt" in usage.lower()
    assert "doctor --json" in usage and "--account <name> --live" in usage
    live_access = re.compile(
        r"(?:only|required)?.{0,100}"
        r"(?:--account\s+<[^>]+>.{0,20}--live|--live.{0,30}--account)"
        r".{0,120}(?:opens?|reads?).{0,40}(?:pat|token|credential)",
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
        "concurrent",
        "login",
        "projects list",
    ):
        assert detail.lower() in security.lower()
    assert "precedence" in security.lower() or "override" in security.lower()
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
    assert "explicit consent" in docs
    assert "never accesses the canonical Supa.cc service" in docs
    assert "never accesses" in docs and "Supabase CLI" in docs


def test_public_support_and_security_surfaces_are_safe_and_official():
    security = Path("SECURITY.md").read_text(encoding="utf-8")
    contributing = Path("CONTRIBUTING.md").read_text(encoding="utf-8")
    assert "https://github.com/dgabreuu/supa.cc/issues" in contributing
    assert "https://github.com/dgabreuu/supa.cc/security/advisories/new" in security
    assert "do not open a public issue" in security.lower()
    assert "python 3.11" in contributing.lower()
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
    assert "credential" in public_copy and "dump" in public_copy
    assert "do not" in public_copy


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
