# Troubleshooting

Always start with the non-live diagnostic:

```bash
supa.cc doctor
supa.cc doctor --json
```

It does not open a PAT or test credential-store availability; it shows only the configured backend. Standard `doctor` output is safe to share because account names are reduced to selected/indexed booleans and local paths are sanitized. Never share live diagnostic output, complete environments, or credential-store dumps without reviewing them separately.

## Safe reinstallation

Before reinstalling, record the installation method, provenance, and version shown by the diagnostic. Do not keep Homebrew, `pipx`, and editable installations active simultaneously on `PATH`. Preserve invalid state for diagnostics and do not delete native credentials; reinstalling the package does not require removing platform-stored PATs.

## macOS

Keychain authorizes the Python runtime that runs Supa.cc. Recreating a `pipx` environment or changing that runtime's path or signature may trigger one new authorization. Repeated prompts with the same runtime indicate inconsistent permissions or access control.

Do not export the item, grant access to all applications, or weaken ACLs. Use `doctor` to compare the invoked and real paths for the launcher, Python, and Supabase CLI. If Keychain is locked, unlock it in the graphical session and try again.

The Python runtime reads the selected Supa.cc account PAT, while the Supabase CLI reads its own persisted session. A prompt naming Python therefore belongs to account storage; a prompt naming `supabase` belongs to the CLI session. Supa.cc does not inspect or repair the CLI's internal Keychain entries. Do not delete entries by guessed service or account names.

### Homebrew tap trust

Homebrew 6.0 and later require trust before loading formulae from non-official
taps. The Supa.cc tap points to the public project repository through a custom
remote, so registering the tap does not by itself authorize Homebrew to evaluate
its formula by a short name.

If Homebrew reports that `dgabreuu/supa-cc` is untrusted, repeat the installation
with the fully qualified formula name:

```bash
brew install supabase/tap/supabase
brew install dgabreuu/supa-cc/supa-cc
```

These commands record trust only for the selected formulae. The Supabase CLI is
a dependency from another non-official tap and must also be installed by its
fully qualified name, even when it is already present. A maintainer who must
evaluate the formula before installing it can grant the same narrow scope
explicitly:

```bash
brew trust --formula dgabreuu/supa-cc/supa-cc
```

Trusting the complete tap is broader because it also authorizes every current
and future formula, cask, and external command in that repository. Keep the
Homebrew trust checks enabled and prefer formula-scoped trust.

## Linux

The accepted backend is only Secret Service on the user-session D-Bus. Confirm that D-Bus exists, that `gnome-keyring` or another compatible provider is running, and that the collection is unlocked. In SSH, containers, or headless environments, forwarding D-Bus variables without a real unlocked service does not help.

Do not install `keyrings.alt` or configure plaintext storage. Debian/Ubuntu, Arch Linux, and Fedora are supported; see the packages in [Installation](installation.md#linux-pipx-only). Secret-free state uses `$XDG_CONFIG_HOME/supa.cc` or `~/.config/supa.cc`.

## Windows

The backend must be exactly Windows Credential Manager through `WinVaultKeyring`. Do not enable alternative backends. Check Credential Manager for availability under the same user account without copying or exposing the credential value.

If `pipx` or `supa.cc` is not on `PATH`, run this in PowerShell:

```powershell
py -m pipx ensurepath
```

Close and reopen PowerShell. `%APPDATA%` must be defined as an absolute path; secret-free metadata is stored in `%APPDATA%\supa.cc`. Missing or relative paths cause a safe failure.

## Inherited variables

An already-defined `SUPABASE_ACCESS_TOKEN` overrides the persisted session and blocks `switch`. Remove it from the current shell and from the configuration that injects it without printing its value. Check only whether the variable is present using tools appropriate for your shell.

Supa.cc blocks the Supabase CLI plaintext `access-token` fallback without reading its contents. Do not paste that file into reports and do not attempt to migrate it to Supa.cc.

## Restricted IDEs and telemetry

Some IDEs and sandboxes allow the Supabase command itself but deny writes to its telemetry directory. An error mentioning `EPERM`, `operation not permitted`, or `telemetry.json` is an environment failure, not evidence of an invalid PAT.

Where organizational policy permits it, disable telemetry explicitly for that IDE task or process by setting either `SUPABASE_TELEMETRY_DISABLED=1` or `DO_NOT_TRACK=1`. Supa.cc does not set these variables, change telemetry consent, edit shell startup files, or alter the global environment automatically. Prefer a narrow IDE run configuration over a system-wide export.

## Live diagnostics and common errors

Use `supa.cc doctor --account <name> --live` only when you want to authorize reading and online validation of the selected account. HTTP 401 indicates a rejected PAT; network failure, missing or incompatible CLI, locked storage, and `EPERM` are distinct categories. An `EPERM` restricted to a sandbox does not prove that the token is invalid.

Failure categories identify the phase that needs remediation:

- `token_missing` means the selected indexed account has no readable PAT in Supa.cc storage.
- `keychain_permission_denied` means the native credential store denied one of the participating executable identities.
- `token_rejected` means the Supabase API rejected the selected PAT during validation.
- `native_login_failed` means the CLI did not complete session persistence after validation.
- `native_verification_failed` means the CLI could not recover and use the session without the PAT environment override.
- `profile_mismatch` means state outside the supported official `supabase` profile was detected.
- `environment_blocked` covers sandbox, filesystem, execution, or telemetry restrictions; it is not an authentication result.
- `network_failure` and `cli_incompatible` remain independent of local credential storage.

If `active-account` names an account absent from `accounts.json`, Supa.cc reports an inconsistent selection and does not open a PAT or mutate the CLI session. It also refuses Add, Switch, and Remove so that rollback cannot depend on an unindexed credential. First preserve the metadata files for diagnosis and confirm with `doctor` that no synchronization journal is pending. Then end the current CLI session explicitly with `supabase logout`, rename the token-free `active-account` file, and run `supa.cc switch <name>` for an indexed account. The file is `~/.config/supa.cc/active-account` on macOS and Linux, or `%APPDATA%\supa.cc\active-account` on Windows. Renaming rather than deleting preserves evidence and makes this repair explicit. Never edit `accounts.json`, a journal, a lock, or native credentials for this repair.

Interrupted operations may leave a token-free recovery journal. Run a mutating Supa.cc command again; do not manually delete the journal, locks, index, or credentials. The lock does not coordinate external `supabase` commands, so avoid running them at the same time as an activation.
