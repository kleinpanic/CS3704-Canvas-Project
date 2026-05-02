"""
prep_dataset_release.py — produce the HF-release artifact for the
Canvas preference dataset, applying the recommendations from
.planning/research/DATASET-AUDIT.md:

  1. Dedup: drop the data-prep 3× hard-neg oversample. The published
     artifact is the underlying 1,347-pair file (1,109 standard + 238
     hard_negative unique pairs) — downstream consumers can reapply
     oversampling if they want to.
  2. Add preference_signal_present: bool — flags the 12.9 % of records
     where chosen and rejected both conclude the same Item is more
     urgent (no preference signal for DPO to fit). Detected by
     comparing the primary "Item X is the/more/most/..." assertion
     between the two responses.
  3. Sanitize "Ut Prosim" titles (Virginia Tech motto) in 2 records to
     a generic descriptor. Preserves dataset semantics; removes the
     institutional identifier.

Output: data/release/canvas-preference-2k.jsonl — single split
suitable for HF datasets push.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

SOURCE = Path("data/dpo_train.jsonl")
OUT_DIR = Path("data/release")
OUT_PATH = OUT_DIR / "canvas-preference-2k.jsonl"

ASSERT_RE = re.compile(
    r"\bItem\s+([AB])\s+is\s+(?:the|a)?\s*"
    r"(?:more|higher|most|highest|top|primary|absolute|clear|immediate|critical)",
    re.IGNORECASE,
)
UT_PROSIM_RE = re.compile(r"Ut\s+Prosim", re.IGNORECASE)
UT_PROSIM_REPLACEMENT = "Service requirement"


def primary_pick(text: str) -> str | None:
    matches = ASSERT_RE.findall(text)
    if not matches:
        return None
    return Counter(matches).most_common(1)[0][0]


def sanitize_text(text: str) -> str:
    return UT_PROSIM_RE.sub(UT_PROSIM_REPLACEMENT, text)


def main():
    records = [json.loads(l) for l in SOURCE.read_text().splitlines() if l.strip()]
    print(f"[load] {len(records)} records from {SOURCE}")

    seen = set()
    unique = []
    for r in records:
        key = (r["prompt"], r["chosen"], r["rejected"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)
    print(f"[dedup] {len(unique)} unique records (dropped {len(records) - len(unique)} duplicates)")

    n_pref_signal = 0
    n_no_signal = 0
    n_unparseable = 0
    n_sanitized = 0
    out_records = []
    for r in unique:
        chosen_pick = primary_pick(r["chosen"])
        rejected_pick = primary_pick(r["rejected"])
        if chosen_pick is None or rejected_pick is None:
            preference_signal_present = None
            n_unparseable += 1
        elif chosen_pick != rejected_pick:
            preference_signal_present = True
            n_pref_signal += 1
        else:
            preference_signal_present = False
            n_no_signal += 1

        out = {
            "prompt": sanitize_text(r["prompt"]),
            "chosen": sanitize_text(r["chosen"]),
            "rejected": sanitize_text(r["rejected"]),
            "pair_type": r["pair_type"],
            "preference_signal_present": preference_signal_present,
        }
        if any(UT_PROSIM_RE.search(t) for t in (r["prompt"], r["chosen"], r["rejected"])):
            n_sanitized += 1
        out_records.append(out)

    pt_counter = Counter(r["pair_type"] for r in out_records)
    print(f"[label] preference_signal_present:")
    print(f"        True (clean DPO contrast):   {n_pref_signal}")
    print(f"        False (no signal):           {n_no_signal}")
    print(f"        None (unparseable):          {n_unparseable}")
    print(f"[type ] pair_type:                  {dict(pt_counter)}")
    print(f"[clean] records with 'Ut Prosim' sanitized: {n_sanitized}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text("\n".join(json.dumps(r) for r in out_records) + "\n")
    print(f"[wrote] {OUT_PATH} ({OUT_PATH.stat().st_size // 1024} KB, {len(out_records)} records)")


if __name__ == "__main__":
    main()
