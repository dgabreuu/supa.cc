![Supa.cc showing the compact home and available terminal actions](https://raw.githubusercontent.com/dgabreuu/supa.cc/main/assets/terminal.svg)

# Supa.cc

> Switch between multiple Supabase accounts from one local CLI.

[![PyPI version](https://img.shields.io/pypi/v/supa.cc?label=PyPI)](https://pypi.org/project/supa.cc/)
[![Python versions](https://img.shields.io/pypi/pyversions/supa.cc?label=Python)](https://pypi.org/project/supa.cc/)
[![License](https://img.shields.io/github/license/dgabreuu/supa.cc?label=License)](https://github.com/dgabreuu/supa.cc/blob/main/LICENSE)

```text
 ____
/ ___| _   _ _ __   __ _   ___ ___
\___ \| | | | '_ \ / _` | / __/ __|
 ___) | |_| | |_) | (_| || (_| (__
|____/ \__,_| .__/ \__,_(_)___\___|
            |_|
```

Supa.cc manages multiple Supabase accounts locally while keeping Personal Access Tokens in Keychain, Secret Service, or Windows Credential Manager. The public source is available from the [official repository](https://github.com/dgabreuu/supa.cc.git).

## 📦 Installation

Supa.cc requires Python 3.11+ and the [official Supabase CLI](https://supabase.com/docs/guides/local-development/cli/getting-started) 2.109.1 or newer. The recommended path is the immutable `v0.5.4` bootstrap for your operating system.

| Platform | Recommended method | Native credential store |
| --- | --- | --- |
| macOS | POSIX bootstrap (`install.sh`) | Keychain |
| Debian/Ubuntu, Arch Linux, and Fedora | POSIX bootstrap (`install.sh`) | Secret Service |
| Windows | PowerShell bootstrap (`install.ps1`) | Windows Credential Manager |

The bootstrap detects supported dependencies, configures the current session's `PATH`, installs or updates the required components, and runs `supa.cc doctor --installation-check`. An administrator password, Homebrew installation prompt, or native credential-store unlock may still be requested by the operating system.

### 🍎 macOS

```bash
curl -fsSL https://raw.githubusercontent.com/dgabreuu/supa.cc/v0.5.4/install.sh | bash
```

### 🐧 Linux

```bash
curl -fsSL https://raw.githubusercontent.com/dgabreuu/supa.cc/v0.5.4/install.sh | bash
```

### 🪟 Windows

```powershell
irm https://raw.githubusercontent.com/dgabreuu/supa.cc/v0.5.4/install.ps1 | iex
```

The [installation guide](https://github.com/dgabreuu/supa.cc/blob/main/docs/installation.md) covers prerequisites, manual Homebrew and `pipx` fallbacks, verification, upgrades, uninstallation, and platform-specific remediation.

## 🔐 Security

PATs are accepted only through hidden prompts, stored only in the platform-native credential store, and never passed as command-line arguments. Read the [security model](https://github.com/dgabreuu/supa.cc/blob/main/docs/security.md) and [safe troubleshooting guide](https://github.com/dgabreuu/supa.cc/blob/main/docs/troubleshooting.md) before sharing diagnostics or changing an installation.

## 📄 License

Supa.cc is released under the [MIT license](https://github.com/dgabreuu/supa.cc/blob/main/LICENSE).
