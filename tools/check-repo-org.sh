#!/usr/bin/env bash
# Repo organization warning hook (Phase 4 of v2.1 — D-06).
#
# Four checks against the repo's top-level structure:
#   1. New top-level files/dirs not in ALLOWLIST
#   2. New root-level *.md files not in ALLOWLIST (subset of 1, called out separately)
#   3. New Dockerfile outside docker/ + hf-space*/
#   4. New pyproject.toml outside src/sdk/ + repo root
#
# WARNING MODE: emits warnings to stderr and ALWAYS exits 0.
# Promotes to blocking after one milestone of stable usage (Phase 9 pattern).

set -u

ALLOWLIST_FILE="ALLOWLIST"
warn_count=0

if [ ! -f "${ALLOWLIST_FILE}" ]; then
    echo "WARN: ALLOWLIST not found at repo root — Phase 4 hasn't shipped fully?" >&2
    exit 0
fi

# Strip comments + blank lines + trailing whitespace from ALLOWLIST.
allowed=$(grep -v '^#' "${ALLOWLIST_FILE}" | grep -v '^[[:space:]]*$' | awk '{print $1}' | sort -u)

# === Check 1: top-level entries not in ALLOWLIST ===
actual=$(find . -maxdepth 1 -mindepth 1 -not -path './.git' -not -path './.git/*' \
    | sed 's|^\./||' | sort -u)

# Skip cache/venv dirs — these are local-only, not committed.
filtered=$(echo "${actual}" | grep -vE '^\.(mypy_cache|pytest_cache|ruff_cache|venv|coverage|tox)$')

while IFS= read -r entry; do
    [ -z "${entry}" ] && continue
    if ! echo "${allowed}" | grep -qFx "${entry}"; then
        echo "WARN [repo-org]: top-level '${entry}' is not in ALLOWLIST. Add it with rationale or move it." >&2
        warn_count=$((warn_count + 1))
    fi
done <<< "${filtered}"

# === Check 2: new root *.md files (called out separately for visibility) ===
while IFS= read -r mdfile; do
    [ -z "${mdfile}" ] && continue
    base=$(basename "${mdfile}")
    if ! echo "${allowed}" | grep -qFx "${base}"; then
        echo "WARN [repo-org]: root markdown '${base}' is not in ALLOWLIST. Either add it or move under docs/." >&2
        warn_count=$((warn_count + 1))
    fi
done < <(find . -maxdepth 1 -name '*.md' -type f | sed 's|^\./||')

# === Check 3: Dockerfile outside sanctioned dirs ===
while IFS= read -r dockerfile; do
    [ -z "${dockerfile}" ] && continue
    if ! [[ "${dockerfile}" =~ ^(./)?docker/ ]] && ! [[ "${dockerfile}" =~ ^(./)?hf-space ]]; then
        echo "WARN [repo-org]: Dockerfile '${dockerfile}' is outside docker/ + hf-space*/. Move it or update ALLOWLIST policy." >&2
        warn_count=$((warn_count + 1))
    fi
done < <(find . -name 'Dockerfile*' -not -path './.git/*' -not -path './.venv/*' -not -path './.planning/*' -type f)

# === Check 4: pyproject.toml outside src/sdk/ + repo root ===
while IFS= read -r pyproject; do
    [ -z "${pyproject}" ] && continue
    rel=$(echo "${pyproject}" | sed 's|^\./||')
    case "${rel}" in
        pyproject.toml | src/sdk/pyproject.toml | src/canvas_tui/pyproject.toml)
            ;; # sanctioned — root, sdk, or canvas_tui
        *)
            echo "WARN [repo-org]: pyproject.toml at '${rel}' is outside src/sdk/ + repo root. Consolidate or document." >&2
            warn_count=$((warn_count + 1))
            ;;
    esac
done < <(find . -name 'pyproject.toml' -not -path './.git/*' -not -path './.venv/*' -not -path './.planning/*' -not -path './node_modules/*' -type f)

if [ "${warn_count}" -gt 0 ]; then
    echo "" >&2
    echo "Repo-org check: ${warn_count} warning(s). Hook is in WARNING MODE (exit 0)." >&2
    echo "Adopt by either updating ALLOWLIST or moving the offending entries." >&2
fi

exit 0
