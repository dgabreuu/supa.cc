# Agent instructions

Keep every contribution generic and safe for this public open source repository.

## Structure

| Path | Responsibility |
| --- | --- |
| `supa_cc/` | Python source code |
| `tests/` | `pytest` suite |
| `docs/` | Installation, usage, security, remediation, and release documentation |
| `.agents/skills/supa-cc/` | Portable coding-agent skill and operational references |
| `Formula/` | Homebrew formula |
| `pyproject.toml` | Metadata, dependencies, build, and tooling |
| `README.md` | Concise public overview |

## Conventions

- Python 3.11+, builds with `hatchling`, and the `supa.cc` console script.
- Follow the existing patterns in `supa_cc/`, keep files focused, and cover behavior changes in `tests/`.
- Runtime dependencies are `click`, `questionary`, and `keyring`. Development dependencies are declared in `pyproject.toml`.
- Run `python3 -m pytest`; see [Contributing](CONTRIBUTING.md) for environment setup, builds, and native smoke tests.
- Update the corresponding canonical document: [Installation](docs/installation.md), [Usage](docs/usage.md), [Security](docs/security.md), or [Troubleshooting](docs/troubleshooting.md).

## GitHub

- The official repository is `https://github.com/dgabreuu/supa.cc.git`.
- GitHub operations use the `dgabreuu` account; do not suggest another account, SSH key, or remote.
- Use concise commit messages aligned with the existing history.

## Public security

- Never expose real PATs in code, tests, logs, documentation, prompts, or transcripts. Accepted formats begin with `sbp_` or `sbp_oauth_` and are validated before storage; do not publish credential-shaped examples.
- Do not publish absolute local paths, personal email addresses, usernames, private remotes, complete environment dumps, or native credential-store contents.
- Do not introduce a plaintext fallback, `keyrings.alt`, or unsupported backends. Preserve the operational invariants in the [Supa.cc skill](.agents/skills/supa-cc/SKILL.md) and the [security model](docs/security.md).
- Preserve the native backends: Keychain on macOS, Secret Service on Linux, and Windows Credential Manager through `WinVaultKeyring` on Windows.
- Before publishing, review history, ignored files, logs, caches, virtual environments, fixtures, and screenshots for secrets.
