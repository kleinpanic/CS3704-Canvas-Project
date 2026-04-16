#!/usr/bin/env python3
"""Nemotron fixup script — called by ai-fixup.yml workflow."""

import argparse
import json
import os
import sys
import urllib.request


def main():
    parser = argparse.ArgumentParser(description="Generate fixup patch via Nemotron")
    parser.add_argument("--log", required=True, help="Path to CI log file")
    parser.add_argument("--host", required=True, help="DGX Spark host")
    parser.add_argument("--port", required=True, help="DGX Spark port")
    parser.add_argument("--key", required=True, help="Spark API key")
    args = parser.parse_args()

    try:
        with open(args.log) as f:
            log_content = f.read()[-4000:]
    except Exception:
        log_content = "could not read log file"

    prompt = (
        "The following CI tests failed. Generate a git diff patch that fixes the failures.\n"
        "Output ONLY the raw patch text (git diff format), nothing else.\n\n"
        f"CI log:\n{log_content}"
    )

    payload = json.dumps({
        "model": "nemotron",
        "messages": [
            {"role": "system", "content": "You are a code fix assistant. Fix failing Python tests. Output ONLY a valid git diff patch."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 2048,
        "temperature": 0.2
    }).encode()

    url = f"http://{args.host}:{args.port}/v1/chat/completions"
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {args.key}"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            result = json.loads(r.read())
            content = result["choices"][0]["message"]["content"]
            print(content, end="")
    except Exception as e:
        print(f"# NEMOTRON_ERROR: {e}", file=sys.stderr)
        # Exit 0 so the workflow step can handle gracefully — do NOT fail the job
        sys.exit(0)


if __name__ == "__main__":
    main()