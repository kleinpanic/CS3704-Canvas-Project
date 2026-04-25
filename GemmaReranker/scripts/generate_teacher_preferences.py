#!/usr/bin/env python3
"""
Gemma 2B Reranker — Generate Teacher Preferences (Path B)
=========================================================
Uses a teacher model (Gemma-4-31B-IT-NVFP4) to generate preference labels
for DPO distillation. The teacher provides natural-language reasoning for WHY
one item is more urgent, which is more informative than heuristic labels.

Usage:
    # Option A: Via forge API on spark-maker (recommended — teacher already loaded)
    python3 scripts/generate_teacher_preferences.py \
        --input data/collab/rerank_clean.jsonl \
        --output data/rerank_dpo.jsonl \
        --teacher-endpoint http://localhost:18080/v1 \
        --api-key "dummy" \
        --batch-size 8

    # Option B: Direct vLLM on spark-maker
    ssh spark
    docker compose run --rm trainer \
        python3 /workspace/scripts/generate_teacher_preferences.py \
            --input $SPARK_MOUNT/datasets/rerank_clean.jsonl \
            --output $SPARK_MOUNT/datasets/rerank_dpo.jsonl \
            --teacher-endpoint http://localhost:8000/v1 \
            --api-key "none"

    # Option C: HuggingFace Inference API (no local GPU needed)
    python3 scripts/generate_teacher_preferences.py \
        --input data/collab/rerank_clean.jsonl \
        --output data/rerank_dpo.jsonl \
        --teacher hf-inference \
        --hf-token hf_xxxx

Output format (DPO):
    {
        "prompt": "Which item is more urgent and why?\n[Query]: What should I work on first?\nItem A: [ASGN] Activity 10 — CS3724 — Due in 24h — 2pts — OPEN\nItem B: [ASGN] HW5 — CS2505 — Due in 48h — 100pts — OPEN",
        "chosen": "Item B is more urgent because it is worth 100 points (vs 2 points) and is due in 48 hours, making it the highest-value task with a near deadline. While Activity 10 is due sooner, 2 points is negligible compared to 100 points.",
        "rejected": "Item A is more urgent because it is due sooner (24h vs 48h) and the course (CS3724) suggests higher immediate priority. The 2-point activity may be a participation check that could affect course standing."
    }
"""

import argparse
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

warnings.filterwarnings("ignore")

# ── Teacher Prompt ──────────────────────────────────────────────────────────────
TEACHER_SYSTEM_PROMPT = """You are a graduate student advisor helping a student prioritize their coursework.
For each pair of Canvas items, determine which is more urgent and explain your reasoning.
Consider: due date (closer = more urgent), point value (more points = higher stakes),
type (exams/homework > projects > readings), submission status (not submitted = must do),
and course importance for the student's major.

Be specific and concise. State which item is more urgent AND why in 2-3 sentences."""

TEACHER_USER_TEMPLATE = """Which Canvas item is more urgent?

[Query]: {query}
Item A: {item_a}
Item B: {item_b}

Which is more urgent and why?"""


