# Linux Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Support macOS and Debian/Ubuntu, Arch Linux, and Fedora with explicit secure credential backends and platform-specific installation guidance.

**Architecture:** Add a small environment model that detects the operating system and supported Linux distribution, then compose paths and a credential store from it. Keep `KeychainManager` as the account-index and account-transaction owner, but inject an explicit credential store so its account API and serialized state remain compatible. Diagnostics and update guidance consume the same environment model.

**Tech Stack:** Python 3.9+, Click, keyring, pytest, Hatchling.

## Global Constraints

- Support only macOS, Debian/Ubuntu, Arch Linux, and Fedora.
- Preserve the `supa.cc.supabase.accounts.v2` service name and existing account-index and active-account file formats.
- macOS uses the macOS Keychain keyring backend; supported Linux uses Secret Service only.
- Reject unavailable, null, fail, plaintext, and alternative keyring backends; never persist tokens outside the system credential store.
- Linux without D-Bus or an unlocked Secret Service must fail safely with sanitized remediation guidance.
- Linux honors `XDG_CONFIG_HOME`; macOS retains `~/.config/supa.cc`.
- Never execute `sudo`, `apt`, `pacman`, or `dnf` from the CLI.
- Keep PATs out of argv, logs, diagnostics, index files, and public errors.
- Use ASCII in new source and documentation unless the target file already requires non-ASCII text.

---

## File Structure

- Create `supa_cc/environment.py`: platform, Linux-distribution, and runtime-path models; pure detection and os-release parsing.
- Create `supa_cc/credentials.py`: explicit macOS/Secret-Service keyring selection and sanitized credential operations.
- Create `supa_cc/installation.py`: static installation/update guidance for supported environments.
- Modify `supa_cc/auth.py`: neutral credential-store errors, stable failure-code mapping, and runtime active-account paths.
- Modify `supa_cc/keychain.py`: inject `CredentialStore`, retain account-index locking, cache, and transaction semantics.
- Modify `supa_cc/accounts.py`: construct the environment-aware manager and catch neutral credential errors.
- Modify `supa_cc/diagnostics.py`: report environment and credential-store availability without reading tokens.
- Modify `supa_cc/__main__.py`: use detected update guidance.
- Modify `pyproject.toml`, `README.md`, `docs/installation.md`, `SKILL.md`, and `AGENTS.md`: publish the supported platform/security contract.
- Create `tests/test_environment.py`, `tests/test_credentials.py`, and `tests/test_installation.py`; modify existing account, CLI, diagnostic, auth, and project-identity tests.

### Task 1: Add Environment Detection And Runtime Paths

**Files:**
- Create: `supa_cc/environment.py`
- Create: `tests/test_environment.py`
- Modify: `supa_cc/auth.py:1-12`
- Test: `tests/test_auth.py`

**Interfaces:**
- Produces `OperatingSystem`, `LinuxDistribution`, `Environment`, `detect_environment()`, and `config_directory()`.
- `ActiveAccountStore` consumes `config_directory()` when no explicit path is passed.

- [ ] **Step 1: Write failing detection and path tests**

```python
from pathlib import Path

from supa_cc.environment import (
    LinuxDistribution,
    OperatingSystem,
    detect_environment,
)


def test_detect_environment_recognizes_supported_linux_id():
    environment = detect_environment(
        system_name="Linux",
        os_release='ID="ubuntu"\nID_LIKE="debian"\n',
    )

    assert environment.operating_system is OperatingSystem.LINUX
    assert environment.distribution is LinuxDistribution.UBUNTU
    assert environment.is_supported


def test_linux_config_directory_honors_xdg_config_home(tmp_path):
    environment = detect_environment(
        system_name="Linux", os_release="ID=fedora\n"
    )

    assert environment.config_directory({"XDG_CONFIG_HOME": str(tmp_path)}) == (
        tmp_path / "supa.cc"
    )


def test_macos_config_directory_preserves_existing_default(tmp_path):
    environment = detect_environment(system_name="Darwin")

    assert environment.config_directory({}, home=tmp_path) == (
        tmp_path / ".config" / "supa.cc"
    )
```

