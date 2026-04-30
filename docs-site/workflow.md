# Workflow & Governance

This page documents how the team should work in the repository after the branch and protection cleanup.

## Canonical Branch Policy

- `main` is the only long-term branch
- feature branches are temporary and should exist only long enough to support a PR
- merged PR branches should be deleted automatically
- maintainers should avoid leaving stale remote branches around

## Contribution Flow

### 1. Create a short-lived branch

```bash
git checkout main
git pull --ff-only
git checkout -b feature/your-change
```

Accepted prefixes:
- `feature/*`
- `fix/*`
- `chore/*`
- `docs/*`
- `refactor/*`
- `test/*`
- `hotfix/*`

### 2. Make changes

- keep commits focused
- test locally when relevant
- avoid landing generated AI artifacts without human review
- keep docs in sync when architecture or workflow changes

### 3. Open a PR to `main`

```bash
git push origin feature/your-change
```

Then open a PR and let GitHub run checks.

## Required Merge Shape

The repository is configured for:
- **squash merge only**
- **linear history**
- **conversation resolution before merge**
- **branch auto-delete after merge**

Merge commits and rebase merges are disabled.

## Required Checks

Current protected-branch checks are:
- `Branch Name Policy`
- `Test`
- `Python Compat (3.11)`
- `Python Compat (3.12)`
- `Python Compat (3.13)`

## Important Maintainer Notes

- admins are enforced on `main`
- protections should match real workflow job names, not guessed names
- if branch protection is blocking valid maintainer work, fix the policy instead of piling on bypasses
- if a repo-owned PR must be merged urgently, document why

## AI and Automation Policy

The repo no longer uses AI auto-fix or AI auto-doc workflows in the normal merge path.

That means:
- CI failures should be fixed intentionally
- documentation updates should be reviewed by a maintainer
- generated output should never be merged blindly

## Docs Site Workflow

The public docs site is built with MkDocs from `docs-site/` and deployed from pushes to `main`.

When updating docs:
- update `docs-site/` for site-facing pages
- update `README.md` for repo-facing overview changes
- keep roadmap/workflow/architecture pages consistent with actual repo behavior

## Quick Reference

| Action | Expected path |
|--------|----------------|
| Feature work | short-lived branch -> PR -> squash merge |
| Docs update | `docs-site/` + README when needed |
| Governance change | update GitHub protections and document it |
| Extension architecture change | update code + `docs-site/extension.md` |
