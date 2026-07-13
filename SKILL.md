---
name: supa-cc-cli
description: Use when operating or maintaining authentication, native storage, diagnostics, or Supabase CLI integration in Supa.cc
---

# Supa.cc CLI

Use [Installation](docs/installation.md) for the installation lifecycle, [Usage](docs/usage.md) for flows and commands, [Security](docs/security.md) for the internal contract, and [Troubleshooting](docs/troubleshooting.md) for remediation.

## Agent invariants

- Never place real PATs or credential-shaped examples in commands, code, fixtures, files, logs, errors, documentation, prompts, or transcripts. PATs are requested through hidden input and accepted only when matching `^(?:sbp_|sbp_oauth_)[0-9a-f]{40}$`.
- On macOS, use only Keychain; on Linux, only Secret Service with user D-Bus and an unlocked collection; on Windows, only Windows Credential Manager through the exact `WinVaultKeyring` backend.
- Never enable a plaintext fallback, `keyrings.alt`, or another backend. Headless Linux environments without the required services must fail with safe guidance.
- No local file contains a PAT. The index, selection, journal, and locks contain only names or metadata; temporary rollback backups remain in native storage.
- Pass the PAT to the Supabase CLI only through `SUPABASE_ACCESS_TOKEN` in the child process environment, never in `argv`. An inherited `SUPABASE_ACCESS_TOKEN` blocks synchronization.
- Use only the official `supabase` profile and Supabase CLI >= 2.109.1. Verify executable trust and the exact native credential; do not edit CLI credentials or profiles directly.
- Rollback and recovery must be mutation-aware. The lock coordinates cooperating Supa.cc processes, not concurrent external `supabase` commands.
- `doctor` and `doctor --json` are non-live, do not open a token, and do not prove backend availability. Only `doctor --account <name> --live` authorizes reading and authenticated validation of the selected account.
- Do not weaken ACLs, export items, dump environments or credentials, or delete legacy items, journals, locks, or credentials without the exact prior state and explicit approval.
- On Linux, validate ownership and modes and execute the open descriptor. On macOS, keep the validated file open, reject writable ancestors, revalidate identity immediately before spawn, and execute the validated path; do not claim descriptor binding. On Windows, compare path and descriptor identity before process creation and execute the validated path without claiming ACL or POSIX-mode validation.

Canonical identities: `macOS: Keychain service supa.cc.supabase.accounts.v2`; `Linux: Secret Service supa.cc.supabase.accounts.v2`; `Windows: Windows Credential Manager (WinVaultKeyring) service supa.cc.supabase.accounts.v2`.
