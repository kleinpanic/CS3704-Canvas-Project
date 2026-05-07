## Summary

<!-- 1-3 sentences explaining what this PR does and why -->

## Type of change

- [ ] feat — new feature
- [ ] fix — bug fix
- [ ] docs — documentation only
- [ ] refactor — code restructure, no behavior change
- [ ] perf — performance improvement
- [ ] test — test additions or fixes
- [ ] chore — tooling, build, CI
- [ ] BREAKING CHANGE — incompatible API or behavior change

## Testing

<!-- How was this verified? Tests added? Manual checks? -->

## Checklist

- [ ] Conventional commit title (`feat:`, `fix:`, etc.)
- [ ] CHANGELOG.md updated under [Unreleased] or current version
- [ ] Tests added or updated (or `skip-changelog` label justified)
- [ ] Documentation updated if user-facing behavior changed
- [ ] No secrets, tokens, or PII committed

## Repo Org Compliance

<!-- Ensures the directory structure stays coherent. Phase 4 of v2.1 locked these rules. -->

- [ ] No new top-level files outside `ALLOWLIST` (or ALLOWLIST updated with rationale)
- [ ] No new root-level `*.md` files outside `ALLOWLIST`
- [ ] New Dockerfile (if any) is in `docker/` or `huggingface/`
- [ ] New `pyproject.toml` (if any) is in `src/sdk/` or repo root
- [ ] `tools/check-repo-org.sh` shows no NEW warnings beyond what was on `main` before this PR
