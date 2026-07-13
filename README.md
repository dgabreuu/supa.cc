```text
 ____
/ ___| _   _ _ __   __ _   ___ ___
\___ \| | | | '_ \ / _` | / __/ __|
 ___) | |_| | |_) | (_| || (_| (__
|____/ \__,_| .__/ \__,_(_)___\___|
            |_|
```

# Supa.cc

Supa.cc is a local CLI for switching between multiple Supabase accounts without spreading Personal Access Tokens (PATs) across files or commands. The primary experience is a TUI; after activation, `supabase` itself uses the selected account.

| Platform | Support | Native credential |
| --- | --- | --- |
| macOS | Supported | Keychain |
| Debian/Ubuntu, Arch Linux, and Fedora | Supported; derivatives are best-effort | Secret Service |
| Windows | Supported | Windows Credential Manager |

Requires Python 3.11+ and the [official Supabase CLI](https://supabase.com/docs/guides/local-development/cli/getting-started) >= 2.109.1 on `PATH`.

![Supa.cc showing the compact home and available terminal actions](https://raw.githubusercontent.com/dgabreuu/supa.cc/main/assets/terminal.svg)

## Installation

Prerequisites, upgrades, and uninstallation are covered in the [installation guide](https://github.com/dgabreuu/supa.cc/blob/main/docs/installation.md).

### macOS

```bash
brew tap dgabreuu/supa-cc https://github.com/dgabreuu/supa.cc.git
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

## Security

PATs remain only in each platform's native credential store; no local file contains a PAT. The token reaches the Supabase CLI through the process environment, never through a command-line argument. See the [security model](https://github.com/dgabreuu/supa.cc/blob/main/docs/security.md) for guarantees and limits.

## License

MIT. See the [full license](https://github.com/dgabreuu/supa.cc/blob/main/LICENSE).
