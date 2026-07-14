# Release checklist

This checklist documents the publication of version 0.4.2. Version 0.4.2 has not been published yet.

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

Confirm Supabase CLI >= 2.109.1, the official `supabase` profile, executable trust, verification of the exact native credential, mutation-aware recovery, logout when removing the active account, and blocking of the plaintext fallback. `doctor` must remain non-live by default; only `doctor --account <name> --live` opens the token for explicit validation. The lock does not coordinate concurrent external `supabase` commands.

## 3. Configure Trusted Publishing

Configure a PyPI Trusted Publisher for the `supa.cc` project with these values before publishing:

- Owner: `dgabreuu`
- Repository: `supa.cc`
- Workflow: `release.yml`
- Environment: `pypi`

Protect the `pypi` environment according to repository policy. The workflow uses OIDC with `id-token: write`; do not create a PyPI API token or secret.

## 4. Publish the GitHub Release

Confirm that the annotated tag and GitHub Release `v0.4.2` do not already exist. Create the annotated tag only on the CI-validated candidate commit, then create a stable, non-draft, non-prerelease GitHub Release using the `0.4.2` section of `CHANGELOG.md` as the release notes.

Publishing the GitHub Release triggers `.github/workflows/release.yml`. The build job checks out the release tag, confirms that it matches the version in `pyproject.toml`, tests, builds once, and uploads one wheel and one sdist as an artifact. Do not attach local builds to the release.

## 5. Publish to PyPI with Trusted Publishing

The `build` job has only `contents: read`. The `publish` job downloads exactly the artifact produced by the build and sends it to PyPI through Trusted Publishing using only `id-token: write`. The verification job receives no `GITHUB_TOKEN` permissions.

Confirm that `supa.cc==0.4.2` is available on PyPI and that the release workflow's Linux and Windows pipx checks pass. If the build, inspection, or publication fails, do not recreate the same version on PyPI and do not proceed to the formula. Correct the cause and prepare a new version according to the immutability of published artifacts.

## 6. Verify pipx on Linux and Windows

The release workflow installs `supa.cc==0.4.2` directly from PyPI with pipx on Linux and Windows and runs both version commands. Confirm that these jobs pass and perform an independent manual verification if release policy requires it:

```bash
pipx install supa.cc==0.4.2
supa.cc --version
supa.cc version
```

## 7. Update the Homebrew formula

Homebrew has not been verified yet for version 0.4.2.

Only after PyPI and pipx verification and after the tag exists, update `Formula/supa-cc.rb`. Download the real tarball for tag `v0.4.2`, calculate its real SHA256, and update the Python resources only through Homebrew tooling; never anticipate or invent the checksum.

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

Commit and publish the verified formula through a separate PR. Run `.github/workflows/homebrew.yml` manually against the exact formula commit and confirm its audit, resource, installation, version, and test gates pass on macOS.

## 8. Update availability documentation

Only after GitHub, PyPI, pipx, and Homebrew have been verified, finalize the `0.4.2` changelog entry with the actual release date and replace the comparison target `HEAD` with `v0.4.2`. Update this checklist with the verified public release, package, workflow, and formula links.

Do not create Debian, AUR, or RPM assets in this process.
