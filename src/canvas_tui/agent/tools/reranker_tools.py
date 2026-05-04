"""Fast preference-hint tool — wraps the published Gemma-4 reranker GGUF.

The agent uses this only as a *fast first-pass priority hint* when it
needs to rank Canvas items by heuristic urgency without spending a full
reasoning turn. The agent's broader context (syllabus, credit hours,
calendar constraints) overrides the model's pick.
"""
from __future__ import annotations

__all__ = ["PriorityHint"]


class PriorityHint:
    NAME = "reranker.priority_hint"
    SCHEMA = {
        "name": NAME,
        "description": (
            "Get a fast priority hint for which of two Canvas items is more urgent "
            "by the trained heuristic. Returns the predicted winner ('A' or 'B') "
            "and the model's natural-language rationale. The agent should treat "
            "this as a heuristic input, not the final answer — richer context "
            "(calendar, syllabus, credit hours) overrides."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural-language ranking criterion."},
                "item_a": {"type": "string", "description": "Item A in the trained format: '[TYPE] Title @COURSEcode STATUS Npts'"},
                "item_b": {"type": "string"},
            },
            "required": ["query", "item_a", "item_b"],
        },
    }
    @staticmethod
    def call(args: dict) -> dict:
        from canvas_tui.reranker import LocalReranker, RANK_PROMPT_FORMAT_SHA, RANK_PROMPT_TEMPLATE
        from canvas_tui.config import Config
        cfg = Config.load()
        if not cfg.use_ai_reranker or not cfg.model_path:
            return {"winner": None, "rationale": "reranker not configured (cfg.use_ai_reranker=False or empty model_path)"}
        rr = LocalReranker(cfg.model_path, expected_sha=RANK_PROMPT_FORMAT_SHA)
        rr._ensure_loaded()
        prompt = RANK_PROMPT_TEMPLATE.format(
            query=args["query"], item_a=args["item_a"], item_b=args["item_b"],
        )
        out = rr._llm.create_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200, temperature=0.0,
        )
        text = out["choices"][0]["message"]["content"]
        import re
        m = re.search(r"\bItem\s*([AB])\b", text)
        return {
            "winner": m.group(1).upper() if m else None,
            "rationale": text,
        }