- [ ] **Step 2: Run the focused tests and confirm they fail**

Run: `pytest tests/test_environment.py -v`

Expected: collection fails because `supa_cc.environment` does not exist.

- [ ] **Step 3: Implement the pure environment model**

```python
class OperatingSystem(str, Enum):
    MACOS = "macos"
    LINUX = "linux"
    UNSUPPORTED = "unsupported"


class LinuxDistribution(str, Enum):
    DEBIAN = "debian"
    UBUNTU = "ubuntu"
    ARCH = "arch"
    FEDORA = "fedora"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Environment:
    operating_system: OperatingSystem
    distribution: Optional[LinuxDistribution] = None

    @property
    def is_supported(self) -> bool:
        return self.operating_system is OperatingSystem.MACOS or (
            self.operating_system is OperatingSystem.LINUX
            and self.distribution not in {None, LinuxDistribution.UNKNOWN}
        )

    def config_directory(self, environ=None, home=None) -> Path:
        values = os.environ if environ is None else environ
        user_home = Path.home() if home is None else Path(home)
        if self.operating_system is OperatingSystem.LINUX:
            xdg_home = values.get("XDG_CONFIG_HOME")
            if xdg_home:
                return Path(xdg_home) / "supa.cc"
        return user_home / ".config" / "supa.cc"
```

Parse `KEY=value` lines with quote removal, prefer `ID`, then match
`ID_LIKE` tokens only to the four supported families. Keep missing, malformed,
and unreadable `os-release` as `LinuxDistribution.UNKNOWN`; do not call a
shell command.

Replace `DEFAULT_ACTIVE_ACCOUNT_PATH` with a `default_active_account_path()`
function and let `ActiveAccountStore.__init__` call it only when `path` is
`None`.

- [ ] **Step 4: Run focused and regression tests**

Run: `pytest tests/test_environment.py tests/test_auth.py -v`

Expected: PASS.

- [ ] **Step 5: Commit the environment boundary**

```bash
git add supa_cc/environment.py supa_cc/auth.py tests/test_environment.py tests/test_auth.py
```

### Task 2: Add Explicit Secure Credential Stores

**Files:**
- Create: `supa_cc/credentials.py`
- Create: `tests/test_credentials.py`
- Modify: `supa_cc/auth.py:50-236`

**Interfaces:**
- Consumes `Environment` from `supa_cc.environment`.
- Produces `CredentialStore`, `CredentialStoreStatus`, `create_credential_store(environment)`, `CredentialAccessError`, and `CredentialPermissionDeniedError`.
- `KeychainManager` will receive a `CredentialStore` in Task 3.

- [ ] **Step 1: Write failing backend-policy tests using fake keyrings**

```python
import pytest

from supa_cc.credentials import CredentialAccessError, create_credential_store
from supa_cc.environment import detect_environment


def test_linux_selects_only_secret_service_backend(
    monkeypatch, fake_secret_service
):
    monkeypatch.setattr(
        "supa_cc.credentials._secret_service_keyring",
        lambda: fake_secret_service,
    )
    store = create_credential_store(
        detect_environment(system_name="Linux", os_release="ID=arch\n")
    )

    assert store.backend_name == "keyring.backends.SecretService.Keyring"


def test_linux_rejects_unavailable_secret_service(monkeypatch):
    monkeypatch.setattr(
        "supa_cc.credentials._secret_service_keyring",
        lambda: (_ for _ in ()).throw(RuntimeError()),
    )
    with pytest.raises(CredentialAccessError):
        create_credential_store(
            detect_environment(system_name="Linux", os_release="ID=debian\n")
        )
```

Patch private concrete-backend constructor helpers in tests rather than expose
injectable backend factories in the public API. Add fakes that implement
`get_password`, `set_password`, and `delete_password`; assert the same fake
receives every operation. Add cases for KeyringLocked, PermissionError,
generic KeyringError, a missing delete, and a read-back mismatch. Assert no
raised public message contains the fake token or backend-detail string.

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `pytest tests/test_credentials.py -v`

Expected: collection fails because `supa_cc.credentials` does not exist.

