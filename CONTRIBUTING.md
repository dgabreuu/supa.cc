# Contributing

Thank you for contributing to Supa.cc. Use [GitHub Issues](https://github.com/dgabreuu/supa.cc/issues) for bugs, installation problems, and feature proposals. Report vulnerabilities exclusively through the [security policy](SECURITY.md).

## Development environment

The project requires Python 3.11 or newer. Fork and clone the repository, then install the package with its development dependencies.

### macOS and Linux (POSIX)

```bash
python3 -m pip install -e ".[dev]"
python3 -m pytest
```

### Windows

```powershell
py -m pip install -e ".[dev]"
py -m pytest
```

For packaging changes, also run:

```text
python3 scripts/security_scan.py --worktree --history
python3 -m pytest --cache-clear --collect-only -q
python3 scripts/security_scan.py --path .pytest_cache
python3 -m build
python3 scripts/inspect_artifacts.py dist
# Windows: replace python3 with py
```

## Native smoke tests

Tests that access a real native credential store are opt-in, platform-specific, and require explicit consent. Each test creates the `supa.cc.tests.<uuid>` service and the `smoke-<uuid>` account, both removed in `finally`; it never accesses the canonical Supa.cc service or Supabase CLI credentials.

```bash
SUPA_CC_RUN_KEYCHAIN_SMOKE=1 .venv/bin/pytest -q tests/test_macos_keychain_smoke.py
SUPA_CC_REAL_SECRET_SERVICE=1 .venv/bin/pytest -q tests/test_linux_secret_service_smoke.py
SUPA_CC_RUN_WINDOWS_CREDENTIAL_MANAGER_SMOKE=1 .venv/bin/pytest -q tests/test_windows_credential_manager_smoke.py
```

## Guidelines

- Keep changes small and focused, with tests whenever behavior changes.
- Preserve support for macOS, Debian/Ubuntu, Arch Linux, Fedora, and Windows as documented.
- Update public documentation when commands or behavior change.
- Describe how the change was validated.

## Sensitive data

Never include PATs, Supabase tokens, native credential-store items, credential dumps, or complete environment dumps in issues, pull requests, tests, logs, or documentation. Use only fictional data that does not resemble a real credential.
