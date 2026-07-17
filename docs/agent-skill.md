# Coding agent skill

The portable Supa.cc skill lets a coding agent translate natural-language account, diagnostic, and authenticated Supabase CLI requests into safe `supa.cc` commands. Installing the Python package does not install the skill; install it separately for every agent that does not share the same skill directory.

The canonical source is [`.agents/skills/supa-cc`](../.agents/skills/supa-cc/SKILL.md). OpenCode, Codex, and Cursor recognize the neutral `.agents/skills` convention. Claude Code uses `.claude/skills`.

## Agent-led installation

Give the coding agent this prompt from a trusted project:

> Install the `supa-cc` skill from the official `dgabreuu/supa.cc` GitHub repository for your user account. Use that agent's documented user-level skill directory, install the complete `.agents/skills/supa-cc` directory without changing its files, verify that the agent discovers it, and report the installed path and verification result. Do not install a marketplace plugin or change the Supa.cc CLI.

The agent should review the repository and destination before writing outside the project. A copied installation is a snapshot; repeat the installation to update it. A supported directory symlink keeps one checkout as the update source, but should be used only where the agent and operating system document support.

For a manual, auditable copy from an existing repository checkout on macOS or Linux:

```bash
mkdir -p ~/.agents/skills
cp -R .agents/skills/supa-cc ~/.agents/skills/supa-cc
```

PowerShell equivalent:

```powershell
New-Item -ItemType Directory -Force "$HOME\.agents\skills"
Copy-Item -Recurse ".agents\skills\supa-cc" "$HOME\.agents\skills\supa-cc"
```

These examples target the shared `.agents` path. Use the agent-specific destination below when required. Review an existing destination before replacing it.

## OpenCode

OpenCode discovers project skills at `.agents/skills/supa-cc` and user skills at `~/.agents/skills/supa-cc`. The checked-out Supa.cc repository therefore needs no additional project configuration.

After a user-level copy, restart OpenCode if the new top-level skill directory is not detected. Ask OpenCode to use its `skill` tool to list available skills and load `supa-cc`, then ask it to explain which command handles a local installation check.

If the skill is absent, confirm the filename is exactly `SKILL.md`, its parent directory is `supa-cc`, and check whether the skill tool is disabled globally or for the selected agent. OpenCode permissions can hide the tool and all available skill metadata.

## Codex

Codex discovers `.agents/skills/supa-cc` from the working directory through the repository root and `~/.agents/skills/supa-cc` for the user. The bundled `agents/openai.yaml` supplies Codex interface metadata without adding tool dependencies.

The preferred agent-led request uses the built-in installer:

> Use `$skill-installer` to install the skill from repository `dgabreuu/supa.cc`, path `.agents/skills/supa-cc`, then verify it appears in `/skills` as `$supa-cc`.

The bundled installer copies repository skills into `$CODEX_HOME/skills/supa-cc` (normally `~/.codex/skills/supa-cc`) and makes the skill available on the next turn. The neutral manual-discovery location remains `~/.agents/skills/supa-cc`. The installer will not overwrite an existing destination; review, remove, or rename the old installation explicitly before reinstalling. Restart Codex if discovery remains stale.

Verify with `/skills` or by mentioning `$supa-cc`, then ask: “Use Supa.cc to check whether my installation is healthy.” The skill should select `supa.cc doctor --installation-check --json`.

## Cursor

Cursor discovers `.agents/skills/supa-cc` and `.cursor/skills/supa-cc` in a project. For user-level installation, use `~/.agents/skills/supa-cc` or `~/.cursor/skills/supa-cc`.

Recent Cursor IDE releases can offer GitHub installation through the Skills or Customize settings. When **Add from GitHub** is available, give it the official `https://github.com/dgabreuu/supa.cc` repository and select `.agents/skills/supa-cc`, then review the locally installed files. Availability and labels vary by Cursor version and surface; the `cursor-agent` CLI may not expose the same installation UI.

