# Troubleshooting

Always start with the non-live diagnostic:

```bash
supa.cc doctor
supa.cc doctor --json
```

It does not open a PAT or test credential-store availability; it shows only the configured backend. Standard `doctor` output is safe to share because account names are reduced to selected/indexed booleans and local paths are sanitized. Never share live diagnostic output, complete environments, or credential-store dumps without reviewing them separately.

After installing or repairing requirements, use the explicit local installation check:

```bash
supa.cc doctor --installation-check
supa.cc doctor --installation-check --json
```

This mode runs `supabase --version`, compares it with the minimum supported version, and probes an isolated native credential-store entry without reading any account or PAT. It cannot be combined with `--live` or `--account`.

## Installer bootstrap

Start with the installer's dry-run and review its complete plan. The POSIX script requires `/dev/tty` for its one confirmation; when execution is intentionally non-interactive, review the tagged script first and pass `--yes`. PowerShell uses the equivalent `-DryRun` and `-Yes` options.

A checksum error is final. Do not bypass it, substitute an unofficial mirror, or extract the archive manually. Retry only after confirming the tagged installer still points to the expected official release. A download, system-package, Python, Homebrew, `pipx`, or final-validation failure identifies its phase and stops without trying an unverified alternative.

If the installer reports a conflicting channel, inspect `supa.cc doctor` and remove the Homebrew, `pipx`, editable, VCS, wheel, or package-manager installation that is not the platform's stable channel. The bootstrap never migrates or overwrites a different channel automatically.

The installers update `PATH` in the current process whenever technically possible. If the final executable is still not found, run `pipx ensurepath` through the selected Python on Linux or Windows, or load `brew shellenv` on macOS, then retry from a normal user session. Do not add an unknown executable directory merely to silence the check.

“Installed, but environment still blocked” means the packages and executables passed installation but the native credential store could not complete its isolated probe. Unlock Keychain through macOS, restore a real user D-Bus and unlocked Secret Service collection on Linux, or use Windows Credential Manager from the same interactive user session, then rerun `supa.cc doctor --installation-check`. The installer does not unlock stores, create Secret Service collections, alter ACLs, or change system policy.

## Safe reinstallation

Before reinstalling, record the installation channel, provenance, and version shown by the diagnostic. Do not keep Homebrew, `pipx`, editable, VCS, wheel, and package-manager installations active simultaneously on `PATH`. Preserve invalid state for diagnostics and remember that reinstalling does not remove native credentials. If a completely clean Supa.cc state is intentional, run `supa.cc reset --all` before uninstalling; it is safer than guessing native credential identifiers.

## macOS

Keychain authorizes the Python runtime that runs Supa.cc. Recreating a `pipx` environment or changing that runtime's path or signature may trigger one new authorization. Repeated prompts with the same runtime indicate inconsistent permissions or access control.

Before opening any credential, Supa.cc checks only the user Keychain routing with these read-only system queries:

```bash
security default-keychain -d user
security list-keychains -d user
```

Do not paste their output into a public report because it can contain a local user path. `keychain_configuration_invalid` means the configured default is missing, is not a regular user-owned Keychain, or is absent from the user search list. Open Keychain Access and use **Reset to Defaults** only after reviewing the macOS prompt and any unrelated Keychain recovery needs. Supa.cc does not change the default Keychain, edit its search list, or modify ACLs automatically.

`keychain_access_cancelled` records a cancelled authorization prompt; `keychain_permission_denied` records a denial; `keychain_locked` requires unlocking the Keychain; and `keychain_unavailable` indicates that the native store is unavailable or read-only. `environment_blocked` can also mean the current IDE or sandbox cannot present Keychain interaction.

Do not export the item, grant access to all applications, or weaken ACLs. Use `doctor` to compare the invoked and real paths for the launcher, Python, and Supabase CLI. If Keychain is locked, unlock it in the graphical session and try again.

The Python runtime reads the selected Supa.cc account PAT, while the Supabase CLI reads its own persisted session. A prompt naming Python therefore belongs to account storage; a prompt naming `supabase` belongs to the CLI session. Supa.cc does not inspect or repair the CLI's internal Keychain entries. Do not delete entries by guessed service or account names.

The canonical Homebrew `Cellar` directory may be user-owned and group-writable (`0775`). Supa.cc accepts only that narrow exception under `/opt/homebrew` or `/usr/local`, while still requiring the Supabase executable itself and every other ancestor to pass the ownership and write checks. A custom group-writable prefix is rejected as `environment_blocked`.

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

Add the directory reported by `pipx` to the current session only if the bootstrap could not do so, or open a new PowerShell after `ensurepath`. `%APPDATA%` must be defined as an absolute path; secret-free metadata is stored in `%APPDATA%\supa.cc`. Missing or relative paths cause a safe failure.

## Inherited variables

An already-defined `SUPABASE_ACCESS_TOKEN` overrides the persisted session for direct Supabase CLI commands. Supa.cc removes it, along with `SUPABASE_PROFILE`, from its controlled child processes and uses the selected account explicitly. Remove an inherited value from the shell if direct CLI commands still select a different account; check only whether it is present and never print it.

Supa.cc blocks the Supabase CLI plaintext `access-token` fallback without reading its contents. Do not paste that file into reports and do not attempt to migrate it to Supa.cc.

## Restricted IDEs and telemetry

Some IDEs and sandboxes allow the Supabase command itself but deny writes to its telemetry directory. An error mentioning `EPERM`, `operation not permitted`, or `telemetry.json` is an environment failure, not evidence of an invalid PAT.

Supa.cc sets `SUPABASE_TELEMETRY_DISABLED=1` and `DO_NOT_TRACK=1` only for its own Supabase CLI subprocesses. It does not change telemetry consent, edit shell startup files, or alter the global environment. For direct CLI commands in a restricted IDE, use the same variables in that IDE's narrow run configuration when organizational policy permits it.

## Live diagnostics and common errors

Use `supa.cc doctor --account <name> --live` only when you want to authorize reading and online validation of the selected account. HTTP 401 indicates a rejected PAT; network failure, missing or incompatible CLI, locked storage, and `EPERM` are distinct categories. An `EPERM` restricted to a sandbox does not prove that the token is invalid.

Failure categories identify the phase that needs remediation:

- `credential_missing` means the listed alias remains in local state but its PAT was removed from native storage. Run `switch` and provide a replacement PAT in the hidden prompt.
- `keychain_configuration_invalid` means the default macOS Keychain routing must be restored in Keychain Access before credential operations can begin.
- `keychain_permission_denied` means the native credential store denied one of the participating executable identities.
- `token_rejected` means the Supabase API rejected the selected PAT during validation.
- `native_login_failed` means the CLI did not complete session persistence after validation.
- `native_verification_failed` means the CLI could not recover and use the session without the PAT environment override.
- `profile_mismatch` means state outside the supported official `supabase` profile was detected.
- `environment_blocked` covers sandbox, filesystem, execution, or telemetry restrictions; it is not an authentication result.
- `network_failure` and `cli_incompatible` remain independent of local credential storage.

Corrupt or conflicting local state is reported as `state_invalid`; it is never silently repaired. Preserve the files for diagnosis. Interrupted operations leave a token-free pending transition in `state.json`; run a mutating Supa.cc command again to trigger idempotent recovery. Do not manually edit the state document or native credentials. The lock does not coordinate external `supabase` commands, so avoid running them at the same time as an activation.
