# Native Sync Task 3 Report

## Status

Implemented active token update and active account removal synchronization.

## Changes

- Inactive account additions and removals retain their existing keychain-only behavior.
- Replacing an active token now runs under the session sync lock, journals the transition, and activates the replacement credential.
- Failed active-token synchronization restores the prior credential with `KeychainManager.save_account()`, restores the prior native session through the existing compensation path, and raises a sanitized `AccountTransactionError`.
- Removing an active account journals intent, logs out before local mutation, clears the active selection, removes the credential/index entry, and clears the journal.
- Logout failure clears the uncommitted intent and leaves account, index, credential, and active selection unchanged.
- Failures after logout retain a token-free `logout` journal for roll-forward recovery.
- Pending logout recovery now completes local active-state and account removal deterministically.

## TDD Evidence

- Initial focused run: 104 passed, 5 failed. The five new active update/removal tests failed on missing synchronization behavior.
- Focused final run: 146 passed.
- Full final run: 431 passed, 4 skipped.
- `git diff --check`: clean.

## Concerns

- Platform credential smoke tests remain skipped when their native services are unavailable; this matches the existing suite behavior.

## Durable Compensation Follow-up

### Root Cause

The original overwrite journal stored only the active account name. Because target and previous names were identical, restart recovery reloaded the replacement PAT and could falsely report it as the restored credential. Logout recovery also repeated the destructive logout call when interruption occurred after logout but before journal advancement.

### Resolution

- Added deterministic reserved backup identities that cannot pass Supa.cc account-name validation.
- Added read-back-verified secure backup create/read/restore/delete operations that never mutate the account index or token cache under the reserved identity.
- Added the token-free `credential_backup` journal phase.
- Active overwrite recovery now uses backup presence to distinguish pre-mutation intent from a possible overwrite, restores the exact old PAT and native session, and removes the backup only after commit or rollback.
- Journal and backup cleanup failures retain deterministic recovery state.
- Native logout now verifies an already-missing session before invoking the destructive logout operation.
- Added stateful credential/index restart tests across every overwrite journal boundary, native activation interruption, successful cleanup, and the post-logout/pre-phase boundary.
- Added security assertions that backup identities and PATs do not enter the index, journal, cache, or public errors.

### Verification

- Primitive RED run: 3 failed as expected for missing secure backup and idempotent logout behavior.
- Restart RED run: replacement PAT remained after recovery instead of the old PAT.
- Focused final run: 157 passed.
- Full final run: 442 passed, 4 skipped.
- `git diff --check`: clean.
