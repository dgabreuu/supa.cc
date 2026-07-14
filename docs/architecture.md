# Architecture

Supa.cc separates user intent, secrets, and the external CLI session.

- `accounts` owns aliases and account rules. Its versioned state document contains no secrets.
- `credentials` owns the native platform store and accepts only Keychain, Secret Service, or WinVault. On macOS it validates default Keychain routing through read-only metadata before invoking the credential backend.
- `supabase_cli` owns executable resolution, immutable child environments, process execution, output redaction, and CLI failure classification.
- `session` owns deterministic logout, login, verification, and recovery phases. The Supabase CLI credential is opaque.
- `ui` and Click adapt the same typed results; they do not implement authentication rules.
- `diagnostics` is non-live unless the user explicitly requests an authenticated check.

## State and transition rules

`state.json` is the sole secret-free source of user intent. It records the schema version, aliases, the last confirmed active alias, and at most one pending transition. PATs remain separate under the canonical native service. The machine-global Supabase CLI session is derived state and can be replaced or recovered.

A switch validates the selected PAT, records `prepared`, logs out the public CLI profile, logs in with the PAT only in the child environment, verifies the persisted session without the PAT, and only then commits the active alias. Each completed phase is persisted atomically. A retry completes the target transition or restores the previous confirmed session; an unverified session is never represented as active.

## Boundaries

Infrastructure exceptions are normalized at their boundary. Public results contain an operation, phase, code, recoverability classification, and sanitized message. Credential values, native error details, raw subprocess output, and private paths cannot cross those boundaries.

The CLI profile and credential implementation belong to the Supabase CLI. Supa.cc uses only its public commands and does not depend on internal keyring names or file formats.
