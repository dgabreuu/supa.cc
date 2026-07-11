# Native Supabase CLI Session Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every successful Supa.cc account selection persist and verify the same account in the official Supabase CLI so direct `supabase ...` commands require no additional login command.

**Architecture:** Add a native-session gateway around public Supabase CLI commands, passing PATs only in a child environment and rejecting the CLI's plaintext fallback. `AccountManager` coordinates credential/index, active-name, and native-session mutations through a token-free journal, while CLI/TUI remain presentation layers.

**Tech Stack:** Python 3.9+, Click, keyring, Supabase CLI subprocesses, pytest.

## Global Constraints

- Never put a PAT in argv, logs, diagnostics, journals, or Supa.cc state files.
- Reject both pre-existing and newly created Supabase CLI plaintext `access-token` fallback files without reading them.
- Reject synchronization while the parent environment contains `SUPABASE_ACCESS_TOKEN`, because it overrides persisted native state.
- Use public `supabase login`, `supabase logout`, and Management API commands; do not manipulate Supabase CLI keyring namespaces or profile files directly.
- Preserve `accounts.json`, `active-account`, and `supa.cc.supabase.accounts.v2` compatibility.
- CLI and TUI call only `AccountManager`; synchronization logic must not be duplicated in presentation code.
- Failures compensate to the previous selected account or preserve a token-free recovery journal and never report false success.
- Removing the active account logs out the native CLI and leaves both systems without an active account.
- `supa.cc run -- ...` remains supported but is no longer required after successful synchronization.

---

### Task 1: Native Session Gateway

**Files:**
- Create: `supa_cc/native_session.py`
- Modify: `supa_cc/config.py`
- Modify: `supa_cc/auth.py`
- Preserve and extend: `tests/test_native_session.py`
- Modify: `tests/test_config.py`

**Interfaces:**
- `SupabaseConfig.login_with_access_token(account: Account) -> AuthResult`
- `SupabaseConfig.verify_persisted_session() -> AuthResult`
- `SupabaseConfig.logout_session() -> AuthResult`
- `NativeSessionSynchronizer.activate(account: Account) -> AuthResult`
- `NativeSessionSynchronizer.logout() -> AuthResult`
- `SessionSyncJournal.read/write/clear`

- [ ] **Step 1: Preserve the existing untracked RED tests and add subprocess-contract tests**

```python
def test_login_passes_token_only_in_child_environment(config, account, popen):
    result = config.login_with_access_token(account)
    argv = popen.call_args.args[0]
    env = popen.call_args.kwargs["env"]
    assert argv[-1] == "login"
    assert account.token not in argv
    assert env["SUPABASE_ACCESS_TOKEN"] == account.token
    assert result.ok


def test_persisted_verification_removes_environment_override(config, popen):
    config.verify_persisted_session()
    assert "SUPABASE_ACCESS_TOKEN" not in popen.call_args.kwargs["env"]
```

- [ ] **Step 2: Run focused tests and verify RED**

Run: `PYTHONPATH="/tmp/opencode/supa-cc-test-deps" python3 -m pytest tests/test_native_session.py tests/test_config.py -v`

Expected: collection fails because `supa_cc.native_session` and the three `SupabaseConfig` methods do not exist.

- [ ] **Step 3: Add typed failures and active-account clear**

Add failure codes for plaintext fallback, native login, native logout,
verification, pending sync, and rollback. Add `ActiveAccountStore.clear()` as
an idempotent unlink that maps permission and OS errors through existing active
account domain errors.

- [ ] **Step 4: Implement secure native subprocess methods**

Reuse the current resolved executable, bounded capture, redaction, timeout,
process-group termination, and failure classifier. Login executes `login` with
the PAT only in a copied child environment. Verification executes `projects
list` after deleting `SUPABASE_ACCESS_TOKEN`. Logout executes `logout --yes`
with the override removed. Return sanitized `AuthResult` values.

- [ ] **Step 5: Implement fallback policy and token-free journal**

```python
def access_token_fallback_path(env=None, home=None) -> Path:
    values = os.environ if env is None else env
    root = Path(values["SUPABASE_HOME"]) if values.get("SUPABASE_HOME") else (
        Path.home() if home is None else Path(home)
    ) / ".supabase"
    return root / "access-token"
```

`NativeSessionSynchronizer.activate()` rejects a parent override and existing
fallback, executes login, removes/rejects a newly created fallback, then
verifies persisted state. `logout()` succeeds only when logout succeeds and
verification reports `TOKEN_MISSING`. Journal writes use `0600`, parent `0700`,
atomic replacement, validated names/phases, and no token field.

- [ ] **Step 6: Run focused and full tests**

Run: `PYTHONPATH="/tmp/opencode/supa-cc-test-deps" python3 -m pytest tests/test_native_session.py tests/test_config.py tests/test_auth.py -v`

