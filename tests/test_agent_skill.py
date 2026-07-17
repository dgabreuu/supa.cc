import re
from pathlib import Path

import yaml

from supa_cc.__main__ import main


SKILL_ROOT = Path(".agents/skills/supa-cc")
SKILL_PATH = SKILL_ROOT / "SKILL.md"
COMMANDS_PATH = SKILL_ROOT / "references/commands.md"
SAFETY_PATH = SKILL_ROOT / "references/safety-and-errors.md"
OPENAI_METADATA_PATH = SKILL_ROOT / "agents/openai.yaml"


def _frontmatter(markdown: str) -> dict:
    match = re.match(r"\A---\n(.*?)\n---\n", markdown, re.DOTALL)
    assert match, "SKILL.md must start with YAML frontmatter"
    return yaml.safe_load(match.group(1))


def test_skill_uses_the_portable_agent_skills_layout():
    assert SKILL_PATH.is_file()
    assert COMMANDS_PATH.is_file()
    assert SAFETY_PATH.is_file()
    assert OPENAI_METADATA_PATH.is_file()
    assert not Path("SKILL.md").exists()


def test_skill_frontmatter_matches_the_agent_skills_specification():
    contents = SKILL_PATH.read_text(encoding="utf-8")
    metadata = _frontmatter(contents)

    assert {"name", "description"} <= set(metadata)
    assert metadata["name"] == SKILL_ROOT.name == "supa-cc"
    assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", metadata["name"])
    assert metadata["description"].startswith("Use when ")
    assert 1 <= len(metadata["description"]) <= 1024
    assert len(contents.splitlines()) < 500


def test_skill_links_to_each_reference_with_relative_paths():
    contents = SKILL_PATH.read_text(encoding="utf-8")

    for target in ("references/commands.md", "references/safety-and-errors.md"):
        assert f"]({target})" in contents
        assert (SKILL_ROOT / target).is_file()


def test_command_reference_tracks_the_click_command_surface():
    commands = COMMANDS_PATH.read_text(encoding="utf-8")

    for command_name in sorted(main.commands):
        assert f"supa.cc {command_name}" in commands
    for required_form in (
        "supa.cc --version",
        "supa.cc add <name>",
        "supa.cc switch <name>",
        "supa.cc remove <name> [--yes]",
        "supa.cc reset --all [--yes]",
        "supa.cc run -- <arguments>",
        "supa.cc doctor [--json]",
        "supa.cc doctor --installation-check [--json]",
        "supa.cc doctor --account <name> --live",
    ):
        assert required_form in commands


def test_skill_requires_safe_agent_command_selection_and_result_handling():
    skill = SKILL_PATH.read_text(encoding="utf-8").lower()
    commands = COMMANDS_PATH.read_text(encoding="utf-8").lower()
    safety = SAFETY_PATH.read_text(encoding="utf-8").lower()
    combined = "\n".join((skill, commands, safety))

    for required in (
        "supa.cc --version",
        "doctor --installation-check --json",
        "exit code",
        "stdout",
        "stderr",
        "hidden prompt",
        "never invent",
        "do not retry",
        "explicit confirmation",
        "--yes",
        "interactive",
    ):
        assert required in combined

    assert "prefer deterministic subcommands" in skill
    assert "do not ask for a pat in chat" in skill
    assert "do not pass a pat through stdin" in skill
    assert "do not repeat the preflight" in skill
    assert "confirm replacing that exact alias" in skill
    assert "authorizes that add or switch" in skill
    assert "cannot present the built-in confirmation" in skill


def test_skill_preserves_native_credential_store_and_diagnostic_guards():
    contents = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (SKILL_PATH, SAFETY_PATH)
    )

    for required in (
        "Keychain",
        "Secret Service",
        "Windows Credential Manager",
        "WinVaultKeyring",
        "keyrings.alt",
        "plaintext",
        "SUPABASE_ACCESS_TOKEN",
        "doctor --json",
        "--account <name> --live",
    ):
        assert required in contents
    assert "does not read a PAT" in contents


def test_openai_metadata_is_minimal_and_keeps_implicit_invocation_enabled():
    metadata = yaml.safe_load(OPENAI_METADATA_PATH.read_text(encoding="utf-8"))

    assert set(metadata) == {"interface", "policy"}
    assert set(metadata["interface"]) == {
        "display_name",
        "short_description",
        "default_prompt",
    }
    assert metadata["policy"] == {"allow_implicit_invocation": True}
    assert "dependencies" not in metadata


def test_agent_installation_document_covers_each_supported_harness():
    documentation = Path("docs/agent-skill.md").read_text(encoding="utf-8")

    headings = ("OpenCode", "Codex", "Cursor", "Claude Code")
    sections = {}
    for index, heading in enumerate(headings):
        assert re.search(rf"^## {re.escape(heading)}$", documentation, re.MULTILINE)
        start = documentation.index(f"## {heading}")
        next_start = (
            documentation.index(f"## {headings[index + 1]}")
            if index + 1 < len(headings)
            else documentation.index("## Credential and interaction limitation")
        )
        sections[heading] = documentation[start:next_start]

    expected_install_and_verification = {
        "OpenCode": ("~/.agents/skills/supa-cc", "skill` tool"),
        "Codex": ("$CODEX_HOME/skills/supa-cc", "/skills"),
        "Cursor": (".cursor/skills/supa-cc", "type `/`"),
        "Claude Code": ("~/.claude/skills/supa-cc", "/supa-cc"),
    }
    for heading, required_phrases in expected_install_and_verification.items():
        for phrase in required_phrases:
            assert phrase in sections[heading]

    for path in (
        ".agents/skills/supa-cc",
        "~/.agents/skills/supa-cc",
        "$CODEX_HOME/skills/supa-cc",
        ".cursor/skills/supa-cc",
        ".claude/skills/supa-cc",
    ):
        assert path in documentation
    for limitation in (
        "2.1.203",
        "does not install the skill",
        "GitHub installation",
        "skill tool is disabled",
        "hidden prompt",
    ):
        assert limitation in documentation

    lifecycle = documentation[documentation.index("## Update and uninstall") :]
    for heading in headings:
        assert f"| {heading} |" in lifecycle
    for action in ("update", "uninstall"):
        assert action in lifecycle.lower()


def test_canonical_docs_link_to_agent_skill_installation_and_usage():
    readme = Path("README.md").read_text(encoding="utf-8")
    installation = Path("docs/installation.md").read_text(encoding="utf-8")
    usage = Path("docs/usage.md").read_text(encoding="utf-8")

    assert "docs/agent-skill.md" in readme
    assert "agent-skill.md" in installation
    assert "agent-skill.md" in usage
    assert "coding agent" in usage.lower()
