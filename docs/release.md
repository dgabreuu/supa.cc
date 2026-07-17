# Release record and checklist

## 0.5.3 publication record (2026-07-17)

The `0.5.3` release containing the TUI active-account switch fix is stable and fully promoted. The `v0.5.2` references used during candidate preparation were transient safeguards while PyPI publication and source-archive verification completed; they are retained below only as historical process context. The historical `0.5.2` and `0.5.0` publication records remain unchanged.

### Publication details

- GitHub Release: https://github.com/dgabreuu/supa.cc/releases/tag/v0.5.3
- PyPI package: https://pypi.org/project/supa.cc/0.5.3/
- Release tag: `v0.5.3` (`cade1976340db77d90c81b6e0fc4277dd1c91c37`)
- Verified release workflow: https://github.com/dgabreuu/supa.cc/actions/runs/29588209075
- Source archive SHA-256: `1fe25483fba910160328559e1433fe09e962cb494cf34da6122ad4f238aa9914`
- Homebrew promotion: `Formula/supa-cc.rb` now uses the immutable `v0.5.3` archive and the source SHA above; `.github/workflows/homebrew.yml` validation is pending for the promoted revision.

### Completed publication checklist

- Confirmed that `pyproject.toml`, `install.sh`, and `install.ps1` declare `0.5.3`, and that `CHANGELOG.md` records `0.5.3` with the effective date `2026-07-17`.
- Confirmed that `.github/workflows/release.yml` defaults to `v0.5.3`, links the `0.5.3` PyPI environment, and verifies `supa.cc==0.5.3` with its existing bounded retry.
- Ran the focused project-identity, publication-assets, and installer tests before publication, then completed the numbered `0.5.3` sections below. The `0.5.2` checklist later in this file is historical.
- During candidate preparation, `Formula/supa-cc.rb`, `README.md`, and `docs/installation.md` stayed on the verified `v0.5.2` assets as a transient safeguard. After PyPI publication and independent archive verification, those assets and their tests were promoted together to `v0.5.3`.

## 1. Validate the 0.5.3 candidate

Review `git status --short`, `git remote -v`, and the history. Confirm that tracked content and artifacts contain no PAT, absolute local path, cache, virtual environment, diff, or private document.

Run the following from the candidate checkout:

```bash
python3 -m pip install --upgrade "pip>=26.1.2"
python3 -m pip install -e ".[dev]"
python3 -m pytest
python3 -m pip check
pip-audit --skip-editable
python3 scripts/runtime_requirements.py runtime-requirements.txt
pip-audit --requirement runtime-requirements.txt
python3 scripts/security_scan.py --tracked --history
python3 -m pytest --cache-clear --collect-only -q
python3 scripts/security_scan.py --path .pytest_cache
python3 -m build
python3 scripts/inspect_artifacts.py dist
python3 -m pytest tests/test_project_identity.py tests/test_publication_assets.py tests/test_install_scripts.py
git diff --check
bash -n install.sh
bash install.sh --dry-run --yes
pwsh -NoProfile -File install.ps1 -Help
pwsh -NoProfile -File install.ps1 -DryRun -Yes
```

The scanner reports only a finding's class and location, never its value. The inspector requires exactly one wheel and one sdist in `dist/`, validates member paths, and applies the same scanner to both artifacts. Verify that both artifact metadata entries identify `supa.cc` version `0.5.3`; install the wheel in a disposable virtual environment, run `pip check`, `supa.cc --version`, and `supa.cc version`, and confirm `0.5.3`.

During candidate preparation, the following publication assets and stable-formula assertions intentionally remained at `v0.5.2` as a transient safeguard: `Formula/supa-cc.rb`, `README.md`, `docs/installation.md`, `.github/workflows/homebrew.yml`, and the `STABLE_FORMULA_VERSION`, `TARBALL_URL`, `TARBALL_SHA256`, and formula assertions in `tests/test_project_identity.py` and `tests/test_publication_assets.py`. Once the tag, PyPI package, and archive SHA were verified, the complete set was promoted to `v0.5.3`.

The CI matrix must pass on Python 3.11 and the current stable Python on Ubuntu, macOS, and Windows, plus the targeted Fedora and Arch jobs, before the release tag is created. Native smoke tests remain opt-in and require explicit execution on a host with the native credential store available.

## 2. Confirm the 0.5.3 operational contract

Confirm Supabase CLI >= 2.109.1, the official `supabase` profile, executable trust, CLI-owned session recovery without the PAT environment override, mutation-aware recovery, logout when removing the active account, and blocking of the plaintext fallback. CLI credential identifiers and formats remain opaque. `doctor` must remain non-live by default; only `doctor --account <name> --live` opens the token for explicit validation. The lock does not coordinate concurrent external `supabase` commands.