Run: `PYTHONPATH="/tmp/opencode/supa-cc-test-deps" python3 -m pytest`

Expected: PASS; real credential smoke tests remain skipped by default.

- [ ] **Step 7: Commit**

```bash
git add supa_cc/native_session.py supa_cc/config.py supa_cc/auth.py tests/test_native_session.py tests/test_config.py tests/test_auth.py
git commit -m "feat: add native Supabase session gateway"
```

### Task 2: Transactional Account Selection

**Files:**
- Modify: `supa_cc/accounts.py`
- Modify: `tests/test_accounts.py`
- Modify: `tests/helpers.py`

**Interfaces:**
- `AccountManager(..., native_session=None, sync_journal=None)` retains existing callers.
- `AccountManager.set_active(name)` returns success only after native verification and local persistence.
- `AccountManager.recover_pending_sync()` runs before account mutations.

- [ ] **Step 1: Write ordering, rollback, and recovery tests**

```python
def test_set_active_synchronizes_native_session_before_success(manager):
    result = manager.set_active("work")
    assert result.ok
    manager.native_session.activate.assert_called_once()
    assert manager.active_store.read() == "work"


def test_set_active_restores_previous_name_when_native_sync_fails(manager):
    manager.active_store.write("old")
    manager.native_session.activate.return_value = AuthResult.failure(
        AuthFailureCode.NATIVE_LOGIN_FAILED, "Falha segura."
    )
    result = manager.set_active("work")
    assert not result.ok
    assert manager.active_store.read() == "old"
```

Add tests for first activation, previous-account compensation, failure to
compensate, journal persistence, restart recovery, environment override, and
false-success prevention.

- [ ] **Step 2: Run tests and verify RED**

Run: `PYTHONPATH="/tmp/opencode/supa-cc-test-deps" python3 -m pytest tests/test_accounts.py -v`

Expected: synchronization assertions fail because `AccountManager` has no native-session coordinator.

- [ ] **Step 3: Compose dependencies and implement selection transaction**

Detect one environment, construct one `NativeSessionSynchronizer`, and place
the journal at `<config-directory>/session-sync.json`. `set_active()` validates
the target, reads the previous name/account, writes intent, invokes native
activation, writes the target name, verifies success, and clears intent.

On failure, restore the previous native account and local name when available;
otherwise perform native logout and clear local selection. If compensation
fails, retain the journal and return `SYNC_ROLLBACK_FAILED`.

- [ ] **Step 4: Implement deterministic recovery**

Recovery reads only names/phases from the journal, retrieves required PATs from
the credential store, and rolls forward or compensates according to phase.
Missing credentials produce a sanitized pending-sync failure, not journal
deletion. Serialize mutations with the existing account index lock or a
dedicated sync lock in the same config directory.

- [ ] **Step 5: Run focused and full tests, then commit**

Run: `PYTHONPATH="/tmp/opencode/supa-cc-test-deps" python3 -m pytest tests/test_accounts.py tests/test_native_session.py -v`

Run: `PYTHONPATH="/tmp/opencode/supa-cc-test-deps" python3 -m pytest`

```bash
git add supa_cc/accounts.py tests/test_accounts.py tests/helpers.py
git commit -m "feat: synchronize selected Supabase account"
```

### Task 3: Active Token Updates And Removal

**Files:**
- Modify: `supa_cc/accounts.py`
- Modify: `supa_cc/keychain.py`
- Modify: `tests/test_accounts.py`

**Interfaces:**
- `AccountManager.add()` resynchronizes only when replacing the active account token.
- `AccountManager.remove()` logs out and clears state only when removing the active account.

- [ ] **Step 1: Write active-update and active-removal tests**

Cover inactive add/remove with no native calls; active token replacement with
successful resync; failed resync restoring the old credential; active removal
ordering; logout failure preserving account/index/active name; removal failure
after logout preserving a recoverable journal.

- [ ] **Step 2: Run tests and verify RED**

Run: `PYTHONPATH="/tmp/opencode/supa-cc-test-deps" python3 -m pytest tests/test_accounts.py tests/test_keychain.py -v`

Expected: active-update/removal synchronization assertions fail.

- [ ] **Step 3: Implement active token replacement transaction**

Read and retain the prior account before overwrite. Persist the new account,
then synchronize it if active. On synchronization failure, restore the prior
credential and native session. Convert failed restoration to
`AccountTransactionError`/sync rollback failure without exposing either token.

- [ ] **Step 4: Implement active removal transaction**

If the target is active, write removal intent, perform native logout, clear
active name, then remove credential/index and clear the journal. Logout failure
does not mutate local state. Later local failures retain a journal for
roll-forward recovery. Non-active removal remains unchanged.

- [ ] **Step 5: Run focused/full tests and commit**

Run: `PYTHONPATH="/tmp/opencode/supa-cc-test-deps" python3 -m pytest tests/test_accounts.py tests/test_keychain.py tests/test_native_session.py -v`

