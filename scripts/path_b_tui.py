#!/usr/bin/env python3
"""
Path B — DPO Distillation TUI
=============================
Textual TUI for running the full Path B DPO distillation pipeline on Spark DGX.

Usage:
    python3 scripts/path_b_tui.py [--state state.json]

On Spark (spark-maker):
    docker compose run --rm trainer \
        python3 /workspace/scripts/path_b_tui.py \
            --state /workspace/gemma2b-reranker/path_b_state.json \
            --output /workspace/gemma2b-reranker/output

Pipeline steps:
    1. [OPTIONAL] forge unload 0          — free Nemotron memory
    2. forge load Gemma-4-31B-IT-NVFP4   — load teacher model
    3. Generate teacher preferences        — label pairs with Gemma-4-31B
    4. forge load Gemma-2B                — load student model
    5. DPO train student                  — train on synthetic preferences
    6. [OPTIONAL] forge load Nemotron      — restart Nemotron inference
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from enum import Enum, auto
from pathlib import Path

try:
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.widgets import (
        Button, Header, Footer, Static, Log, ProgressBar, RichLog
    )
    from textual.containers import Container, ScrollableContainer
    from textual import events
except ImportError:
    print("ERROR: Textual not installed. Run: pip install textual")
    sys.exit(1)


# ── State ────────────────────────────────────────────────────────────────────

class Step(Enum):
    IDLE = auto()
    UNLOAD_NEMOTRON = auto()
    LOAD_TEACHER = auto()
    GENERATE_PREFERENCES = auto()
    LOAD_STUDENT = auto()
    DPO_TRAIN = auto()
    RESTART_NEMOTRON = auto()
    DONE = auto()
    ERROR = auto()


@dataclass
class PipelineState:
    """Persistent state for resumable pipeline runs."""
    step: str = "IDLE"
    output_dir: str = ""
    teacher_model: str = "nvidia/Gemma-4-31B-IT-NVFP4"
    student_model: str = "google/gemma-4-2b-it"
    dataset_path: str = ""
    dpo_dataset_path: str = ""
    adapter_path: str = ""
    error: str = ""
    started_at: str = ""
    completed_at: str = ""
    generation_progress: int = 0
    generation_total: int = 0
    train_progress: float = 0.0
    # Forge slot tracking
    nemotron_slot: int = 0
    teacher_slot: int = 0
    student_slot: int = 0
    # Resume
    generation_done: bool = False
    training_done: bool = False
    restart_done: bool = False

    def save(self, path: str):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def load(cls, path: str) -> "PipelineState":
        if Path(path).exists():
            data = json.loads(Path(path).read_text())
            return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        return cls()


# ── Subprocess Helpers ─────────────────────────────────────────────────────────

def run_cmd(cmd: list[str], timeout: int = 300, capture: bool = True) -> subprocess.CompletedProcess:
    """Run a shell command, raise on failure."""
    print(f"[CMD] {' '.join(cmd[:4])}...")
    result = subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
        timeout=timeout,
        cwd="/srv/spark-maker",
    )
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\nSTDOUT: {result.stdout[-500:]}\nSTDERR: {result.stderr[-500:]}")
    return result


def forge_load(model: str, slot: int = 0) -> bool:
    """Load a model into a vLLM slot via forge."""
    result = subprocess.run(
        ["forge", "load", model, "--slot", str(slot)],
        capture_output=True, text=True, timeout=120,
    )
    return result.returncode == 0


def forge_unload(slot: int = 0) -> bool:
    """Unload a model from a vLLM slot."""
    result = subprocess.run(
        ["forge", "unload", str(slot)],
        capture_output=True, text=True, timeout=60,
    )
    return result.returncode == 0


def forge_status() -> dict:
    """Get forge status as dict."""
    result = subprocess.run(["forge", "status"], capture_output=True, text=True, timeout=15)
    if result.returncode != 0:
        return {}
    # Parse the forge status table
    lines = result.stdout.strip().split("\n")
    status = {}
    for line in lines:
        if "slot0" in line.lower() or "slot1" in line.lower():
            parts = line.split()
            if len(parts) >= 2:
                status[parts[0].lower().replace("slot0", "slot0").replace("slot1", "slot1")] = " ".join(parts[1:])
    return status


# ── Preference Generation ─────────────────────────────────────────────────────

def generate_preferences(
    input_path: str,
    output_path: str,
    endpoint: str = "http://localhost:8000/v1",
    batch_size: int = 8,
    teacher_model: str = "nvidia/Gemma-4-31B-IT-NVFP4",
    progress_callback=None,
) -> int:
    """
    Generate teacher preferences using the loaded vLLM model.
    Returns the number of pairs processed.
    """
    # Build the generation command
    # Uses generate_teacher_preferences.py with spark vLLM endpoint
    cmd = [
        sys.executable,
        "/workspace/scripts/generate_teacher_preferences.py",
        "--input", input_path,
        "--output", output_path,
        "--teacher-endpoint", endpoint,
        "--teacher-model", teacher_model,
        "--batch-size", str(batch_size),
        "--workers", "4",
    ]
    # Run in docker on spark-maker
    docker_cmd = [
        "docker", "compose", "run", "--rm", "-T",
        "trainer",
        "python3", "/workspace/scripts/generate_teacher_preferences.py",
        "--input", input_path,
        "--output", output_path,
        "--teacher-endpoint", "http://host.docker.internal:8000/v1",
        "--teacher-model", teacher_model,
        "--batch-size", str(batch_size),
        "--workers", "4",
    ]
    result = subprocess.run(
        docker_cmd,
        capture_output=True, text=True, timeout=3600,
        cwd="/srv/spark-maker",
    )
    if result.returncode != 0:
        raise RuntimeError(f"Preference generation failed:\n{result.stderr[-1000:]}")
    # Parse output for progress
    lines = result.stdout.strip().split("\n")
    for line in lines:
        if "Progress:" in line or "Done!" in line:
            if progress_callback:
                progress_callback(line)
    return len([l for l in lines if l.strip()])


def run_dpo_training(
    student_model: str,
    dpo_dataset: str,
    output_dir: str,
    epochs: int = 3,
    progress_callback=None,
) -> str:
    """Run DPO training via TRL DPOTrainer. Returns path to trained adapter."""
    import json, torch
    from pathlib import Path
    from datasets import Dataset
    from transformers import AutoTokenizer, AutoModelForCausalLM, TrainingArguments
    from peft import LoraConfig, get_peft_model, TaskType
    from trl import DPOTrainer, DPOConfig

    hf_token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN") or ""
    tok_kwargs = {"trust_remote_code": True}
    if hf_token:
        tok_kwargs["token"] = hf_token

    if progress_callback:
        progress_callback(f"Loading tokenizer: {student_model}")
    tokenizer = AutoTokenizer.from_pretrained(student_model, **tok_kwargs)
    if tokenizer.pad_token is None:
        tokenizer.add_special_tokens({"pad_token": "[PAD]"})

    # Load DPO dataset
    pairs = []
    with open(dpo_dataset) as f:
        for line in f:
            line = line.strip()
            if line:
                pairs.append(json.loads(line))
    n_eval = max(20, int(len(pairs) * 0.1))
    train_ds = Dataset.from_list(pairs[:-n_eval])
    eval_ds  = Dataset.from_list(pairs[-n_eval:])
    if progress_callback:
        progress_callback(f"DPO dataset: {len(train_ds)} train / {len(eval_ds)} eval pairs")

    # Load student model
    model_kwargs = {"device_map": "auto", "trust_remote_code": True, "torch_dtype": torch.bfloat16}
    if hf_token:
        model_kwargs["token"] = hf_token
    try:
        import bitsandbytes  # noqa
        from transformers import BitsAndBytesConfig
        model_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True,
        )
        del model_kwargs["torch_dtype"]
        if progress_callback:
            progress_callback("Loading student in 4-bit QLoRA mode")
    except ImportError:
        if progress_callback:
            progress_callback("bitsandbytes not available — loading student in BF16")

    model = AutoModelForCausalLM.from_pretrained(student_model, **model_kwargs)
    if len(tokenizer) > model.config.vocab_size:
        model.resize_token_embeddings(len(tokenizer))

    lora_cfg = LoraConfig(
        task_type=TaskType.CAUSAL_LM, r=16, lora_alpha=32, lora_dropout=0.05, bias="none",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    )
    model = get_peft_model(model, lora_cfg)
    model.config.use_cache = False
    model.print_trainable_parameters()

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    dpo_config = DPOConfig(
        output_dir=str(out),
        num_train_epochs=epochs,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=16,
        learning_rate=5e-5,
        bf16=True,
        warmup_steps=10,
        max_length=512,           # longer than SFT — DPO pairs include prompt + chosen/rejected
        max_prompt_length=256,
        logging_steps=5,
        eval_strategy="steps",
        eval_steps=50,
        save_strategy="no",
        report_to="none",
        gradient_checkpointing=True,
        optim="paged_adamw_32bit" if "bitsandbytes" in sys.modules else "adamw_torch",
    )

    trainer = DPOTrainer(
        model=model,
        args=dpo_config,
        train_dataset=train_ds,
        eval_dataset=eval_ds,
        processing_class=tokenizer,
    )

    if progress_callback:
        progress_callback("Starting DPO training...")
    trainer.train()

    trainer.save_model(str(out))
    tokenizer.save_pretrained(str(out))
    if progress_callback:
        progress_callback(f"DPO training complete. Adapter saved to {out}")
    return str(out)


# ── Textual App ────────────────────────────────────────────────────────────────

STEPS = [
    (Step.IDLE,              "Ready",                     "Configure and start the pipeline"),
    (Step.UNLOAD_NEMOTRON,   "Unloading Nemotron",         "Stopping Nemotron to free ~58GB"),
    (Step.LOAD_TEACHER,      "Loading Gemma-4-31B Teacher","Loading teacher model into vLLM slot"),
    (Step.GENERATE_PREFERENCES, "Generating Preferences",  "Labeling pairs with teacher model"),
    (Step.LOAD_STUDENT,      "Loading Gemma-2B Student",   "Preparing student model for DPO"),
    (Step.DPO_TRAIN,         "DPO Training",               "Training student on synthetic preferences"),
    (Step.RESTART_NEMOTRON,  "Restarting Nemotron",         "Reloading Nemotron for inference"),
    (Step.DONE,              "Complete",                    "Pipeline finished successfully"),
    (Step.ERROR,             "Error",                      "Pipeline encountered an error"),
]


class PipelineApp(App):
    CSS = """