## 3. Configure Trusted Publishing for 0.5.3

Configure a PyPI Trusted Publisher for the `supa.cc` project with these values before publishing:

- Owner: `dgabreuu`
- Repository: `supa.cc`
- Workflow: `release.yml`
- Environment: `pypi`

Protect the `pypi` environment according to repository policy. The workflow uses OIDC with `id-token: write`; do not create a PyPI API token or secret.

## 4. Publish the GitHub Release for 0.5.3

Create the annotated tag and stable, published, non-draft GitHub Release `v0.5.3` only after the candidate checks pass. Use the `0.5.3` section of `CHANGELOG.md` as the release notes. The release workflow must check out the tag, confirm that it matches `pyproject.toml`, test, build once, and upload one wheel and one sdist as an artifact. Do not attach local builds to the release.

## 5. Publish 0.5.3 to PyPI with Trusted Publishing

The `build` job has only `contents: read`. The `publish` job downloads exactly the artifact produced by the build and sends it to PyPI through Trusted Publishing using only `id-token: write`. The verification jobs receive no `GITHUB_TOKEN` permissions.

## 6. Verify pipx for 0.5.3 on Linux and Windows

The release workflow must install `supa.cc==0.5.3` directly from PyPI on Linux and Windows with its existing bounded propagation retry, then run both version commands:

```bash
pipx install supa.cc==0.5.3
supa.cc --version
supa.cc version
```

## 7. Promote the Homebrew formula and post-publication assets

After `supa.cc==0.5.3` became available on PyPI and the real `v0.5.3` source archive was downloaded and independently verified, the following assets were promoted together:

```bash
archive="${TMPDIR:-.}/supa.cc-v0.5.3.tar.gz"
curl --fail --location --output "$archive" https://github.com/dgabreuu/supa.cc/archive/refs/tags/v0.5.3.tar.gz
shasum -a 256 "$archive"
```

- Update `Formula/supa-cc.rb` to the `v0.5.3` archive and verified SHA-256.
- Update `README.md` and `docs/installation.md` to the reviewed immutable `v0.5.3` installer URLs.
- Update `.github/workflows/homebrew.yml` to validate the promoted formula revision.
- Update `tests/test_project_identity.py` and `tests/test_publication_assets.py`, including `STABLE_FORMULA_VERSION`, `TARBALL_URL`, `TARBALL_SHA256`, and the formula assertions, to the verified `v0.5.3` values.

The `v0.5.2` values in the preparation checklist were transient only; the stable formula, workflow checks, and test constants now use the verified `v0.5.3` archive and SHA.

## 8. Update availability documentation

GitHub, PyPI, pipx, source-archive SHA, and Homebrew validation all passed; the `0.5.3` changelog is final and the reviewed `README.md` and `docs/installation.md` links now use immutable `v0.5.3` refs. No Debian, AUR, or RPM assets were created.

The records that follow preserve the historical 0.5.2 and 0.5.0 publication details.

The historical `0.5.2` candidate checklist below records the PowerShell bootstrap exit-status fix and its publication gates for context only; it is not a procedure for `0.5.3`. The historical `0.5.0` record below describes only assets that existed in that tag.

## 0.5.1 publication record

- GitHub Release: https://github.com/dgabreuu/supa.cc/releases/tag/v0.5.1
- PyPI package: https://pypi.org/project/supa.cc/0.5.1/
- Release tag: `v0.5.1` (`4cc3d51462a02e1a523e10e445f8085bfe6d35e6`)
- Verified release workflow: https://github.com/dgabreuu/supa.cc/actions/runs/29449131978
- Source archive SHA-256 used for the follow-up Homebrew formula: `db263e555a7a0e4b1d9003f3cb87d72cfcceac0b02dbb9e4c794889110815d15`

The initial release-event workflow run failed before publication because its tag checkout exposed the editable package on `PATH`; the corrected workflow was verified with a manual dispatch from a temporary `v0.5.1-ci` tag. That temporary tag was deleted after the successful Trusted Publishing and Linux/Windows pipx verification. The public `v0.5.1` tag and release were not rewritten.

The `0.5.2` publication record below is historical and is not a procedure for the `0.5.3` candidate.

## 0.5.2 publication record

