# Live Demo & ML Assets

The Canvas Calendar Agent is **live, free to try, and requires no setup**. Click anywhere below.

## Try the agent right now

| Surface | Link | What it is |
|---|---|---|
| Browser demo | [kleinpanic.github.io/CS3704-Canvas-Project/agent-demo/](https://kleinpanic.github.io/CS3704-Canvas-Project/agent-demo/) | Polished chat UI, 18 tool buttons, runs on this site |
| HuggingFace Space | [kleinpanic93/canvas-calendar-agent-demo](https://huggingface.co/spaces/kleinpanic93/canvas-calendar-agent-demo) | The live inference Space (ZeroGPU) |
| Cloudflare Worker proxy | [cs3704-demo-proxy.kleinpanic.workers.dev](https://cs3704-demo-proxy.kleinpanic.workers.dev) | Holds HF auth server-side; no tokens reach the browser |

The browser demo calls the Worker, which calls the Space. First request after a quiet period takes ~30 s while ZeroGPU cold-starts; subsequent requests are fast.

## What's the model

| Asset | Link |
|---|---|
| Model card | [kleinpanic93/canvas-calendar-agent-v7-dpo](https://huggingface.co/kleinpanic93/canvas-calendar-agent-v7-dpo) |
| Preference dataset | [kleinpanic93/canvas-calendar-preferences-v7](https://huggingface.co/datasets/kleinpanic93/canvas-calendar-preferences-v7) |
| GGUF quants (Ollama-ready) | [kleinpanic93/canvas-calendar-agent-v7-dpo-gguf](https://huggingface.co/kleinpanic93/canvas-calendar-agent-v7-dpo-gguf) |
| **Collection (full v3.0 9-method matrix)** | [Canvas Calendar Agent v3.0](https://huggingface.co/collections/kleinpanic93/canvas-calendar-agent-v30-69fa6462f697e0342b21dfe0) |

Base model: `google/gemma-4-e2b-it`. Fine-tuned with **Direct Preference Optimization** ([arXiv:2305.18290](https://arxiv.org/abs/2305.18290)) on 1,071 preference pairs.

**Headline metrics:** rewards/accuracies = 0.9032, train_loss = 0.2229, rewards/margins = 5.142 (134 steps in 9:03 on a single Spark GB10).

## Use it locally

### Python SDK (auto-downloads model from HF)

```bash
pip install canvas-sdk[autodownload]

python -c "from canvas_sdk import CanvasAgent; print(CanvasAgent.auto().run('what is due this week?'))"
```

### Ollama (any of the 6 GGUF quants)

```bash
ollama pull hf.co/kleinpanic93/canvas-calendar-agent-v7-dpo-gguf:Q4_K_M
ollama run hf.co/kleinpanic93/canvas-calendar-agent-v7-dpo-gguf:Q4_K_M "list my Canvas courses"
```

Available quants: `Q4_K_M` (3.2 GB, recommended), `Q8_0` (4.7 GB), `F16` (8.7 GB). Full 12-quant expansion ships with v8.

## The 18 tools

The agent speaks the **native Gemma-4 tool-call protocol** for these 18 tools. Each one is wired in the [Python SDK](https://github.com/kleinpanic/CS3704-Canvas-Project/tree/main/src/sdk/canvas_sdk/agent_tools) with a real Canvas / Google Calendar adapter. The browser demo uses mock dispatchers since the public Space has no Canvas creds.

### canvas (8)
`get_assignments` · `get_course` · `get_grades` · `get_syllabus` · `get_todo` · `list_announcements` · `list_courses` · `list_planner_items`

### calendar (5)
`create_event` · `delete_event` · `find_free_blocks` · `list_events` · `modify_event`

### reranker (1)
`priority_hint`

### study (4)
`exam_bracket` · `recommend_block_size` · `semester_schedule` · `spaced_schedule`

## Architecture

```
User browser  →  GitHub Pages (static site)
                  ↓ POST /chat (no token in JS)
Cloudflare Worker  →  https://cs3704-demo-proxy.kleinpanic.workers.dev
                  ↓ Authorization: Bearer hf_*** (server-side secret)
HuggingFace Space  →  Gemma-4 DPO inference (ZeroGPU)
                  ↓ tool calls + mock dispatchers
                final answer + tool-call breakdown
```

**Why the Worker?** ZeroGPU has a small daily quota for *anonymous* callers. Without auth, the demo would be unusable after a handful of visitors. The Worker holds the HF token server-side so authenticated requests use the project's quota; the browser never sees a credential.

See [Architecture → Security](architecture.md) for the full forensic backstory and security design.

## Source repos

| Repo | What lives there |
|---|---|
| [CS3704-Canvas-Project](https://github.com/kleinpanic/CS3704-Canvas-Project) | TUI client, browser extension, SDK, docs site, demo |
| [CS3704-DPO-SSOT](https://github.com/kleinpanic/CS3704-DPO-SSOT) (private) | Training data, fine-tuning code, paper, GSD planning |

## Release

Latest tagged release: [v3.0.0](https://github.com/kleinpanic/CS3704-Canvas-Project/releases/tag/v3.0.0) — extension zip, SDK wheel, source tarball, model card.