# ── API Clients ─────────────────────────────────────────────────────────────────
def make_vllm_client(endpoint: str, api_key: str | None = None):
    """Returns a callable that sends a chat completion request to vLLM."""

    base = endpoint.rstrip("/")
    headers = {"Content-Type": "application/json"}
    if api_key and api_key not in ("none", "dummy", ""):
        headers["Authorization"] = f"Bearer {api_key}"

    def chat(messages: list[dict], model: str | None = None, **kwargs) -> str:
        body = {
            "model": model or "default",
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.3),
            "max_tokens": kwargs.get("max_tokens", 256),
            "stop": kwargs.get("stop"),
        }
        req = urllib.request.Request(
            f"{base}/chat/completions",
            data=json.dumps(body).encode(),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            return f"ERROR: {e}"

    return chat


def make_hf_client(token: str):
    """Returns a callable that uses HuggingFace Inference API."""
    import urllib.request

    headers = {"Authorization": f"Bearer {token}"}

    def chat(messages: list[dict], model: str = "nvidia/Gemma-4-31B-IT-NVFP4", **kwargs) -> str:
        # Convert messages to a single prompt
        prompt = "\n\n".join(
            f"{m['role'].upper()}: {m['content']}"
            for m in messages
        )
        body = {
            "inputs": prompt,
            "parameters": {
                "temperature": kwargs.get("temperature", 0.3),
                "max_new_tokens": kwargs.get("max_tokens", 256),
                "return_full_text": False,
            }
        }
        req = urllib.request.Request(
            f"https://api-inference.huggingface.co/models/{model}",
            data=json.dumps(body).encode(),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read())
            if isinstance(data, list):
                return data[0].get("generated_text", "")
            return data.get("generated_text", "")
        except Exception as e:
            return f"ERROR: {e}"

    return chat


def parse_teacher_response(response: str, item_a: dict, item_b: dict) -> tuple[str, str, str]:
    """
    Parse teacher response to extract: (winner, chosen_reason, rejected_reason)
    winner = 'A' or 'B'
    """
    text = response.strip().upper()

    # Determine winner — text is already uppercased, so only count uppercase patterns
    a_count = text.count("ITEM A")
    b_count = text.count("ITEM B")

    # Count explicit mentions
    explicit_a = any(kw in text for kw in ["ITEM A IS MORE URGENT", "ITEM A:", "CHOICE: A", "PREFER A", "A IS MORE"])
    explicit_b = any(kw in text for kw in ["ITEM B IS MORE URGENT", "ITEM B:", "CHOICE: B", "PREFER B", "B IS MORE"])

    if explicit_a and not explicit_b:
        winner = "A"
    elif explicit_b and not explicit_a:
        winner = "B"
    elif a_count > b_count:
        winner = "A"
    elif b_count > a_count:
        winner = "B"
    else:
        # Fallback: random with seed
        winner = random.choice(["A", "B"])

    # Extract reasoning (everything after "because" or after the winner declaration)
    reason_lines = []
    in_reason = False
    for line in response.strip().split("\n"):
        if "WHY" in line.upper() or "BECAUSE" in line.upper() or "REASON" in line.upper():
            in_reason = True
        if in_reason or (winner in line and ("IS MORE" in line or "MORE URGENT" in line)):
            reason_lines.append(line.strip())

    reasoning = " ".join(reason_lines) if reason_lines else response.strip()[:200]
    reasoning = reasoning.strip('"\' \n')

    loser = item_b if winner == "A" else item_a
    loser_label = "B" if winner == "A" else "A"
    loser_name = loser.get("name", loser.get("title", f"Item {loser_label}"))
    loser_type = loser.get("type", "assignment")
    loser_due = loser.get("due_display", loser.get("due_in", ""))
    loser_pts = loser.get("points", "")
    rejected_reason = (
        f"Item {loser_label} ({loser_name}) could be considered more urgent "
        f"because it is a {loser_type}"
    )
    if loser_due:
        rejected_reason += f" due {loser_due}"
    if loser_pts:
        rejected_reason += f" worth {loser_pts} points"
    rejected_reason += ", but this overlooks the stronger urgency signals favoring the other item."

    return winner, reasoning, rejected_reason


# ── Main Generation ────────────────────────────────────────────────────────────
def generate_preferences(
    input_path: str,
    output_path: str,
    teacher_endpoint: str | None = None,
    hf_token: str | None = None,
    batch_size: int = 4,
    max_workers: int = 4,
    teacher_model: str = "nvidia/Gemma-4-31B-IT-NVFP4",
    skip_existing: bool = True,
):
    print("=" * 60)
    print("Teacher Preference Generation (DPO Distillation — Path B)")
    print(f"  Input:    {input_path}")
    print(f"  Output:   {output_path}")
    print(f"  Teacher:  {teacher_endpoint or 'HuggingFace Inference API'}")
    print(f"  Workers:  {max_workers}")
    print("=" * 60)

    # Load pairs
    pairs = []
    with open(input_path) as f:
        for line in f:
            line = line.strip()
            if line:
                pairs.append(json.loads(line))
    print(f"\nLoaded {len(pairs)} pairs")

    # Set up client
    if teacher_endpoint:
        client = make_vllm_client(teacher_endpoint, "none")
        print(f"Using vLLM endpoint: {teacher_endpoint}")
    elif hf_token:
        client = make_hf_client(hf_token)
        print(f"Using HuggingFace Inference API with model: {teacher_model}")
    else:
        raise ValueError("Must specify --teacher-endpoint or --hf-token")

    # Load existing output (resume support)
    existing_output = []
    if skip_existing and Path(output_path).exists():
        with open(output_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    existing_output.append(json.loads(line))
        print(f"Resuming: {len(existing_output)} examples already exist")
        done_ids = {ex["pair_id"] for ex in existing_output}
        pairs = [p for p in pairs if p.get("id") not in done_ids]
        print(f"Remaining: {len(pairs)} pairs to process")

    all_results = list(existing_output)
    errors = 0
    t0 = time.time()

    def process_pair(pair: dict) -> dict | None:
        query = pair.get("query", "What should I work on next?")
        item_a = pair.get("item_a", {})
        item_b = pair.get("item_b", {})

        prompt_a = TEACHER_USER_TEMPLATE.format(
            query=query,
            item_a=item_a.get("serialized", str(item_a)),
            item_b=item_b.get("serialized", str(item_b)),
        )

        messages = [
            {"role": "system", "content": TEACHER_SYSTEM_PROMPT},
            {"role": "user", "content": prompt_a},
        ]

        try:
            response = client(messages, model=teacher_model, temperature=0.3, max_tokens=350)
        except Exception as e:
            return {"error": str(e), "pair_id": pair.get("id")}

        if response.startswith("ERROR:"):
            return {"error": response, "pair_id": pair.get("id")}

        winner, chosen_reason, rejected_reason = parse_teacher_response(
            response, item_a, item_b
        )

        # DPO format: "chosen" = winner's reasoning, "rejected" = loser's placeholder
        # parse_teacher_response always puts the winner's reasoning in chosen_reason.
        # rejected_reason is always the generic fallback regardless of winner.
        return {
            "pair_id": pair.get("id"),
            "prompt": prompt_a,
            "chosen": chosen_reason,    # winner's actual reasoning (A or B)
            "rejected": rejected_reason,  # "(less urgent based on teacher reasoning)"
            "winner": winner,
            "teacher_model": teacher_model,
            "teacher_raw": response,
        }

    print(f"\nProcessing {len(pairs)} pairs...")
    done = len(all_results)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_pair, p): p for p in pairs}
        for future in as_completed(futures):
            result = future.result()
            done += 1
            if result is None:
                continue
            if "error" in result and result.get("error", "").startswith("ERROR:"):
                errors += 1
                if errors <= 3:
                    print(f"  ERROR: {result['error']}")
                continue

            all_results.append(result)
            if done % 20 == 0:
                elapsed = time.time() - t0
                rate = done / elapsed
                eta = (len(pairs) - len(existing_output) - (done - len(existing_output))) / rate if rate > 0 else 0
                print(f"  Progress: {done}/{len(pairs) + len(existing_output)} | "
                      f"Rate: {rate:.1f}/s | ETA: {eta:.0f}s | Errors: {errors}")

            # Write incrementally
            if done % 50 == 0:
                _write_output(output_path, all_results)

    # Final write
    _write_output(output_path, all_results)

    elapsed = time.time() - t0
    print(f"\n{'=' * 60}")
    print(f"Done! {len(all_results)} examples in {elapsed:.0f}s")
    print(f"  Errors: {errors}")
    print(f"  Output: {output_path}")

    # Stats
    pref_a = sum(1 for r in all_results if "A IS MORE" in r.get("teacher_raw", "").upper())
    pref_b = len(all_results) - pref_a
    print(f"  Teacher preferences: A={pref_a}, B={pref_b}")
    return all_results


