# Installation

This guide covers prerequisites and the complete installation lifecycle for each platform. Stable commands are instructions for releases published through the respective channel.

On every platform, install the [official Supabase CLI](https://supabase.com/docs/guides/local-development/cli/getting-started) >= 2.109.1 first and confirm that `supabase` is on `PATH`. Supa.cc requires Python 3.11+.

## Installation by platform

### Homebrew (macOS only)

#### Prerequisites

Install Homebrew and the official Supabase CLI. The stable channel uses Homebrew and stores PATs in Keychain.

#### Install

```bash
brew tap dgabreuu/supa-cc https://github.com/dgabreuu/supa.cc.git
brew install supabase/tap/supabase
brew install dgabreuu/supa-cc/supa-cc
```

The fully qualified formula names record trust only for the Supabase CLI and
Supa.cc while leaving both non-official taps untrusted. Run the Supabase CLI
command even when it is already installed so Homebrew records its formula-scoped
trust before evaluating Supa.cc's dependency.

#### Verify

```bash
supa.cc --version
```

#### Upgrade

```bash
brew upgrade dgabreuu/supa-cc/supa-cc
```

#### Uninstall

To remove Supa.cc accounts and PATs intentionally before uninstalling, run `supa.cc reset --all`. Package removal alone preserves credentials.

```bash
brew uninstall supa-cc
```

The installed Python runtime accesses Keychain. A path, environment, or signature change may request one new authorization; repeated prompts without a change should be diagnosed, not bypassed.

### Linux (pipx only)

Debian/Ubuntu, Arch Linux, and Fedora are supported; derivatives are best-effort. The stable installation is available only through `pipx`.

#### Prerequisites

Install Python, `pipx`, Secret Service, and its tools with your distribution's command:

```bash
# Debian or Ubuntu
sudo apt install python3 python3-venv pipx gnome-keyring libsecret-tools

# Arch Linux
sudo pacman -S python python-pipx gnome-keyring libsecret

# Fedora
sudo dnf install python3 pipx gnome-keyring libsecret
```

Run `pipx ensurepath` and reopen the shell if instructed. A user D-Bus and an unlocked Secret Service are required. Headless sessions without these services fail safely, without plaintext, `keyrings.alt`, or an alternative backend.

#### Install

```bash
pipx install supa.cc
```

#### Verify

```bash
supa.cc --version
```

#### Upgrade

```bash
pipx upgrade supa.cc
```

#### Uninstall

Optionally run `supa.cc reset --all` first when the intent is to remove all Supa.cc credentials and state. `pipx uninstall` alone preserves them.

```bash
pipx uninstall supa.cc
```

After installation, run `supa.cc doctor`. Secret-free state is stored in `$XDG_CONFIG_HOME/supa.cc` when the variable is defined, or in `~/.config/supa.cc`.

### Windows (pipx only)

The stable installation is available only through `pipx`. PATs are stored in Windows Credential Manager exclusively through the `WinVaultKeyring` backend; secret-free metadata is stored in `%APPDATA%\supa.cc`.

#### Prerequisites in PowerShell

Install Python 3.11+ for the current user and the official Supabase CLI. Then install and configure `pipx`:

```powershell
py -m pip install --user pipx
py -m pipx ensurepath
```

Close and reopen PowerShell to apply `PATH`. Confirm that `pipx` and `supabase` are found before continuing. `%APPDATA%` must exist and be an absolute path.

#### Install

```powershell
pipx install supa.cc
```

#### Verify

```powershell
supa.cc --version
```

#### Upgrade

```powershell
pipx upgrade supa.cc
```

#### Uninstall

Optionally run `supa.cc reset --all` first when the intent is to remove all Supa.cc credentials and state. `pipx uninstall` alone preserves them.

```powershell
pipx uninstall supa.cc
```

If `supa.cc` is not found after reopening the shell, run `py -m pipx ensurepath` again and see [Troubleshooting](troubleshooting.md#windows).

## Development wheel

Version `0.5.0.dev1` identifies the current development package and remains separate from the stable Homebrew formula. From a reviewed source checkout with the development dependencies installed, build and install the wheel rather than leaving an editable checkout on `PATH`:

```bash
python3 -m build
pipx install --force dist/supa_cc-0.5.0.dev1-py3-none-any.whl
supa.cc --version
```

The verification output must include `Installation channel: wheel`. If it reports `editable`, the command is still bound to a source checkout; if it reports another version, locate the executable selected by `PATH` before testing credentials. Do not keep stable, editable, and development-wheel commands active simultaneously.

## After installation

Follow [first use with the TUI](usage.md#first-use-with-the-tui). The default diagnostic shows the backend as configured but not verified: it does not test D-Bus or open credential storage. Before changing the installation method, follow [safe reinstallation](troubleshooting.md#safe-reinstallation). Details about Keychain, Secret Service, and Credential Manager are in [Troubleshooting](troubleshooting.md); state and rollback guarantees are in [Security](security.md).
