#!/usr/bin/env python3
"""Quick demo of the Canvas Calendar Agent with Gemma4 backend."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sdk"))
from canvas_sdk import CanvasAgent
from canvas_sdk.backends.gemma4_backend import Gemma4Backend

QUESTIONS = [
    "What assignments do I have due this week?",
    "I have two midterms next week. Can you help me plan study blocks?",
    "Which assignments are still accepting late submissions?",
]

def main():
    backend = Gemma4Backend(
        endpoint=os.environ.get("LLM_ENDPOINT", "http://localhost:18080/v1"),
        model=os.environ.get("LLM_MODEL", "nvidia/Gemma-4-31B-IT-NVFP4"),
        api_key=os.environ.get("OPENAI_API_KEY", "forge"),
    )
    agent = CanvasAgent(backend)
    for q in QUESTIONS:
        print(f"\n[USER] {q}")
        response = agent.run(q, canvas_token=os.environ.get("CANVAS_TOKEN", ""))
        print(f"[AGENT] {response[:500]}")

if __name__ == "__main__":
    main()
