# Security Policy

## Supported Versions

Active development happens on `main`. The latest GitHub Release is the supported version.
Older tags receive no backported fixes unless severity warrants it.

## Reporting a Vulnerability

Please report vulnerabilities **privately** via GitHub Security Advisories:
- **Security tab → Advisories → Report a vulnerability**

Do **not** open public issues for active vulnerabilities. Public disclosure before a fix
is available puts all users at risk.

For sensitive disclosures, you may also reach the owner directly via the GitHub profile
contact on [kleinpanic](https://github.com/kleinpanic).

## Response Timeline

| Severity | Acknowledgement | Fix Target |
|----------|----------------|------------|
| Critical / High | 48 hours | 30 days |
| Medium | 5 business days | 90 days |
| Low / Informational | 2 weeks | Best effort |

Timelines are targets, not guarantees. Progress updates are provided every 7 days for
active disclosures. The timeline clock starts from the first private report received.

## Scope

### In Scope

- `canvas-sdk` Python package (`src/sdk/`)
- `canvas-tui` Python TUI (`src/canvas_tui/`)
- Cloudflare Worker proxy (`workers/`, `proxy/`)
- HuggingFace Spaces (`huggingface/agent-demo/`, `huggingface/pii-scrub/`)
- GitHub Actions workflows (`.github/workflows/`)
- Dataset pipeline scripts (`scripts/share_my_canvas.py`)

### Out of Scope

- Third-party dependencies (report upstream to the respective project)
- Contributor-uploaded dataset entries (`data/collab/`) — data is accepted after PII scrub
- Chrome Web Store infrastructure (Google's responsibility)
- VT Canvas LMS itself (report to [security@vt.edu](mailto:security@vt.edu))
- GitHub Actions infrastructure (report to GitHub)

## Security Baseline Enforced

- Branch protection on `main`
- Required PR reviews + status checks before merge
- Force-push and deletion disabled on protected branch
- CodeQL analysis enabled (`.github/workflows/security.yml`)
- Dependency review on all PRs
- Dependabot updates for pip + GitHub Actions
- GPG commit signature requirement on protected branch
- All third-party Actions pinned to commit SHAs (Phase 6 hardening)
- `step-security/harden-runner` in all workflows (egress audit)
- OSSF Scorecard workflow enabled

## Hall of Fame

We are grateful to security researchers who responsibly disclose vulnerabilities.

| Researcher | Summary | Date |
|------------|---------|------|
| — | (none yet — be the first!) | — |
