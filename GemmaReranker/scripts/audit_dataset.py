"""
audit_dataset.py — sanity / privacy / integrity audit of data/dpo_train.jsonl
before any potential HuggingFace dataset release.

Checks:
  A. Schema integrity — required fields present, no nulls, pair_type valid
  B. PII / leakage — real course codes, names, emails, URLs, Canvas IDs
  C. Anonymization quality — @COURSE codes consistent, no real-looking codes
  D. Duplicate detection — duplicate prompts / triples
  E. Length distribution — prompt + chosen + rejected token-length stats
  F. Label quality — chosen/rejected lead with "Item A"/"Item B"
  G. Hallucination check — does completion mention attributes absent from prompt
  H. pair_type sanity — hard_negative pairs structurally distinct from standard

Output: structured JSON + human-readable summary.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

DATA_PATHS = [
    Path("data/dpo_train.jsonl"),
    Path("data/dpo_train_v3.jsonl"),
    Path("data/dpo_test_v3.jsonl"),
]

# ── Patterns ──────────────────────────────────────────────────────────────────

EMAIL = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
URL = re.compile(r"https?://[^\s]+")
COURSE_GOOD = re.compile(r"@COURSE\w+")
COURSE_BAD = re.compile(r"@(?!COURSE)([A-Z]{2,5}\d{3,5}[A-Z]?)\b")  # e.g. @CS3704, @ENGL2204
NAME_HINT = re.compile(r"\b(Dr|Prof|Professor|Mr|Mrs|Ms)\.\s+[A-Z][a-z]+", re.IGNORECASE)
CANVAS_ID = re.compile(r"\b[1-9]\d{6,}\b")  # Canvas item IDs are typically 7-9 digit ints
PRONOUN_LEAK = re.compile(r"\b(my professor|my instructor|my TA|my section|my dorm)\b", re.IGNORECASE)

ITEM_RE = re.compile(r"^Item [AB]:\s*(\[[^\]]+\])\s*(.+?)\s*(@COURSE\w+)\s+(.+?)\s+(\d+)pts\s*$", re.MULTILINE)
ITEM_LEAD = re.compile(r"\bItem\s*([AB])\b")


def audit_one_file(path: Path) -> dict:
    rec_list = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    n = len(rec_list)
    report = {"file": str(path), "n_records": n, "checks": {}}

    # A. Schema integrity
    schema_issues = []
    pair_type_counter = Counter()
    for i, r in enumerate(rec_list):
        for k in ("prompt", "chosen", "rejected", "pair_type"):
            if k not in r:
                schema_issues.append(f"rec {i}: missing field {k}")
            elif r[k] is None or (isinstance(r[k], str) and not r[k].strip()):
                schema_issues.append(f"rec {i}: empty/null field {k}")
        pt = r.get("pair_type")
        pair_type_counter[pt] += 1
        if pt not in ("standard", "hard_negative"):
            schema_issues.append(f"rec {i}: unknown pair_type {pt!r}")
    report["checks"]["A_schema"] = {
        "issues": len(schema_issues),
        "pair_type_distribution": dict(pair_type_counter),
        "first_5_issues": schema_issues[:5],
    }

    # B. PII / leakage scan over ALL text fields
    pii_hits = defaultdict(list)
    for i, r in enumerate(rec_list):
        for field in ("prompt", "chosen", "rejected"):
            text = r.get(field, "")
            for m in EMAIL.findall(text):
                pii_hits["emails"].append((i, field, m))
            for m in URL.findall(text):
                pii_hits["urls"].append((i, field, m))
            for m in NAME_HINT.findall(text):
                pii_hits["name_hints"].append((i, field, m))
            for m in CANVAS_ID.findall(text):
                pii_hits["canvas_ids"].append((i, field, m))
            for m in PRONOUN_LEAK.findall(text):
                pii_hits["pronoun_leaks"].append((i, field, m))
    report["checks"]["B_pii"] = {
        category: {"count": len(hits), "first_3": hits[:3]}
        for category, hits in pii_hits.items()
    }
    if not pii_hits:
        report["checks"]["B_pii"]["clean"] = True

    # C. Anonymization quality — course codes
    good_codes = Counter()
    bad_codes = Counter()
    for r in rec_list:
        for m in COURSE_GOOD.findall(r.get("prompt", "")):
            good_codes[m] += 1
        for m in COURSE_BAD.findall(r.get("prompt", "")):
            bad_codes[m] += 1
    report["checks"]["C_anonymization"] = {
        "anonymized_course_codes_distinct": len(good_codes),
        "anonymized_course_codes_top10": good_codes.most_common(10),
        "real_looking_codes_distinct": len(bad_codes),
        "real_looking_codes_first5": list(bad_codes.most_common(5)),
    }

    # D. Duplicate detection
    prompt_counter = Counter()
    triple_counter = Counter()
    for r in rec_list:
        prompt_counter[r.get("prompt", "")] += 1
        triple_counter[(r.get("prompt", ""), r.get("chosen", ""), r.get("rejected", ""))] += 1
    dup_prompts = sum(1 for v in prompt_counter.values() if v > 1)
    dup_triples = sum(1 for v in triple_counter.values() if v > 1)
    report["checks"]["D_duplicates"] = {
        "duplicate_prompts": dup_prompts,
        "duplicate_triples_count": dup_triples,
        "prompt_uniqueness_pct": round(len(prompt_counter) / n * 100, 1),
    }

    # E. Length distribution (chars; tokens is more relevant but expensive)
    p_lens = [len(r.get("prompt", "")) for r in rec_list]
    c_lens = [len(r.get("chosen", "")) for r in rec_list]
    rj_lens = [len(r.get("rejected", "")) for r in rec_list]
    def stats(xs):
        xs = sorted(xs)
        return {
            "min": xs[0], "p25": xs[len(xs)//4], "median": xs[len(xs)//2],
            "p75": xs[3*len(xs)//4], "max": xs[-1], "mean": round(sum(xs)/len(xs), 1),
        }
    report["checks"]["E_lengths_chars"] = {
        "prompt": stats(p_lens),
        "chosen": stats(c_lens),
        "rejected": stats(rj_lens),
    }

    # F. Label quality — chosen/rejected lead with "Item X"
    chosen_picks = Counter()
    rejected_picks = Counter()
    label_consistency_issues = []
    for i, r in enumerate(rec_list):
        cm = ITEM_LEAD.search(r.get("chosen", ""))
        rm = ITEM_LEAD.search(r.get("rejected", ""))
        chosen_picks[cm.group(1) if cm else "(none)"] += 1
        rejected_picks[rm.group(1) if rm else "(none)"] += 1
        if cm and rm and cm.group(1) == rm.group(1):
            label_consistency_issues.append((i, "chosen+rejected pick same letter", cm.group(1)))
    report["checks"]["F_label_quality"] = {
        "chosen_first_letter": dict(chosen_picks),
        "rejected_first_letter": dict(rejected_picks),
        "consistency_issues": len(label_consistency_issues),
        "first_3_issues": label_consistency_issues[:3],
    }

    # G. Hallucination check — does chosen/rejected mention point-values not in prompt
    pts_re = re.compile(r"(\d+)\s*pts?\b", re.IGNORECASE)
    halluc = 0
    halluc_examples = []
    for i, r in enumerate(rec_list):
        prompt = r.get("prompt", "")
        prompt_pts = set(pts_re.findall(prompt))
        for field in ("chosen", "rejected"):
            text = r.get(field, "")
            for pt in pts_re.findall(text):
                if pt not in prompt_pts and pt != "1" and len(pt) > 1:  # exclude common defaults
                    halluc += 1
                    if len(halluc_examples) < 3:
                        halluc_examples.append((i, field, pt, list(prompt_pts)))
                    break
    report["checks"]["G_hallucination_pts"] = {
        "fabricated_points_count": halluc,
        "first_3_examples": halluc_examples,
    }

    # H. pair_type structural distinctness
    standard_prompt_lens = [len(r["prompt"]) for r in rec_list if r.get("pair_type") == "standard"]
    hard_prompt_lens = [len(r["prompt"]) for r in rec_list if r.get("pair_type") == "hard_negative"]
    if standard_prompt_lens and hard_prompt_lens:
        report["checks"]["H_pair_type_check"] = {
            "standard_count": len(standard_prompt_lens),
            "hard_count": len(hard_prompt_lens),
            "standard_mean_len": round(sum(standard_prompt_lens)/len(standard_prompt_lens), 1),
            "hard_mean_len": round(sum(hard_prompt_lens)/len(hard_prompt_lens), 1),
        }

    return report


def main():
    overall = {"audits": [], "summary": {}}
    for path in DATA_PATHS:
        if not path.exists():
            overall["audits"].append({"file": str(path), "error": "missing"})
            continue
        overall["audits"].append(audit_one_file(path))

    out_path = Path(".planning/research/DATASET-AUDIT.json")
    out_path.write_text(json.dumps(overall, indent=2, default=str))
    print(f"\nFull report: {out_path}")
    print("\n=== Headline summary per file ===")
    for a in overall["audits"]:
        if "error" in a:
            print(f"  {a['file']}: ERROR {a['error']}")
            continue
        c = a["checks"]
        print(f"\n  {a['file']} (n={a['n_records']})")
        print(f"    A. schema issues:         {c['A_schema']['issues']}")
        for k, v in c['B_pii'].items():
            if k == 'clean': continue
            print(f"    B. PII {k}: {v['count']}")
        print(f"    C. real-looking codes:    {c['C_anonymization']['real_looking_codes_distinct']}")
        print(f"    C. anonymized codes:      {c['C_anonymization']['anonymized_course_codes_distinct']}")
        print(f"    D. duplicate prompts:     {c['D_duplicates']['duplicate_prompts']}")
        print(f"    D. duplicate triples:     {c['D_duplicates']['duplicate_triples_count']}")
        print(f"    F. label consistency:     {c['F_label_quality']['consistency_issues']} issues")
        print(f"    G. fabricated pts count:  {c['G_hallucination_pts']['fabricated_points_count']}")


if __name__ == "__main__":
    main()
