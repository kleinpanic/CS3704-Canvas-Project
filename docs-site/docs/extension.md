# Browser Extension

**Canvas Deadline Tracker** is a Manifest V3 Chrome extension targeting `canvas.vt.edu`.

Source lives under `extension/`.

## Popup

The popup has four top-level tabs:

- **Upcoming** — assignments due within a configurable window, with course filter, dismiss, and quick-open links
- **Courses** — full course list; clicking a course opens a detail view with sub-tabs for Assignments, Announcements, and Modules, plus a RateMyProfessors rating for the professor
- **Grades** — per-course grade summaries
- **Ask AI** — chat interface with 18 preset tool buttons (see below)

A settings panel (gear icon) handles API token entry, theme, and days-ahead window.

## Ask AI Tab

The agent tab has a free-text input and 18 preset tool buttons grouped by family:

| Family | Count | Examples |
|--------|-------|---------|
| canvas | 8 | get_assignments, get_grades, get_syllabus, list_announcements |
| calendar | 5 | create_event, find_free_blocks, list_events |
| reranker | 1 | priority_hint |
| study | 4 | exam_bracket, spaced_schedule, semester_schedule |

Agent queries hit the Cloudflare Worker proxy. If the native messaging host (`com.cs3704.canvas_tracker`) is installed locally, complex queries can fall through to it.

## Background Service Worker

- Fetches from the Canvas REST API through `canvas-client.js`
- Caches results in IndexedDB with stale-while-revalidate so the popup opens instantly
- Sets the toolbar badge to the count of non-dismissed upcoming assignments
- Fires notifications at 24h and 1h before each deadline

## Permissions

| Permission | Purpose |
|-----------|---------|
| `activeTab` | Read current tab URL |
| `storage` | Persist settings and cache |
| `notifications` | Deadline reminders |
| `nativeMessaging` | Connect to local `com.cs3704.canvas_tracker` host |
| host: `canvas.vt.edu` | Canvas REST API calls |
| host: `ratemyprofessors.com` | Professor rating in course detail view |

## Key Files

| File | Role |
|------|------|
| `extension/src/lib/canvas-client.js` | Canvas REST client (auth, endpoints) |
| `extension/src/lib/extension-contract.js` | Shared message-type constants |
| `extension/src/lib/extension-api.js` | Runtime bridge used by popup code |
| `extension/src/lib/cache.js` | IndexedDB helpers and stale-while-revalidate |
| `extension/src/lib/reranker.js` | JS port of the Python reranker pipeline |
| `extension/src/lib/native-host.js` | Native messaging bridge to local host |
| `extension/src/background.js` | Service worker: cache, badge, notifications, agent |
| `extension/src/popup/app.js` | Popup UI logic |
| `extension/src/popup/styles.css` | Popup styles |

The extension does not call the Python SDK. `canvas-client.js` is the JS-side equivalent of `canvas_sdk`.