- GitHub Release: https://github.com/dgabreuu/supa.cc/releases/tag/v0.5.2
- PyPI package: https://pypi.org/project/supa.cc/0.5.2/
- Release tag: `v0.5.2` (`db7c179ca7c72a910865b7b722ce8e4a83cd4eee`)
- Verified release workflow: https://github.com/dgabreuu/supa.cc/actions/runs/29450123806
- Source archive SHA-256: `cc1bd04ddcd1f5684340fcfc8378859fde8da0ec63d843a4c12f9857335b09e2`

The release workflow built one wheel and one sdist, published them through Trusted Publishing, and verified pipx installation on Ubuntu and Windows. The Windows verification used the workflow's bounded retry for regional PyPI propagation. The temporary `v0.5.2-ci` ref used to satisfy the protected PyPI environment was deleted after verification.

## Publication record

- GitHub Release: https://github.com/dgabreuu/supa.cc/releases/tag/v0.5.0
- Release workflow: https://github.com/dgabreuu/supa.cc/actions/runs/29432932472
- PyPI package: https://pypi.org/project/supa.cc/0.5.0/
- Homebrew formula: https://github.com/dgabreuu/supa.cc/blob/main/Formula/supa-cc.rb
- Homebrew validation workflow: https://github.com/dgabreuu/supa.cc/actions/runs/29434531777
- The annotated tag `v0.5.0` points to commit `d351f6ee084a8b3b0d615badbab4a6872623801d`.
- The Homebrew formula was promoted in commit `b1dbcbe13c29f8ad3301cc2a0c2db5135dc1964c`.
- The release workflow produced and published one wheel and one sdist through Trusted Publishing; its build, publish, Linux pipx, and Windows pipx jobs passed.
- The Homebrew workflow passed its exact-tap, resource, audit, installation, version, and test gates.

## 0.5.2 candidate checklist (historical)

Sections 1–3 below apply to the `0.5.2` candidate. Sections 4–8 are retained as the historical publication record for `0.5.0`.

## 1. Validate the candidate commit

Review `git status --short`, `git remote -v`, and the history. Confirm that tracked content and artifacts contain no PAT, absolute local path, cache, virtual environment, diff, or private document.

Run the following from the candidate checkout:

```bash
python3 -m pip install --upgrade "pip>=26.1.2"
python3 -m pip install -e ".[dev]"
python3 -m pytest
python3 -m pip check
pip-audit --skip-editable
python3 scripts/runtime_requirements.py runtime-requirements.txt
pip-audit --requirement runtime-requirements.txt
python3 scripts/security_scan.py --tracked --history
python3 -m pytest --cache-clear --collect-only -q
python3 scripts/security_scan.py --path .pytest_cache
python3 -m build
python3 scripts/inspect_artifacts.py dist
bash -n install.sh
bash install.sh --dry-run --yes
pwsh -NoProfile -File install.ps1 -Help
pwsh -NoProfile -File install.ps1 -DryRun -Yes
```

The scanner reports only a finding's class and location, never its value. The inspector requires exactly one wheel and one sdist in `dist/`, validates member paths, and applies the same scanner to both artifacts. Install the wheel in a disposable virtual environment, run `pip check`, `supa.cc --version`, and `supa.cc version`, and confirm `0.5.2`.

The CI matrix must pass on Python 3.11 and the current stable Python on Ubuntu, macOS, and Windows, plus the targeted Fedora and Arch jobs, before the release tag is created. Native smoke tests remain opt-in and require explicit execution on a host with the native credential store available.

For the `0.5.2` release that carries the corrected bootstrap, also review `install.sh` and `install.ps1` as publication assets. Confirm that:

- `SUPABASE_VERSION`/`SupabaseVersion` exactly match the Python `MINIMUM_VERSION` source, and `SUPA_CC_VERSION`/`SupaCcVersion` match `pyproject.toml`;
- the Homebrew installer URL contains a reviewed 40-character upstream commit, not a branch;
- the fixed official Python installer version, URLs, architectures, and SHA-256 values still match Python.org;
- the Supabase x64 and arm64 artifact names exist in the pinned release and every download requires `checksums.txt`;
- dry-run plans cover a complete, empty, outdated, conflicting-channel, and non-interactive environment without mutation;
- no command uses broad Homebrew trust, a plaintext credential backend, an unofficial mirror, or a fallback after checksum failure.

For `v0.5.2`, both raw script URLs must be verified against the exact published tag before the one-command bootstrap is promoted in `docs/installation.md` and the README. Never advertise a tag before it contains the reviewed scripts.

## 2. Confirm the operational contract

Confirm Supabase CLI >= 2.109.1, the official `supabase` profile, executable trust, CLI-owned session recovery without the PAT environment override, mutation-aware recovery, logout when removing the active account, and blocking of the plaintext fallback. CLI credential identifiers and formats remain opaque. `doctor` must remain non-live by default; only `doctor --account <name> --live` opens the token for explicit validation. The lock does not coordinate concurrent external `supabase` commands.

