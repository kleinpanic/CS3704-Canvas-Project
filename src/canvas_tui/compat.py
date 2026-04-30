"""Platform compatibility helpers for terminal rendering.

On Windows, braille Unicode characters (U+2800-U+28FF) often render as boxes
because common fonts like Consolas don't include the Braille block. This module
provides ASCII fallbacks so charts look reasonable on every platform.

Set CANVAS_ASCII=1 to force ASCII mode regardless of OS.
Set CANVAS_ASCII=0 to force Unicode mode regardless of OS.
"""

from __future__ import annotations

import os
import sys

# Detect platform; honour explicit override via env var
_env = os.environ.get("CANVAS_ASCII", "").strip()
if _env == "1":
    USE_ASCII = True
elif _env == "0":
    USE_ASCII = False
else:
    USE_ASCII = sys.platform == "win32"

# ─── Braille ─────────────────────────────────────────────────────────────

_BRAILLE_BASE = 0x2800

# Maps a braille dot pattern (0-255) to an ASCII approximation.
# The braille cell is 2 dots wide x 4 dots tall:
#   dot bit layout: 1 8
#                   2 16
#                   4 32
#                   64 128
_ASCII_BRAILLE: dict[int, str] = {}


def _build_ascii_braille_map() -> None:
    for pattern in range(256):
        # Count set dot bits
        bits = bin(pattern).count("1")
        if bits == 0:
            _ASCII_BRAILLE[pattern] = " "
        elif bits <= 1:
            _ASCII_BRAILLE[pattern] = "."
        elif bits <= 3:
            _ASCII_BRAILLE[pattern] = ":"
        else:
            _ASCII_BRAILLE[pattern] = "#"


_build_ascii_braille_map()


def braille_char(pattern: int) -> str:
    """Return a braille character or an ASCII fallback for the given dot pattern."""
    if USE_ASCII:
        return _ASCII_BRAILLE.get(pattern & 0xFF, ".")
    return chr(_BRAILLE_BASE + (pattern & 0xFF))


# ─── Block / bar characters ──────────────────────────────────────────────

BLOCK_FULL: str = "#" if USE_ASCII else "█"
BLOCK_EMPTY: str = "-" if USE_ASCII else "░"
BLOCK_HALF: str = "+" if USE_ASCII else "▄"
HEAT_CHARS: str = " .:-=#" if USE_ASCII else " ░▒▓█"

# Sparkline height characters (low → high)
SPARKLINE_CHARS: str = ".,:-=+|#" if USE_ASCII else "▁▂▃▄▅▆▇█"
