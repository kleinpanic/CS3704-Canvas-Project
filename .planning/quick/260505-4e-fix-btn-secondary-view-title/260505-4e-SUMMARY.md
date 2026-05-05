---
slug: fix-btn-secondary-view-title
quick_id: 260505-4e
status: complete
date: 2026-05-05
commit: e864715
---

# Summary: 260505-4e — Fix Review Issues: btn-secondary + view-title

## What was done

- Removed `.btn-secondary` class from `#refresh-btn` — button now uses `.btn-icon` only, eliminating the dark-mode background override conflict
- Added `<p class="view-title">Assignments</p>` above `#upcoming-list` in the Upcoming view
- Added `<p class="view-title">Your Courses</p>` above `#courses-list` in the Courses view

## Requirements satisfied

- MEDIUM: `.btn-secondary` + `.btn-icon` conflict resolved — no dark-mode override
- MEDIUM: `.view-title` class is no longer dead CSS — applied to section headers satisfying EXT-UI-02 (visual hierarchy)
