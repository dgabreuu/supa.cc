# Release checklist

This checklist documents the publication of version 0.4.1. Version 0.4.1 was published and verified on GitHub and PyPI. Homebrew has not been verified yet; the formula update remains a separate promotion gate.

## 1. Validate the candidate commit

Review `git status --short`, `git remote -v`, and the history. Confirm that tracked content and artifacts contain no PAT, absolute local path, cache, virtual environment, diff, or private document.

Run the following from a clean checkout of the candidate commit:

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
rm -rf dist
python3 -m build
python3 scripts/inspect_artifacts.py dist
```

The scanner reports only a finding's class and location, never its value. The inspector requires exactly one wheel and one sdist in `dist/`, validates member paths, and applies the same scanner to both artifacts. Also install the wheel in a disposable virtual environment, run `pip check`, `supa.cc --version`, and `supa.cc version`, and confirm `0.4.1`.

The CI matrix runs the complete standard suite on Python 3.11 and the current stable Python on Ubuntu, macOS, and Windows, plus targeted tests on Fedora and Arch, without accessing real credential stores on hosted runners. Wait for CI to pass on the exact commit before continuing. Native smoke tests remain opt-in and require explicit execution on a host with the native credential store available.

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

Completed: the annotated tag and stable [GitHub Release v0.4.1](https://github.com/dgabreuu/supa.cc/releases/tag/v0.4.1) point to the CI-validated candidate.

Create the annotated `v0.4.1` tag only on the CI-validated commit. Create the corresponding GitHub Release, use the 0.4.1 section of `CHANGELOG.md` as the release notes, and verify the target before selecting **Publish release**.

Publishing the GitHub Release triggers `.github/workflows/release.yml`. The build job checks out the release tag, confirms that it matches the version in `pyproject.toml`, tests, builds once, and uploads one wheel and one sdist as an artifact. Do not attach local builds to the release.

## 5. Publish to PyPI with Trusted Publishing

Completed: [supa.cc 0.4.1 on PyPI](https://pypi.org/project/supa.cc/0.4.1/) contains one wheel and one sdist published through OIDC.

The `build` job has only `contents: read`. The `publish` job downloads exactly the artifact produced by the build and sends it to PyPI through Trusted Publishing using only `id-token: write`. The verification job receives no `GITHUB_TOKEN` permissions.

If the build, inspection, or publication fails, do not recreate the same version on PyPI and do not proceed to the formula. Correct the cause and prepare a new version according to the immutability of published artifacts.

## 6. Verify pipx on Linux and Windows

Completed: the [release workflow](https://github.com/dgabreuu/supa.cc/actions/runs/29291629029) passed build, Trusted Publishing, and both pipx smoke jobs.

After publication, the workflow installs `supa.cc==0.4.1` directly from PyPI with pipx on Linux and Windows and runs both version commands. Confirm that the jobs pass and perform an independent manual verification if release policy requires it:

```bash
pipx install supa.cc==0.4.1
supa.cc --version
supa.cc version
```

## 7. Update the Homebrew formula

Only after pipx verification on Linux and Windows and after the tag exists, update `Formula/supa-cc.rb`. Use the real tarball for tag `v0.4.1`, calculate its real SHA256, and update the Python resources; never anticipate or invent the checksum.

```bash
archive="${TMPDIR:-.}/supa.cc-v0.4.1.tar.gz"
curl -L -o "$archive" https://github.com/dgabreuu/supa.cc/archive/refs/tags/v0.4.1.tar.gz
sha256sum "$archive"
brew tap dgabreuu/supa-cc https://github.com/dgabreuu/supa.cc.git
cd "$(brew --repo dgabreuu/supa-cc)"
brew trust --formula dgabreuu/supa-cc/supa-cc
brew update-python-resources --ignore-main-package-cooldown Formula/supa-cc.rb
brew audit --strict --formula dgabreuu/supa-cc/supa-cc
brew install --build-from-source dgabreuu/supa-cc/supa-cc
brew test dgabreuu/supa-cc/supa-cc
```

On macOS, use `shasum -a 256` if `sha256sum` is unavailable. Keep `head "https://github.com/dgabreuu/supa.cc.git", branch: "main"`.
The explicit trust command is limited to the formula and is required here because
resource generation evaluates the local formula before the installation step.

## 8. Update availability documentation

Only after PyPI and Homebrew have been verified, finalize the changelog entry by replacing `Unreleased` with the actual release date and replacing `HEAD` with tag `v0.4.1` in the comparison link. Update this checklist to record that the release and formula were published.

Do not create Debian, AUR, or RPM assets in this process.
