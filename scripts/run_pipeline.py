#!/usr/bin/env python3
"""
Unified Canvas Reranker Training Pipeline
==========================================
Runs Path A (QLoRA × 2) and Path B (DPO distillation) sequentially,
benchmarks all outputs, and picks the best performer.

Usage:
    python3 scripts/run_pipeline.py --data data/rerank_train.jsonl --output /srv/spark-maker/output/pipeline

On Spark (via tmux):
    tmux new -s pipeline -d
    tmux send-keys 'cd /srv/spark-maker/gemma2b-reranker && python3 scripts/run_pipeline.py --data data/rerank_train.jsonl --output output/pipeline' Enter
"""

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum, auto
from pathlib import Path

# ── Heuristic weights (MUST match benchmark.py) ────────────────────────────────
W_TIME   = 3.0
W_TYPE   = 2.5
W_POINTS = 1.5
W_STATUS = 2.0

# ── Pipeline State ────────────────────────────────────────────────────────────
@dataclass
class PipelineState:
    phase: str = "idle"        # idle | path_a_1 | path_a_2 | path_b | benchmark | done
    step: str = ""
    output_dir: str = ""
    data_path: str = ""
    teacher_model: str = "nvidia/Gemma-4-31B-IT-NVFP4"
    student_model: str = "google/gemma-3-4b-it"
    adapter_a1: str = ""
    adapter_a2: str = ""
    adapter_b: str = ""
    best_adapter: str = ""
    best_score: float = 0.0
    error: str = ""
    started_at: str = ""
    completed_at: str = ""
    path_a1_done: bool = False
    path_a2_done: bool = False
    path_b_done: bool = False
    benchmark_done: bool = False

    def save(self, path: str):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def load(cls, path: str) -> "PipelineState":
        if Path(path).exists():
            return cls(**json.loads(Path(path).read_text()))
        return cls()

def log(msg: str, out_file=None):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    if out_file:
        with open(out_file, "a") as f:
            f.write(line + "\n")

def run_cmd(cmd: list, timeout: int = 3600, capture: bool = True) -> subprocess.CompletedProcess:
    """Run a shell command, optionally capturing output."""
    log(f"CMD: {' '.join(str(x) for x in cmd)}")
    kwargs = {"capture_output": True, "text": True, "timeout": timeout} if capture else {"timeout": timeout}
    return subprocess.run(cmd, **kwargs)

def forge_list() -> str:
    """List current forge model slots."""
    r = run_cmd(["forge", "list"], timeout=10)
    return r.stdout

def forge_load(model: str, slot: int) -> bool:
    """Load a model on the given slot."""
    log(f"LOADING {model} on slot {slot}")
    r = run_cmd(["forge", "load", model, "--slot", str(slot)], timeout=300)
    if r.returncode != 0:
        log(f"ERROR loading {model}: {r.stderr}")
        return False
    log(f"LOADED {model}")
    return True

def forge_unload(slot: int) -> bool:
    """Unload a model from the given slot."""
    log(f"UNLOADING slot {slot}")
    r = run_cmd(["forge", "unload", str(slot)], timeout=60)
    return r.returncode == 0

def generate_dpo_dataset(input_path: str, output_path: str) -> bool:
    """Export DPO format from cleaned pairwise data."""
    log(f"GENERATING DPO dataset from {input_path}")
    r = run_cmd([
        sys.executable, "scripts/collect_rerank_dataset.py",
        "export-dpo", "--input", input_path, "--output", output_path
    ], timeout=60)
    if r.returncode != 0:
        log(f"DPO export failed: {r.stderr}")
        return False
    log(f"DPO dataset written: {output_path}")
    return True

def train_qlora(data_path: str, output_path: str, tag: str) -> bool:
    """Run QLoRA fine-tune on Gemma 2B. Converts raw pairs to SFT format first."""
    log(f"TRAINING QLoRA ({tag}): {data_path} -> {output_path}")

    # Convert raw pairs to SFT format if needed
    sft_path = str(Path(output_path) / "train_sft.jsonl")
    if not Path(sft_path).exists():
        log(f"  Exporting to SFT format: {sft_path}")
        r = run_cmd([
            sys.executable, "scripts/collect_rerank_dataset.py",
            "export-sft", "--input", data_path, "--output", sft_path,
        ], timeout=60)
        if r.returncode != 0:
            log(f"  SFT export failed: {r.stderr}")
            return False

    r = run_cmd([
        sys.executable, "scripts/train_gemma2b.py",
        "--data", sft_path,
        "--output", output_path,
        "--epochs", "3",
    ], timeout=7200)
    if r.returncode != 0:
        log(f"QLoRA train failed: {r.stderr}")
        return False
    log(f"QLoRA ({tag}) DONE: {output_path}")
    return True

