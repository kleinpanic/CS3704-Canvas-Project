---
slug: ext-ui-prof-ratings
created: 2026-05-05
status: complete
---

# Summary: Issue #52 Plan 2 — Professor Ratings (EXT-UI-04)

## What was done

Implemented professor rating display in the course detail view using the RateMyProfessors public filter API.

### Tasks completed

1. **manifest.json** — `https://www.ratemyprofessors.com/*` already present in host_permissions (pre-existing).
2. **canvas-client.js** — `include[]=teachers` already present in getCourses params (pre-existing).
3. **extension-contract.js** — Added `getRmpRating: 'GET_RMP_RATING'` message type.
4. **background.js** — Added `GET_RMP_RATING` handler: extracts last name, fetches `https://www.ratemyprofessors.com/filter/teacher?institution_id=1346&query={lastName}`, returns `{rating, difficulty, numRatings}`.
5. **extension-api.js** — Added `getRmpRating(professorName)` export.
6. **index.html** — Added `<div id="professor-section" class="hidden"></div>` below `.detail-header` in `#view-course-detail`.
7. **app.js** — In `openCourseDetail()`: extracts teacher from `allCourses`, calls `getRmpRating`, renders star rating + difficulty + count. Added `renderStars()` helper.
8. **styles.css** — Added `.professor-section`, `.prof-name`, `.prof-rating`, `.prof-stars` styles.

## Commit

`08a2dcc` feat(ext-ui): EXT-UI-04 professor ratings via RateMyProfessors
