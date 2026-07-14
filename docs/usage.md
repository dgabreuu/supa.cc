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

`add` requests the PAT in a hidden prompt. `list` shows names only, even when a credential later proves unavailable. `switch` checks index consistency, retrieves the selected PAT from native storage, validates it, and activates the account. `remove` asks for confirmation except with `--yes`; removing the active account also ends its associated official session.

### Use the active account

After `switch`, use the Supabase CLI normally. For an optional isolated execution without changing arguments:

```bash
supa.cc run -- projects list
```

### Diagnose

```bash
supa.cc doctor
supa.cc doctor --json
supa.cc doctor --account <name> --live
```

The first two commands are non-live and do not open a token. Their standard human and JSON output omits the account name and sanitizes local paths. In JSON, `active_account` is an object with the booleans `selected` and `indexed`; executable path objects include `path_relation`. `--live` requires `--account` and authorizes reading and online validation of the selected credential. See [platform remediation](troubleshooting.md#macos) before manually inspecting any storage.

## Commands

| Command | Purpose |
| --- | --- |
| `supa.cc` | Open the TUI |
| `supa.cc add <name>` | Add or update an account |
| `supa.cc list` | List registered names |
| `supa.cc switch <name>` | Validate and activate an account |
| `supa.cc remove <name> [--yes]` | Remove an account |
| `supa.cc run -- <arguments>` | Run the Supabase CLI with the active account |
| `supa.cc doctor [--json]` | Generate a local non-live diagnostic |
| `supa.cc doctor --account <name> --live` | Authorize an authenticated diagnostic |
| `supa.cc --version` | Show the version |
| `supa.cc version` | Show the installed version and deterministic official update guidance, without network access |

Installation, upgrades, and uninstallation are covered in the [installation guide](installation.md).
