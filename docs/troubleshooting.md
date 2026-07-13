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

## Live diagnostics and common errors

Use `supa.cc doctor --account <name> --live` only when you want to authorize reading and online validation of the selected account. HTTP 401 indicates a rejected PAT; network failure, missing or incompatible CLI, locked storage, and `EPERM` are distinct categories. An `EPERM` restricted to a sandbox does not prove that the token is invalid.

Interrupted operations may leave a token-free recovery journal. Run a mutating Supa.cc command again; do not manually delete the journal, locks, index, or credentials. The lock does not coordinate external `supabase` commands, so avoid running them at the same time as an activation.
