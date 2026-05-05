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

    # Calendar backend — "google" | "ical" | "none"
    calendar_backend: str = "none"
    google_credentials_path: str = field(
        default_factory=lambda: os.path.expanduser("~/.config/canvas-tui/google_credentials.json")
    )
    google_token_path: str = field(default_factory=lambda: os.path.expanduser("~/.config/canvas-tui/google_token.json"))
    ical_path: str = field(default_factory=lambda: os.path.expanduser("~/.local/share/canvas-tui/calendar.ics"))
    ical_write_path: str = ""

    # AI reranker
    use_ai_reranker: bool = False
    model_path: str = ""

    # LLM agent settings — OpenAI-compatible endpoint for fine-tuned Gemma4
    llm_endpoint: str = "http://localhost:18080/v1"
    llm_model: str = "google/gemma-4-e2b-it"
    llm_api_key: str = "forge"
    agent_max_turns: int = 8

    config_dir: str = field(default_factory=lambda: os.path.expanduser("~/.config/canvas-tui"))

    # Appearance
    theme: str = "dark"
    sidebar_position: str = "right"
    sidebar_width: int = 44

    # Extra keybindings: action_name → key string.  Empty = use built-in defaults.
    keybindings: dict[str, str] = field(default_factory=dict)

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
        self.agent_max_turns = max(1, min(self.agent_max_turns, 32))
        if self.theme not in ("dark", "light"):
            self.theme = "dark"
        if self.sidebar_position not in ("left", "right"):
            self.sidebar_position = "right"
        self.sidebar_width = max(20, min(self.sidebar_width, 80))

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

    def save(self) -> None:
        """Persist current config to config.toml (user-editable scalars only)."""
        os.makedirs(self.config_dir, exist_ok=True)
        content = _config_to_toml(self)
        with open(self.config_toml, "w", encoding="utf-8") as f:
            f.write(content)


def _load_dotenv() -> None:
    """Load .env file if present (simple key=value parser, no dependencies)."""
    for path in [".env", os.path.expanduser("~/.config/canvas-tui/.env")]:
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        key, _, value = line.partition("=")
                        key = key.strip()
                        value = value.strip().strip("'\"")
                        if key and key not in os.environ:
                            os.environ[key] = value
            except Exception:
                pass
            break


def load_config() -> Config:
    """Load config from .env, environment variables, then overlay file config."""
    _load_dotenv()
    cfg = Config(
        base_url=os.environ.get("CANVAS_BASE_URL", "https://canvas.vt.edu").rstrip("/"),
        token=os.environ.get("CANVAS_TOKEN", ""),
        user_tz=os.environ.get("TZ", "America/New_York"),
        user_agent=os.environ.get("CANVAS_UA", "canvas-tui/1.0 (textual)"),
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
        "past_hours": "past_hours",
        "refresh_cooldown": "refresh_cooldown",
        "auto_refresh_sec": "auto_refresh_sec",
        "http_timeout": "http_timeout",
        "max_retries": "max_retries",
        "download_dir": "download_dir",
        "calendar_backend": "calendar_backend",
        "google_credentials_path": "google_credentials_path",
        "google_token_path": "google_token_path",
        "ical_path": "ical_path",
        "ical_write_path": "ical_write_path",
        "use_ai_reranker": "use_ai_reranker",
        "model_path": "model_path",
        "default_block_min": "default_block_min",
        "open_after_dl": "open_after_dl",
        "calcurse_import": "calcurse_import",
        "calendar_backend": "calendar_backend",
        "google_credentials_path": "google_credentials_path",
        "google_token_path": "google_token_path",
        "ical_path": "ical_path",
        "ical_write_path": "ical_write_path",
        "use_ai_reranker": "use_ai_reranker",
        "model_path": "model_path",
        "llm_endpoint": "llm_endpoint",
        "llm_model": "llm_model",
        "llm_api_key": "llm_api_key",
        "agent_max_turns": "agent_max_turns",
        "ann_past_days": "ann_past_days",
        "ann_future_days": "ann_future_days",
        # Support the typo variant for backwards compat
        "ann_futuredays": "ann_future_days",
        # Appearance / layout
        "theme": "theme",
        "sidebar_position": "sidebar_position",
        "sidebar_width": "sidebar_width",
    }

    for file_key, attr_name in _FIELD_MAP.items():
        if file_key in file_cfg:
            raw = file_cfg[file_key]
            current = getattr(cfg, attr_name)
            try:
                if isinstance(current, bool):
                    if isinstance(raw, bool):
                        setattr(cfg, attr_name, raw)
                    else:
                        setattr(cfg, attr_name, str(raw).lower() in ("1", "true", "yes"))
                elif isinstance(current, int):
                    setattr(cfg, attr_name, int(raw))
                elif isinstance(current, float):
                    setattr(cfg, attr_name, float(raw))
                elif isinstance(current, str):
                    setattr(cfg, attr_name, str(raw))
                else:
                    setattr(cfg, attr_name, raw)
            except (ValueError, TypeError):
                pass  # Skip bad values

    # Keybindings section: dict[str, str]
    raw_kb = file_cfg.get("keybindings")
    if isinstance(raw_kb, dict):
        cfg.keybindings = {str(k): str(v) for k, v in raw_kb.items() if k and v}

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


def _config_to_toml(cfg: Config) -> str:
    """Serialize user-editable config fields to TOML text (no external deps)."""

    def _toml_val(v: Any) -> str:
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, str):
            # json.dumps covers backslash, double-quote, and all control chars
            return json.dumps(v)
        return str(v)

    scalar_fields: list[tuple[str, Any]] = [
        ("days_ahead", cfg.days_ahead),
        ("past_hours", cfg.past_hours),
        ("http_timeout", cfg.http_timeout),
        ("max_retries", cfg.max_retries),
        ("refresh_cooldown", cfg.refresh_cooldown),
        ("auto_refresh_sec", cfg.auto_refresh_sec),
        ("default_block_min", cfg.default_block_min),
        ("open_after_dl", cfg.open_after_dl),
        ("calcurse_import", cfg.calcurse_import),
        ("ann_past_days", cfg.ann_past_days),
        ("ann_future_days", cfg.ann_future_days),
        ("theme", cfg.theme),
        ("sidebar_position", cfg.sidebar_position),
        ("sidebar_width", cfg.sidebar_width),
    ]

    lines = ["# Canvas TUI configuration — auto-generated by settings screen", ""]
    for key, val in scalar_fields:
        lines.append(f"{key} = {_toml_val(val)}")

    if cfg.download_dir is not None:
        lines.append(f"download_dir = {_toml_val(cfg.download_dir)}")

    if cfg.keybindings:
        lines.append("")
        lines.append("[keybindings]")
        for action, key in sorted(cfg.keybindings.items()):
            lines.append(f'"{action}" = {_toml_val(key)}')

    lines.append("")
    return "\n".join(lines)
