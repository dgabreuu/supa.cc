# Safety and error handling

## Credential boundary

Supa.cc accepts PATs only through its hidden prompt and stores them only in the platform-native backend:

- macOS: Keychain, service `supa.cc.supabase.accounts.v2`.
- Linux: Secret Service on the user D-Bus, service `supa.cc.supabase.accounts.v2`.
- Windows: Windows Credential Manager through `WinVaultKeyring`, service `supa.cc.supabase.accounts.v2`.

Canonical identities: `macOS: Keychain service supa.cc.supabase.accounts.v2`; `Linux: Secret Service supa.cc.supabase.accounts.v2`; `Windows: Windows Credential Manager (WinVaultKeyring) service supa.cc.supabase.accounts.v2`.

Never enable plaintext storage, `keyrings.alt`, or an unsupported backend. Never read, enumerate, export, repair, or delete native credential-store items directly. Do not inspect the Supabase CLI credential representation; treat it as opaque.

The PAT reaches the official Supabase CLI only through `SUPABASE_ACCESS_TOKEN` in a controlled child environment. Do not put it in argv, logs, complete environment dumps, fixtures, prompts, or transcripts.

## Operation classes

Read-only operations:

- `supa.cc --version`
- `supa.cc version`
- `supa.cc list`
- `supa.cc doctor`
- `supa.cc doctor --json`
- `supa.cc doctor --installation-check [--json]`

Credential-reading or mutating operations:

- `add`, `switch`, `remove`, and `reset`
- `doctor --account <name> --live`
- `run`, according to the forwarded Supabase CLI command

Default `doctor` and `doctor --json` are non-live: each does not read a PAT or open an account credential. Installation check performs an isolated backend availability probe but does not read an account. Only `doctor --account <name> --live` authorizes reading and validating that credential online.

## Result handling

1. Check the exit code. `0` means the requested command completed; any nonzero value is a failure.
2. Read stdout for results and stderr for safe diagnostic text.
3. With `--json`, parse the JSON instead of matching human prose.
4. Report only the sanitized public failure message and the next safe action.
5. Do not retry a mutation automatically. Re-run only after the user completes the requested remediation or explicitly asks to retry.

## Safe remediation map

| Symptom | Next action |
| --- | --- |
| `supa.cc` not found | Follow the official Supa.cc installation guide, then run `supa.cc --version`. Do not improvise an installation channel. |
| Supabase CLI missing or incompatible | Run `supa.cc doctor --installation-check --json`, follow its official version guidance, and retry the check. |
| No registered accounts | Report the result. Offer `add` only if the user wants to register one. |
| Required account name is absent | Run `supa.cc list` when appropriate, present aliases, and ask the user to choose. Never invent one. |
| Active account missing | Ask which registered alias to activate, then run `switch` after selection. |
| Credential missing for an alias | Start `switch` only with an interactive hidden prompt available; otherwise explain the secure-input limitation. |
| Keychain locked or access cancelled | Ask the user to unlock or approve the native Keychain interaction, then retry only on request. |
| Secret Service or D-Bus unavailable | Require a real user session and unlocked Secret Service collection. Do not add a fallback backend. |
| Windows Credential Manager unavailable | Retry from the same interactive Windows user session; do not impose POSIX permissions or replace `WinVaultKeyring`. |
| Network or API authentication failure | Report the sanitized category. Do not expose or re-request the PAT in chat. |
| Concurrent or partial mutation | Stop. Do not delete locks, journals, state, or credentials manually; follow official troubleshooting. |
| Forwarded Supabase command failed | Preserve its sanitized output and exit code. Do not claim the Supa.cc account switch failed unless the result says so. |

## Approval rules

Require explicit confirmation for replacing an existing alias, removing one account, resetting all state, or forwarding a destructive Supabase command. The confirmation must identify the exact alias or scope. A request naming a new alias and a user's explicit selection of an alias to activate are sufficient authorization for those scoped operations. Prefer the CLI's built-in confirmation for removal and reset; use `--yes` only after equivalent conversational confirmation when the harness cannot present the built-in confirmation. The flag never creates authorization by itself.

If required information is missing, ask a focused question. If secure interaction is unavailable, stop only the credential step. Do not replace missing input with a guess or a less secure transport.