def _write_output(path: str, results: list[dict]):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")


# ── CLI ─────────────────────────────────────────────────────────────────────────
def parse_args():
    p = argparse.ArgumentParser(description="Generate teacher preferences for DPO distillation")
    p.add_argument("--input", required=True, help="Path to rerank_clean.jsonl")
    p.add_argument("--output", required=True, help="Output path for DPO JSONL")
    p.add_argument("--teacher-endpoint",
                   help="vLLM chat endpoint (e.g. http://localhost:18080/v1)")
    p.add_argument("--api-key", default="none",
                   help="API key for endpoint (default: none)")
    p.add_argument("--hf-token",
                   help="HuggingFace token (for HF Inference API)")
    p.add_argument("--teacher-model", default="nvidia/Gemma-4-31B-IT-NVFP4",
                   help="Model ID for HF Inference API")
    p.add_argument("--batch-size", type=int, default=4)
    p.add_argument("--workers", type=int, default=4,
                   help="Concurrent API requests (default: 4)")
    p.add_argument("--no-skip", action="store_true",
                   help="Re-process even if output already exists")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    generate_preferences(
        input_path=args.input,
        output_path=args.output,
        teacher_endpoint=args.teacher_endpoint,
        hf_token=args.hf_token,
        batch_size=args.batch_size,
        max_workers=args.workers,
        teacher_model=args.teacher_model,
        skip_existing=not args.no_skip,
    )
