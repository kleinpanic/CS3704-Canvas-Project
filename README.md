# CS3704 Canvas Project

A maintainable, team-ready **Canvas LMS productivity client** with a Textual TUI frontend, Chrome extension, Python SDK, and a fine-tuned calendar agent — with a documented shared-core architecture.

<!-- Build, repo, tooling, downstream — re-grouped 2026-05-06 -->
[![CI](https://img.shields.io/github/actions/workflow/status/kleinpanic/CS3704-Canvas-Project/ci.yml?branch=main&label=CI)](https://github.com/kleinpanic/CS3704-Canvas-Project/actions/workflows/ci.yml)
[![Security](https://img.shields.io/github/actions/workflow/status/kleinpanic/CS3704-Canvas-Project/security.yml?branch=main&label=Security)](https://github.com/kleinpanic/CS3704-Canvas-Project/actions/workflows/security.yml)
[![Pages](https://img.shields.io/github/actions/workflow/status/kleinpanic/CS3704-Canvas-Project/pages.yml?branch=main&label=Pages)](https://github.com/kleinpanic/CS3704-Canvas-Project/actions/workflows/pages.yml)
[![Release](https://img.shields.io/github/actions/workflow/status/kleinpanic/CS3704-Canvas-Project/release.yml?label=Release)](https://github.com/kleinpanic/CS3704-Canvas-Project/actions/workflows/release.yml)
[![Coverage](https://img.shields.io/github/actions/workflow/status/kleinpanic/CS3704-Canvas-Project/coverage.yml?branch=main&label=Coverage)](https://github.com/kleinpanic/CS3704-Canvas-Project/actions/workflows/coverage.yml)
<br>
[![release](https://img.shields.io/github/v/release/kleinpanic/CS3704-Canvas-Project?label=release)](https://github.com/kleinpanic/CS3704-Canvas-Project/releases)
[![last commit](https://img.shields.io/github/last-commit/kleinpanic/CS3704-Canvas-Project)](https://github.com/kleinpanic/CS3704-Canvas-Project/commits/main)
[![activity](https://img.shields.io/github/commit-activity/m/kleinpanic/CS3704-Canvas-Project?label=activity)](https://github.com/kleinpanic/CS3704-Canvas-Project/commits/main)
[![contributors](https://img.shields.io/github/contributors/kleinpanic/CS3704-Canvas-Project)](https://github.com/kleinpanic/CS3704-Canvas-Project/graphs/contributors)
<br>
[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
[![code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000?logo=ruff)](https://github.com/astral-sh/ruff)
[![types: mypy](https://img.shields.io/badge/types-mypy-blue?logo=python&logoColor=white)](https://mypy-lang.org/)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://pre-commit.com/)
<br>
[![HF Model](https://img.shields.io/badge/🤗_Model-canvas--calendar--agent--v7--dpo-yellow)](https://huggingface.co/kleinpanic93/canvas-calendar-agent-v7-dpo)
[![HF Dataset](https://img.shields.io/badge/🤗_Dataset-canvas--calendar--preferences--v7-blue)](https://huggingface.co/datasets/kleinpanic93/canvas-calendar-preferences-v7)
[![HF Collection](https://img.shields.io/badge/🤗_Collection-Canvas_Calendar_Agent_v3.0-yellow)](https://huggingface.co/collections/kleinpanic93/canvas-calendar-agent-v30-69fa6462f697e0342b21dfe0)
[![HF Space](https://img.shields.io/badge/🤗_Space-Live_Demo-purple)](https://huggingface.co/spaces/kleinpanic93/canvas-calendar-agent-demo)
[![ghcr.io](https://img.shields.io/badge/ghcr.io-canvas--tui-2496ED?logo=docker&logoColor=white)](https://github.com/kleinpanic/CS3704-Canvas-Project/pkgs/container/canvas-tui)

---

## Distribution

| Surface | Channel | Status |
|---------|---------|--------|
| **canvas-sdk** (Python) | [PyPI](https://pypi.org/project/canvas-sdk/) | publish queued — see `release.yml` `publish-pypi` job |
| **canvas-tui** (Python) | [PyPI](https://pypi.org/project/canvas-tui/) | publish queued — `pyproject.toml` v1.2.0 |
| **canvas-tui** (Docker) | `ghcr.io/kleinpanic/canvas-tui` | live — built nightly + on tag (#140) |
| **Chrome extension** | [Chrome Web Store](https://chromewebstore.google.com/) | listing in progress — install via `Load unpacked` for now |
| **HF Space demo** | [Live](https://huggingface.co/spaces/kleinpanic93/canvas-calendar-agent-demo) | live — auto-deploys on push to `main` |
| **HF Model** | [v7-DPO](https://huggingface.co/kleinpanic93/canvas-calendar-agent-v7-dpo) | live |

> **PyPI publication queued — Chrome Web Store listing in progress.** Trusted publisher registration at pypi.org pending; first stable tag (`v1.0.0`+) will fire `publish-pypi`.

---

## Quick Start

### Chrome Extension

1. Clone or download this repo.
2. In Chrome, open `chrome://extensions/` and enable **Developer mode**.
3. Click **Load unpacked** and select the `extension/` directory.
4. Pin the extension, open a Canvas page, and click the icon.

### Python SDK

```bash
pip install canvas-sdk[autodownload]    # fetches the v7-dpo Gemma4 model from HF on first run
pip install canvas-sdk[gemini]          # optional Gemini fallback
pip install canvas-sdk[all]             # both
```

```python
import os
from canvas_sdk import CanvasAgent

os.environ["CANVAS_TOKEN"]    = "..."        # your Canvas API token
os.environ["CANVAS_BASE_URL"] = "https://canvas.vt.edu"

agent = CanvasAgent.auto()                   # auto-resolves: env -> local -> HF -> Gemini
print(agent.run("What is due this week?"))
```

`CanvasAgent.auto()` resolution order:
1. `CANVAS_LLM_ENDPOINT` env (skip auto-download, use your own server)
2. Local cache at `~/.cache/canvas-agent/v7-dpo/` (spawns vLLM on `:8765`)
3. Download `kleinpanic93/canvas-calendar-agent-v7-dpo` from HF, then (2)
4. Fall back to Gemini (`gemini-2.5-flash` by default)

### TUI (Terminal UI)

```bash
export CANVAS_TOKEN="your_canvas_token_here"
export CANVAS_BASE_URL="https://canvas.vt.edu"   # optional, defaults to VT

pipx install .          # recommended
# or: pip install .

canvas-tui
```

---

## Live Demo

Try the fine-tuned Canvas Calendar Agent in your browser — no install required, no tokens needed:

- **Agent demo** (mock Canvas data, hosted DPO model): https://kleinpanic.github.io/CS3704-Canvas-Project/agent-demo/
- **HF Space** (full model, mock tools): https://huggingface.co/spaces/kleinpanic93/canvas-calendar-agent-demo
- **HF Collection** (v3.0 method matrix): https://huggingface.co/collections/kleinpanic93/canvas-calendar-agent-v30-69fa6462f697e0342b21dfe0

### Demo architecture (no tokens in client JS)

```
Browser  ->  Cloudflare Worker  ->  HF Space (ZeroGPU)
              ^                       ^
              |                       |
              | HF_TOKEN held as      | Gemma4 v7-dpo behind
              | Cloudflare secret     | gradio 5 ChatInterface +
              | (never reaches the    | 18 mock tool dispatchers
              | browser)              |
```

The HF token is stored as a Cloudflare Worker secret. Public clients only
see the proxy URL (`cs3704-demo-proxy.kleinpanic.workers.dev`); they never
receive any credential. See [`proxy/README.md`](proxy/README.md) for the
deploy procedure and [`proxy/iframe-fallback.html`](proxy/iframe-fallback.html)
for a zero-infra alternative that embeds the Space directly.

> **Token policy:** the SDK reads `CANVAS_TOKEN` and `GOOGLE_API_KEY` from
> your local environment. Tokens never enter the published browser demo,
> the GH Pages site, or any committed file. The Cloudflare Worker proxy is
> the only place an HF token is held, and it sits server-side as a Cloudflare
> secret. If you fork this project and host your own demo, follow the same
> pattern — see [`proxy/README.md`](proxy/README.md).

---

## Documentation

- **[Docs site](https://kleinpanic.github.io/CS3704-Canvas-Project/)** — live project docs
- **[Agent demo](https://kleinpanic.github.io/CS3704-Canvas-Project/agent-demo/)** — chat with the Canvas Calendar Agent in your browser
- **[Roadmap](https://kleinpanic.github.io/CS3704-Canvas-Project/roadmap.html)** — planned milestones and feature backlog
- **[HF Space](https://huggingface.co/spaces/kleinpanic93/canvas-calendar-agent-demo)** — full v7-dpo model behind a Gradio chat UI
- **[How it Works](https://kleinpanic.github.io/CS3704-Canvas-Project/agent-demo/method.html)** — DPO methodology, 9-method ablation matrix, G1–G13 guardrails, bench harness
- **[PyPI: canvas-sdk](https://pypi.org/project/canvas-sdk/)** — `pip install canvas-sdk`
- **[Architecture docs](https://kleinpanic.github.io/CS3704-Canvas-Project/docs/architecture/)** — system design decisions
- **[Browser extension docs](https://kleinpanic.github.io/CS3704-Canvas-Project/docs/extension/)** — shared client/runtime architecture
- **[Contributing](CONTRIBUTING.md)** — contribution guidelines and developer setup
- **[Maintainers](MAINTAINERS.md)** — maintainer responsibilities
- **[Security policy](SECURITY.md)** — security procedures

---

## Development

For team workflow, branch naming, repo structure, and dev setup, see [`CONTRIBUTING.md`](CONTRIBUTING.md).

---

## Contributors

[![Contributors](https://contrib.rocks/image?repo=kleinpanic/CS3704-Canvas-Project)](https://github.com/kleinpanic/CS3704-Canvas-Project/graphs/contributors)

Made with [contrib.rocks](https://contrib.rocks).

---

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
