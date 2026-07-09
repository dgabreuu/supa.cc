# Installation

Supa.cc is a macOS CLI. It stores tokens in the macOS Keychain and expects the Supabase CLI to be available as `supabase`.

## Homebrew

```bash
brew tap dgabreuu/supa-cc https://github.com/dgabreuu/supa.cc.git
brew install --HEAD supa-cc
```

`--HEAD` instala a versão atual do branch `main`. Depois da primeira release estável, a fórmula poderá ser instalada sem `--HEAD`:

```bash
brew install supa-cc
```

The installed command is:

```bash
supa.cc
```

Upgrade and uninstall:

```bash
brew update
brew upgrade --fetch-HEAD supa-cc
brew uninstall supa-cc
```

## pipx

```bash
pipx install "git+https://github.com/dgabreuu/supa.cc.git"
```

For local development:

```bash
python3 -m pip install -e ".[dev]"
```

## Requirements

- macOS.
- Python 3.9 or newer.
- Supabase CLI installed and available on `PATH`.
- A Supabase Personal Access Token for each local account.
