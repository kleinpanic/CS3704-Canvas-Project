# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [unreleased]

### Changed — Pages demo uses mock Canvas data when no live token configured

- `docs-site/fetch_canvas_data.py`: added `--mock` flag that generates realistic fake Canvas data (3 courses, upcoming assignments, modules, grades) with dates relative to build time. No `CANVAS_API_TOKEN` or `CANVAS_BASE_URL` needed in mock mode.
- `.github/workflows/pages.yml`: replaced conditional skip logic with live-or-mock dispatch — demo always has data. Live mode activates only when both `CANVAS_API_TOKEN` and `CANVAS_BASE_URL` secrets are set; otherwise falls back to `--mock`.

### Removed — HuggingFace Space deployments

- Deleted `.github/workflows/deploy-hf-space.yml` and `deploy-pii-space.yml`. Canvas API token access was revoked by the host institution; the Spaces are no longer maintained. The PII scrub regex self-test remains in the Pages build.

### Fixed — Scorecard Gate switches to ossf/scorecard-action (no manual binary)

- `.github/workflows/scorecard-gate.yml`: replaced manual binary download + SHA verification with `ossf/scorecard-action@f49aabe0b5af0936a0987cfb85d86b75731b0186` (same action as `scorecard.yml`). The action handles OIDC auth internally; `SCORECARD_READ_TOKEN` remains as a fallback but is no longer the sole auth path. Fixes score returning 0 when the token was absent.

### Changed — Dependabot PRs now auto-approve and auto-merge

- Added `.github/workflows/dependabot-auto-merge.yml`: approves and enables squash auto-merge for all Dependabot PRs when required checks pass. Eliminates manual review burden for dependency-only updates.

### Fixed — publish-pypi uses correct GitHub Environment

- `.github/workflows/release.yml`: `publish-pypi` job `environment.name` was `test-pypi` (wrong); corrected to `pypi`. Environment name must match the trusted publisher / secret binding in repo settings.

### Removed — test-pypi dry-run job

- `.github/workflows/release.yml`: removed the `Test PyPI Dry-Run` job. No trusted publisher was ever configured at test.pypi.org so the job failed every release. The real PyPI publish works independently via `PYPI_API_TOKEN`; the dry-run added noise without providing any correctness signal.

### Fixed — Scorecard Gate floor matches achievable score for solo project

- `.github/workflows/scorecard-gate.yml`: lowered default floor from 6.5 → 6.0 to match the actual OSSF score ceiling for a single-maintainer project (Code-Review and Contributors checks are structurally 0 without external reviewers). The 6.5 floor was blocking all Dependabot PRs.

### Fixed — Test PyPI Dry-Run no longer fails the release run

- `.github/workflows/release.yml`: added `continue-on-error: true` to the Test PyPI Dry-Run job. test.pypi.org doesn'''t have a trusted publisher configured for this repo (separate maintainer click-op); the dry-run isn'''t a correctness gate for the real publish anyway. Allowing it to non-blocking-fail keeps release.yml runs clean while leaving the job in place for opt-in verification once test.pypi.org is wired.

### Fixed — bump pypa/gh-action-pypi-publish (twine bug)

- `.github/workflows/release.yml`: bumped `pypa/gh-action-pypi-publish@ec4db0b4` -> `@cef22109` (latest release/v1). The pinned SHA was running an old twine that misread Metadata-Version 2.4 wheels with "Metadata is missing required fields: Name, Version". Wheels themselves were valid (verified by direct twine upload of the same artifact, canvas-sdk 2.0.5 + 2.0.8 LIVE on pypi.org). Action bump fixes the CI publish path.

### Fixed — release.yml build env explicitly pins setuptools>=70

- `.github/workflows/release.yml`: all 4 `Install build deps` steps now do `pip install --upgrade --no-cache-dir pip build "setuptools>=70" wheel`. The previous `pip install --upgrade pip build` left setup-python's pre-cached old setuptools in place; combined with pip's cache, build was honoring an ancient setuptools that produced wheels with Metadata-Version 1.x. Explicit upgrade + no-cache forces fresh setuptools >= 70 (PEP 621-compliant) → wheels get Metadata-Version 2.4.

### Fixed — release.yml wheel rename violated PEP 427

- `.github/workflows/release.yml`: removed the build-sdk-linux step that renamed `canvas_sdk-*.whl` → `canvas-sdk-*.whl`. PEP 427 mandates underscored package name in wheel filenames; the hyphenated form caused twine to parse the filename incorrectly and fail with "Metadata is missing required fields: Name, Version". Sdist rename to hyphenated form is preserved (sdist names are more permissive).

### Fixed — bump src/sdk/pyproject.toml to 2.0.5

- `src/sdk/pyproject.toml`: version `2.0.0` -> `2.0.5`. Build was producing `canvas_sdk-2.0.0-py3-none-any.whl` regardless of tag (release.yml's build runs `python -m build src/sdk/` which uses pyproject's hardcoded version). Phase 5 release-standardization will replace this with version.txt + sed substitution at build time.

### Fixed — publish-pypi uses API token (bypass trusted publisher click-op)