- [ ] **Step 3: Add neutral errors and the credential-store implementation**

In `auth.py`, introduce neutral exception classes while retaining the existing
failure-code values:

```python
class CredentialAccessError(RuntimeError):
    """Base safe error for system credential-store access."""


class CredentialPermissionDeniedError(CredentialAccessError):
    """The system credential store denied access."""


class CredentialReadError(CredentialAccessError):
    """The credential could not be read or verified."""
```

Map these exceptions in `classify_local_failure()` to the existing
`KEYCHAIN_PERMISSION_DENIED` and `KEYCHAIN_READ_FAILED` values, with public
messages that say `armazenamento de credenciais` rather than `Keychain`.

Implement `CredentialStore` with `get(name)`, `set(account)`, `delete(name)`,
`backend_name`, and `status()`. Construct `keyring.backends.macOS.Keyring` for
Darwin and `keyring.backends.SecretService.Keyring` for supported Linux. Do
not call `keyring.get_keyring()` or accept backend factories through the public
API. Normalize known permission/locked exceptions, tolerate only recognized
missing-item delete errors, and use `hmac.compare_digest` to verify writes.
Probe the Linux Secret Service collection with a unique nonexistent lookup so
status detects both D-Bus availability and an unlocked collection without
reading a stored token.

- [ ] **Step 4: Run focused credential tests**

Run: `pytest tests/test_credentials.py -v`

Expected: PASS.

- [ ] **Step 5: Commit credential policy**

```bash
git add supa_cc/auth.py supa_cc/credentials.py tests/test_credentials.py
```

### Task 3: Inject Credentials Into Account Persistence

**Files:**
- Modify: `supa_cc/keychain.py:1-309`
- Modify: `supa_cc/accounts.py:1-161`
- Modify: `tests/test_keychain.py`
- Modify: `tests/test_accounts.py`

**Interfaces:**
- Consumes `CredentialStore` from Task 2 and `Environment` from Task 1.
- `KeychainManager(index_path=None, service=..., credential_store=None, ...)` retains all public account methods.
- `AccountManager` exposes the existing `keychain` property for current callers and diagnostics.

- [ ] **Step 1: Write failing manager-injection tests**

```python
def test_manager_uses_the_injected_credential_store_for_add_get_and_remove(tmp_path):
    store = FakeCredentialStore()
    manager = KeychainManager(
        index_path=tmp_path / "accounts.json", credential_store=store
    )
    account = Account(name="work", token=fake_pat("work"))

    manager.add_account(account)

    assert manager.get_account("work") == account
    manager.remove_account("work")
    assert store.operations == ["get:work", "set:work", "get:work", "delete:work"]


def test_default_index_path_uses_linux_xdg_config_home(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    manager = KeychainManager(environment=ubuntu_environment(), credential_store=FakeCredentialStore())

    assert manager.index_path == tmp_path / "supa.cc" / "accounts.json"
```

- [ ] **Step 2: Run the focused tests and confirm they fail**

Run: `pytest tests/test_keychain.py tests/test_accounts.py -v`

Expected: FAIL because the constructor has no `credential_store` or
`environment` parameters.

- [ ] **Step 3: Preserve account transactions while delegating tokens**

Remove direct `keyring` imports and low-level access helpers from
`keychain.py`. Retain `KEYCHAIN_SERVICE`, JSON validation, lock handling,
cache, rollback, and public method names. Change its token helpers to:

```python
def _read_token_uncached(self, name: str) -> Optional[str]:
    return self.credential_store.get(name)

def _write_token_verified(self, account: Account) -> None:
    self.credential_store.set(account)

def _delete_token(self, name: str) -> None:
    self.credential_store.delete(name)
```

Use `environment.config_directory()` for `default_index_path()` only when
`index_path` is omitted. In `AccountManager`, create one detected environment,
pass it to `KeychainManager` and `ActiveAccountStore`, and replace catches of
Keychain-only exceptions with `CredentialAccessError` subclasses.

- [ ] **Step 4: Run account regressions**

Run: `pytest tests/test_keychain.py tests/test_accounts.py tests/test_cli_commands.py -v`

