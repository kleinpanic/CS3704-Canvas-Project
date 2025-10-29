# Canvas-TUI

## Requirements

* Python 3.11+ (for `tomllib`; JSON config also supported)
* Python deps: `requests`, `textual` (installed by `make setup`)
* Optional helpers:

  * `pdftotext` (Poppler) → syllabus PDF text preview
  * `notify-send` → desktop notifications
  * `xclip` or `wl-copy` → yank URL to clipboard
  * `xdg-open` → open files after download
  * `calcurse` → ICS import (`C` / `Ctrl+C`)

Example packages:

* Debian/Ubuntu: `sudo apt install poppler-utils xclip xdg-utils calcurse`
* Arch: `sudo pacman -S poppler xclip xdg-utils calcurse`

## Install

```bash
# from repo root
make install
# binary installed to ~/.local/bin/canvas-tui
```

Run:

```bash
canvas-tui
# or run in-place (dev)
make run
```

Update:

```bash
make update
```

Uninstall:

```bash
make uninstall
# venv is kept: ~/.local/venv/canvas-tui
```

## Configure

Set your Canvas host + token (required):

```bash
export CANVAS_BASE_URL="https://<your-canvas-host>"  # default: https://canvas.vt.edu
export CANVAS_TOKEN="...personal access token..."
```

Optional env vars (defaults shown):

```bash
export TZ="America/New_York"
export CANVAS_UA="canvas-tui/0.5 (textual)"
export HTTP_TIMEOUT=20
export HTTP_MAX_RETRIES=5
export HTTP_BACKOFF=0.4

# time window for items
export DAYS_AHEAD=7            # future days to fetch
export PAST_HOURS=72           # include recent past (if not submitted)

# UI/refresh
export REFRESH_COOLDOWN=2.0    # seconds
export AUTO_REFRESH_SEC=300    # 0 disables background refresh

# downloads + calendar
export DOWNLOAD_DIR=           # default: XDG_DOWNLOAD_DIR or ~/Downloads
export DEFAULT_BLOCK_MIN=60    # event duration before due
export EXPORT_DIR=~/.local/share/canvas-tui
export OPEN_AFTER_DL=0         # 1 to xdg-open after download
export CALCURSE_IMPORT=0       # (keybinding handles this anyway)
```

Config file (overrides env defaults if present):

* `~/.config/canvas-tui/config.toml` (preferred) or `config.json`

**TOML example:**

```toml
days_ahead = 10
past_hours = 96
refresh_cooldown = 1.5
auto_refresh_sec = 180
download_dir = "/home/you/Downloads/Canvas"
default_block_min = 45
```

> State is saved at `~/.local/share/canvas-tui/state.json` (visibility flags, pomodoro end).

## What it does

* Fetches **Planner items** for `[now - PAST_HOURS, now + DAYS_AHEAD]`.
* Normalizes into rows: type, course, title, due date, points, status.
* Quick/Full details, incl. assignment description and attachments.
* **Announcements** extracted from the same window.
* **Syllabi**: show course list → pull `syllabus_body` HTML; if absent, search course files for `*syllab*` (prefers PDF) → preview via `pdftotext` or open/download.
* **Downloads**: scan attachments on assignments and on detail page.
* **ICS export**: create events ending at due time, starting `DEFAULT_BLOCK_MIN` earlier; optional import into `calcurse`.

## Keybindings (main view)

* `↑/↓` move  `Enter` open details  `d` quick preview
* `o` open in browser  `w` download attachments  `y` copy URL
* `c` export ICS  `C` / `Ctrl+C` export ICS and import via `calcurse -i`
* `g` open course page  `/` filter (toggle with `/` again)
* `x` hide/unhide item  `H` toggle show hidden
* `r` refresh  `q` quit
* Pomodoro: `1` 30m, `2` 60m, `3` 120m, `P` custom minutes, `0` stop
* Views: `A` announcements, `S` syllabi

**Details screen**

* `Enter` open selected link  `w` download links  `Backspace` back

**Announcements screen**

* `Enter` open details  `o` open in browser  `w` download  `Backspace` back

**Syllabi screen**

* `Enter` preview PDF/text or load syllabus HTML
* `w` save  `b` open in browser  `Backspace` back

## Paths

* Binary: `~/.local/bin/canvas-tui`
* App: `~/.local/share/canvas-tui/canvas-tui.py`
* Venv: `~/.local/venv/canvas-tui`
* State/ICS: `~/.local/share/canvas-tui/{state.json, canvas.ics}`

## Notes / Behavior

* **Announcements window** currently uses the same time window as the main planner fetch (`PAST_HOURS` back, `DAYS_AHEAD` forward).
* Color coding: submitted=green, overdue=red, due soon warms from orange→yellow→green→cyan, else white.
* Points cell shows `score/points (pct%)` when graded + submission info is available.
* Clipboard copy requires `xclip` (X11) or `wl-copy` (Wayland).

## Troubleshooting

* **Blank / freeze feeling**: network calls are threaded for details/downloads; the main refresh uses retries/backoff. If UI seems stalled, check network and logs. Increase `HTTP_TIMEOUT`, reduce `AUTO_REFRESH_SEC`, or raise `REFRESH_COOLDOWN` if your Canvas is rate-limiting.
* **401 Unauthorized**: set `CANVAS_TOKEN` and correct `CANVAS_BASE_URL`.
* **Syllabus preview empty**: ensure `pdftotext` is installed, or press `b` to open in browser.
* **Clipboard copy fails**: install `xclip` or `wl-copy`.
* **Calcurse import issues**: check `calcurse -i ~/.local/share/canvas-tui/canvas.ics` output; adjust `DEFAULT_BLOCK_MIN`.

## Tokens

Create a **Canvas access token** in your Canvas profile settings. Export it via shell env (`CANVAS_TOKEN`) before launching.
