# Project Roadmap

This roadmap reflects the current post-cleanup state of the repository.

## Current State

Recently completed:
- repo governance cleanup around `main`
- removal of AI auto-fix and auto-doc workflows from the main merge path
- browser extension popup visual polish pass
- browser extension shared client/runtime contract refactor
- cleanup of stale remote branches

## Near-Term Priorities

### 1. Browser extension hardening
- add tests around the shared client and runtime contract
- expand course-context features that use modules, files, and announcements
- reduce any remaining direct background/runtime coupling

### 2. Docs and site maintenance
- keep MkDocs pages aligned with current architecture
- update screenshots/diagrams when UI or structure changes
- keep workflow/governance pages consistent with real repo settings

### 3. Repo architecture cleanup
- decide how to isolate `GemmaReranker` and related data from core app concerns
- clarify what is core product code versus experimental/support tooling

## Delivery Model

```text
small scoped branch
  -> PR to main
  -> CI checks
  -> maintainer review
  -> squash merge
  -> docs site auto-deploys from main
```

## Extension Roadmap Snapshot

The extension is no longer just a future placeholder.

Implemented now:
- popup UI
- background worker
- IndexedDB cache
- shared Canvas client layer
- shared runtime contract

Still needed:
- broader feature coverage
- deeper tests
- clearer auth strategy if OAuth replaces token entry

## Medium-Term Follow-Ups

- richer extension parity with the TUI
- improved architecture diagrams reflecting the browser-side layers
- possible isolation of optional tooling/data into better-scoped directories or repos

## Success Criteria

The project is in a good state when:
- `main` stays the only durable branch
- docs site reflects actual architecture, not stale plans
- extension changes land through a predictable contract layer
- maintainers do not need ad hoc branch-protection surgery for normal work
