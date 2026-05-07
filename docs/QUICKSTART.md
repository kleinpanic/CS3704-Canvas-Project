# Quick Start (10 minutes)

Get Canvas Tracker running on your machine — no VT affiliation required.

---

## Prerequisites

- Python 3.11 or newer ([python.org](https://www.python.org/downloads/))
- A Canvas API token from your institution's Canvas instance

**Get a Canvas API token:**
1. Log in to your Canvas instance.
2. Click your avatar (top-left) → **Account** → **Settings**.
3. Scroll to **Approved Integrations** → **New Access Token**.
4. Give it a name (e.g. `canvas-tracker`), set an expiry, and click **Generate Token**.
5. Copy the token — you will not see it again.

---

## Install

Install the TUI package from PyPI:

```bash
pip install canvas-tui
```

Or install just the SDK (no TUI):

```bash
pip install canvas-sdk
```

For the full stack including the calendar agent and model auto-download:

```bash
pip install "canvas-sdk[all]"
```

---

## Configure

Set two environment variables. Replace the URL with your institution's Canvas base URL:

```bash
export CANVAS_BASE_URL="https://your-institution.instructure.com"
export CANVAS_TOKEN="your_token_here"
```

Add these to your `~/.bashrc` or `~/.zshrc` to persist them across sessions.

**Common Canvas base URLs:**

| Institution type | Example URL |
|-----------------|-------------|
| Hosted (Instructure) | `https://yourinstitution.instructure.com` |
| Vanity domain | `https://canvas.youruniversity.edu` |

Do **not** include a trailing slash.

---

## Run the TUI

```bash
python -m canvas_tui
```

Or via the installed entry point:

```bash
canvas-tui
```

---

## Explore

Once the TUI opens:

- **Course list** — your active enrollments, updated from the Canvas API
- **Assignments** — per-course assignment list with due dates
- **Calendar agent** — ask natural-language questions like "What is due this week?"
- **Keybindings** — press `?` for the full keybinding reference

Navigate with arrow keys, `j`/`k`, or Tab. Press `q` to quit.

---

## Try the SDK directly

```python
import os
from canvas_sdk import CanvasClient

client = CanvasClient(
    base_url=os.environ["CANVAS_BASE_URL"],
    access_token=os.environ["CANVAS_TOKEN"],
)

courses = client.get_courses()
for course in courses:
    print(course.name)
```

See [`examples/quickstart-sdk.py`](../examples/quickstart-sdk.py) for a complete runnable script.

---

## Try the Chrome Extension

1. In Chrome: `chrome://extensions/` → enable **Developer mode**.
2. Click **Load unpacked** → select the `extension/` directory from the cloned repo.
3. Navigate to a Canvas page and click the extension icon.

See [`examples/quickstart-extension.md`](../examples/quickstart-extension.md) for the full walkthrough.

---

## Next Steps

| What | Where |
|------|-------|
| Contribute Canvas trajectory data | [`examples/contribute-data.sh`](../examples/contribute-data.sh) |
| Full docs site | [GH Pages](https://kleinpanic.github.io/CS3704-Canvas-Project/) |
| Architecture overview | [`docs/architecture/`](architecture/) |
| Contributing guide | [`CONTRIBUTING.md`](../CONTRIBUTING.md) |
| Public roadmap | [`ROADMAP.md`](../ROADMAP.md) |
| Security policy | [`SECURITY.md`](../SECURITY.md) |

---

## Troubleshooting

**`canvas-tui: command not found`** — use `python -m canvas_tui` instead, or ensure your
pip bin directory is on `PATH`.

**`InvalidAccessToken`** — regenerate your Canvas token and re-export `CANVAS_TOKEN`.

**`CANVAS_BASE_URL` not set** — export the variable in the same terminal session that
runs the TUI.

**No courses appear** — confirm your token has API access: try
`curl -H "Authorization: Bearer $CANVAS_TOKEN" "$CANVAS_BASE_URL/api/v1/courses"` — you
should get a JSON array.