If that flow is unavailable, ask Cursor's agent to fetch the official repository, review the source, and copy the complete skill directory to one of the paths above. No `.cursor-plugin` manifest or marketplace installation is required for this integration. In every flow, Cursor ultimately discovers a local `SKILL.md`; do not treat an unreviewed remote page as live instructions.

Restart Cursor or reload its window if a newly created top-level skills directory does not appear. Open Agent chat, type `/`, search for `supa-cc`, and invoke it. Also test implicit discovery by asking Cursor to list Supa.cc account aliases.

## Claude Code

Claude Code discovers project skills at `.claude/skills/supa-cc` and personal skills at `~/.claude/skills/supa-cc`; it does not discover the canonical `.agents` path directly.

Copy the complete canonical directory to the Claude destination:

```bash
mkdir -p ~/.claude/skills
cp -R .agents/skills/supa-cc ~/.claude/skills/supa-cc
```

Claude Code 2.1.203 or newer can instead follow a symlink whose entry is `~/.claude/skills/supa-cc`. Older versions require a copy or an upgrade. On Windows, prefer the copy unless the installed Claude Code version and filesystem configuration explicitly support the chosen link type.

Run `/supa-cc` to verify explicit discovery, then ask Claude to list registered Supa.cc accounts to verify the skill chooses `supa.cc list`. Restart Claude Code if the skills directory was created after the session began and live detection does not register it.

## Credential and interaction limitation

Account creation and orphaned-alias reauthorization require the user to enter a PAT in Supa.cc's hidden prompt. The agent must never request that PAT in chat or pass it through arguments, files, logs, or agent-controlled stdin. If an agent cannot present an interactive hidden prompt, it can complete non-credential operations but must stop the credential-entry step and explain the limitation.

Installing the skill does not install or upgrade `supa.cc`, the official Supabase CLI, or a native credential-store service. Follow [Installation](installation.md) for those prerequisites.

## Update and uninstall

To update a copied skill, ask the agent to fetch a fresh official checkout, compare `.agents/skills/supa-cc` with the installed directory, and replace only that installed skill after review. For a symlinked installation, update the trusted checkout with a fast-forward-only pull and verify discovery again.

To uninstall, remove only the installed `supa-cc` skill directory or symlink from the agent's user-level skills directory. This does not uninstall the CLI and does not delete Supa.cc accounts, PATs, local state, or remote Supabase resources.

| Agent | User-level installation | Update and uninstall verification |
| --- | --- | --- |
| OpenCode | `~/.agents/skills/supa-cc` | Replace or remove only that reviewed copy, restart if needed, and check the `skill` tool again. |
| Codex | `$CODEX_HOME/skills/supa-cc` from `$skill-installer`, or `~/.agents/skills/supa-cc` for neutral discovery | Compare and replace the chosen destination; because the installer does not overwrite, remove or rename its old copy only after review. Verify with `/skills`. |
| Cursor | `~/.cursor/skills/supa-cc` or `~/.agents/skills/supa-cc` | Use Cursor's GitHub-managed update or uninstall control when present; otherwise replace or remove only the local copy. Verify from the `/` skill list. |
| Claude Code | `~/.claude/skills/supa-cc` | Replace the copied directory, or update the trusted target of a supported symlink; remove only that entry to uninstall. Verify with `/supa-cc`. |

## Compatibility sources

The structure and paths follow the [Agent Skills specification](https://agentskills.io/specification), [OpenCode Agent Skills](https://opencode.ai/docs/skills/), [Claude Code skills](https://code.claude.com/docs/en/slash-commands), [Codex skills](https://learn.chatgpt.com/docs/build-skills), and [Cursor Agent Skills](https://cursor.com/docs/skills).

Limitations are intentional: this repository does not publish a Claude, Codex, Cursor, or OpenCode marketplace plugin; skill installation remains local; and product policy can disable skill discovery or command execution.
