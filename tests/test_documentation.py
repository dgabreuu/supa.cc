import itertools
from pathlib import Path
import re
import unicodedata
from urllib.parse import unquote, urlsplit


CANONICAL_DOCS = (
    Path("docs/installation.md"),
    Path("docs/usage.md"),
    Path("docs/troubleshooting.md"),
    Path("docs/security.md"),
)

RETIRED_DOCUMENTATION = (
    Path("docs/getting-started.md"),
    Path("docs/branding.md"),
    Path("docs/license-pt-BR.md"),
    Path("assets/logo.svg"),
)


def _section(markdown: str, heading: str) -> str:
    headings = list(re.finditer(r"^(#{2,6})\s+(.+?)\s*$", markdown, re.MULTILINE))
    selected = next(
        (
            item
            for item in headings
            if re.search(rf"\b{re.escape(heading)}\b", item.group(2), re.IGNORECASE)
        ),
        None,
    )
    assert selected, f"missing documentation section for {heading}"

    level = len(selected.group(1))
    end = next(
        (
            item.start()
            for item in headings
            if item.start() > selected.start() and len(item.group(1)) <= level
        ),
        len(markdown),
    )
    return markdown[selected.end() : end]


def _stable_content(section: str) -> str:
    development_heading = re.compile(
        r"^(#{3,6})\s+.*\b(?:desenvolvimento|development|branch|head)\b.*$",
        re.IGNORECASE | re.MULTILINE,
    )
    while match := development_heading.search(section):
        level = len(match.group(1))
        following = re.search(
            rf"^#{{1,{level}}}\s+",
            section[match.end() :],
            re.MULTILINE,
        )
        end = match.end() + following.start() if following else len(section)
        section = section[: match.start()] + section[end:]
    return section


def _has_command(markdown: str, command: str) -> bool:
    prompt = r"(?:\$|PS>|>)?\s*"
    return bool(
        re.search(
            rf"^{prompt}{re.escape(command)}\s*$",
            markdown,
            re.MULTILINE | re.IGNORECASE,
        )
    )


def _markdown_link_targets(markdown: str) -> set[str]:
    inline = re.findall(r"\[[^\]]+\]\(\s*<?([^\s)>]+)>?(?:\s+[^)]*)?\)", markdown)
    definitions = {
        name.casefold(): target
        for name, target in re.findall(
            r"^\s*\[([^\]]+)\]:\s*<?([^\s>]+)>?", markdown, re.MULTILINE
        )
    }
    references = re.findall(r"\[[^\]]+\]\[([^\]]+)\]", markdown)
    references.extend(re.findall(r"\[([^\]]+)\]\[\]", markdown))
    references.extend(
        name
        for name in definitions
        if re.search(rf"(?<!!)\[{re.escape(name)}\](?![\[(])", markdown, re.IGNORECASE)
    )
    referenced = [definitions[name.casefold()] for name in references if name.casefold() in definitions]
    html = re.findall(
        r"\b(?:href|src)\s*=\s*[\"']([^\"']+)[\"']",
        markdown,
        re.IGNORECASE,
    )
    return {target.split("#", 1)[0] for target in (*inline, *referenced, *html)}


def _contains_mutable_ref(markdown: str) -> bool:
    patterns = (
        r"--head\b",
        r"\bhead\b",
        r"\bbranch\s+`?[\"']?main\b",
        r"\bbranch\s*[:=]\s*[\"']?main\b",
        r"(?:@|refs/heads/|/tree/)main\b",
        r"/archive/(?:refs/heads/)?(?:main|head)(?:\b|[./])",
        r"\b(?:install\w*|installation)\s+from\s+(?:the\s+)?(?:main|default\s+branch)\b",
        r"\bdefault\s+branch\b",
    )
    if any(re.search(pattern, markdown, re.IGNORECASE) for pattern in patterns):
        return True

    git_urls = re.findall(r"git\+https://[^\s\"'`)]+", markdown, re.IGNORECASE)
    return any("@" not in url.rsplit("/", 1)[-1] for url in git_urls)


