# Release Process

## Overview

Releases are triggered by pushing a `v*.*.*` tag to `main`. The CI pipeline gates the release on
a successful `ci.yml` run for the same commit SHA.

## PyPI Trusted Publishing (OIDC)

This repo uses OIDC trusted publishing - no `PYPI_API_TOKEN` secret is needed.

### Setup (one-time, maintainer only)

1. Go to https://pypi.org/manage/account/publishing/
2. Add a new pending publisher:
   - PyPI project name: `canvas-sdk`
   - Owner: `kleinpanic`
   - Repository: `CS3704-Canvas-Project`
   - Workflow filename: `release.yml`
   - Environment name: `pypi`

3. Repeat on https://test.pypi.org/manage/account/publishing/ with environment name: `test-pypi`

### GitHub Environment Setup

Two GitHub Environments must exist in the repo settings:
- `pypi` - no additional secrets needed; OIDC handles auth
- `test-pypi` - no additional secrets needed

To create: Repository Settings -> Environments -> New environment.

## Release Flow

1. Ensure CI passes on `main` for the target commit.
2. Tag the release: `git tag v2.X.Y && git push origin v2.X.Y`
3. The `release.yml` workflow runs automatically:
   - Builds source archives, SDK wheel, and extension ZIP
   - Creates the GitHub Release with all artifacts
   - **Test PyPI dry-run** (`test-pypi` job) publishes to test.pypi.org first
   - If dry-run succeeds, **PyPI publish** (`publish-pypi` job) publishes the real package
   - **SBOM** and **SLSA provenance** are attached to the GitHub Release
4. Verify the release at https://pypi.org/project/canvas-sdk/

## Fork Behavior

Forks that have not configured the `pypi` and `test-pypi` environments will have the
`test-pypi` and `publish-pypi` jobs skipped automatically - no red CI.

## Verifying a Release

See [BREAKING.md](../BREAKING.md) for `slsa-verifier` and `cosign` verification commands.
