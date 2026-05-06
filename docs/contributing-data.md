# Contributing Your Canvas Data

**All you need:** your VT Canvas API token. One script. Done in 2 minutes.

---

## Steps

**1. Get your Canvas token**

Go to [canvas.vt.edu](https://canvas.vt.edu) → Account → Settings → Approved Integrations → **+ New Access Token**.

**2. Clone the repo**

```bash
git clone https://github.com/kleinpanic/CS3704-Canvas-Project.git
cd CS3704-Canvas-Project
pip install requests
```

**3. Run the script**

```bash
export CANVAS_TOKEN=your_token_here
python3 scripts/share_my_canvas.py --contributor yourpid
```

Replace `yourpid` with your VT PID or GitHub handle. The script pulls your full 4-year Canvas history (all courses, all assignments, submission status), anonymizes everything on your machine, and writes the output to `data/collab/yourpid.jsonl`.

**4. Submit your file**

- **PR:** Add `data/collab/yourpid.jsonl` and open a pull request.
- **Email:** Open a [GitHub issue](https://github.com/kleinpanic/CS3704-Canvas-Project/issues) and we'll coordinate directly.

Contributions are validated automatically by CI before merge. See `.github/workflows/` for the validation pipeline.

---

## Before you open a PR: run --dry-run

```bash
python3 scripts/share_my_canvas.py --contributor yourpid --dry-run
```

This runs the full collection and PII scrub pipeline but writes nothing to disk.
It prints a summary to stderr showing record counts, sample field values, and a
SHA-256 checksum of what would be written. Review the sample values to confirm no
real names, course titles, or email addresses appear. If anything looks wrong,
do not open a PR — file an issue instead.

---

## Use a GitHub no-reply email

Before committing your contribution file, configure git to use your GitHub no-reply address:

```bash
git config user.email "YOUR_GITHUB_ID+YOUR_USERNAME@users.noreply.github.com"
```

Your real email address must not appear in the git history of this public repo.

---

## What the script collects

All assignments across your full Canvas history (4 years), including:
- Course code (anonymized to `@COURSE1`, etc.)
- Assignment name, due date, point value
- Whether you submitted / got graded

## What gets anonymized (before anything leaves your machine)

| Original | Replaced with |
|---|---|
| Course codes (e.g. `CS 3704`, `ENGL2204`) | `@COURSE1`, `@COURSE2`, … |
| Course names | same `@COURSE1`, `@COURSE2`, … handle as course code |
| Canvas numeric IDs (7–9 digit numbers) | deterministic hash (`ID######`) |
| Email addresses, phone numbers, SSNs | `[EMAIL]`, `[PHONE]`, `[SSN]` |

Your Canvas token is **never** written to the output.

---

## Troubleshooting

**`CANVAS_TOKEN is not set`** — run `export CANVAS_TOKEN=...` first.

**`401 Unauthorized`** — token expired or copied wrong. Regenerate it in Canvas Settings.
