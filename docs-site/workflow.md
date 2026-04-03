# Workflow & Governance

## Team workflow
1. Open or pick an Issue.
2. Create a branch from `main` using the approved naming rules.
3. Open a PR early and link the Issue.
4. Pass CI, security, and branch-policy checks.
5. Resolve review comments.
6. Merge through GitHub only.

## Enforced protections
- PR-only changes to `main`
- required CI before merge
- required review and code-owner review
- no force-push on protected `main`
- no deletion of protected `main`
- signed commits required on protected `main`
- linear history + resolved conversations

## Automation
- issue templates with default labels
- Dependabot for dependencies and GitHub Actions
- stale issue / PR cleanup
- PR auto-labeling by changed paths
- CodeQL + dependency review
- auto package snapshot release on clean `main` push