def _terms_share_context(markdown: str, terms: tuple[str, ...], limit: int = 500) -> bool:
    positions = []
    for term in terms:
        matches = [match.start() for match in re.finditer(term, markdown, re.IGNORECASE)]
        if not matches:
            return False
        positions.append(matches)

    return any(
        max(candidate) - min(candidate) <= limit
        for candidate in itertools.product(*positions)
    )


def _public_markdown() -> list[Path]:
    root_docs = list(Path(".").glob("*.md"))
    nested_docs = [
        path
        for path in Path("docs").rglob("*.md")
        if "superpowers" not in path.parts
    ]
    return sorted({*root_docs, *nested_docs})


def _github_heading_anchors(markdown: str) -> set[str]:
    anchors = set()
    occurrences: dict[str, int] = {}
    for heading in re.findall(r"^#{1,6}\s+(.+?)\s*#*\s*$", markdown, re.MULTILINE):
        normalized = unicodedata.normalize("NFC", heading).casefold()
        slug = "".join(
            character
            for character in normalized
            if not unicodedata.category(character).startswith(("P", "S"))
            or character == "-"
        ).replace(" ", "-")
        suffix = occurrences.get(slug, 0)
        occurrences[slug] = suffix + 1
        anchors.add(f"{slug}-{suffix}" if suffix else slug)
    return anchors


def test_required_canonical_documentation_exists():
    missing = [str(path) for path in CANONICAL_DOCS if not path.is_file()]

    assert not missing, f"missing canonical documentation: {', '.join(missing)}"


def test_public_documentation_internal_links_are_valid():
    violations = []
    inline_targets = re.compile(r"!?\[[^\]]*\]\(\s*<?([^\s)>]+)>?(?:\s+[^)]*)?\)")

    for document in _public_markdown():
        for raw_target in inline_targets.findall(document.read_text(encoding="utf-8")):
            parsed = urlsplit(raw_target)
            if parsed.scheme or parsed.netloc:
                continue

            relative_path = unquote(parsed.path)
            target = (document.parent / relative_path).resolve() if relative_path else document.resolve()
            if not target.exists():
                violations.append(f"{document}: missing target {raw_target}")
                continue

            if parsed.fragment and target.suffix.casefold() == ".md":
                fragment = unicodedata.normalize("NFC", unquote(parsed.fragment)).casefold()
                anchors = _github_heading_anchors(target.read_text(encoding="utf-8"))
                if fragment not in anchors:
                    violations.append(f"{document}: missing anchor {raw_target}")

    assert not violations, "\n".join(violations)


def test_readme_has_a_focused_public_overview():
    readme = Path("README.md").read_text(encoding="utf-8")
    headings = [
        heading.lower()
        for heading in re.findall(r"^##\s+(.+?)\s*$", readme, re.MULTILINE)
    ]

    for topic in ("install", "security", "licen"):
        assert any(topic in heading for heading in headings), (
            f"README must retain a {topic} section"
        )
    assert all(
        any(topic in heading for topic in ("install", "security", "licen"))
        for heading in headings
    ), "README sections must be limited to installation, security, and license"

    assert "|____/ \\__,_| .__/ \\__,_(_)___\\___|" in readme
    assert re.search(r"(?m)^\s+\|_\|\s*$", readme)
    assert "https://raw.githubusercontent.com/dgabreuu/supa.cc/main/assets/terminal.svg" in readme
    assert "assets/logo.svg" not in readme

    all_headings = "\n".join(
        re.findall(r"^#{1,6}\s+(.+?)\s*$", readme, re.MULTILINE)
    ).lower()
    for delegated_section in (
        "first use",
        "usage",
        "diagnostic",
        "documentation",
        "support",
        "development",
        "branding",
        "release",
    ):
        assert delegated_section not in all_headings

    for delegated_content in ("git clone", "SUPA_CC_RUN_", "tests/test_", "GitHub Issues"):
        assert delegated_content.lower() not in readme.lower()


def test_readme_does_not_duplicate_canonical_technical_details():
    readme = Path("README.md").read_text(encoding="utf-8").lower()
    delegated_details = (
        "accounts.json",
        "active-account",
        "session-sync",
        "mutation-aware",
        "rollback",
        "doctor --json",
        "doctor --account",
        "supabase projects list",
        "supa.cc run --",
        "supabase.accounts.v2",
    )

    for detail in delegated_details:
        assert detail not in readme, f"README duplicates canonical detail: {detail}"


