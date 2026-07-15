# Release record and checklist

This document records the publication of version 0.5.1 on 2026-07-15.

The next stable release is `0.5.2`. Its candidate checklist includes the PowerShell bootstrap exit-status fix; the historical `0.5.0` record below describes only assets that existed in that tag.

## 0.5.1 publication record

- GitHub Release: https://github.com/dgabreuu/supa.cc/releases/tag/v0.5.1
- PyPI package: https://pypi.org/project/supa.cc/0.5.1/
- Release tag: `v0.5.1` (`4cc3d51462a02e1a523e10e445f8085bfe6d35e6`)
- Verified release workflow: https://github.com/dgabreuu/supa.cc/actions/runs/29449131978
- Source archive SHA-256 used for the follow-up Homebrew formula: `db263e555a7a0e4b1d9003f3cb87d72cfcceac0b02dbb9e4c794889110815d15`

The initial release-event workflow run failed before publication because its tag checkout exposed the editable package on `PATH`; the corrected workflow was verified with a manual dispatch from a temporary `v0.5.1-ci` tag. That temporary tag was deleted after the successful Trusted Publishing and Linux/Windows pipx verification. The public `v0.5.1` tag and release were not rewritten.

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

## 0.5.2 candidate checklist

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

## 0.5.2 publication follow-up

After the candidate checks pass, execute the following sequence for `0.5.2`:

1. Push the release commit and create the annotated tag `v0.5.2`.
2. Create a stable, published, non-draft GitHub Release from that tag.
3. Confirm the release workflow publishes `supa.cc==0.5.2` through Trusted Publishing and that Linux and Windows `pipx` verification passes.
4. Download the `v0.5.2` source archive, calculate its SHA-256, update `Formula/supa-cc.rb`, and run the Homebrew audit, install, version, and test gates.
5. Verify both raw installer URLs resolve from `v0.5.2` and that the scripts contain the reviewed checksums and pinned upstream revisions.
6. Only after those checks, update the bootstrap links in `docs/installation.md` and `README.md` to `v0.5.2`; retain this immutable-tag requirement for future releases.

The verified `v0.5.1` source archive SHA-256 is `db263e555a7a0e4b1d9003f3cb87d72cfcceac0b02dbb9e4c794889110815d15`. The `v0.5.2` archive hash must be calculated from the public tag after publication.
