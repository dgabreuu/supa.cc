# Changelog

All notable changes to this project will be documented in this file.
The format follows Keep a Changelog in a simplified form.

## [0.4.0] - 2026-07-13

### Changed

- The minimum supported runtime is now Python 3.11.
- `doctor --json` represents `active_account` with `selected` and `indexed` booleans, sanitizes local paths, and includes `path_relation` for executable paths.
- `supa.cc version` is deterministic and no longer contacts the Git remote.
- The TUI keeps Questionary, arrow navigation, the banner, and the `#00D388` identity while using a shorter home with Add, Switch, Remove, and Exit. The redundant list-only action and Rich spinner were removed.
- Runtime dependencies are now Click, Questionary, and keyring; removing Rich also removes Markdown-It, mdurl, and Pygments from new installations.
- Account, session, and token policy code is grouped by feature while compatibility facades preserve existing internal import paths.

### Performance

- Streaming PAT redaction copies ordinary output in slices and preserves candidate state across chunks.
- Account mutations reuse a completed Supabase CLI preflight instead of spawning the same validation twice.
- TUI, installer, integration, and keyring imports are deferred until their handlers need them, reducing `--help` startup work.
- PyPI sdists exclude tests, screenshots, scripts, and packaging formulae.

### Security

- Account representations never include PATs, and unit tests isolate all user-state directories and native-storage access.
- Standard diagnostics omit account names and identifying local paths.
- Linux uses descriptor-bound CLI execution; macOS uses a validated path with an open handle, trusted ancestors, and immediate identity revalidation; Windows keeps its path/descriptor identity checks without unsupported ACL claims.
- CI and release gates scan tracked files, full reachable history, pytest metadata, wheel, and sdist without echoing matches.
- GitHub Actions are pinned by commit, checkout credentials are not persisted, container images are pinned by digest, and dependency auditing has no Python 3.9 exceptions.

[0.4.0]: https://github.com/dgabreuu/supa.cc/compare/v0.3.0...v0.4.0

## [0.3.0] - 2026-07-12

### Added

- Support for Debian/Ubuntu, Arch Linux, and Fedora with Secret Service, plus Windows Credential Manager support.
- Safe diagnostics with `doctor`, JSON output, and explicit authenticated validation through `--account <name> --live`.
- Native session synchronization for the official `supabase` profile when activating or removing the active account.

### Changed

- Account switching now verifies the Supabase CLI's effective native session and maintains coordination state without secrets.
- Credential storage and state paths are now selected according to macOS, Linux, or Windows.

### Security

- Credential backends are restricted to Keychain, Secret Service, or `WinVaultKeyring`, with no plaintext fallback.
- On macOS and Linux, the Supabase CLI executable is validated by type, executability, ownership, and modes; on Windows, regular-file and path identity checks avoid unsupported ACL or POSIX-mode claims.
- The native credential and recovery operations are verified before sensitive changes complete.
- Locks and recovery metadata make session updates resilient to interruptions between stages.

### Migration from 0.2.0

- On macOS, 0.3.0 preserves the `supa.cc.supabase.accounts.v2` credential service and `~/.config/supa.cc/accounts.json` index used by 0.2.0.
- Linux and Windows are new channels in 0.3.0 and therefore have no 0.2.0 state to migrate on those systems.

[0.3.0]: https://github.com/dgabreuu/supa.cc/compare/v0.2.0...v0.3.0
