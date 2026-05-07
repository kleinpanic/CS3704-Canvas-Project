# Licensing Notes

## Canonical License

This project is licensed under the **[GNU General Public License v3.0 or later (GPL-3.0-or-later)](LICENSE)**.
All source code under `src/` carries `SPDX-License-Identifier: GPL-3.0-or-later` file headers.

## HF Space Deployment Exception

Two Hugging Face Space deployments in this repository declare `apache-2.0` in their frontmatter:

- `hf-space/README.md` — `license: apache-2.0`
- `hf-space-pii/README.md` — `license: apache-2.0`

### Rationale

Hugging Face Spaces function as hosted service deployments. The `apache-2.0` declaration in HF
Space frontmatter follows the Hugging Face Space delivery convention and applies to the **Space
deployment layer only** — the configuration, wrapper scripts, and Space-specific metadata.

The underlying source code that drives both Spaces lives under `src/` and remains
**GPL-3.0-or-later**. The `apache-2.0` frontmatter does not change the license of the GPL source.

### Deferral note

Changing the HF Space frontmatter from `apache-2.0` to `gpl-3.0` (which HF supports as an enum
value) is deferred to a future revision (v2.2). This file will be updated when that change lands.
