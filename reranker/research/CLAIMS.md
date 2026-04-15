# Gemma 2B Reranker — Claims & Priority Algorithm

## What Is an "Important" Canvas Item?

### The 5-Signal Urgency Formula

The existing `generate_rerank_data.py` uses a weighted combination of 5 signals:

```
urgency = w1*time_factor + w2*type_factor + w3*points_factor + w4*status_factor + w5*grade_impact
```

| Signal | Weight | How It Works |
|--------|--------|-------------|
| **Time** | 3.0 | Hours until due. Non-linear: overdue gets +10–30 boost, within 24h gets +20, within 48h gets +15. |
| **Type** | 2.5 | Hierarchy: exam(10) > quiz(7) > assignment(5) > discussion(3) > event(1) > announcement(0) |
| **Points** | 1.5 | points/25, capped at 8. Rewards high-value assignments. |
| **Status** | 2.0 | missing(+15), late(+7), none(0), submitted(-60), excused(-60). Submitted items drop to bottom. |
| **Grade Impact** | 2.0 | course_weight × (100 - current_score)/100. If you're doing poorly in a course, its items matter more. |

### Why This Isn't Just a Date Sort

A naive "sort by due date" fails in these scenarios:

1. **A 10-point quiz due tomorrow vs a 200-point exam due in 3 days**  
   → Date says quiz. Urgency formula says exam (high points + high grade impact).

2. **Two assignments due in 2 hours — one you're already done with, one missing**  
   → Date says tie. Urgency says the missing one (+15 status boost).

3. **A low-stakes discussion post due tonight vs a major lab due Friday**  
   → Date says discussion. Urgency says the lab (high points + exam-adjacent weight).

4. **You're acing a course vs barely passing one**  
   → Same item in both courses. The struggling course gets a higher grade_impact boost.

5. **An item that's been overdue for days vs a new item due tomorrow**  
   → Overdue gets a compounding urgency multiplier (already late × time factor).

### Fine-tuning Lets Gemma Learn Nuance

The heuristic formula is good but has limits:
- **Hardcoded weights**: Weights (3.0, 2.5, etc.) are our guesses. Fine-tuning adjusts these automatically.
- **No course context**: Gemma learns that "CS 3704 project phase 3" from Klein's history might be more urgent than a NEUR discussion because of workload.
- **Pairwise nuance**: Some pairs are genuinely ambiguous — Gemma learns to distinguish where the heuristic fails.

---

## Claims We Are Making

| Claim | Evidence | Gaps |
|-------|---------|------|
| Pairwise ranking is the right formulation | Natural for human preference data, proven in NLP (BERT-to-BERT) | May need more data than pointwise |
| 17 query types cover Klein's use cases | Matches Canvas TUI navigation modes | May miss "what can I skip" / "what's optional" |
| 5 urgency signals are sufficient | Matches Canvas item fields, covers academic judgment | Missing: course difficulty, professor strictness, group member reliance |
| Gemma 2B is capable enough | 2B params is sweet spot for LoRA on consumer GPU | May need 7B for more nuanced multi-course reasoning |
| 300 steps is enough | ~1 epoch on ~1000 pairs, QLoRA is sample-efficient | May need more if data is diverse |
| GGUF Q4_K_M is good enough quality | Industry standard for quantized LLM | May prefer Q5 or F16 if VRAM allows |

---

## Open Discussion Points

1. **Weight tuning**: Should we let Gemma learn all 5 weights from scratch, or prime it with the current heuristic as a prior?
2. **Course-specific vs general**: Train one model for all courses, or one per course based on Klein's patterns?
3. **"Importance" vs "Urgency"**: These are different — a major project might be important but not urgent (due in 2 weeks). Do we need both axes?
4. **Submitted items**: The formula penalizes submitted items heavily (-60). Should "submitted and not yet graded" be less negative?
5. **Hard negatives**: The current formula creates "hard negatives" for items with within-5-point urgency difference. Is this the right threshold?
