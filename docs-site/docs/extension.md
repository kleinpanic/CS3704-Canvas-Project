# Browser Extension Architecture

This page documents the current browser extension architecture after the shared-client refactor landed on `main`.

## Current Status

The browser extension is now a real part of the project, not just a future placeholder.

Implemented pieces:
- MV3 browser extension source under `extension/`
- popup UI for upcoming assignments and course filtering
- background service worker for sync, badge updates, and notifications
- IndexedDB cache adapter for stale-while-revalidate behavior
- shared extension-side Canvas client layer
- shared runtime contract between popup and background code

## What Changed Recently

The extension no longer keeps raw Canvas access logic scattered across UI files.

Instead, the browser-facing stack is organized like this:

```text
popup UI
  -> extension-api.js
  -> extension-contract.js
  -> background.js
  -> canvas-client.js
  -> Canvas REST API
```

## Key Files

| File | Role |
|------|------|
| `extension/src/lib/canvas-client.js` | Shared Canvas domain client for browser-side code |
| `extension/src/lib/extension-contract.js` | Central message-type contract |
| `extension/src/lib/extension-api.js` | Shared runtime bridge used by popup/content code |
| `extension/src/background.js` | Service worker orchestration, cache access, notifications, badge refresh |
| `extension/src/lib/cache.js` | IndexedDB cache and stale-while-revalidate helpers |
| `extension/src/popup/app.js` | Popup UI logic |
| `extension/src/popup/styles.css` | Popup visual system |

## Why This Matters

Before the refactor, raw endpoint knowledge and runtime message details leaked into more than one layer.

Now:
- Canvas auth and endpoint access are centralized in `canvas-client.js`
- popup code talks through a shared runtime bridge instead of raw message strings
- runtime message names are defined once in `extension-contract.js`
- background logic is thinner and easier to extend

That gives the project:
- cleaner maintenance
- fewer UI-to-background coupling mistakes
- easier future extension features
- a better path toward testable shared browser logic

## Current Constraints

The browser extension does **not** use the Python SDK directly.

That is expected.

A browser extension cannot natively consume the Python package in the same way the TUI does. The correct browser-side equivalent is a shared JS client layer, which is what this project now uses.

## Next Recommended Steps

1. Extend the shared client for more Canvas domains as features expand
2. Add tests around the browser-side runtime contract and client methods
3. Reduce any remaining direct Chrome runtime assumptions outside the bridge layer
4. Decide whether content scripts should also consume `extension-api.js`
5. Document token/auth strategy more explicitly if OAuth replaces manual tokens later

## Relationship to the TUI

The TUI and browser extension are still separate runtime stacks, but the extension is now closer to the same architectural discipline:
- domain access centralized
- cache isolated
- UI and transport separated

That is the right intermediate step before any deeper shared-core unification.