def run_benchmark(adapter_path: str, test_data: str, output_path: str, label: str) -> dict:
    """Run benchmark on a fine-tuned adapter. Returns results dict."""
    log(f"BENCHMARKING {label}: {adapter_path}")
    r = run_cmd([
        sys.executable, "scripts/benchmark.py",
        "--adapter", adapter_path,
        "--test-data", test_data,
        "--output", output_path,
    ], timeout=600)
    if r.returncode != 0:
        log(f"Benchmark failed: {r.stderr}")
        return {"accuracy": 0, "label": label}
    try:
        results = json.loads(Path(output_path).read_text())
        results["label"] = label
        return results
    except Exception as e:
        log(f"Could not parse benchmark results: {e}")
        return {"accuracy": 0, "label": label}

def generate_teacher_preferences(dpo_path: str, output_path: str) -> bool:
    """Use Gemma-4-31B to label DPO pairs (Path B teacher step)."""
    log(f"GENERATING teacher preferences via Gemma-4-31B")
    r = run_cmd([
        sys.executable, "scripts/generate_teacher_preferences.py",
        "--input", dpo_path,
        "--output", output_path,
        "--teacher", "nvidia/Gemma-4-31B-IT-NVFP4",
    ], timeout=7200)
    if r.returncode != 0:
        log(f"Teacher labeling failed: {r.stderr}")
        return False
    log(f"Teacher preferences written: {output_path}")
    return True

def run_dpo_training(teacher_prefs_path: str, student_model: str, output_path: str) -> bool:
    """Run DPO distillation on the student model."""
    log(f"RUNNING DPO distillation: teacher={teacher_prefs_path}")
    # Use the Path B TUI for DPO if available
    r = run_cmd([
        sys.executable, "scripts/path_b_tui.py",
        "--state", str(Path(output_path).parent / "path_b_state.json"),
        "--output", output_path,
        "--dataset", teacher_prefs_path,
        "--teacher", "nvidia/Gemma-4-31B-IT-NVFP4",
        "--student", student_model,
    ], timeout=7200)
    if r.returncode != 0:
        log(f"DPO training failed: {r.stderr}")
        return False
    log(f"DPO training DONE: {output_path}")
    return True

