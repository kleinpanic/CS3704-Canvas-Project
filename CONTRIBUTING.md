# Contributing

## Workflow
1. Open or pick an Issue.
2. Create a feature branch using one of:
   - `feature/<name>`
   - `fix/<name>`
   - `chore/<name>`
   - `docs/<name>`
   - `refactor/<name>`
   - `test/<name>`
   - `hotfix/<name>`
3. Open a PR to `main`.
4. Ensure required checks pass.
5. Get required review approval.
6. Merge via PR (direct pushes to `main` are blocked).

## Commit Signing
Protected branch rules require signed commits on `main`.
Please sign local commits with GPG/SSH signing keys.

## Local quality checks
```bash
ruff check src tests
pytest tests -q
```

## PR expectations
- Link an Issue
- Keep scope tight
- Update docs for behavior changes
- Include screenshots/evidence for UI/docs updates
