# Native Supabase CLI Session Synchronization

## Goal

Selecting an account in Supa.cc must synchronize the official Supabase CLI so
subsequent direct `supabase ...` commands use that account without another
manual command. CLI and TUI must share the same orchestration.

## Current Gap

Supa.cc currently validates tokens and stores only an `active-account` name.
It injects `SUPABASE_ACCESS_TOKEN` only for `supa.cc run`, so direct Supabase
CLI commands continue using the CLI's independently persisted session.

## Native Session Contract

Supa.cc will invoke the official `supabase login` command with the selected PAT
only in the child environment. It will never place a PAT in argv. After login,
Supa.cc will verify a Management API command with `SUPABASE_ACCESS_TOKEN`
removed, proving the persisted native session is usable.

An inherited `SUPABASE_ACCESS_TOKEN` makes direct-command synchronization
unreliable because it overrides persisted credentials. Supa.cc must reject the
operation with clear remediation rather than claim success.

## Plaintext Policy

The Supabase CLI may fall back to `$SUPABASE_HOME/access-token` or
`~/.supabase/access-token` when its native keyring is unavailable. Supa.cc
must fail closed:

- reject a pre-existing fallback file without reading it;
- remove a fallback file created by the attempted login;
- report a sanitized synchronization failure;
- never copy, log, or migrate the fallback token automatically.

## Coordination And Recovery

Native CLI state and Supa.cc state cannot be updated atomically. A private
`session-sync.json` journal will record only operation, target account,
previous account, and phase. It will never contain a PAT.

Mutations recover an existing journal before starting. Switch and active-token
updates validate the target, record intent, synchronize native state, update
local state, verify consistency, and clear the journal. Failures compensate to
the previous Supa.cc account when available; otherwise they log out the native
session. A failed compensation preserves the journal and blocks later account
mutations until automatic recovery succeeds.

There may be a brief observable transition for a concurrently executed direct
`supabase` command because the official CLI provides no transaction API. The
journal guarantees detected, recoverable eventual consistency rather than
cross-process atomicity.

## Account Lifecycle

- Switching an account synchronizes native login before reporting success.
- Updating the token of the active account resynchronizes the native session;
  failure restores the previous stored token and session.
- Updating an inactive account does not affect native state.
- Removing an inactive account does not affect native state.
- Removing the active account performs controlled native logout, clears the
  local active selection, and removes the account. Logout failure leaves the
  account intact.

The official logout may remove auxiliary project credentials managed by the
Supabase CLI; this effect must be documented.

## Components

- `supa_cc/native_session.py`: native login/logout/verification, fallback-file
  policy, journal persistence, and sanitized typed results.
- `supa_cc/config.py`: secure subprocess methods for native login, logout, and
  verification using the existing process and redaction infrastructure.
- `supa_cc/accounts.py`: account-lifecycle transaction coordinator.
- `supa_cc/auth.py`: synchronization failure codes and active-account clear.
- `supa_cc/diagnostics.py`: read-only consistency, journal, environment
  override, and fallback-presence reporting.
- CLI/TUI: presentation only; no duplicated synchronization logic.

## Diagnostics And UX

Success states explicitly say the Supabase CLI was synchronized. Errors
identify validation, login, verification, fallback, rollback, or pending
recovery without exposing backend output or PATs. `doctor` remains read-only
and reports possible divergence without opening a token.

`supa.cc run -- ...` remains available as an explicit isolated execution path,
but is no longer required after a successful switch.

## Compatibility

The implementation uses public Supabase CLI commands and environment input,
not internal keyring namespaces or profile-file formats. Capability failures
are classified as CLI incompatibility. Existing account index, credential
service, and active-account formats remain unchanged.

## Testing

Unit tests use fake stores and subprocesses. Integration tests use a fake
Supabase CLI to cover login, direct verification without an environment token,
logout, plaintext fallback, crashes at journal phases, compensation, active
token replacement, active removal, and output sanitization. No normal test
touches the user's real native Supabase session.

## Acceptance Criteria

- Successful `switch` makes direct `supabase ...` use the selected account.
- No additional Supabase command is required from the user.
- PATs never enter argv, logs, journals, or Supa.cc state files.
- Plaintext Supabase CLI fallback is rejected.
- Active-account updates and removal keep local and native state coordinated.
- Failures compensate or leave a recoverable journal; they never report false
  success.