def test_canonical_documents_own_technical_and_diagnostic_contracts():
    security = Path("docs/security.md").read_text(encoding="utf-8").lower()
    troubleshooting = Path("docs/troubleshooting.md").read_text(encoding="utf-8").lower()
    usage = Path("docs/usage.md").read_text(encoding="utf-8").lower()

    for detail in ("accounts.json", "active-account", "session-sync", "rollback", "mutation-aware"):
        assert detail in security, f"security guide must own technical detail: {detail}"
    assert "doctor --json" in security and "doctor --account" in security
    assert "non-live" in security and "do not open a token" in security

    for platform in ("macos", "linux", "windows"):
        assert re.search(rf"^##\s+{platform}\b", troubleshooting, re.MULTILINE)
    assert "doctor --json" in troubleshooting and "doctor --account" in troubleshooting
    assert "does not open a pat" in troubleshooting

    for command in ("supa.cc add", "supa.cc switch", "supa.cc run --", "supa.cc doctor"):
        assert command in usage, f"usage guide must own command: {command}"


def test_retired_documentation_is_absent_and_unlinked():
    public_docs = _public_markdown()
    violations = []

    for retired in RETIRED_DOCUMENTATION:
        if retired.exists():
            violations.append(f"retired asset exists: {retired}")
        for document in public_docs:
            contents = document.read_text(encoding="utf-8")
            targets = _markdown_link_targets(contents)
            references = (retired.as_posix().casefold(), retired.name.casefold())
            if any(
                reference in target.casefold()
                for target in targets
                for reference in references
            ):
                violations.append(f"{document} links to retired asset: {retired}")
            if any(reference in contents.casefold() for reference in references):
                violations.append(f"{document} contains retired path: {retired}")

    assert not violations, "\n".join(violations)


def test_installation_covers_each_platform_lifecycle():
    installation = Path("docs/installation.md").read_text(encoding="utf-8")

    for platform in ("macOS", "Linux", "Windows"):
        section = _section(installation, platform).lower()
        for lifecycle_term in ("install", "verif", "upgrad", "uninstall"):
            assert lifecycle_term in section, (
                f"{platform} installation section must cover {lifecycle_term}"
            )


def test_readme_stable_installation_uses_platform_bootstrap_commands():
    readme = _section(Path("README.md").read_text(encoding="utf-8"), "Installation")

    expected = {
        "macOS": "curl -fsSL https://raw.githubusercontent.com/dgabreuu/supa.cc/v0.5.4/install.sh | bash",
        "Linux": "curl -fsSL https://raw.githubusercontent.com/dgabreuu/supa.cc/v0.5.4/install.sh | bash",
        "Windows": "irm https://raw.githubusercontent.com/dgabreuu/supa.cc/v0.5.4/install.ps1 | iex",
    }
    for platform, command in expected.items():
        stable = _stable_content(_section(readme, platform))
        assert _has_command(stable, command), f"{platform} README install command must be exactly: {command}"
        assert not _contains_mutable_ref(stable), f"mutable ref in README {platform} stable section"

    manual_homebrew = (
        "brew tap dgabreuu/supa-cc https://github.com/dgabreuu/supa.cc.git",
        "brew install supabase/tap/supabase",
        "brew install dgabreuu/supa-cc/supa-cc",
    )
    assert not any(command in readme for command in manual_homebrew)


def test_readme_restores_emoji_heading_hierarchy():
    readme = Path("README.md").read_text(encoding="utf-8")

    for heading in (
        "## 📦 Installation",
        "## 🔐 Security",
        "## 📄 License",
        "### 🍎 macOS",
        "### 🐧 Linux",
        "### 🪟 Windows",
    ):
        assert heading in readme


