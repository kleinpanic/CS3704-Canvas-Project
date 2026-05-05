# Release Checklist

Use this checklist for every release. Replace `X.Y.Z` with the actual version.

---

## 1. Pre-release: Generate changelog

```bash
git log vX.Y.Z..HEAD --oneline
```

Review the output and add meaningful entries to `CHANGELOG.md`. Typical format:

```markdown
## [X.Y.Z] — YYYY-MM-DD

### Features
- ...

### Bug Fixes
- ...

### Maintenance
- ...
```

---

## 2. Verify version in pyproject.toml

```bash
grep "^version" pyproject.toml
```

The version string **must match** the tag you are about to create (`X.Y.Z`). If it does not, update it first:

```bash
# Edit pyproject.toml → [project] → version = "X.Y.Z"
git add pyproject.toml && git commit -m "chore: bump version to X.Y.Z"
```

---

## 3. Tag and push

```bash
git tag vX.Y.Z && git push origin vX.Y.Z
```

> **Important:** Always use the `v` prefix. The release workflow triggers on tags matching `v*.*.*`.

---

## 4. Watch the release workflow

The `require-ci` job in the release workflow runs CI checks with polling retry (~2–3 minutes).

- Go to the **Actions** tab on GitHub → `Release` workflow run
- Wait for `require-ci` to complete (all checks must pass)
- Do **not** proceed to the next step if CI is still running

---

## 5. Verify release artifacts

After the workflow completes, check the GitHub Release page:

1. Navigate to **Releases** → click the tag `vX.Y.Z`
2. Confirm both `.whl` and `.tar.gz` artifacts are attached
3. Confirm the release title and changelog match what you intended

If artifacts are missing, check the workflow logs and re-run the job before announcing the release.

---

## 6. Local install verification

```bash
pip install -e . --break-system-packages
```

Verify the package installs cleanly and the CLI entry point is functional:

```bash
canvas-tui --help   # or the project's actual entry point
```

---

## 7. Post-release

- [ ] Announce in Discord/project channel if applicable
- [ ] Close the associated milestone on GitHub (if any)
- [ ] Update `CHANGELOG.md` on `main` if you added release notes there