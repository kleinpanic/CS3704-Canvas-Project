# Team Workflow

This page documents how the team coordinates on the CS3704 Canvas project.

## Quick Reference

| Action | How |
|--------|-----|
| **Report a bug** | [Open an Issue](https://github.com/kleinpanic/CS3704-Canvas-Project/issues/new/choose) |
| **Request a feature** | [Open an Issue](https://github.com/kleinpanic/CS3704-Canvas-Project/issues/new/choose) |
| **Ask a question** | [Start a Discussion](https://github.com/kleinpanic/CS3704-Canvas-Project/discussions) |
| **Check sprint tasks** | [Project Board](https://github.com/users/kleinpanic/projects/5) |
| **Read documentation** | [Wiki](https://github.com/kleinpanic/CS3704-Canvas-Project/wiki) |

## Contribution Flow

### 1. Find Work

- Check the [Project Board](https://github.com/users/kleinpanic/projects/5) for ready tasks
- Browse [Open Issues](https://github.com/kleinpanic/CS3704-Canvas-Project/issues)
- Comment on an issue to claim it

### 2. Create Branch

```bash
git checkout main
git pull
git checkout -b feature/your-feature-name
```

**Branch naming**:

| Prefix | Purpose | Example |
|--------|---------|---------|
| `feature/` | New functionality | `feature/grades-chart` |
| `fix/` | Bug fixes | `fix/api-timeout` |
| `chore/` | Maintenance | `chore/update-deps` |
| `docs/` | Documentation | `docs/improve-readme` |

### 3. Make Changes

- Write clean, tested code
- Follow the [Development Guide](https://github.com/kleinpanic/CS3704-Canvas-Project/wiki/Development-Guide)
- Commit with descriptive messages

### 4. Open Pull Request

```bash
git push origin feature/your-feature-name
```

Then:
1. Go to GitHub and open a PR
2. Fill in the PR template
3. Link to related issues
4. Request review from a maintainer

### 5. Pass Checks

CI will automatically run:
- **Lint** (ruff) — code style
- **Tests** (pytest) — unit tests on Python 3.11/3.12/3.13
- **Package build** — verify build succeeds
- **Security** (CodeQL) — vulnerability scan

Fix any failures before review.

### 6. Address Review

- Respond to all comments
- Make requested changes
- Mark conversations as resolved
- Push new commits

### 7. Merge

A maintainer will merge when:
- All checks pass
- Review is approved
- Conversations are resolved

## Branch Protection

The `main` branch is protected with:

- ✅ PR required (no direct push for team)
- ✅ Passing CI checks required
- ✅ Code owner review required
- ✅ Signed commits required
- ✅ Linear history enforced
- ✅ Conversations must be resolved

**Maintainers** can bypass these for emergency fixes.

## Automation

| Bot | Purpose | Frequency |
|-----|---------|-----------|
| **CI** | Lint, test, build | Every push |
| **Dependabot** | Dependency updates | Weekly |
| **Stale** | Close inactive issues | Daily |
| **Labeler** | Label PRs by files | Every PR |
| **Auto-assign** | Assign new issues | Every issue |
| **Release** | Create snapshots | Every main push |

## Issue Templates

Use the appropriate template when opening issues:

- **Bug Report** — Report something broken
- **Feature Request** — Propose new functionality
- **Task** — General work item

[Create an Issue →](https://github.com/kleinpanic/CS3704-Canvas-Project/issues/new/choose)

## Questions?

- **Quick questions**: [Discussions](https://github.com/kleinpanic/CS3704-Canvas-Project/discussions)
- **Bugs/Features**: [Issues](https://github.com/kleinpanic/CS3704-Canvas-Project/issues)
- **Urgent**: Contact [@kleinpanic](https://github.com/kleinpanic)

---

**See also**: [Team Workflow (Wiki)](https://github.com/kleinpanic/CS3704-Canvas-Project/wiki/Team-Workflow)
