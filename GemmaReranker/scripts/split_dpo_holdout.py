"""
split_dpo_holdout.py — reconstruct an item-ID-level held-out split from
data/dpo_train.jsonl, since the original 827-pair test partition was lost
in the 2026-05-01 workspace wipe.

Item identity is reconstructed from the prompt: every prompt embeds two
"[TYPE] Title @COURSE STATUS Npts" item descriptors. The (TYPE, Title,
COURSE) triple is treated as a stable item identifier; STATUS and points
shift over time and across pairs but TYPE+Title+COURSE pin the underlying
Canvas item.

Split rule (strict item-disjoint, seed 42):
  - Collect all unique items
  - Shuffle items deterministically (seed 42)
  - First test_frac of items → test_items
  - Pairs where BOTH items ∈ test_items → test partition
  - Pairs where BOTH items ∈ train_items → train partition
  - Pairs that span the boundary (one item in each set) → DISCARDED to
    eliminate item-leak risk

This is stricter than the original collect_rerank_dataset.py cmd_split
(which routed span pairs to train). The original was acceptable for v1
because a held-out test pair containing a single train-item was still
better than nothing; the v3 retrain explicitly aims for zero item overlap
at the test-pair level so the held-out validation cannot be contaminated
by item-memorization.

Tradeoff: smaller test partition than the test_frac suggests, but a clean
held-out signal.
"""
from __future__ import annotations

import json
import random
import re
from pathlib import Path

DATA_PATH = Path("data/dpo_train.jsonl")
TRAIN_OUT = Path("data/dpo_train_v3.jsonl")
TEST_OUT = Path("data/dpo_test_v3.jsonl")
SEED = 42
# Bumped from 0.20 → 0.30: at 0.20 the strict-disjoint test partition has
# only 111 pairs and zero hard-negatives. At 0.30 we get 148 test pairs,
# still zero hard-neg (hard-negs concentrate among similar-item-pairs that
# don't co-partition under random item-level splits) but train retains 477
# hard-neg records — DPO can still learn the hard-neg signal at training,
# just not be tested on hard-neg pairs at validation. Documented as a known
# limitation in §6.5 of the paper.
TEST_FRAC = 0.30

ITEM_LINE = re.compile(
    r"^Item [AB]:\s*(\[[^\]]+\])\s*(.+?)\s*(@COURSE\w+)\s",
    re.MULTILINE,
)


def parse_items(prompt: str) -> tuple[tuple[str, str, str], tuple[str, str, str]]:
    matches = ITEM_LINE.findall(prompt)
    if len(matches) != 2:
        raise ValueError(f"Expected 2 item lines, got {len(matches)} in prompt:\n{prompt[:200]}")
    a, b = matches
    return tuple(a), tuple(b)


def main():
    assert DATA_PATH.exists(), f"missing {DATA_PATH}"
    records = [json.loads(l) for l in DATA_PATH.read_text().splitlines() if l.strip()]
    print(f"[load] {len(records)} records from {DATA_PATH}")

    parsed = []
    item_to_id = {}
    for i, rec in enumerate(records):
        a_key, b_key = parse_items(rec["prompt"])
        for k in (a_key, b_key):
            if k not in item_to_id:
                item_to_id[k] = len(item_to_id)
        parsed.append((item_to_id[a_key], item_to_id[b_key], rec))

    n_items = len(item_to_id)
    print(f"[items] {n_items} unique items detected")

    rng = random.Random(SEED)
    item_ids = list(range(n_items))
    rng.shuffle(item_ids)
    n_test = max(1, int(n_items * TEST_FRAC))
    test_items = set(item_ids[:n_test])
    train_items = set(item_ids[n_test:])
    print(f"[split] test_items={len(test_items)} train_items={len(train_items)} (seed={SEED}, test_frac={TEST_FRAC})")

    train_pairs, test_pairs, span_count = [], [], 0
    for ia, ib, rec in parsed:
        both_train = ia in train_items and ib in train_items
        both_test = ia in test_items and ib in test_items
        if both_train:
            train_pairs.append((ia, ib, rec))
        elif both_test:
            test_pairs.append((ia, ib, rec))
        else:
            span_count += 1

    rng.shuffle(train_pairs)
    rng.shuffle(test_pairs)

    train_item_set = set()
    for ia, ib, _ in train_pairs:
        train_item_set.add(ia); train_item_set.add(ib)
    test_item_set = set()
    for ia, ib, _ in test_pairs:
        test_item_set.add(ia); test_item_set.add(ib)
    leak = train_item_set & test_item_set

    print(f"[split] train_pairs={len(train_pairs)} test_pairs={len(test_pairs)} discarded_span_pairs={span_count}")
    print(f"[leak] {len(leak)} items appear in both partitions (target: 0)")
    assert not leak, f"item leak between partitions: {leak}"

    train_pairs = [r for _, _, r in train_pairs]
    test_pairs = [r for _, _, r in test_pairs]

    pt_counts = lambda pairs, k: sum(1 for r in pairs if r.get("pair_type") == k)
    print(f"[train] hard_negative={pt_counts(train_pairs,'hard_negative')} standard={pt_counts(train_pairs,'standard')}")
    print(f"[test ] hard_negative={pt_counts(test_pairs,'hard_negative')} standard={pt_counts(test_pairs,'standard')}")

    TRAIN_OUT.write_text("\n".join(json.dumps(r) for r in train_pairs) + "\n")
    TEST_OUT.write_text("\n".join(json.dumps(r) for r in test_pairs) + "\n")
    print(f"[wrote] {TRAIN_OUT} ({TRAIN_OUT.stat().st_size//1024} KB)")
    print(f"[wrote] {TEST_OUT}  ({TEST_OUT.stat().st_size//1024} KB)")


if __name__ == "__main__":
    main()
