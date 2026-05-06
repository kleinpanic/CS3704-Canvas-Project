# Workflow & Governance

This page documents how the team works in this repository.

## Branch Policy

`main` is the only long-term branch. Feature branches are short-lived — open a PR, get it merged, delete the branch.

## Contribution Flow

### 1. Create a branch

```bash
git checkout main
git pull --ff-only
git checkout -b feature/your-change
```

Accepted prefixes (enforced by CI):

- `feature/*`
- `fix/*`
- `chore/*`
- `docs/*`
- `refactor/*`
- `test/*`
- `hotfix/*`
- `dependabot/*`

### 2. Make changes

- Keep commits focused and signed (GPG signing is required)
- Run `ruff check src tests` and `pytest tests -q` before pushing
- Update docs when behavior or architecture changes

### 3. Open a PR to `main`

```bash
git push origin feature/your-change
```

Open a PR, wait for CI, get a review approval from `@kleinpanic` (required by CODEOWNERS for all files; `.github/workflows/`, `README.md`, and `docs/**` are additionally gated).

## Merge Convention

PRs are squash-merged to keep a linear history. Merge commits and rebase merges are not used. Resolve all conversations before merging.

## CI Jobs

Every PR and push to `main` runs the following jobs:

| Workflow | Jobs |
|----------|------|
| `ci.yml` | Test, Coverage, Python Compat (3.11 / 3.12 / 3.13), Dead Code Analysis |
| `quick-checks.yml` | Ruff Lint, Ruff Format, Mypy Type Check |
| `branch-policy.yml` | Branch Name Policy |
| `security.yml` | CodeQL Analyze, Dependency Review |

Dead Code Analysis and Mypy are non-blocking (warnings only). Coverage threshold is 80%; add `no-coverage-check` to the PR body to bypass when justified.

## AI and Automation Policy

No AI auto-fix or auto-doc workflows run in the merge path.

- Fix CI failures intentionally.
- Review all generated output before merging it.
- Documentation updates go through normal PR review.

## Docs Site

The public docs site is built with MkDocs Material from `docs-site/` and deployed to GitHub Pages on every push to `main` via `pages.yml`. The deploy pre-fetches live Canvas data into static JSON and installs the agent demo page and extension source.

When updating docs:

- Edit `docs-site/` for site-facing pages
- Edit `README.md` for repo-facing overview changes
- Keep roadmap, workflow, and architecture pages in sync with actual behavior

## Quick Reference

| Action | Path |
|--------|------|
| Feature work | short-lived branch → PR → squash merge |
| Docs update | `docs-site/` + `README.md` when needed |
| Governance change | update GitHub settings and document it here |
| Architecture change | update code + `docs-site/architecture.md` |
