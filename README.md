![Supa.cc showing the compact home and available terminal actions](https://raw.githubusercontent.com/dgabreuu/supa.cc/main/assets/terminal.svg)

# Supa.cc

> Switch between multiple Supabase accounts from one local CLI.

[![PyPI version](https://img.shields.io/pypi/v/supa.cc?label=PyPI)](https://pypi.org/project/supa.cc/)
[![Python versions](https://img.shields.io/pypi/pyversions/supa.cc?label=Python)](https://pypi.org/project/supa.cc/)
[![License](https://img.shields.io/github/license/dgabreuu/supa.cc?label=License)](LICENSE)

Supa.cc is a local CLI for managing multiple Supabase accounts without spreading Personal Access Tokens (PATs) across files or commands. After activation, the official `supabase` CLI uses the selected account.

## ✨ Why Supa.cc?

- **Switch accounts locally.** Move between Supabase accounts without changing your everyday CLI workflow.
- **Use native credential storage.** PATs stay in Keychain, Secret Service, or Windows Credential Manager instead of local files.
- **Keep using the official CLI.** Activate an account with Supa.cc, then run `supabase` normally.

## 🧩 Supported platforms

| Platform | Installation channel | Native credential store |
| --- | --- | --- |
| macOS | Homebrew | Keychain |
| Debian/Ubuntu, Arch Linux, and Fedora | `pipx` | Secret Service |
| Windows | `pipx` | Windows Credential Manager |

Supa.cc requires Python 3.11+ and the [official Supabase CLI](https://supabase.com/docs/guides/local-development/cli/getting-started) >= 2.109.1 on `PATH`. Linux derivatives are best-effort; a user D-Bus session and an unlocked Secret Service are required.

## 📦 Installation

Install the official Supabase CLI first, then choose the stable installation for your platform.

### macOS

```bash
brew tap dgabreuu/supa-cc https://github.com/dgabreuu/supa.cc.git
brew install supabase/tap/supabase
brew install dgabreuu/supa-cc/supa-cc
```

### Linux

```bash
pipx install supa.cc
```

### Windows

```powershell
pipx install supa.cc
```

See the [installation guide](docs/installation.md) for prerequisites, verification, upgrades, uninstallation, and platform-specific remediation.

## 🚀 First use

1. Create a Personal Access Token on the [official Supabase token page](https://supabase.com/dashboard/account/tokens). Never put the PAT in commands, files, logs, or reports.
2. Open the interactive interface:

   ```bash
   supa.cc
   ```

3. Choose **Add account**, enter a local name, provide the PAT in the hidden prompt, and then choose **Switch active account**.
4. Verify the activated session:

   ```bash
   supabase projects list
   ```

Supa.cc validates the selected account before marking it active. The [usage guide](docs/usage.md) covers account management, isolated commands, diagnostics, and the complete command reference.

## 🛠️ Essential commands

| Command | Purpose |
| --- | --- |
| `supa.cc` | Open the interactive account switcher |
| `supa.cc add <name>` | Add or update an account |
| `supa.cc list` | List registered account names |
| `supa.cc switch <name>` | Validate and activate an account |
| `supa.cc remove <name> [--yes]` | Remove an account |
| `supa.cc doctor` | Generate a local, non-live diagnostic |

Use the [usage guide](docs/usage.md) for reset, isolated execution, live diagnostics, and all supported options.

## 📚 Documentation

| Guide | Covers |
| --- | --- |
| [Installation](docs/installation.md) | Prerequisites, stable channels, upgrades, and uninstallation |
| [Usage](docs/usage.md) | TUI workflow, account commands, and diagnostics |
| [Security model](docs/security.md) | Credential storage, activation, recovery, and platform limits |
| [Troubleshooting](docs/troubleshooting.md) | Safe remediation for supported platforms |

> 🔐 Supa.cc stores PATs only in each platform's native credential store and never passes them as command-line arguments. Read the [security model](docs/security.md) before sharing diagnostics or changing an installation.

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, testing, native smoke tests, and contribution guidelines.

## 📄 License

Supa.cc is released under the MIT license. See the [full license](LICENSE).