def main():
    p = argparse.ArgumentParser(description="Unified Canvas Reranker Training Pipeline")
    p.add_argument("--data", required=True, help="Path to rerank_train.jsonl")
    p.add_argument("--test-data", default=None, help="Path to rerank_test.jsonl (auto-find if omitted)")
    p.add_argument("--output", default="/srv/spark-maker/output/pipeline", help="Output base dir")
    p.add_argument("--teacher", default="nvidia/Gemma-4-31B-IT-NVFP4", help="Teacher model")
    p.add_argument("--student", default="google/gemma-2b-it", help="Student model")
    p.add_argument("--skip-path-a", action="store_true", help="Skip Path A QLoRA")
    p.add_argument("--skip-path-b", action="store_true", help="Skip Path B DPO")
    p.add_argument("--state", default="/tmp/pipeline_state.json", help="State file for resume")
    p.add_argument("--log", default=None, help="Log file path")
    args = p.parse_args()

    state = PipelineState.load(args.state)
    state.data_path = args.data
    state.output_dir = args.output
    state.teacher_model = args.teacher
    state.student_model = args.student

    Path(args.output).mkdir(parents=True, exist_ok=True)
    Path(args.output, "path_a1").mkdir(exist_ok=True)
    Path(args.output, "path_a2").mkdir(exist_ok=True)
    Path(args.output, "path_b").mkdir(exist_ok=True)
    Path(args.output, "benchmarks").mkdir(exist_ok=True)

    log_file = args.log or str(Path(args.output) / "pipeline.log")

    if state.started_at == "":
        state.started_at = datetime.now(timezone.utc).isoformat()
        log(f"=== PIPELINE STARTED ===", log_file)
        log(f"Output: {args.output}", log_file)
        log(f"Data: {args.data}", log_file)
        log(f"Teacher: {args.teacher} | Student: {args.student}", log_file)

    if args.test_data:
        test_data = args.test_data
    else:
        # Auto-find test data (sibling of train data)
        train_p = Path(args.data)
        test_candidate = train_p.parent / "rerank_test.jsonl"
        if test_candidate.exists():
            test_data = str(test_candidate)
        else:
            test_data = str(train_p.parent / "rerank_test.jsonl")
            log(f"WARNING: test data not found at {test_data}", log_file)

    log(f"Test data: {test_data}", log_file)

    results = {}
    errors = []

    # ── PATH A: QLoRA Fine-tune #1 ──────────────────────────────────────────
    if not args.skip_path_a and not state.path_a1_done:
        log("=== PATH A-1: QLoRA Fine-tune (standard pairs) ===", log_file)
        state.phase = "path_a_1"
        ok = train_qlora(args.data, str(Path(args.output, "path_a1")), "path_a1")
        if not ok:
            errors.append("Path A-1 failed")
            state.error = "Path A-1 failed"
        state.path_a1_done = True
        state.save(args.state)
    else:
        log("SKIPPING Path A-1 (already done or --skip-path-a)", log_file)

    # ── PATH A: QLoRA Fine-tune #2 (hard negative pairs) ────────────────────
    if not args.skip_path_a and not state.path_a2_done and not errors:
        log("=== PATH A-2: QLoRA Fine-tune (hard negative pairs) ===", log_file)
        state.phase = "path_a_2"
        hardneg_data = str(Path(args.data).parent / "rerank_hardneg_train.jsonl")
        # If hard negative split exists, train on it; else reuse main data
        data_a2 = hardneg_data if Path(hardneg_data).exists() else args.data
        ok = train_qlora(data_a2, str(Path(args.output, "path_a2")), "path_a2")
        if not ok:
            errors.append("Path A-2 failed")
            state.error = "Path A-2 failed"
        state.path_a2_done = True
        state.save(args.state)
    else:
        log("SKIPPING Path A-2 (already done, skipped, or prior error)", log_file)

    # ── PATH B: DPO Distillation ────────────────────────────────────────────
    if not args.skip_path_b and not state.path_b_done and not errors:
        log("=== PATH B: DPO Distillation with Gemma-4-31B teacher ===", log_file)
        state.phase = "path_b"

        # Step 1: Export DPO dataset
        dpo_path = str(Path(args.output) / "path_b" / "dpo_pairs.jsonl")
        ok = generate_dpo_dataset(args.data, dpo_path)
        if not ok:
            errors.append("DPO export failed")
            state.error = "DPO export failed"
            state.save(args.state)

        if ok:
            # Step 2: Teacher labeling (Gemma-4-31B)
            teacher_prefs = str(Path(args.output) / "path_b" / "teacher_prefs.jsonl")
            ok = generate_teacher_preferences(dpo_path, teacher_prefs)

        if ok:
            # Step 3: DPO training
            ok = run_dpo_training(teacher_prefs, args.student, str(Path(args.output, "path_b")))

        if not ok:
            errors.append("Path B DPO failed")
            state.error = "Path B DPO failed"

        state.path_b_done = True
        state.save(args.state)
    else:
        log(f"SKIPPING Path B (done={state.path_b_done}, skipped={args.skip_path_b}, errors={bool(errors)})", log_file)

    # ── BENCHMARK ALL ADAPTERS ───────────────────────────────────────────────
    if not state.benchmark_done and not errors:
        log("=== BENCHMARKING ALL ADAPTERS ===", log_file)
        state.phase = "benchmark"

        adapters = []
        if state.path_a1_done:
            adapters.append(("path_a1", str(Path(args.output, "path_a1"))))
        if state.path_a2_done:
            adapters.append(("path_a2", str(Path(args.output, "path_a2"))))
        if state.path_b_done:
            adapters.append(("path_b", str(Path(args.output, "path_b"))))

        for label, adapter_path in adapters:
            results_path = str(Path(args.output, "benchmarks", f"{label}_results.json"))
            res = run_benchmark(adapter_path, test_data, results_path, label)
            results[label] = res
            acc = res.get("accuracy", 0)
            log(f"  {label}: accuracy={acc}", log_file)
            if acc > state.best_score:
                state.best_score = acc
                state.best_adapter = label
                state.save(args.state)

        state.benchmark_done = True
        state.save(args.state)
    else:
        log(f"SKIPPING benchmark (done={state.benchmark_done}, errors={bool(errors)})", log_file)

    # ── FINAL REPORT ────────────────────────────────────────────────────────
    state.phase = "done"
    state.completed_at = datetime.now(timezone.utc).isoformat()
    state.save(args.state)

    log("", log_file)
    log("=" * 50, log_file)
    log(" PIPELINE COMPLETE ", log_file)
    log("=" * 50, log_file)
    for label, res in results.items():
        winner_tag = " ← BEST" if label == state.best_adapter else ""
        log(f"  {label}: accuracy={res.get('accuracy', 0):.1%}{winner_tag}", log_file)
    if errors:
        log(f" ERRORS: {errors}", log_file)
    log(f"Best adapter: {state.best_adapter} ({state.best_score:.1%})", log_file)
    log(f"Started: {state.started_at}", log_file)
    log(f"Completed: {state.completed_at}", log_file)

    report_path = Path(args.output) / "pipeline_report.json"
    report_path.write_text(json.dumps(asdict(state), indent=2))
    log(f"Full report: {report_path}", log_file)

if __name__ == "__main__":
    main()