Expected: PASS, including cache, atomic index writes, rollback, and no-token
in-index assertions.

- [ ] **Step 5: Commit transaction-preserving integration**

```bash
git add supa_cc/keychain.py supa_cc/accounts.py tests/test_keychain.py tests/test_accounts.py
```

### Task 4: Add Platform Installation Guidance And Diagnostics

**Files:**
- Create: `supa_cc/installation.py`
- Modify: `supa_cc/diagnostics.py:1-488`
- Modify: `supa_cc/__main__.py:1-45`
- Create: `tests/test_installation.py`
- Modify: `tests/test_diagnostics.py`
- Modify: `tests/test_cli_commands.py`

**Interfaces:**
- `installation_guidance(environment)` returns an immutable object with `install_hint`, `update_hint`, and `remediation`.
- `DiagnosticService(environment=None, credential_store=None, ...)` reports environment and credential status.

- [ ] **Step 1: Write failing guidance and doctor-report tests**

```python
def test_debian_guidance_is_informational_and_uses_apt():
    guidance = installation_guidance(ubuntu_environment())

    assert "apt" in guidance.install_hint
    assert "gnome-keyring" in guidance.install_hint
    assert "pipx" in guidance.install_hint


def test_doctor_reports_linux_distribution_and_unavailable_store():
    report = DiagnosticService(
        environment=ubuntu_environment(), credential_store=UnavailableStore()
    ).run()

    assert report.runtime["operating_system"] == "linux"
    assert report.runtime["linux_distribution"] == "ubuntu"
    assert report.credentials["available"] is False
    assert "keychain" not in report.to_human().lower()
```

Add table-driven guidance cases for macOS, Debian, Ubuntu, Arch, Fedora, and
unsupported Linux. Assert each command string is display-only: no test should
mock or observe `subprocess.run` for a package manager.

- [ ] **Step 2: Run the focused tests and confirm they fail**

Run: `pytest tests/test_installation.py tests/test_diagnostics.py tests/test_cli_commands.py -v`

Expected: FAIL because installation guidance and doctor credential status do
not exist.

- [ ] **Step 3: Implement guidance and diagnostic composition**

Use immutable data in `installation.py`; include these prerequisite commands:

```python
DEBIAN = "sudo apt install python3 python3-venv pipx gnome-keyring libsecret-tools"
ARCH = "sudo pacman -S python python-pipx gnome-keyring libsecret"
FEDORA = "sudo dnf install python3 pipx gnome-keyring libsecret"
```

These strings are documentation only. Compose `installation_guidance` in
`_check_for_updates()` so Linux update help says `pipx upgrade supa.cc` and
macOS retains Homebrew plus pipx guidance.

Extend `DoctorReport` with a neutral `credentials` dictionary and runtime OS
fields. Its serialized output must preserve the existing `keychain` object as
a compatibility alias only if necessary for current callers; human output must
say `Armazenamento de credenciais`. Call the signature resolver only on macOS;
return `{"status": "not_applicable"}` on Linux. A credential status failure
adds the stable existing credential-read failure code and returns remediation,
but never reads a token unless `--live` is explicitly requested.

- [ ] **Step 4: Run diagnostic and CLI tests**

Run: `pytest tests/test_installation.py tests/test_diagnostics.py tests/test_cli_commands.py -v`

Expected: PASS.

- [ ] **Step 5: Commit environment-aware diagnostics**

```bash
git add supa_cc/installation.py supa_cc/diagnostics.py supa_cc/__main__.py tests/test_installation.py tests/test_diagnostics.py tests/test_cli_commands.py
```

### Task 5: Update Package Metadata And Public Documentation

**Files:**
- Modify: `pyproject.toml:5-59`
- Modify: `README.md`
- Modify: `docs/installation.md`
- Modify: `SKILL.md`
- Modify: `AGENTS.md`
- Modify: `docs/release.md`
- Modify: `tests/test_project_identity.py`
- Modify: `tests/test_publication_assets.py`

**Interfaces:**
- Consumes the supported-environment and credential policy created in Tasks 1-4.
- Produces consistent installation and security guidance for users and agents.

