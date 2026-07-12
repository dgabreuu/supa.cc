# Homebrew Validation Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update the Homebrew formula to v0.3.0 and validate it reproducibly on a read-only GitHub Actions macOS runner before declaring the tap published.

**Architecture:** Keep formula generation and commits in the normal repository workflow. Add one manually dispatched, least-privilege macOS workflow that validates the committed formula without editing, committing, pushing, or publishing anything.

**Tech Stack:** Homebrew Ruby formula, GitHub Actions, macOS, PyYAML, pytest, GitHub CLI

## Global Constraints

- The formula source is exactly `https://github.com/dgabreuu/supa.cc/archive/refs/tags/v0.3.0.tar.gz` with SHA256 `0b54c209831fef223d8bff3518c54310f3c89e7e4bde0e676f84dd5dd8c2acdd`.
- `.github/workflows/homebrew.yml` is triggered only by `workflow_dispatch` and runs on `macos-latest`.
- Workflow-level permissions are empty; the validation job has only `contents: read`.
- The workflow uses no secrets, OIDC, write permissions, commit, push, release, or package-upload operation.
- The workflow validates committed resources with `brew update-python-resources` followed by `git diff --exit-code`.
- The workflow runs strict audit, source installation, both version commands, and `brew test`.
- The installed version must be exactly `0.3.0`.
- Do not publish an unverified formula or force-push `main`.

## File Map

- Create `.github/workflows/homebrew.yml`: manual read-only macOS formula validation.
- Modify `Formula/supa-cc.rb`: v0.3.0 tag URL and real archive checksum; resources remain generated from the published runtime graph.
- Modify `tests/test_publication_assets.py`: enforce formula identity, workflow trigger, permissions, commands, and prohibited capabilities.

---

### Task 1: Add the read-only macOS validation workflow and update the formula

**Files:**
- Create: `.github/workflows/homebrew.yml`
- Modify: `Formula/supa-cc.rb:6-7`
- Modify: `tests/test_publication_assets.py:12-46`

**Interfaces:**
- Consumes: immutable GitHub tag `v0.3.0` and published Python runtime dependencies
- Produces: a formula for v0.3.0 and a manually dispatched workflow that validates the checked-out commit

- [ ] **Step 1: Update formula expectations and add failing workflow tests**

Change the constants in `tests/test_publication_assets.py` to:

```python
TARBALL_URL = "https://github.com/dgabreuu/supa.cc/archive/refs/tags/v0.3.0.tar.gz"
TARBALL_SHA256 = "0b54c209831fef223d8bff3518c54310f3c89e7e4bde0e676f84dd5dd8c2acdd"
```

Replace the pre-release formula assertion with:

```python
def test_release_formula_uses_verified_0_3_0_tag():
    release = Path("docs/release.md").read_text(encoding="utf-8")
    formula = Path("Formula/supa-cc.rb").read_text(encoding="utf-8")

    assert "v0.3.0" in formula
    assert "v0.2.0" not in formula
    assert "brew test supa-cc" in release
```

Add these tests:

```python
def test_homebrew_workflow_is_manual_read_only_macos_validation():
    path = Path(".github/workflows/homebrew.yml")
    workflow_text = path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)
    trigger = workflow.get("on", workflow.get(True))

    assert trigger == {"workflow_dispatch": None}
    assert workflow["permissions"] == {}
    validate = workflow["jobs"]["validate"]
    assert validate["runs-on"] == "macos-latest"
    assert validate["permissions"] == {"contents": "read"}
    assert "secrets" not in workflow_text.lower()
    assert "id-token" not in workflow_text.lower()
    for permission in ("write", "packages:", "deployments:"):
        assert permission not in workflow_text.lower()


def test_homebrew_workflow_validates_committed_formula_without_publishing():
    workflow_text = Path(".github/workflows/homebrew.yml").read_text(encoding="utf-8")

    for command in (
        "brew update-python-resources Formula/supa-cc.rb",
        "git diff --exit-code -- Formula/supa-cc.rb",
        "brew audit --strict --formula ./Formula/supa-cc.rb",
        "brew install --build-from-source ./Formula/supa-cc.rb",
        "supa.cc --version",
        "supa.cc version",
        "brew test supa-cc",
    ):
        assert command in workflow_text
    assert "0.3.0" in workflow_text
    for prohibited in ("git commit", "git push", "gh release", "upload-artifact"):
        assert prohibited not in workflow_text
```

