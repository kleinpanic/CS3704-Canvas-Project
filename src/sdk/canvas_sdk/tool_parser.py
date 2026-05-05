from __future__ import annotations
import json, logging, re

logger = logging.getLogger(__name__)

_TOOL_CALL_RE = re.compile(r"<\|tool_call>(.*?)<tool_call\|>", re.DOTALL)
_FUNC_RE = re.compile(r"^call:([\w.]+)\{(.*)\}$", re.DOTALL)


def _args_to_dict(args_str: str) -> dict:
    strings: list[str] = []

    def _stash(m: re.Match) -> str:
        strings.append(m.group(1))
        return f'"__S{len(strings) - 1}__"'

    sanitized = re.sub(r"<\|\"\|>([^<]*(?:<(?!\|\"\|>)[^<]*)*)<\|\"\|>", _stash, args_str, flags=re.DOTALL)
    sanitized = re.sub(r"(?:^|(?<=,)|(?<=\{))(\s*\w+):", r'"\1":', sanitized)
    obj = json.loads("{" + sanitized + "}")

    def _restore(v):
        if isinstance(v, str):
            m = re.fullmatch(r"__S(\d+)__", v)
            return strings[int(m.group(1))] if m else v
        if isinstance(v, dict):
            return {k: _restore(val) for k, val in v.items()}
        if isinstance(v, list):
            return [_restore(x) for x in v]
        return v

    return _restore(obj)


def parse_tool_calls(text: str) -> list[dict]:
    """Parse Gemma4 tool calls: <|tool_call>call:name{args}<tool_call|>"""
    results = []
    for match in _TOOL_CALL_RE.finditer(text):
        body = match.group(1).strip()
        m = _FUNC_RE.match(body)
        if not m:
            continue
        try:
            arguments = _args_to_dict(m.group(2))
        except (json.JSONDecodeError, IndexError, KeyError):
            continue
        results.append({"tool": m.group(1), "args": arguments})
    return results


def format_tool_result(tool_name: str, result: dict) -> str:
    body = json.dumps(result)
    return f'<|tool_response>response:{tool_name}{{value:<|"|>{body}<|"|>}}<tool_response|>'


def extract_final_answer(text: str) -> str:
    return re.sub(r"<\|tool_call>.*?<tool_call\|>", "", text, flags=re.DOTALL).strip()
