# Release record and checklist

## 0.5.5 publication record (2026-07-17)

The GitHub Release, PyPI publication, Linux/Windows `pipx` verification, and
Homebrew promotion for `v0.5.5` completed successfully. The formula was
promoted only after the immutable source archive checksum was verified and the
manual Homebrew workflow passed.

### Publication details

- GitHub Release: https://github.com/dgabreuu/supa.cc/releases/tag/v0.5.5
- PyPI package: https://pypi.org/project/supa.cc/0.5.5/
- Release tag: `v0.5.5` (`2d286b03e8ddb4d5484ba4c6bb496d97e7e35aa1`)
- Verified release workflow: https://github.com/dgabreuu/supa.cc/actions/runs/29598792471
- Source archive SHA-256: `9c7fc187d3d25ad9eec6a7fad88b0c64df519968cf3beb3439ef4d3764376166`
- Homebrew promotion commit/tap revision: `6442b35e088bd1b225b8b1f3057a6e73ce4b9f62` (PR #17)
- Homebrew validation workflow: https://github.com/dgabreuu/supa.cc/actions/runs/29599592869

## 0.5.5 candidate checklist

`v0.5.5` is the patch release after `v0.5.4`. It packages the portable
coding-agent skill and its installation documentation. The checklist below
records the gates used for publication and the completed Homebrew promotion.
Do not publish a guessed checksum or attach local build artifacts to a release.

## 1. Validate the 0.5.5 candidate

Review `git status --short`, `git remote -v`, the exact candidate commit, and the complete staged scope. Confirm that the candidate contains no PAT, absolute local path, cache, virtual environment, diff, or private document, and that no file under `supa_cc/` changed.

Run the following from the candidate checkout:

```bash
python -m pytest
python -m pip check
pip-audit --skip-editable
python scripts/runtime_requirements.py runtime-requirements.txt
pip-audit --requirement runtime-requirements.txt
python scripts/security_scan.py --tracked --history
python -m pytest --cache-clear --collect-only -q
python scripts/security_scan.py --path .pytest_cache
python -m build
python scripts/inspect_artifacts.py dist
bash -n install.sh
bash install.sh --dry-run --yes
pwsh -NoProfile -File install.ps1 -Help
pwsh -NoProfile -File install.ps1 -DryRun -Yes
git diff --check
```

Verify that the wheel and sdist metadata identify `supa.cc` version `0.5.5`, that the immutable installer references are `v0.5.5`, and that the Agent Skills validator accepts `.agents/skills/supa-cc`.

## 2. Confirm the 0.5.5 operational and publication contract

Confirm Supabase CLI >= 2.109.1, the official `supabase` profile, native credential-store protections, and the existing release workflow's OIDC configuration. Do not create a PyPI API token. The public skill remains separate from package installation and does not change the CLI behavior.

## 3. Publish the GitHub Release for 0.5.5

After the candidate PR is merged and its CI is green, create the annotated tag `v0.5.5` on that exact commit and publish a stable, non-draft, non-prerelease GitHub Release using the `0.5.5` changelog section. The release workflow must validate the tag/version match, test, build one wheel and one sdist, inspect them, and upload only that artifact set.

## 4. Publish 0.5.5 to PyPI with Trusted Publishing

The existing `release.yml` workflow publishes through the protected `pypi` environment using OIDC `id-token: write`. It must build once and publish only the inspected wheel and sdist.

## 5. Verify pipx for 0.5.5 on Linux and Windows

The release workflow installs `supa.cc==0.5.5` on Linux and Windows with `pipx`. Verify that both version commands complete successfully before changing the Homebrew formula.

## 6. Update the Homebrew formula after PyPI verification

Download the real source archive only after `v0.5.5` exists:

```bash
archive="${TMPDIR:-.}/supa.cc-v0.5.5.tar.gz"
curl --fail --location --output "$archive" https://github.com/dgabreuu/supa.cc/archive/refs/tags/v0.5.5.tar.gz
shasum -a 256 "$archive"
```

Use that measured SHA-256 to update `Formula/supa-cc.rb` and its publication tests. Run the formula-scoped trust, audit, install, version, resource, and test gates through the manual Homebrew workflow. Never infer or prefill the checksum.

## 7. Update availability documentation

After GitHub, PyPI, pipx, and Homebrew verification, record the actual tag SHA, release URL, workflow URLs, source SHA-256, tap commit, and validation results here. Keep the changelog comparison link at `v0.5.4...v0.5.5` and do not create Debian, AUR, or RPM assets.

## 0.5.4 publication record (2026-07-17)

`v0.5.4` is the corrective release for the immutable `v0.5.3` publication snapshot. The `v0.5.3` tag and PyPI files cannot be rewritten; their embedded README still contains the earlier `v0.5.2` bootstrap references. The corrective package was tagged only after all package-facing references were aligned to `v0.5.4`; the formula was then promoted after PyPI and source-archive verification.

The historical `0.5.3`, `0.5.2`, and `0.5.0` publication records remain below. No credentials, local paths, build artifacts, or private documents belong in the release commit.

### Publication details

- GitHub Release: https://github.com/dgabreuu/supa.cc/releases/tag/v0.5.4
- PyPI package: https://pypi.org/project/supa.cc/0.5.4/
- Release tag: `v0.5.4` (`ae6e149a326e8f3db135e6eb0643a9732ccde1a5`)
- Verified release workflow: https://github.com/dgabreuu/supa.cc/actions/runs/29590240342
- Source archive SHA-256: `ac98e4c7c4a39fe0ded8684fac5fca7c3c4c38314ed6c2ce66ccde30481ca47f`
- Homebrew promotion commit/tap revision: `0221d8b32e9721effe2ef11ae2a8b340db173c4a`
- Homebrew validation workflow: https://github.com/dgabreuu/supa.cc/actions/runs/29590864802

## 1. Validate the 0.5.4 candidate (completed)

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

The scanner reports only a finding's class and location, never its value. The inspector requires exactly one wheel and one sdist in `dist/`, validates member paths, and applies the same scanner to both artifacts. Verify that both artifact metadata entries identify `supa.cc` version `0.5.4`; install the wheel in a disposable virtual environment, run `pip check`, `supa.cc --version`, and `supa.cc version`, and confirm `0.5.4`.

Before the tag is created, `pyproject.toml`, `install.sh`, `install.ps1`, `README.md`, and `docs/installation.md` must all reference `0.5.4`/`v0.5.4`. `Formula/supa-cc.rb`, `.github/workflows/homebrew.yml`, and the stable-formula assertions intentionally remain at verified `v0.5.3` values until the PyPI package and the real `v0.5.4` archive have been independently verified. This separation keeps package metadata correct without inventing a source checksum.

The CI matrix must pass on Python 3.11 and the current stable Python on Ubuntu, macOS, and Windows, plus the targeted Fedora and Arch jobs, before the release tag is created. Native smoke tests remain opt-in and require explicit execution on a host with the native credential store available.

## 2. Confirm the 0.5.4 operational contract

Confirm Supabase CLI >= 2.109.1, the official `supabase` profile, executable trust, CLI-owned session recovery without the PAT environment override, mutation-aware recovery, logout when removing the active account, and blocking of the plaintext fallback. CLI credential identifiers and formats remain opaque. `doctor` must remain non-live by default; only `doctor --account <name> --live` opens the token for explicit validation. The lock does not coordinate concurrent external `supabase` commands.

## 3. Configure Trusted Publishing for 0.5.4

Configure a PyPI Trusted Publisher for the `supa.cc` project with these values before publishing:

- Owner: `dgabreuu`
- Repository: `supa.cc`
- Workflow: `release.yml`
- Environment: `pypi`

Protect the `pypi` environment according to repository policy. The workflow uses OIDC with `id-token: write`; do not create a PyPI API token or secret.

## 4. Publish the GitHub Release for 0.5.4

Create the annotated tag and stable, published, non-draft GitHub Release `v0.5.4` only after the candidate checks pass. Use the `0.5.4` section of `CHANGELOG.md` as the release notes. The release workflow must check out the tag, confirm that it matches `pyproject.toml`, test, build once, and upload one wheel and one sdist as an artifact. Do not attach local builds to the release.

## 5. Publish 0.5.4 to PyPI with Trusted Publishing

The `build` job has only `contents: read`. The `publish` job downloads exactly the artifact produced by the build and sends it to PyPI through Trusted Publishing using only `id-token: write`. The verification jobs receive no `GITHUB_TOKEN` permissions.

## 6. Verify pipx for 0.5.4 on Linux and Windows

The release workflow must install `supa.cc==0.5.4` directly from PyPI on Linux and Windows with its existing bounded propagation retry, then run both version commands:

```bash
pipx install supa.cc==0.5.4
supa.cc --version
supa.cc version
```

## 7. Promote the Homebrew formula and post-publication assets (completed)

After `supa.cc==0.5.4` becomes available on PyPI and the real `v0.5.4` source archive is downloaded and independently verified, promote the following assets together:

```bash
archive="${TMPDIR:-.}/supa.cc-v0.5.4.tar.gz"
curl --fail --location --output "$archive" https://github.com/dgabreuu/supa.cc/archive/refs/tags/v0.5.4.tar.gz
shasum -a 256 "$archive"
```

- Update `Formula/supa-cc.rb` to the `v0.5.4` archive and verified SHA-256.
- Keep `README.md` and `docs/installation.md` on the reviewed immutable `v0.5.4` installer URLs already present in the tag.
- Update `.github/workflows/homebrew.yml` to validate the promoted formula revision.
- Update `tests/test_project_identity.py` and `tests/test_publication_assets.py`, including `STABLE_FORMULA_VERSION`, `TARBALL_URL`, `TARBALL_SHA256`, and the formula assertions, to the verified `v0.5.4` values.

The `v0.5.3` values in the candidate checklist were transient only; the stable formula, workflow checks, and test constants now use the verified `v0.5.4` archive and SHA.

## 8. Update availability documentation

The GitHub Release, PyPI package, release workflow, source-archive SHA, formula promotion, and Homebrew validation are complete. The Homebrew run confirmed the exact tap commit, a clean `brew update-python-resources` result, strict audit, installation, supported Supabase CLI, `0.5.4` version, and formula test. The `0.5.4` changelog is final and the reviewed `README.md` and `docs/installation.md` links use immutable `v0.5.4` refs. No Debian, AUR, or RPM assets were created.

## 0.5.3 publication record (historical)

- GitHub Release: https://github.com/dgabreuu/supa.cc/releases/tag/v0.5.3
- PyPI package: https://pypi.org/project/supa.cc/0.5.3/
- Release tag: `v0.5.3` (`cade1976340db77d90c81b6e0fc4277dd1c91c37`)
- Verified release workflow: https://github.com/dgabreuu/supa.cc/actions/runs/29588209075
- Source archive SHA-256: `1fe25483fba910160328559e1433fe09e962cb494cf34da6122ad4f238aa9914`

The TUI active-account switch fix was published successfully, and the tag and PyPI artifacts remain immutable. The source archive and PyPI README were created before the follow-up availability promotion, so their embedded bootstrap references still point to `v0.5.2`; `v0.5.4` corrects that user-facing metadata. The Homebrew promotion was intentionally not used to rewrite the tag.

The historical `0.5.2` candidate checklist below records the PowerShell bootstrap exit-status fix and its publication gates for context only; it is not a procedure for `0.5.4`. The historical `0.5.0` record below describes only assets that existed in that tag.

## 0.5.1 publication record

- GitHub Release: https://github.com/dgabreuu/supa.cc/releases/tag/v0.5.1
- PyPI package: https://pypi.org/project/supa.cc/0.5.1/
- Release tag: `v0.5.1` (`4cc3d51462a02e1a523e10e445f8085bfe6d35e6`)
- Verified release workflow: https://github.com/dgabreuu/supa.cc/actions/runs/29449131978
- Source archive SHA-256 used for the follow-up Homebrew formula: `db263e555a7a0e4b1d9003f3cb87d72cfcceac0b02dbb9e4c794889110815d15`

The initial release-event workflow run failed before publication because its tag checkout exposed the editable package on `PATH`; the corrected workflow was verified with a manual dispatch from a temporary `v0.5.1-ci` tag. That temporary tag was deleted after the successful Trusted Publishing and Linux/Windows pipx verification. The public `v0.5.1` tag and release were not rewritten.

The `0.5.2` publication record below is historical and is not a procedure for the `0.5.4` candidate.

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
