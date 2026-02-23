"""Configuration loading and validation for Canvas TUI."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Config:
    """All configuration values with validated defaults."""

    base_url: str = "https://canvas.vt.edu"
    token: str = ""
    user_tz: str = "America/New_York"
    user_agent: str = "canvas-tui/0.5 (textual)"
    http_timeout: int = 20
    max_retries: int = 5
    backoff_factor: float = 0.4

    days_ahead: int = 7
    past_hours: int = 72
    refresh_cooldown: float = 2.0
    auto_refresh_sec: int = 300
    download_dir: str | None = None
    default_block_min: int = 60
    export_dir: str = field(default_factory=lambda: os.path.expanduser("~/.local/share/canvas-tui"))
    open_after_dl: bool = False
    calcurse_import: bool = False

    ann_past_days: int = 14
    ann_future_days: int = 14

    config_dir: str = field(default_factory=lambda: os.path.expanduser("~/.config/canvas-tui"))

    def __post_init__(self) -> None:
        self._validate()

    def _validate(self) -> None:
        """Validate configuration values and clamp to safe ranges."""
        self.base_url = self.base_url.rstrip("/")
        self.days_ahead = max(1, min(self.days_ahead, 365))
        self.past_hours = max(0, min(self.past_hours, 8760))
        self.refresh_cooldown = max(0.5, min(self.refresh_cooldown, 60.0))
        self.auto_refresh_sec = max(30, min(self.auto_refresh_sec, 3600))
        self.http_timeout = max(5, min(self.http_timeout, 120))
        self.max_retries = max(0, min(self.max_retries, 10))
        self.backoff_factor = max(0.1, min(self.backoff_factor, 5.0))
        self.default_block_min = max(5, min(self.default_block_min, 480))
        self.ann_past_days = max(0, min(self.ann_past_days, 365))
        self.ann_future_days = max(0, min(self.ann_future_days, 365))

    @property
    def config_toml(self) -> str:
        return os.path.join(self.config_dir, "config.toml")

    @property
    def config_json(self) -> str:
        return os.path.join(self.config_dir, "config.json")

    @property
    def state_path(self) -> str:
        return os.path.join(self.export_dir, "state.json")

    @property
    def export_ics_path(self) -> str:
        return os.path.join(self.export_dir, "canvas.ics")


def load_config() -> Config:
    """Load config from environment variables, then overlay file config."""
    cfg = Config(
        base_url=os.environ.get("CANVAS_BASE_URL", "https://canvas.vt.edu").rstrip("/"),
        token=os.environ.get("CANVAS_TOKEN", ""),
        user_tz=os.environ.get("TZ", "America/New_York"),
        user_agent=os.environ.get("CANVAS_UA", "canvas-tui/0.5 (textual)"),
        http_timeout=int(os.environ.get("HTTP_TIMEOUT", "20")),
        max_retries=int(os.environ.get("HTTP_MAX_RETRIES", "5")),
        backoff_factor=float(os.environ.get("HTTP_BACKOFF", "0.4")),
        days_ahead=int(os.environ.get("DAYS_AHEAD", "7")),
        past_hours=int(os.environ.get("PAST_HOURS", "72")),
        refresh_cooldown=float(os.environ.get("REFRESH_COOLDOWN", "2.0")),
        auto_refresh_sec=int(os.environ.get("AUTO_REFRESH_SEC", "300")),
        download_dir=os.environ.get("DOWNLOAD_DIR"),
        default_block_min=int(os.environ.get("DEFAULT_BLOCK_MIN", "60")),
        export_dir=os.path.expanduser(os.environ.get("EXPORT_DIR", "~/.local/share/canvas-tui")),
        open_after_dl=os.environ.get("OPEN_AFTER_DL", "0") == "1",
        calcurse_import=os.environ.get("CALCURSE_IMPORT", "0") == "1",
        ann_past_days=int(os.environ.get("ANN_PAST_DAYS", "14")),
        ann_future_days=int(os.environ.get("ANN_FUTURE_DAYS", "14")),
    )

    if not cfg.token:
        # Try keyring as fallback
        cfg.token = _try_keyring()
    if not cfg.token:
        print(
            "ERROR: Set CANVAS_TOKEN env var or store it via:\n"
            "  python3 -c \"import keyring; keyring.set_password('canvas-tui', 'token', 'YOUR_TOKEN')\"",
            file=sys.stderr,
        )
        sys.exit(1)

    _overlay_file_config(cfg)
    return cfg


def _overlay_file_config(cfg: Config) -> None:
    """Overlay config from TOML or JSON file if present."""
    file_cfg = _read_config_file(cfg.config_toml, cfg.config_json)
    if not file_cfg:
        return

    _FIELD_MAP: dict[str, str] = {
        "days_ahead": "days_ahead",
        "refresh_cooldown": "refresh_cooldown",
        "auto_refresh_sec": "auto_refresh_sec",
        "download_dir": "download_dir",
        "default_block_min": "default_block_min",
        "past_hours": "past_hours",
        "ann_past_days": "ann_past_days",
        "ann_future_days": "ann_future_days",
        # Support the typo variant for backwards compat
        "ann_futuredays": "ann_future_days",
    }

    for file_key, attr_name in _FIELD_MAP.items():
        if file_key in file_cfg:
            raw = file_cfg[file_key]
            current = getattr(cfg, attr_name)
            try:
                if isinstance(current, int):
                    setattr(cfg, attr_name, int(raw))
                elif isinstance(current, float):
                    setattr(cfg, attr_name, float(raw))
                elif isinstance(current, str):
                    setattr(cfg, attr_name, str(raw))
                else:
                    setattr(cfg, attr_name, raw)
            except (ValueError, TypeError):
                pass  # Skip bad values

    cfg._validate()


def _read_config_file(toml_path: str, json_path: str) -> dict[str, Any]:
    """Read TOML or JSON config file, returning dict or empty."""
    try:
        if os.path.exists(toml_path):
            import tomllib

            with open(toml_path, "rb") as f:
                return tomllib.load(f)
        if os.path.exists(json_path):
            with open(json_path, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _try_keyring() -> str:
    """Try to get token from system keyring."""
    try:
        import keyring

        token = keyring.get_password("canvas-tui", "token")
        return token or ""
    except Exception:
        return ""


def ensure_dirs(cfg: Config) -> None:
    """Create required directories."""
    os.makedirs(cfg.export_dir, exist_ok=True)
    os.makedirs(cfg.config_dir, exist_ok=True)