- [ ] **Step 1: Write metadata and documentation assertions**

```python
def test_project_metadata_declares_macos_and_linux_support():
    project = load_project_metadata()

    assert "Operating System :: MacOS" in project["classifiers"]
    assert "Operating System :: POSIX :: Linux" in project["classifiers"]
    assert "Linux" in project["description"]


def test_installation_guide_covers_supported_linux_distributions():
    contents = Path("docs/installation.md").read_text(encoding="utf-8")

    for distribution in ("Debian", "Ubuntu", "Arch", "Fedora"):
        assert distribution in contents
    assert "Secret Service" in contents
    assert "plaintext" in contents.lower()
```

- [ ] **Step 2: Run the tests and confirm documentation support is missing**

Run: `pytest tests/test_project_identity.py tests/test_publication_assets.py -v`

Expected: FAIL because metadata and installation docs are macOS-only.

- [ ] **Step 3: Update public support declarations**

Change the project description, keywords, and classifiers to include Linux
while retaining MacOS. Add a `real_secret_service` opt-in pytest marker next
to the existing macOS marker.

Document pipx installation plus the exact platform prerequisites from Task 4.
Document `supa.cc doctor` verification, user D-Bus/Secret Service
requirements, headless failure behavior, and the explicit prohibition on
plaintext/keyrings-alt fallbacks. Preserve the Homebrew formula as macOS-only;
do not add Debian, PKGBUILD/AUR, or RPM packaging assets.

Update release guidance to run wheel/sdist build and Linux test jobs. Add
`build` to the development dependency extra if the release guide invokes
`python -m build`.

- [ ] **Step 4: Run documentation and packaging tests**

Run: `pytest tests/test_project_identity.py tests/test_publication_assets.py -v`

Expected: PASS.

- [ ] **Step 5: Commit documentation and packaging contract**

```bash
git add pyproject.toml README.md docs/installation.md docs/release.md SKILL.md AGENTS.md tests/test_project_identity.py tests/test_publication_assets.py
```

### Task 6: Add Linux Smoke Coverage And Verify The Release Candidate

**Files:**
- Create: `tests/test_linux_secret_service_smoke.py`
- Modify: `tests/conftest.py`
- Modify: `docs/release.md`

**Interfaces:**
- Uses the `CredentialStore` and `Environment` interfaces from Tasks 1-2.
- The smoke test runs only with explicit opt-in and an available Secret Service.

- [ ] **Step 1: Write the skipped-by-default Secret Service smoke test**

```python
@pytest.mark.real_secret_service
def test_secret_service_round_trip_uses_an_isolated_entry():
    store = create_credential_store(
        detect_environment(system_name="Linux", os_release="ID=fedora\n")
    )
    name = f"supa-cc-test-{uuid4().hex}"
    token = fake_pat("secret-service")
    try:
        store.set(Account(name=name, token=token))
        assert store.get(name) == token
    finally:
        store.delete(name)
```

Guard it with an environment opt-in such as `SUPA_CC_REAL_SECRET_SERVICE=1`;
otherwise skip before constructing the backend. Ensure cleanup never prints
the token or the account name.

- [ ] **Step 2: Run the default suite and confirm the smoke test skips**

Run: `pytest -v`

Expected: all unit tests pass and the real Secret Service test is skipped.

- [ ] **Step 3: Build distribution artifacts and install them in a disposable environment**

Run: `python -m build`

Expected: one wheel and one source distribution under `dist/`.

Run: `python -m venv /tmp/supa-cc-verify && /tmp/supa-cc-verify/bin/pip install dist/*.whl && /tmp/supa-cc-verify/bin/supa.cc --version`

Expected: the installed CLI prints `Supa.cc v0.2.0`.

- [ ] **Step 4: Review the complete diff and final state**

Run: `git diff main...HEAD --check && git status --short && git log --oneline main..HEAD`

Expected: no whitespace errors, only intended files, and commits for the
design plus each completed task.

- [ ] **Step 5: Commit final test and release updates**

```bash
git add tests/test_linux_secret_service_smoke.py tests/conftest.py docs/release.md
```