Screen {
    background: $surface;
}

#header {
    height: 3;
    background: $primary;
    color: $text;
    dock: top;
}

#log-container {
    height: 1fr;
    border: solid $primary;
    margin: 1 2;
}

#log {
    height: 100%;
    border: none;
    background: $surface;
}

#progress-area {
    height: 3;
    margin: 1 2;
}

#controls {
    height: 5;
    dock: bottom;
    background: $surface;
    align: center middle;
}

#status-bar {
    height: 1;
    dock: bottom;
    background: $primary;
    color: $text;
}

Button {
    margin: 0 2;
}

.button-start {
    background: $success;
    color: $text;
}

.button-stop {
    background: $error;
    color: $text;
}

.button-resume {
    background: $warning;
    color: $text;
}
"""

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "resume", "Resume"),
        Binding("s", "start", "Start"),
        Binding("c", "clear_log", "Clear Log"),
    ]

    def __init__(self, state_path: str, output_dir: str, dataset_path: str):
        super().__init__()
        self.state_path = state_path
        self.output_dir = Path(output_dir)
        self.dataset_path = dataset_path
        self.state = PipelineState.load(state_path)
        self.state.output_dir = str(self.output_dir)
        self.state.dataset_path = dataset_path
        self.running = False
        self._log_lines = []
        self._progress_pct = 0

    def compose(self) -> ComposeResult:
        yield Header(id="header")
        yield Container(
            RichLog(id="log", highlight=True, auto_scroll=True),
            id="log-container",
        )
        yield Container(
            ProgressBar(id="progress", total=100),
            Static("", id="progress-label"),
            id="progress-area",
        )
        yield Container(
            Button("Start", id="btn-start", variant="success"),
            Button("Resume", id="btn-resume", variant="warning", disabled=False),
            Button("Stop", id="btn-stop", variant="error", disabled=True),
            Button("Clear Log", id="btn-clear"),
            Button("Quit", id="btn-quit", variant="primary"),
            id="controls",
        )
        yield Static("", id="status-bar")

    def on_mount(self):
        self.title = "Path B — DPO Distillation TUI"
        self.sub_title = f"State: {self.state.step} | Output: {self.output_dir}"
        self._update_status(f"Loaded state: {self.state.step}")
        self._update_progress(0, "")
        if self.state.step == "DONE":
            self._log("✓ Pipeline was previously completed. Press Resume to review logs.")
        elif self.state.step == "ERROR":
            self._log(f"✗ Previous run error: {self.state.error}")
        self.refresh_bindings()

    def _log(self, msg: str):
        self._log_lines.append(msg)
        log_widget = self.query_one("#log", RichLog)
        log_widget.write(msg)

    def _update_progress(self, pct: int, label: str):
        self._progress_pct = pct
        pb = self.query_one("#progress", ProgressBar)
        pb.update(progress=pct)
        lbl = self.query_one("#progress-label", Static)
        lbl.update(label)

    def _update_status(self, msg: str):
        sb = self.query_one("#status-bar", Static)
        sb.update(f"  {datetime.now().strftime('%H:%M:%S')}  {msg}")

    def _set_step(self, step: Step, label: str):
        self.state.step = step.name
        self.state.save(self.state_path)
        self._update_status(f"[{step.name}] {label}")

    def _run_async(self, coro):
        """Run an async task."""
        async def wrapper():
            try:
                await coro()
            except Exception as e:
                self._log(f"\n[ERROR] {e}")
                self.state.error = str(e)
                self.state.step = Step.ERROR.name
                self.state.save(self.state_path)
                self.running = False
                self._update_buttons("error")
        asyncio.create_task(wrapper())

    async def _run_pipeline(self):
        """Main pipeline run — runs in async context."""
        self.running = True
        self._update_buttons("running")
        self._log(f"\n{'='*60}")
        self._log(f"Path B DPO Distillation Pipeline")
        self._log(f"Started: {datetime.now().isoformat()}")
        self._log(f"Output: {self.output_dir}")
        self._log(f"Dataset: {self.dataset_path}")
        self._log(f"{'='*60}\n")

        output_path = Path(self.state_path).parent

        try:
            # ── Step 1: Unload Nemotron ────────────────────────────────────
            if not self.state.restart_done:
                self._set_step(Step.UNLOAD_NEMOTRON, "Unloading Nemotron...")
                self._log("[1/6] Unloading Nemotron from slot 0...")
                self._log("  (Freeing ~58GB for teacher + student models)")
                ok = forge_unload(slot=0)
                if not ok:
                    self._log("  WARNING: forge unload failed, continuing anyway...")
                self._log(f"  Done. Slot 0 free.")
                self.state.save(self.state_path)
            else:
                self._log("[1/6] Skipping (already done)")

            # ── Step 2: Load Teacher ──────────────────────────────────────────
            self._set_step(Step.LOAD_TEACHER, "Loading Gemma-4-31B Teacher...")
            self._log(f"\n[2/6] Loading teacher model: {self.state.teacher_model}")
            self._log("  Loading into slot 0...")
            ok = forge_load(self.state.teacher_model, slot=0)
            if not ok:
                raise RuntimeError(f"Failed to load {self.state.teacher_model}")
            self._log("  Teacher model loaded ✓")
            self.state.save(self.state_path)

            # ── Step 3: Generate Preferences ──────────────────────────────────
            self._set_step(Step.GENERATE_PREFERENCES, "Generating Teacher Preferences...")
            self._log(f"\n[3/6] Generating teacher preferences...")
            dpo_path = str(output_path / "rerank_dpo.jsonl")
            self.state.dpo_dataset_path = dpo_path

            self._log(f"  Input:  {self.dataset_path}")
            self._log(f"  Output: {dpo_path}")
            self._log(f"  Teacher endpoint: http://localhost:8000/v1")

            # Check if already done (resume)
            if self.state.generation_done and Path(dpo_path).exists():
                self._log("  Preferences already generated, skipping...")
            else:
                n_pairs = generate_preferences(
                    self.dataset_path, dpo_path,
                    endpoint="http://localhost:8000/v1",
                    progress_callback=lambda l: self._log(f"  {l}"),
                )
                self.state.generation_done = True
                self._log(f"  Generated {n_pairs} preference pairs ✓")
            self._update_progress(50, "[3/6] Preferences generated")
            self.state.save(self.state_path)

            # ── Step 4: DPO Training ───────────────────────────────────────────
            self._set_step(Step.DPO_TRAIN, "Running DPO Training...")
            self._log(f"\n[4/6] DPO training student: {self.state.student_model}")
            adapter_dir = str(output_path / "gemma2b-dpo")
            self.state.adapter_path = adapter_dir
            self.output_dir.mkdir(parents=True, exist_ok=True)

            if self.state.training_done and Path(adapter_dir).exists():
                self._log("  Training already done, skipping...")
            else:
                run_dpo_training(
                    self.state.student_model,
                    dpo_path,
                    adapter_dir,
                    progress_callback=lambda l: self._log(f"  {l}"),
                )
                self.state.training_done = True
                self._log(f"  Training complete. Adapter: {adapter_dir}")
            self._update_progress(90, "[4/6] Training complete")
            self.state.save(self.state_path)

            # ── Step 5: Restart Nemotron ─────────────────────────────────────
            self._set_step(Step.RESTART_NEMOTRON, "Restarting Nemotron...")
            self._log(f"\n[5/6] Restarting Nemotron inference...")
            nem_model = "nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-NVFP4"
            ok = forge_load(nem_model, slot=0)
            if not ok:
                self._log("  WARNING: Failed to restart Nemotron. Run manually:")
                self._log(f"    forge load {nem_model} --slot 0")
            else:
                self._log("  Nemotron restarted ✓")
            self.state.restart_done = True
            self.state.save(self.state_path)

            # ── Done ─────────────────────────────────────────────────────────
            self.state.completed_at = datetime.now(timezone.utc).isoformat()
            self._set_step(Step.DONE, "Pipeline complete!")
            self._log(f"\n{'='*60}")
            self._log(f"✓ Pipeline complete at {self.state.completed_at}")
            self._log(f"  Adapter: {self.state.adapter_path}")
            self._log(f"  DPO dataset: {self.state.dpo_dataset_path}")
            self._log(f"  State saved to: {self.state_path}")
            self._log(f"{'='*60}")
            self._update_progress(100, "✓ Complete")

        except Exception as e:
            self._log(f"\n[ERROR] {e}")
            self.state.error = str(e)
            self._set_step(Step.ERROR, f"Error: {e}")
            raise

        finally:
            self.running = False
            self._update_buttons("idle")

    def _update_buttons(self, mode: str):
        btn_start = self.query_one("#btn-start", Button)
        btn_resume = self.query_one("#btn-resume", Button)
        btn_stop = self.query_one("#btn-stop", Button)
        if mode == "running":
            btn_start.disabled = True
            btn_resume.disabled = True
            btn_stop.disabled = False
        elif mode == "error":
            btn_start.disabled = True
            btn_resume.disabled = False
            btn_stop.disabled = True
        else:
            btn_start.disabled = False
            btn_resume.disabled = (self.state.step == "DONE")
            btn_stop.disabled = True

    def action_start(self):
        if self.running:
            self._log("Pipeline already running.")
            return
        if not self.dataset_path:
            self._log("ERROR: --dataset required")
            return
        self.state.started_at = datetime.now(timezone.utc).isoformat()
        self.state.step = Step.UNLOAD_NEMOTRON.name
        self.state.error = ""
        self.state.save(self.state_path)
        self._run_async(self._run_pipeline())

    def action_resume(self):
        self._log("\n[RESUME] Re-running from last saved state...")
        self._run_async(self._run_pipeline())

    def action_quit(self):
        self.exit()

    def action_clear_log(self):
        log_widget = self.query_one("#log", RichLog)
        log_widget.clear()

    def on_button_pressed(self, event: events.Click):
        btn_id = event.button.id
        if btn_id == "btn-start":
            self.action_start()
        elif btn_id == "btn-resume":
            self.action_resume()
        elif btn_id == "btn-quit":
            self.action_quit()
        elif btn_id == "btn-clear":
            self.action_clear_log()
        elif btn_id == "btn-stop":
            self._log("[STOP] Not implemented — kill the process manually if needed.")


# ── CLI ────────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Path B DPO Distillation TUI")
    p.add_argument("--state", default="/tmp/path_b_state.json",
                   help="Path to state file (for resume support)")
    p.add_argument("--output", default="/srv/spark-maker/output/gemma2b-reranker",
                   help="Output directory for adapter and results")
    p.add_argument("--dataset", default="/srv/spark-maker/datasets/rerank_clean.jsonl",
                   help="Path to cleaned + merged pairwise dataset")
    p.add_argument("--teacher", default="nvidia/Gemma-4-31B-IT-NVFP4",
                   help="Teacher model ID")
    p.add_argument("--student", default="google/gemma-4-2b-it",
                   help="Student model ID")
    p.add_argument("--headless", action="store_true",
                   help="Run DPO training without TUI (for subprocess use)")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.headless:
        print(f"[headless] Running DPO training: student={args.student}")
        adapter_path = run_dpo_training(
            student_model=args.student,
            dpo_dataset=args.dataset,
            output_dir=args.output,
            progress_callback=lambda msg: print(f"[headless] {msg}"),
        )
        print(f"[headless] Adapter saved: {adapter_path}")
    else:
        app = PipelineApp(
            state_path=args.state,
            output_dir=args.output,
            dataset_path=args.dataset,
        )
        app.run()
