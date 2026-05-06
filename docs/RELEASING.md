# Release Channels

This project ships through three channels:

## 1. Stable releases (`v*`)

- Tag format: `v1.2.0`, `v1.3.0-rc1`, etc.
- Triggered by pushing a `v*` tag to `main`.
- Workflow: `.github/workflows/release.yml`
- Publishes to: GitHub Releases + PyPI (canvas-sdk via OIDC trusted publishing) + GHCR (canvas-tui Docker image)
- PyPI publishing requires a one-time trusted-publisher registration at pypi.org for repo `kleinpanic/CS3704-Canvas-Project`, workflow `release.yml`, environment `pypi`.

## 2. Nightly snapshots (`nightly-*`)

- Tag format: `nightly-YYYYMMDD-<sha>`
- Triggered: daily cron at 06:00 UTC, or manual `workflow_dispatch`.
- Workflow: `.github/workflows/nightly.yml`
- Publishes to: GitHub Releases (marked as pre-release) ONLY. NOT PyPI.
- Use case: bleeding-edge testing without PyPI noise.

## 3. CI snapshot tags (`snapshot-*`)

Legacy. Created by older release.yml versions. Do not push new ones.

## Cutting a stable release

1. Decide on the new version (e.g., v1.3.0). Bump:
   - `pyproject.toml` (root) version field
   - `src/sdk/pyproject.toml` version field
   - Add CHANGELOG entry under `## [1.3.0] — YYYY-MM-DD`
2. PR + merge. CI's version-check + changelog-enforcer must pass.
3. From `main`: `git tag v1.3.0 && git push origin v1.3.0`
4. `release.yml` fires: builds artifacts, creates GitHub Release, uploads to PyPI/GHCR.

## Branch protection (operator action — manual)

Recommended `main` branch protection:

- [ ] Require pull request before merging
- [ ] Require approvals: 1+ (codeowners review)
- [ ] Dismiss stale approvals on new commits
- [ ] Require status checks to pass before merging:
  - Branch Name Policy
  - Ruff Format / Ruff Lint
  - Mypy Type Check
  - Test
  - Coverage (advisory)
  - CodeQL Analyze
  - Conventional title (PR Quality)
  - Changelog required (PR Quality)
  - Version Check
- [ ] Require branches to be up to date before merging
- [ ] Require signed commits
- [ ] Require linear history
- [ ] Do NOT allow force pushes
- [ ] Do NOT allow deletions

Apply via: GitHub Repo Settings → Branches → Branch protection rules → Edit rule for `main`.

Or via API:
```bash
gh api -X PUT repos/kleinpanic/CS3704-Canvas-Project/branches/main/protection \
  --input branch-protection.json
```
