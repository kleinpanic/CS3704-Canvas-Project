"""
deposit_zenodo.py — upload paper/main.pdf to Zenodo for a permanent
DOI + citable record.

Setup:
  1. Create a Zenodo account (or use sandbox.zenodo.org for testing)
  2. Generate a personal access token at:
        https://zenodo.org/account/settings/applications/tokens/new/
     Scope: deposit:write + deposit:actions
  3. Export it:
        export ZENODO_TOKEN=...
  4. Run:
        python3 source/deposit_zenodo.py

What this does (in one transaction):
  - Create a new deposit
  - Upload paper/main.pdf
  - Set metadata (title, creators, description, keywords, license, etc.)
  - Publish (assigns DOI; record is permanent and immutable)

After publish, the script prints the DOI + landing-page URL. Add the
DOI badge to README/HF cards.

Note: PUBLISHING IS PERMANENT. The script defaults to publishing
immediately. Set --draft to leave the deposit unpublished so you can
review on the Zenodo web UI before publishing.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PAPER_PATH = Path("paper/main.pdf")
USE_SANDBOX = os.environ.get("ZENODO_SANDBOX", "0") == "1"
BASE_URL = "https://sandbox.zenodo.org/api" if USE_SANDBOX else "https://zenodo.org/api"

METADATA = {
    "title": "Fine-Tuning Gemma-4-E2B-IT for Canvas Assignment Prioritization: A Comparative Study of SFT, LoRA, QLoRA, DPO, IPO, and KTO",
    "creators": [
        {"name": "Thompson, Klein", "affiliation": "Virginia Tech (CS 3704)"},
    ],
    "description": (
        "<p>Domain-specific fine-tuning pipeline for Gemma-4-E2B-IT on the task of "
        "Canvas LMS assignment prioritization. Trains and benchmarks six method variants "
        "(SFT, LoRA, QLoRA, DPO, IPO, KTO) on the same corrected gemma4-text-base and the "
        "same item-disjoint train/test split. Includes the methodology, errata for an "
        "early v1 weight-mapping bug, a v3 retrospective audit identifying "
        "training-set-as-validation contamination in v2, a held-out validation on "
        "n=148 item-disjoint pairs, and a discussion of where DPO (and DPO variants) "
        "do and don't improve over SFT on this saturated preference task.</p>"
        "<p>Companion artifacts:</p>"
        "<ul>"
        "<li>Model: <a href='https://huggingface.co/kleinpanic93/gemma4-canvas-reranker'>kleinpanic93/gemma4-canvas-reranker</a> (4 GGUF quants + BF16)</li>"
        "<li>Six method-variant models: see the "
        "<a href='https://huggingface.co/collections/kleinpanic93/canvas-reranker-gemma-4-e2b-it-v10-69f5799662d65c8f39be0a94'>Canvas Reranker Collection</a></li>"
        "<li>Dataset: <a href='https://huggingface.co/datasets/kleinpanic93/canvas-preference-2k'>kleinpanic93/canvas-preference-2k</a></li>"
        "</ul>"
    ),
    "upload_type": "publication",
    "publication_type": "report",
    "keywords": [
        "Direct Preference Optimization", "DPO", "IPO", "KTO",
        "Gemma-4", "Canvas LMS", "preference learning",
        "domain-specific fine-tuning", "small language models",
        "educational AI", "task prioritization",
    ],
    "license": "cc-by-4.0",
    "communities": [],
    "related_identifiers": [
        {"identifier": "https://huggingface.co/kleinpanic93/gemma4-canvas-reranker", "relation": "isSupplementedBy", "scheme": "url"},
        {"identifier": "https://huggingface.co/datasets/kleinpanic93/canvas-preference-2k", "relation": "isSupplementedBy", "scheme": "url"},
        {"identifier": "https://github.com/kleinpanic/CS3704-Canvas-Project", "relation": "isSupplementedBy", "scheme": "url"},
    ],
}


def main():
    import requests
    token = os.environ.get("ZENODO_TOKEN")
    if not token:
        print("ERROR: set ZENODO_TOKEN to your Zenodo personal access token")
        print("  Get one at: https://zenodo.org/account/settings/applications/tokens/new/")
        print("  Scopes needed: deposit:write, deposit:actions")
        sys.exit(1)
    if not PAPER_PATH.exists():
        print(f"ERROR: {PAPER_PATH} missing")
        sys.exit(1)

    publish_now = "--draft" not in sys.argv

    headers = {"Content-Type": "application/json"}
    auth = {"access_token": token}

    print(f"[1/4] Create deposit at {BASE_URL} ...")
    r = requests.post(f"{BASE_URL}/deposit/depositions", params=auth, json={}, headers=headers)
    r.raise_for_status()
    dep = r.json()
    dep_id = dep["id"]
    bucket_url = dep["links"]["bucket"]
    print(f"      deposit_id={dep_id}")

    print(f"[2/4] Upload {PAPER_PATH} ({PAPER_PATH.stat().st_size//1024} KB) ...")
    with open(PAPER_PATH, "rb") as fp:
        r = requests.put(f"{bucket_url}/{PAPER_PATH.name}", data=fp, params=auth)
    r.raise_for_status()

    print(f"[3/4] Set metadata ...")
    r = requests.put(
        f"{BASE_URL}/deposit/depositions/{dep_id}",
        params=auth, headers=headers,
        data=json.dumps({"metadata": METADATA}),
    )
    if not r.ok:
        print(f"  metadata error: {r.status_code} {r.text[:500]}")
        r.raise_for_status()

    if publish_now:
        print(f"[4/4] PUBLISH (immutable) ...")
        r = requests.post(f"{BASE_URL}/deposit/depositions/{dep_id}/actions/publish", params=auth)
        r.raise_for_status()
        pub = r.json()
        doi = pub["doi"]
        url = pub["links"]["html"]
        print(f"\n  DOI:  {doi}")
        print(f"  URL:  {url}")
        print(f"\nAdd this badge to README:")
        print(f"  [![DOI](https://zenodo.org/badge/DOI/{doi}.svg)](https://doi.org/{doi})")
    else:
        print(f"[4/4] DRAFT mode — leaving deposit unpublished")
        print(f"  Review at: {dep['links']['html']}")
        print(f"  Publish via web UI when ready.")


if __name__ == "__main__":
    main()
