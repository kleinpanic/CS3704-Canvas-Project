#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""README honesty linter. Checks for false claims and probes live badge state."""
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

README = Path("README.md")

FAIL_PATTERNS = [
    ("optional, defaults to VT", "CANVAS_BASE_URL marked optional (Phase 3 removed this)"),
    ("publish queued", "stale publish-queued claim"),
]

COMMENT_STRIPPED_PATTERNS = [
    ("types-mypy", "types-mypy badge (stripped in Phase 3; replace with mypy-advisory)"),
    ("pypi/v/canvas-tui", "canvas-tui PyPI badge (stripped in Phase 3; restore when #177 ships)"),
]

ERROR_MESSAGES = {"unknown", "invalid", "not found", "missing", "error"}


def check_string_patterns(lines):
    failures = []
    for i, line in enumerate(lines, 1):
        for pattern, description in FAIL_PATTERNS:
            if pattern in line:
                truncated = line.rstrip()[:80]
                failures.append(f"FAIL [line {i:03d}]: {description}: {truncated}")
        for pattern, description in COMMENT_STRIPPED_PATTERNS:
            stripped = line.strip()
            if pattern in line and not stripped.startswith("<!--"):
                truncated = line.rstrip()[:80]
                failures.append(f"FAIL [line {i:03d}]: {description}: {truncated}")
    return failures


def extract_badge_urls(text):
    return re.findall(r"https://img\.shields\.io/[^\s\)\">]+", text)


def probe_badge(url):
    if "/badge/" in url:
        return None
    json_url = url if url.endswith(".json") else url.split("?")[0] + ".json"
    try:
        req = urllib.request.Request(json_url, headers={"User-Agent": "check-readme-claims/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            message = data.get("message", "").lower()
            if any(err in message for err in ERROR_MESSAGES):
                return f"WARN [badge]: {url} returned message: {data.get('message')}"
    except Exception as e:
        print(f"WARN [badge]: could not probe {url}: {e}")
    return None


def main():
    if not README.exists():
        print(f"ERROR: {README} not found", file=sys.stderr)
        sys.exit(1)

    text = README.read_text(encoding="utf-8")
    lines = text.splitlines()

    failures = check_string_patterns(lines)

    badge_urls = extract_badge_urls(text)
    for url in badge_urls:
        time.sleep(0.5)
        warn = probe_badge(url)
        if warn:
            print(warn)

    if failures:
        for f in failures:
            print(f)
        sys.exit(1)

    print(f"OK: README.md passed all checks ({len(badge_urls)} badges probed)")
    sys.exit(0)


if __name__ == "__main__":
    main()