## 3. Configure Trusted Publishing

Configure a PyPI Trusted Publisher for the `supa.cc` project with these values before publishing:

- Owner: `dgabreuu`
- Repository: `supa.cc`
- Workflow: `release.yml`
- Environment: `pypi`

Protect the `pypi` environment according to repository policy. The workflow uses OIDC with `id-token: write`; do not create a PyPI API token or secret.

## 4. Publish the GitHub Release

The annotated tag and GitHub Release `v0.5.0` were created only after the candidate checks passed. The release is stable, non-draft, and non-prerelease, and uses the `0.5.0` section of `CHANGELOG.md` as its notes.

Publishing the GitHub Release triggered `.github/workflows/release.yml`. The workflow checked out the release tag, confirmed that it matched `pyproject.toml`, tested, built once, and uploaded one wheel and one sdist as an artifact. No local builds were attached to the release.

## 5. Publish to PyPI with Trusted Publishing

The `build` job had only `contents: read`. The `publish` job downloaded exactly the artifact produced by the build and sent it to PyPI through Trusted Publishing using only `id-token: write`. The verification jobs received no `GITHUB_TOKEN` permissions.

`supa.cc==0.5.0` is available on PyPI with both a wheel and sdist. The release workflow's Linux and Windows pipx checks passed after the Linux index-propagation retry. The published version was not recreated.

## 6. Verify pipx on Linux and Windows

The release workflow installed `supa.cc==0.5.0` directly from PyPI with pipx on Linux and Windows and ran both version commands. Both jobs passed:

```bash
pipx install supa.cc==0.5.0
supa.cc --version
supa.cc version
```

## 7. Update the Homebrew formula

The Homebrew formula now points to tag `v0.5.0` and uses the verified SHA256 `a23f5f57d663cc5989b353e77475f7f0154116961c8d343257ff9d0cd28b0a49`.

The formula was updated only after PyPI and pipx verification and after the tag existed. The real tarball for tag `v0.5.0` was downloaded and its SHA256 was calculated; Python resources were checked with Homebrew tooling and the committed resources required no changes.

```bash
archive="${TMPDIR:-.}/supa.cc-v0.5.0.tar.gz"
curl --fail --location --output "$archive" https://github.com/dgabreuu/supa.cc/archive/refs/tags/v0.5.0.tar.gz
shasum -a 256 "$archive"
brew tap dgabreuu/supa-cc https://github.com/dgabreuu/supa.cc.git
cd "$(brew --repo dgabreuu/supa-cc)"
brew trust --formula supabase/tap/supabase
brew install supabase/tap/supabase
brew trust --formula dgabreuu/supa-cc/supa-cc
brew update-python-resources --ignore-main-package-cooldown Formula/supa-cc.rb
brew audit --strict --formula dgabreuu/supa-cc/supa-cc
brew install --build-from-source dgabreuu/supa-cc/supa-cc
brew test dgabreuu/supa-cc/supa-cc
```

Keep `head "https://github.com/dgabreuu/supa.cc.git", branch: "main"`. The explicit trust command is limited to the formula and is required because resource generation evaluates the local formula before installation.

`.github/workflows/homebrew.yml` ran manually against commit `4a8ba5baf870571014493059138b9edf9492740e`, verified the exact public tap revision, and passed its resource, audit, installation, version, and test gates on macOS.

## 8. Update availability documentation

After GitHub, PyPI, pipx, and Homebrew were verified, the `0.5.0` changelog entry was finalized with the publication date and its comparison target was set to `v0.4.2...v0.5.0`. This checklist records the verified public release, package, workflow, and formula links above.

Do not create Debian, AUR, or RPM assets in this process.

## 0.5.2 publication summary

The candidate sequence for `0.5.2` completed as follows:

1. The annotated tag `v0.5.2` was pushed and a stable, published, non-draft GitHub Release was created.
2. The release workflow published `supa.cc==0.5.2` through Trusted Publishing and verified Linux and Windows `pipx` installation.
3. The real `v0.5.2` source archive was hashed, and `Formula/supa-cc.rb` was updated to the verified URL and SHA-256.
4. Both raw installer URLs were verified against `v0.5.2`; `docs/installation.md` and `README.md` now use that immutable tag.

The verified `v0.5.1` source archive SHA-256 remains `db263e555a7a0e4b1d9003f3cb87d72cfcceac0b02dbb9e4c794889110815d15`.
