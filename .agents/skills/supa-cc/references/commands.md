# Supa.cc command reference

Use these exact public forms. Run `supa.cc <command> --help` when a future installed version differs from this reference. Always interpret the process exit code before stdout or stderr.

## Inspection and diagnostics

| Command | Inputs and effect | Success |
| --- | --- | --- |
| `supa.cc --version` | No input. Prints the installed version and sanitized installation channel without a network request. | Exit code `0`; both lines are present. |
| `supa.cc version` | No input. Prints version, channel, and deterministic official update guidance. | Exit code `0`; output includes `Update:`. |
| `supa.cc list` | No input. Lists aliases without opening the native credential store. | Exit code `0`; aliases or `No accounts registered.` appear on stdout. |
| `supa.cc doctor [--json]` | Local, non-live diagnostics. It does not read a PAT or prove credential-store availability. | Exit code `0` only when the report is healthy. With `--json`, parse the JSON report. |
| `supa.cc doctor --installation-check [--json]` | Validates installation dependencies only: the supported environment, Supabase CLI compatibility, a writable Supabase CLI operational directory (`SUPABASE_HOME` or its default), and one isolated native credential-store probe with random identifiers. It does not read an account or PAT. | Exit code `0` when requirements are available and compatible. |
| `supa.cc doctor --account <name> --live` | Requires an exact registered alias and explicit authorization for online credential validation. | Exit code `0` when the selected credential validates. |

`--installation-check` cannot be combined with `--account` or `--live`. It does not load, create, migrate, validate, or recover account state; account, index, and activation fields outside its scope are `not_checked` or **not checked**. Live mode requires `--account <name>`.

`sync_pending` belongs to normal `doctor` consistency diagnostics. Recover it by rerunning the appropriate mutating Supa.cc account command, such as `switch` or `remove`; never edit the state document or native credentials manually.

## Account mutations

| Command | Required input and effect | Agent rule |
| --- | --- | --- |
| `supa.cc add <name>` | Requires a 1–50 character alias using ASCII letters, numbers, `_`, or `-`; then requests the PAT in a hidden prompt. Adds or replaces the alias after validation. | List aliases first. If the alias exists, confirm replacing its credential. Never accept the PAT through chat, arguments, files, or agent-controlled stdin. |
| `supa.cc switch <name>` | Requires an exact alias. Validates and activates it; an orphaned alias may request a replacement PAT in a hidden prompt. | Use `supa.cc list` or ask when the alias is missing. Do not choose for the user. |
| `supa.cc remove <name> [--yes]` | Requires an exact alias and removes its Supa.cc credential and related active session after confirmation. | Prefer the built-in confirmation. Use `--yes` only after explicit confirmation of the alias. |
| `supa.cc reset --all [--yes]` | `--all` is mandatory. Removes all Supa.cc aliases, PATs, and local session intent; it does not delete Supabase projects or remote resources. | Confirm the complete scope. Never infer consent from uninstall or cleanup wording. |

Do not retry these commands automatically after failure. A partial or uncertain result requires reporting the error and following documented remediation.

## Supabase CLI execution

Use `supa.cc run -- <arguments>` to run the official Supabase CLI with the active account. At least one Supabase CLI argument is required. The separator `--` prevents Supa.cc from consuming forwarded options.

Example without credentials:

```bash
supa.cc run -- projects list
```

The child process receives the PAT only through `SUPABASE_ACCESS_TOKEN` in its controlled environment; it never belongs in argv. Apply the normal approval policy for the forwarded command. Listing projects is read-only; database pushes, function deployments, project mutations, and destructive database commands require the corresponding explicit authorization.

## Interactive TUI

Running bare `supa.cc` opens the TUI. Use it only when the user specifically asks for the interactive interface or when direct subcommands cannot express the requested workflow. Coding agents should otherwise use the deterministic commands above.
