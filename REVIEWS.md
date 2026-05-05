---
reviewers: [gemini]
reviewed_at: 2026-05-04T23:15:00Z
branch: feature/settings-and-config
pr: 81
---

# Cross-AI Review — Settings & Config (Issue #53)

## Gemini Review

This is a high-quality implementation of a configuration management system. The architecture effectively balances multiple configuration sources (Environment, Dotenv, Keyring, and Files) while maintaining internal consistency through an atomic update pattern. The use of Python dataclasses with clamping logic in `__post_init__` ensures the application remains in a valid state even if the configuration file is manually tampered with.

### Strengths

- **Atomic State Management:** The "scratch copy and swap" pattern in `app.py` (`_dc_replace` followed by `self.cfg = candidate`) is excellent. It prevents background threads from observing partially updated configuration states during a live settings change.
- **Validation & Safety:** The `_validate` method provides robust clamping for all numeric ranges, and the system correctly prioritizes `keyring` for the sensitive `CANVAS_TOKEN` while ensuring it is never serialized back to the user-visible TOML file.
- **Conflict Detection:** The keybinding conflict logic in `settings.py` is proactive, checking both user-defined duplicates and collisions with the application's built-in `BINDINGS`.
- **Clean Serialization:** `_config_to_toml` is a dependency-free implementation that handles the transition from `None` (system default) to a scalar string/bool cleanly.

### Issues

- **~~MEDIUM: Python Version Compatibility (`tomllib`)~~** *(non-issue — `requires-python = ">=3.11"` is enforced in `pyproject.toml`)*

- **MEDIUM: Incomplete Field Persistence** — `src/canvas_tui/config.py` (`_FIELD_MAP` and `_config_to_toml`): Several valid `Config` fields (`open_after_dl`, `calcurse_import`, `http_timeout`, `max_retries`) are absent from both the TOML load map and the save serializer. These can only be set via environment variables; a user who writes them into `config.toml` will have them silently ignored.

- **LOW: Redundant Mapping Entry** — `src/canvas_tui/config.py:185-186`: `"download_dir": "download_dir"` appears twice in `_FIELD_MAP`. Python dicts silently accept duplicate keys (last wins), but it indicates a copy-paste error.

- **LOW: Minimal TOML String Escaping** — `src/canvas_tui/config.py:228`: The custom `_toml_val` only escapes `\` and `"`. Control characters (newlines, tabs) in a path or `user_agent` string would produce invalid TOML. Recommendation: use `json.dumps(v)` for the string value, as JSON string escaping is TOML-compatible for basic strings.

### Missing Test Cases

- TOML string injection: a value containing a newline/hash to ensure `_config_to_toml` doesn't break the file.
- Dotenv edge case: `VAR=key=value` (value contains `=`).
- Extension JS: unit test that `savePreferences` merge doesn't clobber unrelated keys when schema expands.

### Overall Verdict: **APPROVE WITH NOTES**

The implementation is solid and production-ready. The noted issues are edge-case portability and minor inconsistencies in field mapping that should be addressed in a follow-up PR.

---
*Reviewer: Gemini CLI (gemini-3.1-pro-preview via google-api-nodejs-client)*

---

## Consensus Summary

Single reviewer — no consensus required.

### Agreed Strengths
- Atomic config swap via `dataclasses.replace()` is the correct approach
- CANVAS_TOKEN never written back to TOML (correctly excluded from serializer)
- Keybinding conflict detection covers both custom and built-in bindings

### Actionable Follow-ups (new issues, not already fixed)
1. Fix duplicate `"download_dir"` entry in `_FIELD_MAP`
2. Expand TOML persistence to include `open_after_dl`, `calcurse_import`, `http_timeout`, `max_retries`
3. Harden TOML string escaping in `_config_to_toml`
