# Release Checklist

Use this checklist before publishing Supa.cc to GitHub or updating the Homebrew formula.

## Repository Safety

```bash
git status --short
git remote -v
git log -1 --format='%an <%ae>'
```

Confirm the remote is `https://github.com/dgabreuu/supa.cc.git` and that the public commit author is acceptable for the release.

Remove local artifacts before publishing:

```bash
rm -rf .pytest_cache .ruff_cache .venv venv
find . -name __pycache__ -type d -prune -exec rm -rf {} +
find . -name .DS_Store -type f -delete
```

## Version

Update the version in:

- `pyproject.toml`
- `supa_cc/__init__.py`

Then run:

```bash
python3 -m pip install -e ".[dev]"
python3 -m pytest
python3 -m build
```

## GitHub Release

```bash
git tag v0.1.0
git push origin main
git push origin v0.1.0
```

Create a GitHub Release from the tag and attach generated artifacts only if needed. Do not attach local config files, virtual environments, caches, logs, or token exports.

## Homebrew Formula

The repository is not named with the `homebrew-` prefix. Tap it with an explicit URL when testing locally:

```bash
brew tap dgabreuu/supa-cc https://github.com/dgabreuu/supa.cc.git
```

After the tag exists, update `Formula/supa-cc.rb` with the stable tarball URL and SHA256, then generate Python resources from a tapped checkout:

```bash
cd "$(brew --repo dgabreuu/supa-cc)"
brew update-python-resources Formula/supa-cc.rb
brew audit --strict supa-cc
brew test supa-cc
```

The stable source URL should follow this form:

```ruby
url "https://github.com/dgabreuu/supa.cc/archive/refs/tags/v0.1.0.tar.gz"
sha256 "<sha256-from-release-tarball>"
```

Keep `head "https://github.com/dgabreuu/supa.cc.git", branch: "main"` for development installs.
