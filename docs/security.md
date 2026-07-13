# Security model

This is the canonical document for Supa.cc security guarantees and limits.

## Storage

- The canonical service is `supa.cc.supabase.accounts.v2`.
- PATs are stored in macOS Keychain, Linux Secret Service, or Windows Credential Manager through `WinVaultKeyring`.
- No local file contains a PAT. `accounts.json` and `active-account` store names; `session-sync.json`, `.session-sync.lock`, and `.accounts.json.lock` store recovery and coordination metadata.
- Rollback backups remain in native storage under a reserved identity, never in the index or journal.
- Credential reads do not use a cache: every read queries `CredentialStore.get()` and the native backend directly. Invalid or unreadable indexes are preserved for diagnostics.
- There is no plaintext fallback, `keyrings.alt`, or alternative backend. Previous namespaces are not migrated implicitly.

## Activation and native session

`switch` validates the PAT, uses only the official `supabase` profile and the public `login`, `logout --yes`, and `projects list` commands from Supabase CLI >= 2.109.1. The PAT is passed through `SUPABASE_ACCESS_TOKEN` in the child process environment and never in `argv`.

Executable binding is explicit per platform:

- Linux accepts only a regular executable owned by the user or root and not writable by group or others, then executes the open descriptor.
- macOS applies the same file checks, keeps the file open, rejects group- or world-writable ancestors, revalidates identity immediately before spawning, and executes the validated path. `/dev/fd` is not assumed to be executable on macOS.
- Windows opens a regular file and compares path identity with the descriptor after opening and again immediately before process creation. The API executes the validated path; Supa.cc does not claim descriptor-bound execution, owner validation, ACL validation, or POSIX-mode validation.

Post-login verification confirms the exact persisted native credential. Supa.cc does not edit CLI credentials or profiles directly.

An inherited `SUPABASE_ACCESS_TOKEN` takes precedence and blocks synchronization. A plaintext `access-token` fallback is blocked without reading or migrating it. Output, errors, and exceptions are sanitized.

Removing the active account runs `logout --yes`; this may remove project-support credentials managed by the Supabase CLI itself.

## Rollback, recovery, and concurrency

Rollback and recovery are mutation-aware. The token-free journal records the operation, phase, and names; a secure backup can restore the exact previous credential when required by the phase. The lock coordinates cooperating Supa.cc processes but not concurrent external `supabase` commands.

## Diagnostics

`supa.cc doctor` and `supa.cc doctor --json` are non-live by default: they do not open a token or perform an authenticated operation. The backend appears as configured but not verified; this execution does not test credential-store availability. Standard output is designed to be shareable: it reports only whether an account is selected and indexed, sanitizes local paths, and never includes the account name or PAT. The `invoked` and `realpath` fields remain present and `path_relation` reports `same`, `symlinked`, or `unavailable`.

Only `supa.cc doctor --account <name> --live` opens the selected credential once and performs explicit online validation with `projects list`.

## Platform limits

- macOS: the Python runtime is the Keychain accessor; Supa.cc does not bypass locks or expand ACLs.
- Linux: user D-Bus and an unlocked Secret Service are required; headless environments without both fail with safe guidance.
- Windows: only Windows Credential Manager through `WinVaultKeyring` is accepted; `%APPDATA%` stores metadata without secrets. Locks reject reparse paths, additional links, and detectable identity changes before and after acquisition. The directory and files inherit the access controls of `%APPDATA%`; Supa.cc does not create a private ACL or impose POSIX modes on Windows.

For remediation without exposing secrets, see [Troubleshooting](troubleshooting.md).

## Repository and artifact scanning

The release gate scans tracked files, reachable Git history, the pytest cache, wheel, and sdist for high-confidence credential and private-key patterns. Findings report only the secret class and location, never the matching value. Historical synthetic fixtures require an exact object allowlist; new credential-shaped examples are rejected.
