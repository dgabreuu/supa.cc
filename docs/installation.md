# Installation

This guide covers the supported installation lifecycle. Supa.cc requires Python 3.11+ and the [official Supabase CLI](https://supabase.com/docs/guides/local-development/cli/getting-started) 2.109.1 or newer.

## Official bootstrap rollout

`install.sh` and `install.ps1` make the installation self-sufficient: they inspect the environment, reject conflicting installation channels, show one plan, request at most one installation confirmation, install missing requirements, update the current session's `PATH`, and finish with `supa.cc doctor --installation-check`. That final command validates installation dependencies only: the supported environment, Supabase CLI compatibility, a writable Supabase CLI operational directory (`SUPABASE_HOME` or its default), and one isolated native credential-store probe. A failure means the diagnostic shown above identified a blocked requirement; it does not necessarily mean the credential store failed.

The public bootstrap URL uses the reviewed immutable `v0.5.6` release tag. It must never point to `main`, `HEAD`, a branch, or an unpublished tag:

```bash
curl -fsSL https://raw.githubusercontent.com/dgabreuu/supa.cc/v0.5.6/install.sh | bash
```

```powershell
irm https://raw.githubusercontent.com/dgabreuu/supa.cc/v0.5.6/install.ps1 | iex
```

Use `--dry-run` or `-DryRun` from a downloaded script when the plan must be reviewed without changes. `--yes` and `-Yes` skip only Supa.cc's confirmation; administrator passwords and native operating-system prompts remain under system control. The POSIX installer reads confirmation from `/dev/tty`, so a piped non-interactive run must use `--yes` after review.

Downloads come only from the official Homebrew, Python, Supabase, PyPI, and project sources. Release archives require their official SHA-256 checksum. Temporary files are removed on success and failure. Neither installer creates, unlocks, weakens, or replaces a native credential store.

## Installation by platform

### Homebrew (macOS only)

The immutable bootstrap above is the recommended path. The stable manual channel is Homebrew and stores PATs in Keychain; use it only as an advanced fallback when Homebrew is already managed separately. The bootstrap can install Homebrew from a reviewed immutable revision, load `brew shellenv`, and install the two fully qualified formulae. An administrator password or the normal Homebrew installer interaction may still be required.

The commands below are the manual fallback and are not required after a successful bootstrap.

#### Install

```bash
brew tap dgabreuu/supa-cc https://github.com/dgabreuu/supa.cc.git
brew install supabase/tap/supabase
brew install dgabreuu/supa-cc/supa-cc
```

Fully qualified formula names keep trust limited to the selected Supabase CLI and Supa.cc formulae. Do not trust the complete tap or disable Homebrew's trust protection.

#### Verify

```bash
supa.cc --version
supa.cc doctor --installation-check
```

The installation check executes `supabase --version` and performs an isolated Keychain availability probe. It does not read an account or PAT. A locked Keychain must be unlocked through macOS before retrying.

#### Upgrade

```bash
brew upgrade dgabreuu/supa-cc/supa-cc
```

#### Uninstall

Run `supa.cc reset --all` first only when the intent is to remove Supa.cc accounts and native credentials. Package removal alone preserves them.

```bash
brew uninstall supa-cc
```

### Linux (pipx only)

Debian 12+, Ubuntu 24.04+, Arch Linux, and Fedora are directly supported. These minimum Debian/Ubuntu releases guarantee a distribution Python that satisfies Python 3.11+ without introducing an unofficial runtime source. Derivatives are resolved best-effort through ordered `ID_LIKE` compatibility metadata. A derivative must provide working Python 3.11+ through the resolved compatible package family; its own `VERSION_ID` is not interpreted as the base distribution's version. The stable package channel is PyPI through `pipx`; PATs remain in Secret Service on the user-session D-Bus.

The immutable bootstrap above is the recommended path. The bootstrap uses a shared flow with distribution-specific package data. It installs Python, venv support where needed, `pipx`, GNOME Keyring, download tools, and CA certificates. The Python `keyring` dependency already supplies SecretStorage and Jeepney, so `libsecret-tools` and separate `libsecret` packages are not installed explicitly.

Manual prerequisite commands are available as an advanced fallback:

```bash
# Debian or Ubuntu
sudo apt install python3 python3-venv pipx gnome-keyring curl ca-certificates tar

# Arch Linux
sudo pacman -S python python-pipx gnome-keyring curl ca-certificates tar

# Fedora
sudo dnf install python3 pipx gnome-keyring curl ca-certificates tar
```

The bootstrap downloads the official x64 or arm64 Supabase CLI archive and `checksums.txt`, requires a matching SHA-256, and installs it in the user's executable directory. It runs `pipx ensurepath` and updates the current session so reopening the shell is normally unnecessary.

The command below is the manual `pipx` fallback and is not required after a successful bootstrap.

#### Install

```bash
pipx install supa.cc
```

#### Verify

```bash
supa.cc --version
supa.cc doctor --installation-check
```

A real user D-Bus session and an unlocked Secret Service collection are required. The installer never creates or unlocks a collection. In a headless session, container, or incomplete login session, it stops safely with a remediation and retry instruction—never with plaintext, `keyrings.alt`, or a fallback backend.

#### Upgrade

```bash
pipx upgrade supa.cc
```

#### Uninstall

Run `supa.cc reset --all` first only when native credentials should also be removed.

```bash
pipx uninstall supa.cc
```

Secret-free state is stored in `$XDG_CONFIG_HOME/supa.cc` when defined, otherwise in `~/.config/supa.cc`.

### Windows (pipx only)

The stable package channel is PyPI through `pipx`; PATs remain in Windows Credential Manager through `WinVaultKeyring` and secret-free metadata remains under `%APPDATA%\supa.cc`.

The immutable bootstrap above is the recommended path. It reuses Python 3.11+ when available. Otherwise it installs Python for the current user with `winget`; if `winget` is unavailable, it downloads a fixed official Python x64 or arm64 installer and requires its pinned SHA-256 before silent execution. It then installs `pipx`, updates both the persistent user `PATH` and current PowerShell session, downloads and verifies the official Supabase CLI archive, and installs Supa.cc from PyPI without requiring a PowerShell restart.

Manual setup is available as an advanced fallback:

```powershell
py -m pip install --user pipx
py -m pipx ensurepath
```

The commands below are the manual `pipx` fallback and are not required after a successful bootstrap.

#### Install

```powershell
pipx install supa.cc
```

#### Verify

```powershell
supa.cc --version
supa.cc doctor --installation-check
```

The installation check probes Windows Credential Manager without reading or modifying existing credentials, ACLs, or policy.

#### Upgrade

```powershell
pipx upgrade supa.cc
```

#### Uninstall

Run `supa.cc reset --all` first only when native credentials should also be removed.

```powershell
pipx uninstall supa.cc
```

## After installation

Continue with [first use](usage.md#first-use-with-the-tui). The default `supa.cc doctor` remains non-live and does not probe credential availability; only `--installation-check` performs one isolated local probe with random identifiers. The installation check does not read an account or PAT and does not load, create, migrate, validate, or recover account state. Account, index, and activation fields outside this scope are reported as `not_checked` or **not checked**. It is incompatible with `--live` and `--account` and can be combined with `--json`.

To manage Supa.cc through OpenCode, Claude Code, Codex, or Cursor, install the separate [portable coding-agent skill](agent-skill.md). Installing the Python package does not install agent instructions.

Before changing channels, follow [safe reinstallation](troubleshooting.md#safe-reinstallation). Credential-store and blocked-environment remediation is documented in [Troubleshooting](troubleshooting.md), and state guarantees are documented in [Security](security.md).
