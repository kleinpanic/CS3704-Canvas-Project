import json
import sys
from pathlib import Path


def validate_dpo_records(records: list[dict]) -> int:
    """Validate DPO records schema. Returns zero-grad pair count. Raises on data errors."""
    zero_grad = 0
    for i, r in enumerate(records):
        for key in ("prompt", "chosen", "rejected"):
            if not isinstance(r.get(key), str) or not r[key]:
                raise ValueError(f"Record {i}: missing or empty '{key}'")
        pair_type = r.get("pair_type", "")
        if pair_type not in ("hard_negative", "standard"):
            raise ValueError(f"Record {i}: invalid pair_type '{pair_type}'")
        if r["chosen"] == r["rejected"]:
            zero_grad += 1
    print(
        f"WARNING: {zero_grad} zero-gradient pairs (chosen==rejected) "
        f"— expected 2 per D-11, not filtered."
    )
    if zero_grad > 5:
        raise ValueError(f"Too many zero-gradient pairs ({zero_grad}); likely a data error")
    return zero_grad


def format_for_dpo(record: dict) -> dict:
    """Extract TRL-schema fields plus pair_type. Strips training metadata."""
    return {
        "prompt": record["prompt"],
        "chosen": record["chosen"],
        "rejected": record["rejected"],
        "pair_type": record.get("pair_type", "standard"),
    }


def join_pair_types(tl_records: list[dict], dp_records: list[dict]) -> list[dict]:
    """Join pair_type from dpo_pairs onto teacher_labels via (pair_id/id, prompt[:60])."""
    lookup = {(r["id"], r["prompt"][:60]): r["pair_type"] for r in dp_records}
    result = []
    unmatched = 0
    for r in tl_records:
        key = (r["pair_id"], r["prompt"][:60])
        pair_type = lookup.get(key)
        if pair_type is None:
            unmatched += 1
            pair_type = "standard"
        result.append({**r, "pair_type": pair_type})
    if unmatched:
        print(f"WARNING: {unmatched} teacher_labels records had no pair_type match in dpo_pairs")
    return result


def oversample_hard_negatives(dataset, multiplier: int = 3):
    """3x oversample hard_negative rows via concatenate_datasets (DPO-05, not WPO)."""
    from datasets import concatenate_datasets

    hard = dataset.filter(lambda x: x["pair_type"] == "hard_negative")
    standard = dataset.filter(lambda x: x["pair_type"] != "hard_negative")
    oversampled = concatenate_datasets([hard] * multiplier + [standard])
    return oversampled.shuffle(seed=42)


def build_dpo_dataset(
    tl_path: str = "/tmp/canvas-review/GemmaReranker/data/teacher_labels.jsonl",
    dp_path: str = "/tmp/canvas-review/GemmaReranker/data/dpo_pairs.jsonl",
    output_path: str = None,
    multiplier: int = 3,
) -> None:
    from datasets import Dataset

    if output_path is None:
        output_path = str(Path(__file__).parent.parent / "data" / "dpo_train.jsonl")

    tl_records = [json.loads(l) for l in open(tl_path)]
    dp_records = [json.loads(l) for l in open(dp_path)]

    joined = join_pair_types(tl_records, dp_records)
    formatted = [format_for_dpo(r) for r in joined]
    validate_dpo_records(formatted)

    dataset = Dataset.from_list(formatted)
    dataset = oversample_hard_negatives(dataset, multiplier=multiplier)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for record in dataset:
            f.write(json.dumps(record) + "\n")

    print(f"Written {len(dataset)} records to {output_path}")


if __name__ == "__main__":
    tl = sys.argv[1] if len(sys.argv) > 1 else None
    dp = sys.argv[2] if len(sys.argv) > 2 else None
    out = sys.argv[3] if len(sys.argv) > 3 else None
    kwargs = {}
    if tl:
        kwargs["tl_path"] = tl
    if dp:
        kwargs["dp_path"] = dp
    if out:
        kwargs["output_path"] = out
    build_dpo_dataset(**kwargs)
