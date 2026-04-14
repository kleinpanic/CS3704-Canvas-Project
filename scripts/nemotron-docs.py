#!/usr/bin/env python3
"""Nemotron auto-docs script — called by auto-docs.yml workflow."""

import argparse
import ast
import os
import subprocess
import sys
import urllib.request


def find_undocumented_modules(repo_path, max_modules=8):
    """Find modules in recent commits that lack docstrings."""
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "-5", "--name-only"],
            capture_output=True, text=True, cwd=repo_path
        )
        files = set()
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith("src/") and stripped.endswith(".py"):
                files.add(stripped)
    except Exception:
        return []

    missing = []
    for f in sorted(files)[:max_modules]:
        path = os.path.join(repo_path, f)
        if not os.path.exists(path):
            continue
        try:
            with open(path) as src:
                content = src.read()
            tree = ast.parse(content)
            funcs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
            if funcs and not any(ast.get_docstring(fn) for fn in funcs):
                missing.append(f)
        except Exception:
            pass
    return missing


def generate_docstrings(modules, repo_path, host, port, api_key):
    """Call Nemotron to generate docstrings for listed modules."""
    results = []
    for mod in modules:
        path = os.path.join(repo_path, mod)
        try:
            with open(path) as f:
                content = f.read()[:3500]
        except Exception:
            continue

        prompt = (
            f"Generate Python docstrings for this module. Output ONLY valid Python docstrings as comments, nothing else.\n\n"
            f"Module: {mod}\n{content}"
        )

        payload = {
            "model": "nemotron",
            "messages": [
                {"role": "system", "content": "You are a documentation generator. Output ONLY valid Python docstrings with proper indentation as // comments, nothing else."},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 1536,
            "temperature": 0.3
        }

        url = f"http://{host}:{port}/v1/chat/completions"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                result = json.loads(r.read())
                docstring = result["choices"][0]["message"]["content"]
                results.append(f"# --- {mod} ---\n{docstring}")
        except Exception as e:
            results.append(f"# --- {mod} ---\n# NEMOTRON_ERROR: {e}")

    return results


if __name__ == "__main__":
    import json

    parser = argparse.ArgumentParser(description="Generate docstrings via Nemotron")
    parser.add_argument("--scan-only", action="store_true", help="Only scan, print modules and exit")
    parser.add_argument("--modules", help="Comma-separated list of modules")
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True)
    parser.add_argument("--key", required=True)
    args = parser.parse_args()

    repo = "__REPO_ROOT__/"

    if args.scan_only:
        missing = find_undocumented_modules(repo)
        print("MISSING_MODULES=" + ",".join(missing))
        sys.exit(0)

    if args.modules:
        modules = [m.strip() for m in args.modules.split(",") if m.strip()]
        results = generate_docstrings(modules, repo, args.host, args.port, args.key)
        print("\n\n".join(results))
    else:
        print("No modules specified", file=sys.stderr)
        sys.exit(1)