- [ ] **Step 2: Run the targeted tests and verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_publication_assets.py -q
```

Expected: failures because the formula still references v0.2.0 and `.github/workflows/homebrew.yml` does not exist.

- [ ] **Step 3: Update the formula source identity**

Change `Formula/supa-cc.rb` lines 6-7 to:

```ruby
url "https://github.com/dgabreuu/supa.cc/archive/refs/tags/v0.3.0.tar.gz"
sha256 "0b54c209831fef223d8bff3518c54310f3c89e7e4bde0e676f84dd5dd8c2acdd"
```

- [ ] **Step 4: Add the manual read-only workflow**

Create `.github/workflows/homebrew.yml` with:

```yaml
name: Validate Homebrew formula

on:
  workflow_dispatch:

permissions: {}

jobs:
  validate:
    runs-on: macos-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4
        with:
          persist-credentials: false
      - name: Verify generated Python resources
        run: |
          brew update-python-resources Formula/supa-cc.rb
          git diff --exit-code -- Formula/supa-cc.rb
      - name: Audit formula
        run: brew audit --strict --formula ./Formula/supa-cc.rb
      - name: Install formula from source
        run: brew install --build-from-source ./Formula/supa-cc.rb
      - name: Verify installed version
        run: |
          test "$(supa.cc --version)" = "supa.cc, version 0.3.0"
          supa.cc version | grep -Fx "Supa.cc v0.3.0"
      - name: Test formula
        run: brew test supa-cc
```

- [ ] **Step 5: Run targeted and full tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_publication_assets.py -q
.venv/bin/python -m pytest
.venv/bin/python -m pip check
.venv/bin/pip-audit --skip-editable
git diff --check
```

Expected: all tests and dependency checks pass; no whitespace error.

- [ ] **Step 6: Commit the implementation**

Run:

```bash
git add .github/workflows/homebrew.yml Formula/supa-cc.rb tests/test_publication_assets.py
git diff --cached --check
git diff --cached --stat
git commit -m "brew: validate formula for v0.3.0"
```

Expected: exactly the workflow, formula, and publication tests are committed.

### Task 2: Publish the formula commit and validate it on macOS

**Files:**
- No additional file changes

**Interfaces:**
- Consumes: committed formula and workflow from Task 1
- Produces: green normal CI and green manual Homebrew validation on the same commit

- [ ] **Step 1: Push the reviewed commit to main**

Run:

```bash
git fetch origin main
test "$(git rev-parse origin/main)" = "e5f9f726667c5d9580145bcaae0ecd62fa073cc5"
git status --short --branch
git push origin main
```

Expected: normal non-force push succeeds. Stop if `origin/main` advanced unexpectedly.

- [ ] **Step 2: Require normal CI on the exact formula SHA**

Run:

```bash
formula_sha=$(git rev-parse HEAD)
ci_run=$(gh run list --repo dgabreuu/supa.cc --commit "$formula_sha" --workflow CI --limit 1 --json databaseId --jq '.[0].databaseId')
test -n "$ci_run"
gh run watch --repo dgabreuu/supa.cc --exit-status "$ci_run"
```

Expected: all CI jobs succeed for the exact formula SHA.

- [ ] **Step 3: Dispatch the Homebrew workflow on main**

Run:

```bash
gh workflow run homebrew.yml --repo dgabreuu/supa.cc --ref main
homebrew_run=$(gh run list --repo dgabreuu/supa.cc --workflow homebrew.yml --event workflow_dispatch --branch main --limit 1 --json databaseId,headSha --jq 'select(.[0].headSha == "'"$formula_sha"'") | .[0].databaseId')
test -n "$homebrew_run"
gh run watch --repo dgabreuu/supa.cc --exit-status "$homebrew_run"
```

Expected: the manual workflow runs on the exact formula SHA and every macOS validation step succeeds.

- [ ] **Step 4: Verify a clean installation from the public tap in the workflow evidence**

Run:

```bash
gh run view --repo dgabreuu/supa.cc "$homebrew_run" --json url,headSha,event,status,conclusion,jobs
gh run view --repo dgabreuu/supa.cc "$homebrew_run" --log
```

Expected: logs show resource verification, strict audit, source installation, both 0.3.0 version commands, and `brew test` succeeding. No write or publication operation appears.

- [ ] **Step 5: Record evidence before final release documentation**

Record the formula commit SHA, normal CI URL, Homebrew workflow URL, and successful macOS commands in the release progress report. Do not remove pre-release availability warnings until this task is green.