def test_release_docs_record_all_publication_channels():
    readme = Path("README.md").read_text(encoding="utf-8")
    installation = Path("docs/installation.md").read_text(encoding="utf-8")
    release = Path("docs/release.md").read_text(encoding="utf-8")

    assert "the channels below are planned for the release" not in readme
    assert "do not mean that version 0.3.0 has already been published" not in installation
    assert "Version 0.5.0 has not been published yet." not in release
    assert "Homebrew has not been verified yet" not in release
    assert "v0.5.0" in release
    assert "https://github.com/dgabreuu/supa.cc/actions/runs/29432932472" in release
    assert "https://github.com/dgabreuu/supa.cc/actions/runs/29434531777" in release
    assert "continua não lançada" not in release
    assert "deve permanecer em `v0.2.0`" not in release


def test_stable_installation_uses_exact_lifecycle_commands():
    installation = Path("docs/installation.md").read_text(encoding="utf-8")
    expected = {
        "macOS": (
            "brew install supabase/tap/supabase",
            "brew install dgabreuu/supa-cc/supa-cc",
            "brew upgrade dgabreuu/supa-cc/supa-cc",
            "brew uninstall supa-cc",
        ),
        "Linux": ("pipx install supa.cc", "pipx upgrade supa.cc", "pipx uninstall supa.cc"),
        "Windows": ("pipx install supa.cc", "pipx upgrade supa.cc", "pipx uninstall supa.cc"),
    }

    for platform, commands in expected.items():
        stable = _stable_content(_section(installation, platform))
        for command in (*commands, "supa.cc --version"):
            assert _has_command(stable, command), f"{platform} command must be exactly: {command}"


def test_platform_lifecycle_commands_use_separately_labeled_blocks():
    installation = Path("docs/installation.md").read_text(encoding="utf-8")

    for platform in ("macOS", "Linux", "Windows"):
        stable = _stable_content(_section(installation, platform))
        headings = re.findall(r"^####\s+(.+)$", stable, re.MULTILINE)
        for label in ("Install", "Verify", "Upgrade", "Uninstall"):
            assert any(label.lower() == heading.lower() for heading in headings), (
                f"{platform} must label {label} separately"
            )


def test_security_claims_distinguish_posix_checks_from_windows_guarantees():
    security = Path("docs/security.md").read_text(encoding="utf-8").lower()
    skill = Path("SKILL.md").read_text(encoding="utf-8").lower()

    assert "linux" in security and "open descriptor" in security
    assert "macos" in security and "executes the validated path" in security
    assert "owned by the user or root" in security
    assert "windows" in security and "before process creation" in security
    assert "path" in security and "descriptor" in security
    assert "%appdata%" in security and "inherit" in security
    assert "does not create a private acl" in security
    assert "impose posix modes" in security
    assert not re.search(r"windows[^\n]+private[^\n]+current user", security)
    for document in (security, skill):
        assert not re.search(
            r"windows[^\n]+(?:preserva|garante)[^\n]+identidade[^\n]+execução",
            document,
        )


def test_stable_installation_does_not_use_mutable_repository_revisions():
    documents = (Path("README.md"), Path("docs/installation.md"))

    for path in documents:
        installation = _section(path.read_text(encoding="utf-8"), "Installation")
        for platform in ("macOS", "Linux", "Windows"):
            stable = _stable_content(_section(installation, platform)).lower()
            assert not _contains_mutable_ref(stable), (
                f"mutable branch/main/HEAD ref in {path} {platform} stable section"
            )


def test_usage_promotes_tui_before_advanced_commands():
    usage = Path("docs/usage.md").read_text(encoding="utf-8")
    command_prefix = r"(?:^\s*(?:\$|PS>|>)?\s*|`)"
    command_suffix = r"(?:\s*$|`)"
    bare_tui = re.search(rf"{command_prefix}supa\.cc{command_suffix}", usage, re.MULTILINE)
    advanced = re.search(
        rf"{command_prefix}supa\.cc\s+(?:add|list|switch|run|doctor|remove|version)\b",
        usage,
        re.MULTILINE,
    )

    assert bare_tui, "usage guide must show the bare supa.cc TUI command"
    assert advanced, "usage guide must retain discoverable advanced commands"
    assert bare_tui.start() < advanced.start(), "TUI must precede advanced commands"


