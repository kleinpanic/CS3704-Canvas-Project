#!/usr/bin/env python3
"""
Batch dataset generation for all teammates.

Usage:
  python3 scripts/batch_generate.py data/manifest.txt

Manifest format (one per line, # for comments):
  handle,token
  alice,vt_xxxx
  bob,vt_yyyy

The script:
  1. Parses manifest for all handles+tokens
  2. Runs generate_dataset.py for each (3 at a time to avoid Canvas rate limits)
  3. Runs convert_to_pipeline.py for each output
  4. Merges all into data/collab/all_pairs_pipeline.jsonl

Teammates only need: pip install requests && python3 batch_generate.py manifest.txt
"""

import argparse
import concurrent.futures
import os
import subprocess
import sys
import time
from dataclasses import dataclass


MAX_WORKERS = 3


@dataclass
class Teammate:
    handle: str
    token: str
    anon_output: str = ""
    pipeline_output: str = ""


def parse_manifest(path: str) -> list[Teammate]:
    teammates = []
    with open(path) as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(",", 1)
            if len(parts) != 2:
                print(f"  Warning: line {lineno}: invalid — '{line}', skipping")
                continue
            handle = parts[0].strip()
            token = parts[1].strip()
            if not handle or not token:
                print(f"  Warning: line {lineno}: empty field, skipping")
                continue
            teammates.append(Teammate(handle=handle, token=token))
    return teammates


def run_generate(tm: Teammate, repo_root: str) -> tuple[Teammate, str]:
    """Run generate_dataset.py. Returns (teammate, error_msg)."""
    anon = os.path.join(repo_root, "data", "collab", f"{tm.handle}_anon.jsonl")
    cmd = [
        sys.executable,
        os.path.join(repo_root, "scripts", "generate_dataset.py"),
        "--token", tm.token,
        "--handle", tm.handle,
        "--output", anon,
        "--seed", "42",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300, cwd=repo_root)
        if r.returncode != 0:
            return tm, f"gen failed: {r.stderr.strip()}"
        tm.anon_output = anon
        return tm, ""
    except subprocess.TimeoutExpired:
        return tm, "timed out (>300s)"
    except Exception as e:
        return tm, f"error: {e}"


def run_convert(tm: Teammate, repo_root: str) -> tuple[Teammate, str]:
    """Run convert_to_pipeline.py. Returns (teammate, error_msg)."""
    if not tm.anon_output:
        return tm, "no anon output"
    pipe = tm.anon_output.replace("_anon.jsonl", "_pipeline.jsonl")
    cmd = [
        sys.executable,
        os.path.join(repo_root, "scripts", "convert_to_pipeline.py"),
        "--input", tm.anon_output,
        "--output", pipe,
        "--source", tm.handle,
        "--seed", "42",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60, cwd=repo_root)
        if r.returncode != 0:
            return tm, f"convert failed: {r.stderr.strip()}"
        tm.pipeline_output = pipe
        return tm, ""
    except Exception as e:
        return tm, f"error: {e}"


def merge_all(teammates: list[Teammate], repo_root: str) -> int:
    """Merge all pipeline JSONLs. Returns total pair count."""
    merged = os.path.join(repo_root, "data", "collab", "all_pairs_pipeline.jsonl")
    total = 0
    with open(merged, "w") as out:
        for tm in teammates:
            if not tm.pipeline_output or not os.path.exists(tm.pipeline_output):
                continue
            with open(tm.pipeline_output) as f:
                for line in f:
                    if line.strip():
                        out.write(line)
                        total += 1
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch dataset generation from manifest.")
    parser.add_argument("manifest", help="Manifest file: handle,token per line")
    parser.add_argument("--output-dir", default="data/collab")
    parser.add_argument("--script-dir", default="scripts")
    parser.add_argument("--workers", type=int, default=MAX_WORKERS)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--merge-only", action="store_true")
    args = parser.parse_args()

    # Resolve repo root to the directory containing scripts/ (GemmaReranker/)
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    script_dir = os.path.join(repo_root, args.script_dir)
    output_dir = os.path.join(repo_root, args.output_dir)
    manifest_path = os.path.abspath(args.manifest)

    print("=== Batch Dataset Generator ===")
    print(f"Manifest: {manifest_path}")
    print(f"Repo: {repo_root}")
    print(f"Workers: {args.workers}")
    print()

    if not os.path.exists(manifest_path):
        print(f"ERROR: Manifest not found: {manifest_path}")
        sys.exit(1)

    teammates = parse_manifest(manifest_path)
    print(f"Found {len(teammates)} entries in manifest:")
    for tm in teammates:
        print(f"  {tm.handle}")

    if not teammates:
        print("ERROR: No valid handle,token lines found.")
        print("  Format: alice,vt_your_token_here")
        print("  See: data/manifest.example.txt")
        sys.exit(1)

    if args.dry_run:
        print("\n[dry-run — no execution]\n")
        return

    if args.merge_only:
        print("\n=== Merging existing outputs ===")
        total = merge_all(teammates, repo_root)
        merged = os.path.join(repo_root, "data", "collab", "all_pairs_pipeline.jsonl")
        print(f"Done. {total} pairs → {merged}")
        return

    # Step 1: generate_dataset (parallel)
    print("\n=== Step 1: generate_dataset.py ===")
    gen_results: list[tuple[Teammate, str]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(run_generate, tm, repo_root): tm for tm in teammates}
        for fut in concurrent.futures.as_completed(futures):
            tm, err = fut.result()
            gen_results.append((tm, err))
            if err:
                print(f"  ✗ {tm.handle}: {err}")
            else:
                print(f"  ✓ {tm.handle}: {tm.anon_output}")

    ok = [(tm, e) for tm, e in gen_results if not e]
    print(f"\nGen: {len(ok)}/{len(teammates)} ok")
    if len(ok) == 0:
        print("ERROR: No generation succeeded. Check tokens and Canvas connectivity.")
        sys.exit(1)

    # Step 2: convert_to_pipeline (parallel)
    print("\n=== Step 2: convert_to_pipeline.py ===")
    convert_results: list[tuple[Teammate, str]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures2 = {ex.submit(run_convert, tm, repo_root): tm
                    for tm, _ in gen_results if not _}
        for fut in concurrent.futures.as_completed(futures2):
            tm, err = fut.result()
            convert_results.append((tm, err))
            if err:
                print(f"  ✗ {tm.handle}: {err}")
            else:
                print(f"  ✓ {tm.handle}: {tm.pipeline_output}")

    ok_convert = [(tm, p) for tm, p in convert_results if not p]
    print(f"\nConvert: {len(ok_convert)}/{len(ok)} ok")

    # Step 3: merge
    print("\n=== Step 3: Merging ===")
    total = merge_all(teammates, repo_root)
    merged = os.path.join(repo_root, "data", "collab", "all_pairs_pipeline.jsonl")
    print(f"Done. {total} pairs → {merged}")

    # Summary
    print("\n=== Summary ===")
    print(f"  Entries: {len(teammates)}")
    print(f"  Generated: {len(ok)}")
    print(f"  Converted: {len(ok_convert)}")
    print(f"  Total pairs: {total}")
    all_fail = [tm for tm, e in gen_results if e] + [tm for tm, e in convert_results if e]
    if all_fail:
        for tm, err in [(tm, e) for tm, e in gen_results if e] + [(tm, e) for tm, e in convert_results if e]:
            print(f"  FAIL: {tm.handle}: {err}")


if __name__ == "__main__":
    main()