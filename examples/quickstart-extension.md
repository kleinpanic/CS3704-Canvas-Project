# Chrome Extension Quick Start

Load the Canvas Tracker browser extension in developer mode and connect it to your Canvas instance.

**Estimated time:** 5 minutes
**Requirement:** Chrome or a Chromium-based browser

---

## 1. Clone the repository

```bash
git clone https://github.com/kleinpanic/CS3704-Canvas-Project.git
cd CS3704-Canvas-Project
```

The Chrome extension source is in the `extension/` directory at the root of the repo.

---

## 2. Open Chrome Extensions

1. Open a Chrome window.
2. Navigate to `chrome://extensions/` in the address bar.
3. Enable **Developer mode** using the toggle in the top-right corner.

---

## 3. Load the extension

1. Click **Load unpacked** (top-left, visible after enabling Developer mode).
2. In the file picker, navigate to the `extension/` directory inside the cloned repo.
3. Click **Select Folder** (Windows) or **Open** (macOS/Linux).

The extension icon (Canvas Tracker) will appear in the Chrome toolbar.

---

## 4. Pin the extension

1. Click the puzzle-piece icon in the Chrome toolbar to open the extensions menu.
2. Find **Canvas Tracker** and click the **pin** icon to keep it visible.

---

## 5. Open a Canvas page and activate

1. Navigate to your institution's Canvas instance (e.g. `https://your-institution.instructure.com`).
2. Click the **Canvas Tracker** icon in the toolbar.
3. If prompted, enter your Canvas base URL in the settings field (the extension infers it from your active tab for supported instances).

The extension will read your current Canvas page context and display the overlay.

---

## 6. Configure the host URL (if prompted)

Some Canvas instances use custom subdomains. If the extension cannot auto-detect the host:

1. Click the gear icon inside the extension popup.
2. Enter your full Canvas base URL: `https://your-institution.instructure.com`
3. Save. The extension will refresh its connection.

---

## Troubleshooting

### Extension loads but shows no data

- Make sure you are on an active Canvas page (assignments, course home, dashboard).
- Confirm the host URL matches your institution's Canvas URL exactly (no trailing slash).

### CORS errors in the DevTools console

The extension uses the Canvas API with your session cookies. CORS errors typically mean:
- The Canvas token has insufficient scopes — regenerate with full API access.
- Your institution has restricted third-party access — check with your Canvas admin.

### Token scope errors

Generate a fresh access token:
`Canvas → Account (top-left avatar) → Settings → Approved Integrations → New Access Token`

Grant all read permissions. For assignment writes or calendar operations, also grant write access.

### Extension not updating after code changes

Reload the extension:
1. Go to `chrome://extensions/`
2. Find **Canvas Tracker** and click the circular ↺ refresh icon.

---

## Next Steps

- **SDK integration:** see [`examples/quickstart-sdk.py`](quickstart-sdk.py) to automate Canvas API calls from Python.
- **Extension architecture:** see [`docs/EXTENSION_ROADMAP.md`](../docs/EXTENSION_ROADMAP.md) for the host/client split and upcoming features.
- **Contribute:** see [`CONTRIBUTING.md`](../CONTRIBUTING.md) for the contribution workflow.
