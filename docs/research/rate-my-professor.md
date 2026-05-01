# Rate My Professor Integration Research Spike

## Goal
Investigate strategies for integrating professor ratings from RateMyProfessors.com into the CS3704 Canvas Project (TUI and browser extension) and provide recommendations for implementation.

## Existing Solutions
- [tisuela/ratemyprof-api](https://github.com/tisuela/ratemyprof-api): A Python class that scrapes RateMyProfessors.com for a given university. It fetches the list of professors for a university ID and allows searching by first/last name, returning a `Professor` object with rating, difficulty, number of ratings, etc.
  - Pros: Already implements the scraping logic, handles pagination, provides a simple API.
  - Cons: Relies on scraping HTML, which may break if the site changes; requires a university ID; no official API; rate limiting concerns.
  - The code is MIT licensed.

## Data Sources
### Canvas LMS
- The Canvas API provides course information including instructors (teachers) via:
  - `GET /api/v1/courses/:id` includes an array of `teachers` objects with `id`, `display_name`, `bio`, etc.
  - `GET /api/v1/courses/:id/users?enrollment_type[]=teacher` returns a list of teacher enrollments.
- Teacher objects may include `display_name` (e.g., "John Smith") but not necessarily separate first/last. Some may include `sortable_name` (e.g., "Smith, John").
- We can extract first and last names from `display_name` or `sortable_name`.

### RateMyProfessors.com
- No official public API.
- The tisuela scraper works by:
  1. Fetching the number of professors for a given university ID from `https://www.ratemyprofessors.com/filter/professor/?&page=1&filter=teacherlastname_sort_s+asc&query=*%3A*&queryoption=TEACHER&queryBy=schoolId&sid=<university_id>`
  2. Then iterating through pages to fetch professor cards.
  3. Each professor card contains name, rating, difficulty, number of ratings, and a link to the professor's page.
- The scraper caches the list of professors in memory (or could be persisted).

## Matching Strategy
Given a Canvas teacher name (e.g., "John Smith"), we need to find the matching professor on RateMyProfessors.com.

Challenges:
- Name variations: middle initials, nicknames, suffixes (Jr., Sr.), different ordering.
- Multiple professors with the same name at the same institution.
- Missing data: some instructors may not have a rating.

Proposed approach:
1. Normalize both Canvas teacher name and RMP professor name:
   - Convert to lowercase.
   - Remove punctuation (periods, commas, hyphens).
   - Remove common suffixes (jr, sr, ii, iii, md, phd, etc.).
   - Extract first and last tokens; if there are more than two tokens, consider the first as first name and the last as last name (ignore middle).
2. Attempt exact match on normalized first + last.
3. If no exact match, try fuzzy matching (e.g., Levenshtein distance) on last name only, then first name, with a threshold (e.g., distance <= 2).
4. If multiple candidates, disambiguate by:
   - Prefer the professor with the highest number of ratings (more likely to be the correct one).
   - If still tied, prefer the one with a higher rating (or just pick the first).
5. If no match above threshold, return "No match found".

We could also consider using the Canvas teacher's `id` or `sis_user_id` if it maps to something in RMP, but it does not.

## University ID
The tisuela scraper requires a university ID for Virginia Tech. We need to determine the correct ID for Virginia Tech.

We can find it by inspecting the network requests when searching for Virginia Tech on RateMyProfessors.com, or by looking up known IDs.

From the tisuela README, the example uses `UniversityId = 1055` for "University of Texas at Austin". We need to find VT's ID.

We can attempt to scrape the search page for "Virginia Tech" to get the ID, or we can hardcode after research.

Let's quickly try to find it using a request.

We'll do a quick check in the research.

## Caching
To reduce load on the RMP site and improve performance, we should cache professor data.

Options:
- Cache the entire professor list for a given university ID (maybe per semester) in a JSON file or SQLite table.
- Cache individual professor lookups (by normalized name) with a TTL (e.g., 24 hours).
- For the TUI, we could prefetch at startup or on demand and store in the existing SQLite cache.
- For the extension, we could use IndexedDB with stale-while-revalidate (similar to the current cache layer).

## Implementation Recommendation
### 1. Vendor the tisuela ratemyprof-api (with modifications)
- Copy the relevant source into our codebase (under `src/rmp/` or `sdk/rmp/`).
- Adapt it to:
  - Accept a configurable university ID (default to Virginia Tech's ID after we determine it).
  - Provide a method `get_professor_by_name(first_name, last_name)` that returns a dict or None.
  - Add caching layer (optional, to be integrated with existing cache).
  - Add error handling for network failures and parsing changes.
  - Respect rate limiting: add a delay between requests (e.g., 1 second) and maybe use a session with retries.
- Ensure the code is MIT licensed (compatible).

### 2. Create a service layer
- In the TUI: a `ProfessorService` that uses the RMP client and optionally caches results in the existing SQLite cache (or a separate table).
- In the extension: a similar service that uses the shared JS client? Actually, the extension cannot directly use the Python library. We would need to either:
  - Expose a backend endpoint (not desirable) OR
  - Implement a JavaScript version of the scraper (or use the same logic in JS) OR
  - Have the TUI provide an API that the extension can call via native messaging? Not ideal.
Given the extension is client-side only, we likely need a separate JavaScript implementation for the extension, or we could decide that the RMP feature is TUI-only initially and later we can share via a common API if we ever create a backend.

Alternatively, we could have the extension request rating data from the TUI via a custom endpoint (if we ever implement sync), but that's complex.

Simpler: Implement the RMP lookup in both Python (for TUI) and JavaScript (for extension) using similar logic. We can share the matching algorithm and university ID config via a shared JSON file or constants.

Given the scope, we might start with TUI-only for the spike and note that extension would need a JS port.

### 3. UI Integration
- TUI: Add a new screen `ProfessorRatingsScreen` that shows a list of courses with their instructors and any available rating (showing score, difficulty, number of ratings). Allow drilling down to see detailed reviews.
- Extension: Add a section in the popup or a new tab that shows professor ratings for the current Canvas page (e.g., when viewing a course or assignment).

### 4. Failure Modes
- If the RMP site is unreachable or returns an error, we should gracefully degrade and show "Rating data unavailable".
- If no match is found, show "No rating available".
- If multiple matches, we can show a disambiguation prompt or pick the best match and note that it's an estimate.

## Next Steps
1. Determine the Virginia Tech university ID for RateMyProfessors.com.
2. Prototype the matching strategy with a few sample Canvas course teacher names.
3. Implement a thin wrapper around the tisuela library (or a direct port) and integrate with the TUI's course data.
4. Create a mock UI to verify the flow.
5. Document caching strategy and implementation details.

## Open Questions
- How often should we refresh the professor list? (Once per semester seems reasonable.)
- Should we allow users to manually correct a mismatch?

## Recommendation
Proceed with the implementation as described above. The VT school ID (1346) is configured in the seeded university registry. Caching uses atomic writes with UTF-8 encoding. Matching handles titles, suffixes, accents, and comma-formatted names.
