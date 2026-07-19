# Security model

This is the canonical document for Supa.cc security guarantees and limits.

## Storage

- The canonical service is `supa.cc.supabase.accounts.v2`.
- PATs are stored in macOS Keychain, Linux Secret Service, or Windows Credential Manager through `WinVaultKeyring`.
- No local file contains a PAT. One atomic, versioned `state.json` document stores aliases, the confirmed active alias, and an optional token-free transition with its phase.
- Credential reads do not use a cache: every requested read queries the native backend directly. Listing accounts and starting the TUI read only `state.json`, so they do not prompt for credential access.
- Existing `accounts.json`, `active-account`, the legacy journal `session-sync.json`, and `.lock` coordination metadata are migrated atomically. The old data files are removed only after the new document is written, synchronized, and re-read successfully; private lock files may remain as coordination primitives and contain no account data.
- There is no plaintext fallback, `keyrings.alt`, or alternative backend. Previous namespaces are not migrated implicitly.

## Activation and native session

`switch` validates the PAT, uses only the official `supabase` profile and the public `login`, `logout --yes`, and `projects list` commands from Supabase CLI >= 2.109.1. Every internal command receives `--profile supabase`. The PAT is passed through `SUPABASE_ACCESS_TOKEN` only for validation and login and never in `argv`, stdin output, logs, or exceptions.

Executable binding is explicit per platform:

- Linux accepts only a regular executable owned by the user or root and not writable by group or others, then executes the open descriptor.
- macOS applies the same file checks, keeps the file open, and rejects world-writable ancestors. Group-writable ancestors are rejected except for the user-owned `Cellar` directory under the canonical `/opt/homebrew` and `/usr/local` Homebrew prefixes; the executable itself must remain non-writable by group or others. Supa.cc revalidates binary identity immediately before spawning and executes the validated path. `/dev/fd` is not assumed to be executable on macOS.
- Windows opens a regular file and compares path identity with the descriptor after opening and again immediately before process creation. The API executes the validated path; Supa.cc does not claim descriptor-bound execution, owner validation, ACL validation, or POSIX-mode validation.

After login, Supa.cc removes `SUPABASE_ACCESS_TOKEN` from the child environment and runs `projects list`. Success confirms that the Supabase CLI persisted and recovered a usable native session through its own credential layer. Supa.cc does not read, write, migrate, compare, or remove the CLI's internal credential entries, identifiers, or formats.

Inherited `SUPABASE_ACCESS_TOKEN` and `SUPABASE_PROFILE` values are removed from the controlled child environment, preventing their normal precedence from overriding the selected account. Internal subprocesses disable telemetry with `SUPABASE_TELEMETRY_DISABLED=1` and `DO_NOT_TRACK=1`; the user's shell and global consent are not changed. The controlled temporary `SUPABASE_HOME` remains empty while inspecting or ending an existing session, then physically blocks the plaintext `access-token` fallback before login and persisted-session verification. Supa.cc never reads or migrates that fallback. Output, errors, and exceptions are sanitized.

Removing the active account runs `logout --yes`; this may remove project-support credentials managed by the Supabase CLI itself.

## Rollback, recovery, and concurrency

Rollback and recovery are mutation-aware. The token-free pending transition records the operation, target, previous alias, and phase in the same atomic state document. After a failed switch, Supa.cc attempts to restore the previous session from its separately stored PAT. If neither target nor previous session can be confirmed, no account is advertised as active and recovery remains explicit. The lock coordinates cooperating Supa.cc processes but not concurrent external `supabase` commands.

The Supabase CLI session is machine-global and derived. External `supabase login` or `supabase logout` commands can therefore replace it outside Supa.cc. Supa.cc never reads, edits, migrates, or deletes the CLI's internal credential identifiers directly.

## Diagnostics

`supa.cc doctor` and `supa.cc doctor --json` are non-live by default: they do not open a token or perform an authenticated operation. The backend appears as configured but not verified; this execution does not test credential-store availability. Standard output is designed to be shareable: it reports only whether an account is selected and indexed, sanitizes local paths, and never includes the account name or PAT. The `invoked` and `realpath` fields remain present and `path_relation` reports `same`, `symlinked`, or `unavailable`.

`supa.cc doctor --installation-check` remains unauthenticated and validates installation dependencies only: the supported environment, Supabase CLI compatibility, a writable Supabase CLI operational directory (`SUPABASE_HOME` or its default), and one isolated native credential-store probe. The probe uses random service and account identifiers separate from the canonical account namespace and does not read an account or PAT. This mode does not load, create, migrate, validate, or recover account state; account, index, and activation fields outside its scope are reported as `not_checked` or **not checked**. On Linux it checks that the default Secret Service collection is already unlocked before the lookup and never calls an unlock operation. The accepted native backends remain Keychain on macOS, Secret Service on Linux, and Windows Credential Manager through `WinVaultKeyring` on Windows; there is no plaintext fallback, `keyrings.alt`, or alternative backend. Failures are sanitized. This option is mutually exclusive with `--live` and `--account`.

The installation check does not report account-state consistency. Normal `doctor` detects persisted pending transitions as `sync_pending`; mutating account operations may also surface recovery failures while resuming them. Recovery reruns the appropriate mutating Supa.cc account command; manual editing of the state document or native credentials is unsupported.

Only `supa.cc doctor --account <name> --live` opens the selected credential once and performs explicit online validation with `projects list`.

## Platform limits

- macOS: before accessing a PAT, Supa.cc validates the default user Keychain path and search-list membership with read-only `security` queries. This preflight does not enumerate Keychain items, read credential values, change the default, edit the search list, or expand ACLs. The Python runtime accesses only Supa.cc account credentials, while the Supabase CLI accesses its own session credential; Keychain can authorize those executable identities independently.
- Linux: user D-Bus and an unlocked Secret Service are required; headless environments without both fail with safe guidance.
- Windows: only Windows Credential Manager through `WinVaultKeyring` is accepted; `%APPDATA%` stores metadata without secrets. Locks reject reparse paths, additional links, and detectable identity changes before and after acquisition. Supabase CLI subprocesses start suspended, are assigned to a kill-on-close Job Object, and only then resume, so descendants cannot escape containment before timeout and interruption handling is active. The directory and files inherit the access controls of `%APPDATA%`; Supa.cc does not create a private ACL or impose POSIX modes on Windows.

For remediation without exposing secrets, see [Troubleshooting](troubleshooting.md).

## Repository and artifact scanning

The release gate scans tracked files, reachable Git history, the pytest cache, wheel, and sdist for high-confidence credential and private-key patterns. Findings report only the secret class and location, never the matching value. Historical synthetic fixtures require an exact object allowlist; new credential-shaped examples are rejected.
