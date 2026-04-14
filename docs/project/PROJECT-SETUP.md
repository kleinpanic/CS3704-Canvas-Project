# CS3704 Canvas TUI — Project Setup Proposal

**Goal:** Simplify the CI pipeline, make contributions pass with help not rejection, and add a post-merge AI documentation layer. Realistic for a 4–6 person class project.

---

## 1. Current State

The project has 8 GitHub Actions workflows. Most are over-engineered for a course project:

| Workflow | Status | Problem |
|----------|--------|---------|
| `ci.yml` | Over-engineered | Matrix of 3 Python versions, strict lint gates, mypy enforced as blocking |
| `coverage.yml` | Over-engineered | Coverage threshold blocks merge (too strict for class project) |
| `release.yml` | Over-engineered | Requires passing CI commit — fine but complex for scope |
| `pages.yml` | OK | Works, keeps docs site live |
| `branch-policy.yml` | Hard-block | Branch naming as a hard fail is too strict for novices |
| `auto-assign.yml` | OK | Auto-assigns reviewers, useful |
| `security.yml` | Over-engineered | CodeQL + dependency review — enterprise tooling for a class project |
| `stale.yml` | OK | Closes stale issues, useful |

Teammate PRs are sitting unmerged (jiepan #26, 802797liu #25, feature/grades-screen #23).

---

## 2. Proposed Workflows

### 2.1 `ci.yml` — Slimmed Down

**What it does:**
- Runs unit tests (pytest)
- Runs only critical lint: `ruff check --select=E,F` (syntax + undefined names + import errors)
- NOT blocking for style issues — formatter handles those

**What it removes:**
- Matrix Python versions (use 3.11 only — the class standard)
- Mypy as blocking (advisory-only, run locally with `make typecheck`)
- Ruff full lint suite as hard blocker
- Coverage threshold enforcement

**Failure behavior:**
- First failure → posts a comment with the error
- Triggers `ai-fixup.yml` (see below) automatically

### 2.2 `ai-fixup.yml` — Post-Failure Help, Not Rejection

**Trigger:** `ci.yml` fails on a pull request

**What it does:**
1. Reads the failing test / lint output
2. Calls Nemotron (DGX Spark, local, no external API exposure) to generate a fix
3. Pushes a `fixup/<pr-number>-attempt-1` branch with the patch
4. Posts a PR comment: "Automated fix applied — review and merge"

**Security model:**
- Nemotron runs in GitHub Actions as a job, API key stored as GitHub secret
- Contributors never interact with the model directly
- The fixup branch is clearly labeled as auto-generated

**If fixup also fails:**
- Second attempt with more specific context
- If still failing → hard fail with clear error message (not a vague "CI failed")

**If fixup passes:**
- Original PR author reviews the fixup branch
- Merges the fixup into their branch → CI goes green
- Original contributor learns from the patch

### 2.3 `auto-docs.yml` — Post-Merge Documentation

**Trigger:** `push` to `main` (post-merge)

**What it does:**
1. Scans newly merged modules for missing docstrings (via AST analysis)
2. Calls Nemotron to generate docstrings for public functions/classes
3. Opens an `auto-docs` PR targeting `main` with the generated stubs
4. Team reviews and merges (or closes if not needed)

**Rules:**
- Non-blocking — does not affect the original PR
- Never overwrites manually written docs
- Only fills in empty stubs

### 2.4 `pages.yml` — Keep As-Is

Docs site deployment on main push. Already works.

### 2.5 `auto-assign.yml` — Keep As-Is

Auto-assigns reviewers to PRs. Useful for team accountability.

---

## 3. Make Targets That Matter

The current Makefile has too many targets. Simplify to only what contributors actually need:

| Target | Purpose |
|--------|---------|
| `make install-dev` | **Start here.** Creates venv, installs `.[dev]`, sets up pre-commit hooks |
| `make test` | Run pytest quietly (`-q`) — what CI runs |
| `make build` | `python -m build` → `dist/` for release |
| `make typecheck` | `mypy` — advisory only, not blocking |
| `make ci` | Full local simulation: lint + tests + build |
| `make check` | Pre-commit: format + lint + test |

### Developer Guide (DEVELOPER_GUIDE.md)

Created at `docs/project/DEVELOPER_GUIDE.md`. One page covering:
- Clone → setup → run
- Dev vs prod build difference
- How to write and run tests
- How to make a release

---

## 4. PR Contribution Agreement

Before merging, contributor must:
1. `make check` passes locally
2. New code includes at minimum a module-level docstring
3. PR description links to the relevant Issue

That's it. No signed commits, no branch naming police, no coverage threshold.

---

## 5. Staged Test Model

Contributors must be able to run all test stages locally:

```bash
make test          # unit tests (fast, ~211 tests currently)
make typecheck     # mypy (advisory)
make ci            # full pipeline simulation
```

CI runs the same stages. No hidden gates.

---

## 6. Integration Tests (Item 5 — Fix)

Add a `tests/integration/` directory with mock Canvas API responses so contributors can test their screen/module against a realistic API surface without hitting a live server. This is the staging area.

Current test suite covers unit tests only. Integration stubs are a missing layer.

---

## 7. Workflow Changes Summary

| Action | File |
|--------|------|
| **Replace** | `.github/workflows/ci.yml` → slimmed version |
| **Replace** | `.github/workflows/coverage.yml` → removed (advisory only) |
| **Create** | `.github/workflows/ai-fixup.yml` |
| **Create** | `.github/workflows/auto-docs.yml` |
| **Remove** | `.github/workflows/branch-policy.yml` (soft warn only) |
| **Simplify** | `.github/workflows/security.yml` → remove CodeQL/dependency-review |
| **Keep** | `pages.yml`, `auto-assign.yml`, `stale.yml`, `dependabot.yml` |

---

## 8. Staging Overview

```
PR opened
    → ci.yml fires (lint + test)
        → PASS → review + merge
        → FAIL → ai-fixup.yml fires
            → fixup branch pushed to PR
            → PASS → author merges fixup → CI green → merge
            → FAIL → hard fail with specific error
    → merged to main
        → auto-docs.yml fires
            → PR opened with doc stubs
            → team reviews → merge or close
```

---

_This is a proposal — implement after Klein approves the structure._