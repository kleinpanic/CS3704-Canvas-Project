#!/usr/bin/env python3
"""
Nemotron documentation stub generator — called by auto-docs.yml workflow.

Two modes:
  --scan-only        Scan src/ for undocumented public modules, emit MISSING_MODULES.
  --modules <list>  Generate docstring stubs for the given comma-separated modules.

Security: never print tokens, keys, or auth headers. All public output is CI-visible.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import sys
import urllib.request


# ---------- Scanning ----------

def find_python_files(root: str = "src") -> list[str]:
    """Walk src/ and return all .py files, skipping __pycache__ and private files."""
    files: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip pycache and test-related dirs
        dirnames[:] = [d for d in dirnames if d not in ("__pycache__", ".mypy_cache", "tests")]
        for fname in filenames:
            if fname.endswith(".py") and not fname.startswith("_"):
                files.append(os.path.join(dirpath, fname))
    return sorted(files)


def has_docstring(filepath: str) -> bool:
    """Return True if the module has a non-empty module-level docstring."""
    try:
        with open(filepath, encoding="utf-8") as f:
            first_lines: list[str] = []
            for i, line in enumerate(f):
                line = line.rstrip()
                if i > 5:
                    # Only check the first 5 lines for a module docstring
                    break
                if line.strip() in ("", "#"):
                    continue
                first_lines.append(line)
                if len(first_lines) >= 2:
                    break

            if not first_lines:
                return False
            # First non-blank, non-comment line should be an opening docstring
            first = first_lines[0].strip()
            return first.startswith('"""') or first.startswith("'''")
    except Exception:
        return True  # Assume documented on error to avoid noise


def scan_for_undocumented(src_root: str = "src") -> list[str]:
    """Return list of module paths that lack module-level docstrings."""
    missing: list[str] = []
    for filepath in find_python_files(src_root):
        if not has_docstring(filepath):
            # Convert path/to/file.py → path.to.file (dot-separated module)
            module = os.path.relpath(filepath, src_root)
            module = module.replace(os.sep, ".").removesuffix(".py")
            missing.append(module)
    return missing


# ---------- Docstring generation via Spark ----------

SYSTEM_PROMPT = (
    "You are a documentation assistant. You add missing module-level and function-level "
    "docstrings to Python code. "
    "Rules:\n"
    "1. Output ONLY the complete updated file content as a plain code block — no markdown, "
    "no explanations, no diffs.\n"
    "2. Preserve ALL existing code exactly as-is — only add or improve docstrings.\n"
    "3. Use Google-style docstrings (:param:, :rtype:, :returns:) for functions.\n"
    "4. Module docstrings should be 1-3 sentences describing the module's purpose.\n"
    "5. Never remove existing docstrings unless they are genuinely empty.\n"
    "6. Never touch imports, logic, or function bodies.\n"
    "7. Keep AUTHORS_LINES and version info if present.\n"
    "8. The file will be written directly to disk — output only valid Python."
)

USER_PROMPT_TEMPLATE = (
    "Add or improve docstrings for this Python file. "
    "Preserve everything exactly as-is. Output only the complete file:\n\n{code}"
)


def generate_docstrings(modules: list[str], host: str, port: str, key: str) -> dict[str, str]:
    """
    Call the Spark API for each module and return {module_name: patched_code}.

    The API key is passed as Bearer token but is NEVER printed or logged.
    Only the response content (docstring stubs) is used.
    """
    url = f"http://{host}:{port}/v1/chat/completions"
    results: dict[str, str] = {}

    for module in modules:
        # Resolve module path
        src_root = "src"
        module_path = module.replace(".", os.sep) + ".py"
        filepath = os.path.join(src_root, module_path)

        if not os.path.exists(filepath):
            filepath = os.path.join(src_root, module_path.replace(".", os.sep, 1))

        if not os.path.exists(filepath):
            print(f"# SKIP: {module} — file not found", file=sys.stderr)
            continue

        try:
            with open(filepath, encoding="utf-8") as f:
                original_code = f.read()
        except Exception as e:
            print(f"# SKIP: {module} — could not read: {e}", file=sys.stderr)
            continue

        payload = json.dumps({
            "model": "nemotron",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": USER_PROMPT_TEMPLATE.format(code=original_code[:8000])},
            ],
            "max_tokens": 4096,
            "temperature": 0.2,
        }).encode()

        # Build request — key goes in Authorization header only, never in output
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=180) as response:
                result = json.loads(response.read().decode("utf-8"))
                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                # Strip code fences if present
                content = content.strip()
                if content.startswith("```python"):
                    content = content[9:]
                elif content.startswith("```"):
                    content = content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()
                results[module] = content
                print(f"# OK: {module}", file=sys.stderr)
        except Exception as e:
            print(f"# ERROR: {module} — {e}", file=sys.stderr)
            continue

    return results


# ---------- GITHUB_OUTPUT formatting (safe — no secrets) ----------

def github_output(key: str, value: str) -> None:
    """
    Write a GITHUB_OUTPUT key=value line.
    Value is shell-escaped to prevent injection.
    Newlines in values are replaced with %0A (GitHub's line-break encoding).
    """
    safe_value = value.replace("%", "%25").replace("\n", "%0A").replace("\r", "%0D")
    print(f"{key}={safe_value}", file=sys.stdout)


# ---------- CLI ----------

def main() -> None:
    parser = argparse.ArgumentParser(description="Nemotron docstring generator")
    parser.add_argument("--scan-only", action="store_true",
                        help="Scan src/ for undocumented modules and emit MISSING_MODULES")
    parser.add_argument("--modules",
                        help="Comma-separated list of modules to generate docstrings for")
    parser.add_argument("--host", help="Spark API host")
    parser.add_argument("--port", help="Spark API port")
    parser.add_argument("--key", help="Spark API key (never printed or logged)")

    args = parser.parse_args()

    if args.scan_only:
        missing = scan_for_undocumented("src")
        if missing:
            modules_str = ",".join(missing)
            github_output("MISSING_MODULES", modules_str)
            # Also print summary to stdout (CI-visible, no secrets)
            print(f"Found {len(missing)} undocumented modules", file=sys.stderr)
        else:
            github_output("MISSING_MODULES", "")
            print("All modules documented", file=sys.stderr)
        return

    if args.modules:
        if not all([args.host, args.port, args.key]):
            print("# ERROR: --host, --port, and --key required for docstring generation",
                  file=sys.stderr)
            sys.exit(1)

        modules = [m.strip() for m in args.modules.split(",") if m.strip()]
        results = generate_docstrings(modules, args.host, args.port, args.key)

        # Output each module's result as a JSON blob to stdout
        # (picked up by the workflow step, not printed to CI log)
        output_lines: list[str] = []
        for module, patched_code in results.items():
            if patched_code:
                output_lines.append(f"# === {module} ===\n{patched_code}")

        if output_lines:
            print("\n\n".join(output_lines))
        return

    parser.print_help()


if __name__ == "__main__":
    main()
