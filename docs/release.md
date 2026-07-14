# Release record and checklist

This document records the publication of version 0.4.2 on 2026-07-14.

## Publication record

- GitHub Release: https://github.com/dgabreuu/supa.cc/releases/tag/v0.4.2
- Release workflow: https://github.com/dgabreuu/supa.cc/actions/runs/29337523022
- PyPI package: https://pypi.org/project/supa.cc/0.4.2/
- Homebrew formula: https://github.com/dgabreuu/supa.cc/blob/main/Formula/supa-cc.rb
- Homebrew validation workflow: https://github.com/dgabreuu/supa.cc/actions/runs/29338145621
- The annotated tag `v0.4.2` points to commit `8a83e931c85a6db61539e371ee1b1c3d09f79604`.
- The Homebrew formula was promoted in commit `019a5d6a017139a303baccd403036646e689236a`.
- The release workflow produced and published one wheel and one sdist through Trusted Publishing; its build, publish, Linux pipx, and Windows pipx jobs passed.
- The Homebrew workflow passed its exact-tap, resource, audit, installation, version, and test gates.

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
```

The scanner reports only a finding's class and location, never its value. The inspector requires exactly one wheel and one sdist in `dist/`, validates member paths, and applies the same scanner to both artifacts. Install the wheel in a disposable virtual environment, run `pip check`, `supa.cc --version`, and `supa.cc version`, and confirm `0.4.2`.

The CI matrix must pass on Python 3.11 and the current stable Python on Ubuntu, macOS, and Windows, plus the targeted Fedora and Arch jobs, before the release tag is created. Native smoke tests remain opt-in and require explicit execution on a host with the native credential store available.

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

The annotated tag and GitHub Release `v0.4.2` were created only after the candidate checks passed. The release is stable, non-draft, and non-prerelease, and uses the `0.4.2` section of `CHANGELOG.md` as its notes.

Publishing the GitHub Release triggered `.github/workflows/release.yml`. The workflow checked out the release tag, confirmed that it matched `pyproject.toml`, tested, built once, and uploaded one wheel and one sdist as an artifact. No local builds were attached to the release.

## 5. Publish to PyPI with Trusted Publishing

The `build` job had only `contents: read`. The `publish` job downloaded exactly the artifact produced by the build and sent it to PyPI through Trusted Publishing using only `id-token: write`. The verification jobs received no `GITHUB_TOKEN` permissions.

`supa.cc==0.4.2` is available on PyPI with both a wheel and sdist. The release workflow's Linux and Windows pipx checks passed after the Linux index-propagation retry. The published version was not recreated.

## 6. Verify pipx on Linux and Windows

The release workflow installed `supa.cc==0.4.2` directly from PyPI with pipx on Linux and Windows and ran both version commands. Both jobs passed:

```bash
pipx install supa.cc==0.4.2
supa.cc --version
supa.cc version
```

## 7. Update the Homebrew formula

The Homebrew formula now points to tag `v0.4.2` and uses the verified SHA256 `917a22b0bbf29b3f76dec009994d597adad7d03307d9a7fb57b177c61c2380d5`.

The formula was updated only after PyPI and pipx verification and after the tag existed. The real tarball for tag `v0.4.2` was downloaded and its SHA256 was calculated; Python resources were checked with Homebrew tooling and required no changes.

```bash
archive="${TMPDIR:-.}/supa.cc-v0.4.2.tar.gz"
curl --fail --location --output "$archive" https://github.com/dgabreuu/supa.cc/archive/refs/tags/v0.4.2.tar.gz
shasum -a 256 "$archive"
brew tap dgabreuu/supa-cc https://github.com/dgabreuu/supa.cc.git
cd "$(brew --repo dgabreuu/supa-cc)"
brew install supabase/tap/supabase
brew trust --formula dgabreuu/supa-cc/supa-cc
brew update-python-resources --ignore-main-package-cooldown Formula/supa-cc.rb
brew audit --strict --formula dgabreuu/supa-cc/supa-cc
brew install --build-from-source dgabreuu/supa-cc/supa-cc
brew test dgabreuu/supa-cc/supa-cc
```

Keep `head "https://github.com/dgabreuu/supa.cc.git", branch: "main"`. The explicit trust command is limited to the formula and is required because resource generation evaluates the local formula before installation.

The verified formula was published through separate PR #9: https://github.com/dgabreuu/supa.cc/pull/9. `.github/workflows/homebrew.yml` ran manually against the exact formula commit and its audit, resource, installation, version, and test gates passed on macOS.

## 8. Update availability documentation

After GitHub, PyPI, pipx, and Homebrew were verified, the `0.4.2` changelog entry was finalized with the publication date and its comparison target was changed from `HEAD` to `v0.4.2`. This checklist records the verified public release, package, workflow, and formula links above.

Do not create Debian, AUR, or RPM assets in this process.