Run: `PYTHONPATH="/tmp/opencode/supa-cc-test-deps" python3 -m pytest`

```bash
git add supa_cc/accounts.py supa_cc/keychain.py tests/test_accounts.py tests/test_keychain.py
git commit -m "feat: synchronize active account lifecycle"
```

### Task 4: UX, Diagnostics, And Documentation

**Files:**
- Modify: `supa_cc/diagnostics.py`
- Modify: `supa_cc/strings.py`
- Modify: `supa_cc/ui/screens.py`
- Modify: `tests/test_diagnostics.py`
- Modify: `tests/test_cli_commands.py`
- Modify: `tests/test_ui_screens.py`
- Modify: `README.md`
- Modify: `docs/installation.md`
- Modify: `docs/release.md`
- Modify: `SKILL.md`
- Modify: `tests/test_publication_assets.py`

**Interfaces:**
- `doctor` remains read-only and reports sync metadata without token access.
- CLI/TUI display the `AccountManager` result and contain no native-session subprocess logic.

- [ ] **Step 1: Write failing UX and diagnostic tests**

Assert switch success says the official CLI is synchronized; failures identify
login, verification, plaintext, or rollback categories; `doctor` reports
journal presence, parent override, fallback presence, and activation mode
`native_session` without reading a credential.

- [ ] **Step 2: Run tests and verify RED**

Run: `PYTHONPATH="/tmp/opencode/supa-cc-test-deps" python3 -m pytest tests/test_diagnostics.py tests/test_cli_commands.py tests/test_ui_screens.py tests/test_publication_assets.py -v`

Expected: old `environment_only` and `supa.cc run`-required assertions fail.

- [ ] **Step 3: Update presentation and diagnostics**

Use neutral, sanitized messages. Keep CLI/TUI as delegates. Diagnostics checks
only journal/fallback existence and environment-key presence; it never opens a
PAT or repairs state. Preserve JSON compatibility while adding structured sync
status.

- [ ] **Step 4: Update public contract**

Document direct `supabase ...` behavior, continued optional `supa.cc run`,
override blocking, plaintext policy, logout side effects, crash recovery,
concurrency limitation, and supported CLI capability checks. Remove statements
that native sessions are unmanaged.

- [ ] **Step 5: Test and commit**

Run: `PYTHONPATH="/tmp/opencode/supa-cc-test-deps" python3 -m pytest tests/test_diagnostics.py tests/test_cli_commands.py tests/test_ui_screens.py tests/test_publication_assets.py -v`

```bash
git add supa_cc/diagnostics.py supa_cc/strings.py supa_cc/ui/screens.py tests/test_diagnostics.py tests/test_cli_commands.py tests/test_ui_screens.py README.md docs/installation.md docs/release.md SKILL.md tests/test_publication_assets.py
git commit -m "docs: explain native Supabase session sync"
```

### Task 5: Integration And Release Verification

**Files:**
- Modify: `tests/test_supabase_cli_integration.py`
- Modify: `docs/release.md`

**Interfaces:**
- Fake Supabase CLI persists only synthetic test state in temporary directories.

- [ ] **Step 1: Add end-to-end fake CLI scenarios**

Implement a fake CLI that handles `login`, `logout --yes`, and `projects list`,
persists a token fingerprint outside argv, supports forced fallback/failure,
and records whether verification received `SUPABASE_ACCESS_TOKEN`. Cover first
selection, account switch, direct command use, rollback, active removal, and
crash recovery.

- [ ] **Step 2: Run integration and full tests**

Run: `PYTHONPATH="/tmp/opencode/supa-cc-test-deps" python3 -m pytest tests/test_supabase_cli_integration.py -v`

Run: `PYTHONPATH="/tmp/opencode/supa-cc-test-deps" python3 -m pytest -v`

Expected: all normal tests pass; real keyring/Secret Service smoke tests skip unless explicitly enabled.

- [ ] **Step 3: Build and install the wheel cleanly**

Run: `PYTHONPATH="/tmp/opencode/supa-cc-test-deps" python3 -m build`

Run: `PYTHONPATH="/tmp/opencode/supa-cc-test-deps" python3 -m virtualenv /tmp/opencode/supa-cc-native-sync-verify`

Run: `/tmp/opencode/supa-cc-native-sync-verify/bin/pip install dist/*.whl && /tmp/opencode/supa-cc-native-sync-verify/bin/supa.cc --version`

Expected: wheel/sdist build and installed CLI version succeed.

- [ ] **Step 4: Review security invariants and commit**

Run: `git diff main...HEAD --check && git status --short && git log --oneline main..HEAD`

Confirm no test fixture, docs, argv assertion, journal, or captured output contains a real PAT.

```bash
git add tests/test_supabase_cli_integration.py docs/release.md
git commit -m "test: verify native Supabase session sync"
```
