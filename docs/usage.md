# Usage

## First use with the TUI

Create a Personal Access Token on the [official Supabase token page](https://supabase.com/dashboard/account/tokens). Do not put the PAT in commands, files, logs, or reports.

Open the interactive interface:

```bash
supa.cc
```

The home keeps only the compact brand banner, account count, active-account state, and the four useful actions: Add, Switch, Remove, and Exit. Switch and Remove present the account list when needed, avoiding a separate list-only screen. Arrow-key navigation and the existing green visual identity are preserved; smaller terminals receive the compact banner automatically.

During an interactive session, the banner and application title stay fixed. Menus, forms, account state, and feedback messages reuse the same area below that frame, so navigating back to the home does not append another interface to the terminal. Exiting leaves one final Supa.cc frame with the goodbye message.

1. Choose **Add account**, enter a local name, and provide the PAT in the hidden prompt. The name must contain 1 to 50 ASCII letters, numbers, underscores, or hyphens (`[a-zA-Z0-9_-]{1,50}`).
2. Choose **Switch active account** and select the registered account.
3. Verify the activated session:

```bash
supabase projects list
```

Activation validates the PAT, asks the Supabase CLI to synchronize the official `supabase` profile, removes the PAT from the verification environment, and confirms that the CLI can recover its own persisted session. Only then does Supa.cc record the active account. Supa.cc treats the CLI credential format and identifiers as private implementation details. If activation fails, follow [Troubleshooting](troubleshooting.md); see [Security](security.md) for guarantees and limits.

## Workflows

### Manage accounts

```bash
supa.cc add <name>
supa.cc list
supa.cc switch <name>
supa.cc remove <name>
supa.cc remove <name> --yes
```

`add` requests the PAT in a hidden prompt and validates it before storing it. `list` shows names only and never opens the credential store. If a listed alias has lost its PAT, `switch` explains that the credential was removed, requests a replacement in a hidden prompt, validates it, and continues without requiring the alias to be recreated. `remove` asks for confirmation except with `--yes`; removing the active account also ends its associated official session.

To intentionally remove every known Supa.cc PAT and all Supa.cc local state:

```bash
supa.cc reset --all
supa.cc reset --all --yes
```

The first form confirms interactively. The command does not change projects, databases, project configuration, or remote resources. Uninstalling the package does not remove credentials automatically.

### Use the active account

After `switch`, use the Supabase CLI normally. For an optional isolated execution without changing arguments:

```bash
supa.cc run -- projects list
```

### Diagnose

```bash
supa.cc doctor
supa.cc doctor --json
supa.cc doctor --installation-check
supa.cc doctor --installation-check --json
supa.cc doctor --account <name> --live
```

The first two commands are non-live and do not open a token or native credential store. Their standard human and JSON output omits the account name and sanitizes local paths. The explicit installation check runs `supabase --version` once and performs one isolated credential-store probe without reading an account or PAT; its `supabase_cli` object adds `minimum_version` and `compatibility` (`compatible`, `missing`, `incompatible`, `blocked`, or `not_checked`). It cannot be combined with `--live` or `--account`. `--live` requires `--account` and authorizes reading and online validation of the selected credential. See [platform remediation](troubleshooting.md#macos) before manually inspecting any storage.

## Commands

| Command | Purpose |
| --- | --- |
| `supa.cc` | Open the TUI |
| `supa.cc add <name>` | Add or update an account |
| `supa.cc list` | List registered names |
| `supa.cc switch <name>` | Validate and activate an account |
| `supa.cc remove <name> [--yes]` | Remove an account |
| `supa.cc reset --all [--yes]` | Intentionally clear all Supa.cc accounts, PATs, and local state |
| `supa.cc run -- <arguments>` | Run the Supabase CLI with the active account |
| `supa.cc doctor [--json]` | Generate a local non-live diagnostic |
| `supa.cc doctor --installation-check [--json]` | Validate the CLI and native credential-store availability without reading an account |
| `supa.cc doctor --account <name> --live` | Authorize an authenticated diagnostic |
| `supa.cc --version` | Show the version and sanitized installation channel |
| `supa.cc version` | Show the installed version, installation channel, and deterministic official update guidance, without network access |

Installation, upgrades, and uninstallation are covered in the [installation guide](installation.md).