def test_usage_documents_account_names_and_version_update_check():
    usage = Path("docs/usage.md").read_text(encoding="utf-8")

    assert "[a-zA-Z0-9_-]{1,50}" in usage
    assert re.search(r"version.{0,100}update", usage, re.IGNORECASE | re.DOTALL)


def test_troubleshooting_owns_safe_reinstallation_guidance():
    troubleshooting = Path("docs/troubleshooting.md").read_text(encoding="utf-8")
    reinstall = _section(troubleshooting, "Safe reinstallation").lower()

    for detail in ("provenance", "version", "homebrew", "pipx", "editable"):
        assert detail in reinstall
    assert "not" in reinstall and "simult" in reinstall
    assert "preserv" in reinstall and "state" in reinstall and "diagnostic" in reinstall
    assert "not" in reinstall and "native credentials" in reinstall


def test_installation_links_directly_to_safe_reinstallation():
    installation = Path("docs/installation.md").read_text(encoding="utf-8")

    assert "(troubleshooting.md#safe-reinstallation)" in installation


def test_macos_keychain_configuration_remediation_is_explicit_and_safe():
    troubleshooting = Path("docs/troubleshooting.md").read_text(encoding="utf-8")
    security = Path("docs/security.md").read_text(encoding="utf-8")

    assert "keychain_configuration_invalid" in troubleshooting
    assert "Reset to Defaults" in troubleshooting
    assert "does not change the default Keychain" in troubleshooting
    assert "default-keychain -d user" in troubleshooting
    assert "list-keychains -d user" in troubleshooting
    assert "does not enumerate Keychain items" in security


def test_stable_installation_is_not_described_as_a_development_wheel():
    installation = Path("docs/installation.md").read_text(encoding="utf-8")
    usage = Path("docs/usage.md").read_text(encoding="utf-8")

    assert "0.5.0.dev1" not in installation
    assert "Development wheel" not in installation
    assert "installation channel" in usage.lower()


def test_skill_names_every_supported_native_credential_backend():
    skill = Path("SKILL.md").read_text(encoding="utf-8")
    mappings = {
        "macOS": (r"\bmacOS\b", r"\bKeychain\b"),
        "Linux": (r"\bLinux\b", r"\bSecret Service\b"),
        "Windows": (
            r"\bWindows\b",
            r"\bWindows Credential Manager\b",
            r"\bWinVaultKeyring\b",
        ),
    }

    for platform, terms in mappings.items():
        assert _terms_share_context(skill, terms), (
            f"SKILL must map {platform} to {', '.join(terms[1:])} "
            "within the same bounded section-level context"
        )


def test_public_documentation_has_no_placeholders_or_local_workspace_paths():
    forbidden = (
        re.compile(
            r"\bTBD\b|\bTODO\b(?=\s*(?::|-|$)|\s+"
            r"(?:item|later|here|pending|add|update|document|write|fix|finish|"
            r"complete|replace|decide|fill|this)\b)",
            re.IGNORECASE | re.MULTILINE,
        ),
        re.compile(r"/(?:home|Users|workspace|workspaces|tmp|var/tmp)/[^\s)`]+", re.IGNORECASE),
        re.compile(r"/(?:private/var/folders|root)/[^\s)`]+", re.IGNORECASE),
        re.compile(
            r"(?:[A-Za-z]:[/\\]|/mnt/[a-z]/)Users[/\\][^\s)`]+",
            re.IGNORECASE,
        ),
    )

    for path in _public_markdown():
        contents = path.read_text(encoding="utf-8")
        for pattern in forbidden:
            assert not pattern.search(contents), f"unsafe content in {path}: {pattern.pattern}"


def test_public_documentation_has_no_credential_like_pat_examples():
    credential_like_pat = re.compile(
        r"sbp_oauth_[A-Za-z0-9_-]{8,}"
        r"|sbp_(?!oauth_(?:\W|$))[A-Za-z0-9_-]{8,}"
    )

    for path in _public_markdown():
        contents = path.read_text(encoding="utf-8")
        assert not credential_like_pat.search(contents), (
            f"credential-like PAT example found in {path}"
        )
