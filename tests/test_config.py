"""Tests for configuration loading and validation."""

from __future__ import annotations

import json
import os

import pytest

from canvas_tui.config import Config, load_config


class TestConfig:
    def test_defaults(self):
        cfg = Config(token="test")
        assert cfg.days_ahead == 7
        assert cfg.past_hours == 72
        assert cfg.http_timeout == 20
        assert cfg.max_retries == 5

    def test_validation_clamps_values(self):
        cfg = Config(token="test", days_ahead=-5, past_hours=99999, http_timeout=0)
        assert cfg.days_ahead >= 1
        assert cfg.past_hours <= 8760
        assert cfg.http_timeout >= 5

    def test_base_url_strips_trailing_slash(self):
        cfg = Config(token="test", base_url="https://canvas.vt.edu/")
        assert not cfg.base_url.endswith("/")

    def test_state_path(self):
        cfg = Config(token="test", export_dir="/tmp/test-canvas")
        assert cfg.state_path == "/tmp/test-canvas/state.json"

    def test_config_json_path(self):
        cfg = Config(token="test", config_dir="/tmp/cfg")
        assert cfg.config_json == "/tmp/cfg/config.json"


class TestLoadConfig:
    def test_loads_from_env(self, sample_config_env):
        cfg = load_config()
        assert cfg.token == "test-token-12345"
        assert cfg.base_url == "https://canvas.example.edu"

    def test_exits_without_token(self, monkeypatch):
        monkeypatch.delenv("CANVAS_TOKEN", raising=False)
        with pytest.raises(SystemExit):
            load_config()

    def test_overlay_json_config(self, sample_config_env, tmp_dir):
        # Write a JSON config file
        cfg_dir = os.path.join(tmp_dir, "config")
        os.makedirs(cfg_dir, exist_ok=True)
        cfg_path = os.path.join(cfg_dir, "config.json")
        with open(cfg_path, "w") as f:
            json.dump({"days_ahead": 14, "ann_future_days": 30}, f)

        import canvas_tui.config as config_mod
        cfg = load_config()
        # Overlay from the test config dir
        config_mod._overlay_file_config(cfg)
        # Now overlay manually with the right paths
        file_cfg = config_mod._read_config_file(
            os.path.join(cfg_dir, "config.toml"),
            cfg_path,
        )
        assert file_cfg.get("days_ahead") == 14
        assert file_cfg.get("ann_future_days") == 30

    def test_overlay_handles_legacy_ann_futuredays(self, sample_config_env, tmp_dir):
        """Test backward compat for the ann_futuredays typo."""
        cfg_dir = os.path.join(tmp_dir, "config")
        os.makedirs(cfg_dir, exist_ok=True)
        with open(os.path.join(cfg_dir, "config.json"), "w") as f:
            json.dump({"ann_futuredays": 21}, f)

        import canvas_tui.config as config_mod
        cfg = load_config()
        cfg.config_dir = cfg_dir
        config_mod._overlay_file_config(cfg)
        assert cfg.ann_future_days == 21