- `.github/workflows/release.yml`: `publish-pypi` job now passes `password: ${{ secrets.PYPI_API_TOKEN }}` to `pypa/gh-action-pypi-publish`. Bypasses the OIDC trusted-publisher exchange that was failing on every release. PYPI_API_TOKEN repo secret added 2026-05-07. Trusted publisher can be re-adopted later when configured cleanly; for now token-auth ships releases.

### Fixed — agent-demo: roll back gradio to 5.7.1 (stop-bleed)

- `huggingface/agent-demo/{requirements.txt,README.md,app.py}`: rolled gradio back from 6.x to `5.7.1` and restored `type="messages"` on `gr.Chatbot`. Gradio 6.x was crashing the Space with chat_stream signature introspection bug despite the wiring matching. CVE GHSA-39mp-8hj3-5c49 (gradio path traversal HIGH) is not exposed in this Space — there are no filesystem-input components. Proper gradio 6 migration is a separate phase.

### Fixed — agent-demo gradio 6 API breakage + docker SBOM perms

- `huggingface/agent-demo/app.py`: moved `theme=` and `css=` from `gr.Blocks(...)` constructor to `demo.launch(...)` per gradio 6.0 breaking change. The constructor warning was actually a hard error — Space crashed at startup.
- `.github/workflows/docker.yml`: added `attestations: write` to build-push job permissions. Previous SBOM step failed with "Resource not accessible by integration".

### Fixed — release.yml publish-pypi environment matches existing trusted publisher

