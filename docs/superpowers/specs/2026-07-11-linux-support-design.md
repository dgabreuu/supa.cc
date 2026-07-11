# Linux Support Design

## Scope

Supa.cc will support macOS, Debian/Ubuntu, Arch Linux, and Fedora. Existing
macOS behavior and stored credentials must remain compatible. Windows and
other Linux distributions are outside this change.

Linux support is limited to user environments with a running, unlocked
Freedesktop Secret Service. A missing D-Bus session, unavailable Secret
Service provider, or insecure credential backend fails safely. Supa.cc will
not store tokens in plaintext or use `keyrings.alt` as a fallback.

The CLI will detect the operating system and supported Linux distribution to
choose its credential policy and show installation guidance. It will never
invoke `sudo`, `apt`, `pacman`, or `dnf`.

## Architecture

### Environment Detection

A small environment module will detect macOS or Linux and parse
`/etc/os-release` on Linux. It will identify Debian, Ubuntu, Arch, and Fedora
from `ID`, with `ID_LIKE` used only to recognize compatible variants of those
families. Detection receives injectable platform and file-reading inputs for
unit tests and returns a typed result rather than executing shell commands.

Unsupported operating systems and unrecognized Linux distributions have
explicit diagnostic results. They must not silently select a generic or
insecure credential backend.

### Credential Storage

A credential-store boundary owns get, set, delete, backend description, and
availability validation. The application composition selects one explicit
backend:

- macOS uses the macOS Keychain keyring backend.
- Supported Linux uses the Secret Service keyring backend.

The existing service identifier, `supa.cc.supabase.accounts.v2`, remains
unchanged, so existing macOS credentials continue to resolve. Backend errors
are translated to neutral credential-store domain errors without including
tokens or backend exception details in user output.

The Linux policy rejects null, fail, plaintext, and alternative insecure
backends. Headless or locked-session failures explain the missing Secret
Service prerequisite rather than offering insecure persistence.

### Account State

The account-name index remains JSON and contains no tokens. Its existing
atomic-write, restrictive-permission, and POSIX-locking behavior remains in
place. Credential operations move behind the credential-store boundary while
the account repository retains the transaction and rollback between a token
write/delete and index update.

The serialized index format and active-account format remain unchanged.

### Paths

macOS preserves `~/.config/supa.cc` for backward compatibility. Linux uses
`$XDG_CONFIG_HOME/supa.cc` when available, otherwise `~/.config/supa.cc`.
Path resolution happens at runtime, not module import time. Directory and file
permissions remain `0700` and `0600` respectively.

### Installation Guidance

An installation-guidance module maps the detected environment to static,
displayable prerequisites:

- Debian/Ubuntu: apt packages for Python, pipx, GNOME Keyring, and Secret
  Service support.
- Arch: pacman packages for Python/pipx, GNOME Keyring, and libsecret.
- Fedora: dnf packages for pipx, GNOME Keyring, and libsecret.
- macOS: Homebrew is the primary route and pipx remains an alternative.

Supa.cc installation uses pipx on Linux. Supabase CLI installation remains a
separate documented prerequisite. The guidance is informational only.

### Diagnostics

`supa.cc doctor` will report the detected operating system, Linux
distribution, selected credential backend, backend security/availability, and
environment-specific remediation. macOS-only code-signature inspection will
run only on macOS. Linux will not present missing macOS provenance as an
error.

CLI, TUI, and public domain messages will use neutral credential-store wording
instead of macOS-only Keychain terminology. Existing behavior codes remain
stable where practical.

## Data Flow

At startup, application composition detects the environment, resolves paths,
and constructs the credential store. Account add, switch, run, list, and
remove continue through `AccountManager`; only the account repository's token
operations change implementation. Token transport to the Supabase CLI remains
limited to the child environment variable `SUPABASE_ACCESS_TOKEN`.

`doctor` uses the same environment and credential-store composition, but must
not read a stored token.

## Testing

Unit tests will use injected environment data and fake backend objects. They
will cover supported and unsupported operating systems, `os-release` parsing,
XDG paths, backend policy, unavailable Secret Service, missing credential
semantics, transactional rollback, diagnostics, and installation guidance.

An opt-in Linux integration smoke test will exercise a disposable Secret
Service session and clean up its unique test entry. Existing macOS smoke tests
remain opt-in. CI will cover Linux packaging and tests, including Debian, Arch,
and Fedora container validation where practical.

## Documentation And Packaging

Project metadata and public documentation will declare the supported Linux
platforms. Installation documentation will provide per-distribution commands,
explain D-Bus/Secret Service requirements, and explicitly prohibit plaintext
fallbacks. The Homebrew formula remains macOS-only.

## Acceptance Criteria

- Existing macOS tokens work without migration.
- Each supported Linux distribution is detected and receives matching
  guidance.
- Linux writes tokens only through Secret Service.
- Missing or insecure credential storage blocks token operations safely.
- No token is written to the account index, command arguments, diagnostics, or
  public errors.
- The CLI does not execute system package managers.
- Existing account-state formats and Supabase CLI token transport are
  preserved.
