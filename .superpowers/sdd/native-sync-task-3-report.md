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