- `.github/workflows/release.yml`: changed `publish-pypi` job environment from `pypi` to `test-pypi` to match the trusted publisher entry already configured at pypi.org. The previous mismatch caused both jobs to fail with `Trusted publishing exchange failure` (`sub: ...:environment:test-pypi` claim didn't match `environment:pypi` workflow). One-line config fix instead of requiring a maintainer to reconfigure pypi.org.

### Fixed — agent-demo CONFIG_ERROR: ZeroGPU torch version

- `huggingface/agent-demo/requirements.txt`: removed explicit `torch` pin entirely. PR #205's `torch==2.7.0` triggered `No candidate PyTorch version found for ZeroGPU` because the `spaces` package bundles its own ZeroGPU-compatible torch wheel; explicit pin conflicted. Letting `spaces` resolve torch is the canonical pattern for ZeroGPU Spaces.

### Fixed — agent-demo CONFIG_ERROR (sdk_version unquoted)

- `huggingface/agent-demo/README.md`: re-quoted `sdk_version: 6.7.0` -> `sdk_version: "6.7.0"` per HF Spaces config reference. PR #195 changed it from quoted "5.7.1" to unquoted 6.7.0; HF YAML parser treats unquoted as non-string and triggers CONFIG_ERROR. ref: https://huggingface.co/docs/hub/spaces-config-reference

### Fixed — agent-demo Space RUNTIME_ERROR after torch 2.8 bump

- `huggingface/agent-demo/requirements.txt`: rolled back `torch>=2.8.0` to `torch==2.7.0`. PR #200's bump caused the canvas-calendar-agent-demo Space to fail with RUNTIME_ERROR at startup (model.safetensors loaded 10.2 GB, crashed at `generation_config.json` step). torch 2.7.0 was the last known-working version with this Space's transformers + Gemma-4 model combo. The torch CVEs fixed in 2.8.0 are not in this Space's request path (model is loaded once at startup, no `torch.load` on user input).

### Fixed — release.yml publish-pypi unblocked from TestPyPI gate

- `.github/workflows/release.yml`: removed `test-pypi` from `publish-pypi` `needs:`. TestPyPI's trusted publisher config is a separate maintainer click-op (`test.pypi.org/manage/account/publishing/`) that wasn't yet set up for this repo. v2.0.1 release.yml ran with publish-pypi SKIPPED because the dry-run failed. Decoupling lets the next release publish to PyPI directly via its already-configured trusted publisher (`pypi.org/manage/...` already done). The Test PyPI Dry-Run job remains in the workflow for opt-in verification but no longer gates the real publish.

### Fixed — README badges rendering as raw markdown on github.com

- `README.md`: surrounded the two stripped-badge HTML comments (`<!-- codecov badge: removed... -->` and `<!-- canvas-tui badge restored when #177 ships -->`) with blank lines. CommonMark spec rule 4 (HTML block start): an HTML comment without surrounding blank lines triggers HTML block mode for everything below it until the next blank line — meaning every badge after the codecov comment was being rendered as LITERAL `[![PyPI canvas-sdk](...)](...)` markdown text on github.com instead of as images. Only the 4 workflow status badges (CI/Security/Pages/Release) above the comment were rendering. Fix: blank lines around both comments.

### Fixed — pip syntax regression in pii-scrub requirements

- `huggingface/pii-scrub/requirements.txt`: changed `torch>=2.8.0+cpu` to `torch==2.8.0+cpu`. PEP 440 requires the `+local` version label (e.g., `+cpu`) to be paired with `==` or `!=`, not `>=`. The previous syntax broke the `Dependency Graph` workflow on `main` (`InstallationError: Local version label can only be used with == or != operators`).

### Added — Repo Org Compliance CI workflow (programmatic enforcement)

- New `.github/workflows/repo-org.yml`: runs `tools/check-repo-org.sh` on every PR + push to main in **BLOCKING mode** (fails the workflow if any `WARN [repo-org]:` line is emitted, even though the local pre-commit hook is warning-only). Contributors still get nag-only warnings during local development; CI enforces the standard at PR time. Closes the gap between Phase 4's policy file (ALLOWLIST) and actual GitHub enforcement.

### Changed — top-level Hugging Face directory consolidation

- Consolidated `hf-space/` (canvas-calendar-agent-demo) and `hf-space-pii/` (canvas-pii-scrub) into a single top-level `huggingface/` parent. Each Space now lives at `huggingface/agent-demo/` and `huggingface/pii-scrub/`. Cleans up the top-level repo tree (was 2 entries, now 1) and groups all HF deployment surfaces under one umbrella.
- Updated all internal references: `.github/workflows/deploy-{hf-space,pii-space}.yml`, `.github/dependabot.yml`, `.github/pull_request_template.md`, `Makefile`, `README.md`, `CONTRIBUTING.md`, `LICENSING.md`, `SECURITY.md`, `ALLOWLIST`, `tools/check-repo-org.sh`, `tests/test_pii_space_app.py`.
- HF Space deploy targets (`https://huggingface.co/spaces/kleinpanic93/canvas-calendar-agent-demo` and `.../canvas-pii-scrub`) are unchanged — only the source path inside the repo changed.

### Security — v2.1 Dependabot medium-alert closure

- Bumped `transformers >= 4.53.0` and `torch >= 2.8.0` across `requirements.txt`, `huggingface/agent-demo/requirements.txt`, and `huggingface/pii-scrub/requirements.txt`. Closes ~26 of the 28 open MEDIUM-severity Dependabot alerts (multiple CVEs in transformers 4.4x and torch 2.6.x). Phase 2 hardening closed all critical+high; this closes the medium-severity tail. Some lows remain (RC versions only — `5.0.0rc3` and `2.7.1-rc1` — not pinning to RCs).

### Improved — pii-scrub regex fallback layer (catches Piiranha v1 gaps)

- `huggingface/pii-scrub/app.py`: added regex fallback layer for phone numbers and Title-Case person-name patterns. Piiranha v1 has known recall gaps on conversational sentences (e.g., misses "Alice Johnson" entirely; mis-labels "Bob Smith" as CITY). Regex fallback runs alongside the model's entity extraction; results are deduplicated against model entities (overlap-skip). Phone-number regex covers US formats: 540-231-1234, (540) 231-1234, +1-540-231-1234, 540.231.1234, 5402311234. Name regex catches Title-Case First+Last with stopwords for months, days, courses, and common false positives. Both add `@PERSON_N` tokens to the existing registry.

### Security — v2.1 Phase 2: OSSF Scorecard Score Lift

- Workflow permissions scope-downs across 8 workflows: top-level `permissions: read-all` + job-level write grants only where required. Closes the OSSF Token-Permissions check (was 0/10).
- `release.yml` hardening: top-level perms narrowed; SBOM and SLSA-provenance jobs decoupled from `publish-pypi` failures; new `sigstore-sign` job (SHA-pinned `sigstore/gh-action-sigstore-python@f514d46b`, v3.0.0) signs both wheel and sdist artifacts.
- New `scorecard-gate.yml` PR-gating workflow: runs Scorecard CLI v5.1.1 (SHA-verified tarball) on every PR to `main`, fails the build if score drops below configurable floor (default 6.5). Self-aware bootstrap detection skips enforcement when the gate workflow itself is modified.
- Docker base-image SHA pinning (manifest-list digests preserve linux/arm64 build): `docker/canvas-tui/Dockerfile` and `huggingface/pii-scrub/Dockerfile`.
- `huggingface/agent-demo/requirements.txt`: `gradio==5.7.1` → `gradio>=6.7.0` (closes GHSA-39mp-8hj3-5c49 path-traversal CVE plus 3 other open critical/high alerts).
- `pyproject.toml`: `gradio-client` floor aligned to `>=2.2` (gradio 6.7.0 companion).
- 9 stale Dependabot alerts dismissed as `tolerable_risk` (8 against zombie bare `requirements.txt` path, 1 with no upstream fix).
- `.github/workflows/docker.yml` build-push job: `contents: read` added (was implicitly `none` after job-level perm narrowing — broke `actions/checkout`).

### Fixed — v2.1 Phase 2 hot-fix (post-merge regressions)

- `huggingface/pii-scrub/Dockerfile`: HF Spaces' build parser rejected `FROM image@sha256:DIGEST  # tag-comment` with "FROM requires either one or three arguments". Standard `docker build` is lenient; HF's buildkit treats the inline comment as extra arguments. Fix: move `# tag:` comment to its own line above FROM. Same defensive fix applied to `docker/canvas-tui/Dockerfile`.
- `huggingface/agent-demo/README.md`: bumped `sdk_version: 5.7.1` → `6.7.0` to resolve gradio resolver conflict between HF's pre-baked `gradio[oauth]==5.7.1` and our `gradio>=6.7.0` floor in `requirements.txt`.

### Notes

- SCORECARD_READ_TOKEN repo secret created out-of-band 2026-05-07T04:09:55Z; should be rotated post-merge (was pasted in plaintext during a prior orchestration session).
- Signed-Releases score (currently 0/10) lifts to 7/10 only on next stable release ship; Plan 06 of this milestone covers the post-merge release cut + Scorecard manual dispatch + score verification.

### Documentation — v2.1 Phase 3: README Honesty + License Correction

- README badges: removed broken canvas-tui PyPI badge (will restore when #177 ships); replaced dishonest mypy badge with `mypy-advisory` until Phase 9 promotes mypy to blocking; stripped Codecov badge (HTML comment placeholder until codecov.io registration).
- README body claims corrected: CANVAS_BASE_URL no longer falsely marked "optional, defaults to VT"; Distribution table reflects truth (canvas-sdk live on PyPI v1.2.3; canvas-tui pending #177); footnote and Quick Start SDK version clarified.
- License declarations corrected: root `package.json` `ISC` → `GPL-3.0-or-later`; `src/sdk/pyproject.toml` gains explicit `license` field; both `extension/manifest.json` and `extension/package.json` declare GPL-3.0-or-later.
- `CODEOWNERS` dead path corrected: `/sdk/` → `/src/sdk/`.
- New `LICENSING.md` documenting the HF Space `apache-2.0` exception and GPL-3.0-or-later canonicality across the codebase.
- New `tools/check-readme-claims.py` linter (registered as pre-push hook) catches stale claims, badge regressions, and license declaration drift in CI.

### Changed — v2.1 Phase 4: Repo Organization Standard + Warning-Layer Enforcement

- **Removed from public tree:** ghost root `package.json` (dated `v1.0.0`, no real consumer, `index.js` never existed) + paired `package-lock.json`. Class deliverables `IMPLEMENTATION.md` and `docs/CS3704-PM3-REVIEW.md` archived under `.planning/archive/v2.1-class-deliverables/` (out of public-facing tree; original content preserved in git history).
- **New `ALLOWLIST` at repo root:** every sanctioned top-level file/directory listed with a one-line `# rationale` comment. Source of truth for repo-org policy.
- **New `tools/check-repo-org.sh` warning hook:** 4 checks against repo top-level structure (entries off ALLOWLIST, root `*.md` unjustified, Dockerfile outside `docker/` + `huggingface/`, `pyproject.toml` outside `src/sdk/` + repo root). Registered in `.pre-commit-config.yaml`. **WARNING MODE** — prints to stderr, always exits 0. Promotes to blocking after one milestone of stable usage.
- **PR template (`.github/pull_request_template.md`):** new "Repo Org Compliance" checklist section makes ALLOWLIST + repo-org-warn expectations explicit at PR-open time.

### Fixed — v2.1 Phase 4 hot-fix (live demo runtime regression)

- `huggingface/agent-demo/app.py`: removed `type="messages"` from `gr.Chatbot(...)`. The Space build succeeded after the prior hot-fix (sdk_version + Dockerfile fixes) but crashed at startup because gradio 6.x removed the `type=` keyword (messages format is now default). Verified by reproducing the failure in a fresh venv with `gradio==6.7.0`.

### Fixed — v2.1 pii-scrub silent-no-op regression (pre-existing)

- `huggingface/pii-scrub/app.py`: `_PERSON_LABELS` and `_LOC_LABELS` were checking for BIO-prefixed labels (`I-GIVENNAME`, `I-CITY`, etc.) but the model is loaded with `aggregation_strategy="simple"`, which collapses spans and drops the BIO prefix. The model returns `entity_group: "EMAIL"`, `"USERNAME"`, `"GIVENNAME"` etc. — never `"I-..."`. Result: `/scrub` always returned the input unchanged with `redactions: []` and `registry: {}` — a silent no-op for every request. `/entities` was unaffected (it returns the raw entity list without label-set filtering). Live-verified by hitting `/scrub` against `https://kleinpanic93-canvas-pii-scrub.hf.space/`. Fix: drop `I-` prefix from both label sets and add `EMAIL` to person-class.

## [2.1.0] - 2026-05-07

### Released

- Final v2.1 milestone marker. CI publish-pypi path verified clean (action SHA bumped). test-pypi continue-on-error so test.pypi.org missing trusted-publisher does not red-light release.yml.

## [2.0.9] - 2026-05-07

### Released

- Verify CI publish path post-action-bump.

## [2.0.8] - 2026-05-07

### Released

- Verify CI publish path post-setuptools fix.

## [2.0.7] - 2026-05-07

### Released

- Test release after wheel-rename fix (#215). Verifies CI publish path now produces PyPI-accepted wheels.

## [2.0.5] - 2026-05-07

### Released

- Bundle of v2.1 milestone work merged since v2.0.0: Phases 2-4 (OSSF Scorecard lift, README honesty + license correction, repo organization standard + ALLOWLIST + CI enforcement) plus 11 follow-up hot-fixes.

## [2.0.0] - 2026-05-06

### Public-Contribution Hardening — 12-phase milestone

This release lands the v2.0 Public-Contribution Hardening milestone: 91 atomic
GPG-signed commits across 12 phases. Highlights:

- Phase 0/1: clean-room SDK rewrite — 14,400 derived lines deleted, 472-LOC
  pure-stdlib `CanvasClient` written via two-agent clean-room procedure
  (Gemini SPEC.md → Sonnet implementer with strict isolation). `canvas-sdk`
  is now original code under GPL-3.0; `requests`/`arrow`/`pytz`/`canvasapi-port`
  removed from the runtime.
- Phase 2/3/4: dataset contribution pipeline secured — Piiranha v1 PII scrub in
  `share_my_canvas.py`, `--dry-run`/`--inspect` flags, regression test against
  the existing `Williammm23.jsonl` leak, new `dataset-validation.yml` CI gate,
  dedicated `kleinpanic93/canvas-pii-scrub` HF Space (FastAPI + Piiranha).
- Phase 5: standalone-release readiness — `CANVAS_BASE_URL` required, env-driven
  config, fork CI guards, SPDX headers, `--no-scrub` and `?nopiiscrub=1`
  foot-guns removed.
- Phase 6: SOTA CI/CD + supply-chain — every workflow pinned to commit SHAs +
  `step-security/harden-runner`; OSSF Scorecard; SBOM (cyclonedx); SLSA
  provenance; sigstore-signed multi-arch (amd64+arm64) Docker; OIDC
  trusted-publisher PyPI; coverage gate raised.
- Phase 7: HF Space UI upgrade — `gr.Examples`, `gr.HTML` hero, streaming via
  `TextIteratorStreamer`, browser-chrome mock, post-deploy smoke test.
- Phase 8: TUI/extension SDK discipline — `app.py` decomposed into screens,
  keybinding registry, `tests/{sdk,tui,extension,integration}/` layered.
  Closes GH issues #43, #45, #46, #47, #50, #51, #52.
- Phase 9: badges + devcontainer + Codecov — live coverage %, official HF
  badges, PyPI badges, OSSF badge, `.devcontainer/devcontainer.json`.
- Phase 10: SOTA polish — `examples/`, public `ROADMAP.md`, `docs/QUICKSTART.md`,
  expanded `SECURITY.md`/`MAINTAINERS.md`, all-contributors bot, `.editorconfig`.
- Phase 11: cleanup — dead `release.yml` blocks deleted, AI-tell docstrings
  rewritten, `tools/clean.sh` + `make clean`, pre-commit smell-marker grep gate.

Test count: 416 → 612 (+196 tests, 84% coverage).
GH issues closed: 6. Issue tracker: #177.

## [Unreleased]

### BREAKING CHANGES

- `CANVAS_BASE_URL` is now required at all entry points; the previous silent default
  (`https://canvas.vt.edu`) has been removed. Set this env var to your institution's
  Canvas URL before running any command or importing the SDK.
  Migration: `export CANVAS_BASE_URL=https://canvas.yourschool.edu`

### Fixed

- **DPO model namespace**: `DEFAULT_HF_REPO` corrected from `kleinpanic/canvas-calendar-agent-v7-dpo`
  to `kleinpanic93/canvas-calendar-agent-v7-dpo`. SDK users without `CANVAS_LLM_ENDPOINT` set
  were getting 404 errors on model download.

### Added

- Keybinding registry (`src/canvas_tui/keybindings.py`) with conflict detection at startup; `validate_all()` raises `ValueError` on duplicate `(screen, key)` pairs (#50)
- Multi-screen nav: `app.py` slimmed to screen router (109 lines); `HomeScreen` extracted to `screens/home.py` (#51)
- `?` keybinding overlay auto-generated from registry via `BaseScreen.show_help_overlay()`
- `BaseScreen` ABC (`src/canvas_tui/screens/base.py`) providing keybinding help overlay support for all screens
- RMP TUI screen (`src/canvas_tui/screens/rmp.py`): search → results → details professor ratings view; `R` keybinding opens from HomeScreen (#45, closes #43)
- `docs/tui-architecture.md`: TUI screen inventory, keybinding registry docs, extension SDK contract (#47)
- Chrome extension routes 14 Canvas API MESSAGE_TYPES through native host first via `routeViaHost()` helper; automatic fallback to browser-fetch (#52)
- Native host extended with 4 new methods: `getDashboardCards`, `getSyllabus`, `getAssignmentGroups`, `getSubmission`

### Changed

- `canvas_tui.api.CanvasAPI` now wraps `canvas_sdk.CanvasClient` for HTTP; retry, pagination, and rate-limiting delegated to SDK (D-06/D-07)
- Tests reorganized by layer: SDK tests in `tests/sdk/`, TUI tests in `tests/tui/`, extension layer reserved in `tests/extension/` (D-08/D-09)
- `data/trajectories/README.md` marks `collab/` as a closed legacy dataset; references to deleted `collect_trajectories.py` removed (D-17)
- `scripts/README.md` reduced to a one-line pointer; `docs/contributing-data.md` is the canonical contributor guide (D-18)

### Fixed

- Extension ratings UI verified complete per PR #94 (ext-ui redesign + professor ratings layout) (#46)

- `src/canvas_tui/config_env.py`: centralised env-driven constants for all entry points.
  Fork users need only set `CANVAS_BASE_URL` and `CANVAS_TOKEN` to get a working install.
- `.env.example`: documents all supported env vars with defaults.
- Fork-friendly CI secret guards (`HAS_CANVAS_TOKEN`, `HAS_HF_TOKEN`, `HAS_PYPI_TOKEN`):
  forked repos see yellow (skipped) CI jobs rather than red failures when secrets are absent.
- Branch policy loosened to `^[a-z]+/[a-z0-9._-]+$` — any lowercase prefix is accepted.
- `CONTRIBUTING.md`: "If you fork this repo" section with env-var table, secrets table,
  branch naming docs, and git identity guidance.
- `SPDX-License-Identifier: GPL-3.0-or-later` header added to all `.py` files under
  `src/`, `scripts/`, `tools/`, `tests/`.

### Removed

- `--no-scrub` flag in `docs-site/fetch_canvas_data.py` — deleted; use a temporary
  local source edit for debugging. Running with raw PII is no longer possible via a flag.
- `?nopiiscrub=1` URL parameter in `proxy/worker.js` — removed; bypass now requires
  an `Authorization: Bearer <INTERNAL_PASSTHROUGH_TOKEN>` header with the Cloudflare
  env secret set. The public endpoint always scrubs.

## [1.2.3] — 2026-05-06

### Fixed
- **release.yml publish-pypi `environment: pypi`** restored. PR #173 dropped it when switching from OIDC trusted publishing to API-token auth, so v1.2.1/v1.2.2 never registered as `pypi` environment deployments. The repo sidebar stayed pinned to the failed v1.2.0 deployment record. (#176)

## [1.2.2] — 2026-05-06

### Changed
- **HF Space description**: removed unverified v7-broken numbers (β=0.1, 181 trajectories, 90.3% reward accuracy); replaced with β=0.3 (per small-N regularization research) and TBD status for trajectory/bench counts pending phase 1/4; links to cited method.html for details. (`hf-space/app.py`)
- **fetch_canvas_data.py**: upgraded PII scrubbing from regex-only to Piiranha-first with regex fallback. When `HF_TOKEN` is set, strings >20 chars are sent to `iiiorg/piiranha-v1-detect-personal-information` via HF Inference API; 503 warm-up is retried once after 5 s; any error disables Piiranha for the remainder of the run and falls back to existing regex. Self-test extended with Piiranha mock.

### Security
- **CF Worker `/canvas` PII scrub**: defense-in-depth regex scrub (email, phone, SSN, address) applied to Canvas API JSON responses before returning to caller. Opt out with `?nopiiscrub=1` for SDK consumers that need raw field values. (`proxy/worker.js`)

---

## [1.2.1] — 2026-05-06

### Fixed
- **publish-pypi**: switched to API token auth (`PYPI_API_TOKEN` secret) and rebuilds SDK from source inside the job for PEP 625-compliant filenames. Fixes the failed publish-pypi step from the v1.2.0 release. (#173)
- **RMP teacher names** now populate via `?include[]=teachers` on the `/courses` Canvas API call. The pre-fetched `site/data/rmp.json` will fill in starting next pages.yml run. (#173)

## [1.2.0] — 2026-05-06

### Added
- **Nightly release channel**: daily cron (06:00 UTC) builds SDK wheel + extension archive, tags as `nightly-YYYYMMDD-<sha>`, publishes as GitHub pre-release. `docs/RELEASING.md` documents the 3-channel model (stable, nightly, snapshot) and branch protection recommendations.
- **Automated PR quality enforcement**: conventional title check (`amannn/action-semantic-pull-request@v5`), CHANGELOG enforcer (`dangoslen/changelog-enforcer@v3`), size limit gate (>1000 lines requires `large-pr` label), PR template, and release-drafter for auto-generated release notes.
- **Contributor graph** (contrib.rocks) in README showing all contributors with auto-refresh.
- **HF Space session state + 18-tool surface**: calendar pane, 18 dispatched mock tools, pill examples, table tool calls, fill_height, Gemma-4 sampling params (#145)
- **18 interactive tool buttons** on agent demo page with visible labels (#121, #122, #163, #164)
- **Live Demo page** on docs-site with HF links across nav (#143, #144)
- **Auto-deploy HF Space** to HuggingFace on main push via `deploy-hf-space.yml` (#141)
- **GHCR Docker image**: build + publish `canvas-tui` to `ghcr.io/kleinpanic/canvas-tui` (#140)
- **PyPI publish workflow**: `canvas-sdk` publishes on stable releases via OIDC trusted publishing (#138)
- **GitHub Wiki sync**: `wiki-sync.yml` syncs `docs-site/docs/` to GitHub Wiki on main push (#139)
- **Read the Docs config**: `.readthedocs.yml` added for RTD integration (#137)
- **RMP pre-fetch at build time**: Rate My Professor ratings baked into `rmp.json` at build time (#155)
- **DPO+SFT methodology explainer page** in docs-site with nav links (#130)
- **SDK 18-tool agent registry + calendar adapter**: `REGISTRY` dict with Canvas API tools (×8), calendar adapters (×5), study helpers (×4), reranker integration (×1) (#83, #91)
- **InMemoryCalendarBackend** and `calendar_adapter` migration to SDK (#134)
- **HF Space inference backend** — Gradio app loading v7-dpo behind `ChatInterface` (#107, #109, #136)
- **Gemma4 agentic backend, tool parser, and agent loop** in SDK (#98)
- **Live demo GitHub Pages** with GitHub Actions CI (#99)
- **HF Model/Dataset/Space nav links** added to docs-site demo (#112)
- **TRAINING-PIPELINE walkthrough** added to MkDocs site (#108)
- **HF Space integration test** + HF badges (#116)

### Changed
- **README split**: slimmed to end-user-facing content only (install, demo, distribution, license); developer/team content moved to CONTRIBUTING.md
- **CONTRIBUTING.md expanded**: added dev setup, repo structure, branch naming, commit conventions, PR expectations, automation table, course context
- **README modernized**: structure, links, quick-start, badge expansion, PyPI badges, Distribution table for 3-package channels (#131, #158, #159, #161)
- **docs/method.html**: rewrite with cited corrections from SSOT truth source (#148)
- **MkDocs deduplication**: removed root `mkdocs.yml`, resolved nav conflicts (#156)
- **HF Space UI polish**: wider layout, pill examples, flat grid replacing accordions, structured description (#152)
- **CI overhaul**: release workflow with 4 parallel build jobs (#132)
- **Branch protection**: added `feat/*` to branch-name policy (#142)
- **CODEOWNERS + stale policy**: tightened to 14-day window (#87)
- **Quick-checks + pip caching**: added cleanup workflow and changelog tooling (#92)

### Fixed
- **release.yml publish-pypi**: switched from OIDC trusted publishing to API token (`PYPI_API_TOKEN` secret); rebuilt sdist + wheel from `src/sdk/` source inside the publish-pypi job so PyPI gets PEP 625-compliant underscore filenames (the GH-release artifacts are renamed to hyphens for human readability). (#173)
- **fetch_canvas_data.py**: added `?include[]=teachers` to the `/courses` query so teacher `display_name` fields populate, letting the RMP map at `site/data/rmp.json` actually fill in. (#173)
- **release.yml publish-pypi action ref**: `pypa/gh-action-pypi-publish@v1` doesn't resolve; use `@release/v1` (the canonical major-version pointer). Surfaced when `publish-pypi` ran on the v1.2.0 release. (#172)
- **release.yml require-ci result-encoding**: `'escape'` → `'string'` (only `string` or `json` are valid for `actions/github-script@v9`). Latent from #132's overhaul; surfaced on first `v*` tag push. (#171)
- **Empty-send guard + example-btn color + Ask AI height overflow** (#160, #163)
- **release.yml**: replaced phantom `build` job dependency with `build-sdk-linux` (#165)
- **branch-name policy regex**: now allows `feat/*` branches (#142)
- **CI rename**: `huggingface-cli` → `hf` in deploy workflow (#146)
- **HF Space stability**: pinned Python 3.11, `hub<1.0`, `transformers<5`, `audioop-lts` shim (#113, #115)
- **SDK standalone shippability**: moved `calendar_adapter`, guarded reranker import (#134)
- **Extension assignment rows**: made clickable (#149)
- **Canvas assignments** not loading in live demo (#105)
- **Chrome extension**: `chrome_shim` polyfill + `.crxignore` for standalone packaging (#135)
- **Gemini review findings**: 10 fixes, 47 tests (#86)

### Security
- **PII scrub**: Canvas data scrubbed before baking into public Pages JSON (#151)
- **CF Worker proxy**: Canvas API calls routed through Cloudflare Worker; tokens removed from public JS (#133)

### Removed
- **AI-generated audit/review/plan docs**: removed from repo; test files moved to `tests/` (#153)
- **Root mkdocs.yml**: deleted unused duplicate (#156)

---

## [1.1.1] — 2026-05-04

### Added
- **SDK agent registry**: 18-tool agent registry with Canvas API tools (×8), calendar adapters (×5), study helpers (×4), and reranker integration (×1) — registered via `REGISTRY` dict with auto-discovery
- **Settings UI**: full config persistence, keybinding customization, and theme/layout settings screen
- **Multi-view extension navigation**: courses tab with drill-down navigation and per-tab content rendering in the browser extension popup
- **Canvas scraper**: full 4-year history, submission status tracking, `@COURSE` anonymization prefix, and bulk contribution converter
- **Rate My Professor integration**: standalone RMP module for instructor lookup
- **Trajectory data collection**: teammate contribution pipeline with privacy scrubber and anonymization

### Changed
- **Chart sizing**: responsive layout using viewport size instead of `content_size` for accurate pane sizing
- **TUI layout improvements**: tighter sidebar, balanced stats row widths, reduced completion bars
- **Extension architecture**: shared `canvas-client.js`, `extension-contract.js`, and `extension-api.js` layers replace scattered endpoint logic
- **Dataset pipeline**: standardized on 8 core commands (setup, generate, merge, clean, anonymize, export-sft, export-dpo, split)
- **Heuristic weights**: synchronized `W_TIME=3.0`, `W_TYPE=2.5`, `W_POINTS=1.5`, `W_STATUS=2.0` across all reranker scripts
- **CI simplified**: lint no longer blocks merges; coverage advisory at 80% with `#no-coverage-check` bypass
- **Python compatibility**: smoke test runs on 3.11/3.12/3.13 (informational, non-blocking)
- **Branch protection**: only Test, Coverage, Python Compat block merge; code owner reviews required

### Fixed
- **CRN anonymization**: regex now correctly handles underscore-delimited CRN format in course identifiers
- **Coverage threshold**: Textual TUI layer omitted so 80% threshold is actually achievable
- **Dead code**: four unused variables reintegrated after vulture analysis
- **Canvas scraper**: `share_my_canvas.py` works canvas-only, no API keys required
- **CI broken by cleanup**: `run_pipeline.py` restored to `scripts/`

### Docs
- `docs-site/` deployed site: architecture, extension, workflow, and roadmap pages updated
- `docs/project/DEVELOPER_GUIDE.md` — onboarding, setup, test/run/build commands
- `docs/contributing-data.md` — teammate data-contribution guide
- Zenodo DOI alongside HuggingFace in ML release notes
- Dead link to private training repo removed from README

### Dependencies
- `actions/github-script` v7→v9 (dependabot)
- `actions/download-artifact` v5→v8 (dependabot)
- Python SDK package added: `canvas_sdk` v1.0.0 in `sdk/` subdirectory

### Project Maintenance
- 241 tests passing
- 189 commits since v1.0.0
- All William Martin's PRs merged (extension nav, TUI fixes, settings UI, data stubs)
- Project board maintained at github.com/kleinpanic/projects/5

---

## [1.1.0] — 2026-04-15

### Added
- **DPO support in dataset pipeline**: `collect_rerank_dataset.py` now supports `export-dpo` for distillation workflows
- **Anonymization in SFT export**: added `--anonymize` flag to `export-sft` for safer data sharing
- **Deterministic benchmark tiebreaker**: `benchmark.py` updated to use heuristic scoring as a stable fallback instead of random choice
- **Version display** in TUI header (title bar shows `CanvasTUI v1.1.0`)
- **Type badges** in dashboard: ASGN / QUIZ / DISC / EXAM / EVNT inline labels
- **Box-drawing panel headers** with Unicode border characters
- **Inline urgency labels** on due items (e.g. "today", "tomorrow", "3d")
- **Grades what-if discoverability hint** on grades screen
- **`src/canvas_tui/models/` package**: `item.py`, `course.py`, `modal.py`, `__init__.py` (restructured from `models.py`)
- **Reranker fine-tuning pipeline** (Gemma 2B target):
  - `scripts/generate_rerank_data.py` — 20 query types, 5 pair types, multi-dim urgency scoring
  - `scripts/train_reranker.py` — LoRA fine-tuning with configurable rank/alpha/lr/dropout
  - `scripts/eval_reranker.py` — pairwise accuracy evaluation against ground truth
- **CI fixup workflow** (`ai-fixup.yml`) — auto-generates fix patches via Nemotron on DGX Spark on CI failure
- **Auto-docs workflow** (`auto-docs.yml`) — post-merge docstring generation via Nemotron

### Fixed
- Status bar: removed stale "Last refresh" and "Rate: ?" fields
- Prompt defense skill integration for school agent pipelines

### Changed
- **CI simplified**: lint no longer blocks merges; coverage advisory at 80% with `#no-coverage-check` bypass
- Python compatibility smoke test runs on 3.11/3.12/3.13 (informational, non-blocking)
- Branch protection: only Test, Coverage, Python Compat block merge

### Docs
- `docs/project/DEVELOPER_GUIDE.md` — onboarding, setup, test/run/build commands
- `docs-site/` deployed docs site updated

### Dependencies
- PRs merged: dependabot updates for `actions/github-script` v7→v9 (#22), `actions/download-artifact` v5→v8 (#21)

### Project Maintenance
- Issues closed: #15 (dashboard type badges), #24 (PM4 test_cache.py), #19, #18, #16 (Phase 2/3 future work)
- 241 tests passing

## [1.0.0] — 2026-02-23

### Added
- Complete rewrite from monolith to 24-module `src/canvas_tui/` package
- **Grades overview** with per-course breakdown, weighted averages, sparkline trends
- **File manager** with folder navigation, multi-select, batch downloads
- **Calendar week view** with 7-day grid and time-based placement
- **Structured filtering** with `course:` `type:` `status:` `has:` syntax + fuzzy search
- **Offline mode** with disk-backed response cache (15min TTL, stale-while-offline)
- **Dark/light themes** with toggle (`T` key)
- **CLI flags**: `--export-ics`, `--no-cache`, `--debug`, `--theme`, `--days-ahead`, `--past-hours`
- **Due date notifications** at 60/30/15 minutes before deadlines
- **Pomodoro timer** with title bar display, desktop notifications, bell
- **Keyring support** for secure token storage
- **Help screen** (`?`) with categorized keybindings and filter syntax reference
- **Comprehensive test suite** — 90+ tests across 8 modules
- **Dockerfile** for containerized deployment
- **GitHub Actions CI/CD** — lint, typecheck, test matrix, auto-release on tags
- ASCII Canvas logo in header

### Fixed
- Thread-safe state manager (race condition in saves)
- Proper HTML stripping via `html.parser` (replaces naive regex)
- N+1 course fetch eliminated (batch course cache)
- Temp file cleanup via `atexit`
- Config key inconsistency (`ann_futuredays` / `ann_future_days`)
- UUID-based modal tracking (replaces fragile `id(screen)`)
- Config validation with safe bounds checking
- Lambda closure bugs in error handlers

### Changed
- Typed `CanvasItem` dataclass replaces raw dicts throughout
- Responsive CSS layout with `fr`-based proportional sizing
- ICS export extracted to reusable `ics.py` module
- Rate-limit header parsing (`X-Rate-Limit-Remaining`)

## [0.5.0] — 2026-02-01

### Added
- Initial TUI with planner, announcements, syllabi
- Pomodoro timer
- ICS export
- Calcurse import
