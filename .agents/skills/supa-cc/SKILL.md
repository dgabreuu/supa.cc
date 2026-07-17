---
name: supa-cc
description: Use when a user wants to manage Supabase accounts with Supa.cc, switch authentication, diagnose a Supa.cc installation, or run the Supabase CLI with the active account.
---

# Operating Supa.cc

Translate the user's intent into the smallest safe `supa.cc` subcommand. Prefer deterministic subcommands to the interactive TUI when acting through a coding agent.

## Start safely

1. Run `supa.cc --version` when availability is unknown. Do not repeat the preflight within the same task after it succeeds.
2. If installation health matters, run `supa.cc doctor --installation-check --json`.
3. Read [the command reference](references/commands.md) before choosing flags or forwarding Supabase CLI arguments.
4. Read [safety and error handling](references/safety-and-errors.md) before credentials, mutation, diagnostics, or remediation are involved.

Do not inspect native credential stores, Supabase CLI credential files, complete environments, or local state files to reconstruct an answer.

## Select the operation

| User intent | Action |
| --- | --- |
| List saved account aliases | `supa.cc list` |
| Add or replace an account | `supa.cc add <name>` |
| Activate an account | `supa.cc switch <name>` |
| Remove one account | `supa.cc remove <name>` |
| Remove all Supa.cc state | `supa.cc reset --all` |
| Check local health | `supa.cc doctor --json` |
| Check installation dependencies | `supa.cc doctor --installation-check --json` |
| Validate one credential online | `supa.cc doctor --account <name> --live` |
| Run the Supabase CLI with the active account | `supa.cc run -- <arguments>` |
| Show version and update guidance | `supa.cc version` |

Never invent an account name, project reference, Supabase subcommand, flag, or other required value. Discover account aliases with `supa.cc list` when that is sufficient; otherwise ask the user for the missing value.

## Handle credentials

PAT entry belongs exclusively in Supa.cc's hidden prompt. Do not ask for a PAT in chat. Do not place a PAT in command arguments, tool input, source code, files, logs, or messages. Do not pass a PAT through stdin controlled by the agent.

For `add`, and for `switch` when an orphaned alias needs reauthorization, start the command only when the harness can present an interactive hidden prompt directly to the user. If it cannot, stop only the credential-requiring step and explain that the user must enter the PAT in a secure Supa.cc prompt. Continue any safe, non-credential work.

Accepted tokens begin with `sbp_` or `sbp_oauth_`; Supa.cc validates the remaining `[0-9a-f]{40}` body. Never fabricate an example matching that shape.

## Confirm mutations

Treat `add`, `switch`, `remove`, `reset`, and potentially destructive commands forwarded through `run` as mutations.

- A request naming a new alias, or the user's selection of an alias to activate, authorizes that add or switch operation. If `supa.cc list` shows that an `add` alias already exists, explain that its credential may be replaced and confirm replacing that exact alias.
- Obtain explicit confirmation before `remove`, `reset`, or a destructive Supabase command.
- Prefer the built-in confirmation for `remove` and `reset`. Use `--yes` only after the user explicitly confirmed the exact operation and scope in the current conversation and the harness cannot present the built-in confirmation.
- Do not retry a mutation automatically after a nonzero exit code or uncertain result.
- Do not infer authorization for a broader operation from a narrower request.

## Interpret results

Check the exit code before reporting success. Use stdout as the command result and stderr as diagnostic context; keep both sanitized. For JSON diagnostics, parse the report and use its `ok`, status, compatibility, and remediation fields instead of guessing from prose.

A zero exit code is necessary for success. On a nonzero exit code, report the safe message and recommended next action. Do not expose tracebacks, hidden input, credential-store contents, or inherited environment values.

## Common mistakes

- Opening the TUI when a direct subcommand represents the request.
- Asking the user to paste a PAT into chat because an interactive tool is unavailable.
- Guessing the only account from context instead of using `list` or asking.
- Treating `doctor` as proof that credentials are usable; only explicit live mode reads and validates an account.
- Omitting `--` before forwarded Supabase CLI arguments.
- Using `--yes` to avoid an approval boundary.
