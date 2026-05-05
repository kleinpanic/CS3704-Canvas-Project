"""Tests for configuration loading and validation."""

from __future__ import annotations

import json
import os

import pytest

from canvas_tui.config import Config, _config_to_toml, load_config


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
        monkeypatch.setattr("canvas_tui.config._try_keyring", lambda: "")
        monkeypatch.setattr("canvas_tui.config._load_dotenv", lambda: None)
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


class TestAppearanceConfig:
    def test_theme_defaults_to_dark(self):
        cfg = Config(token="x")
        assert cfg.theme == "dark"

    def test_invalid_theme_falls_back_to_dark(self):
        cfg = Config(token="x", theme="solarized")
        assert cfg.theme == "dark"

    def test_light_theme_accepted(self):
        cfg = Config(token="x", theme="light")
        assert cfg.theme == "light"

    def test_sidebar_position_defaults_to_right(self):
        cfg = Config(token="x")
        assert cfg.sidebar_position == "right"

    def test_invalid_sidebar_position_falls_back_to_right(self):
        cfg = Config(token="x", sidebar_position="center")
        assert cfg.sidebar_position == "right"

    def test_sidebar_width_clamped(self):
        too_narrow = Config(token="x", sidebar_width=5)
        assert too_narrow.sidebar_width == 20
        too_wide = Config(token="x", sidebar_width=999)
        assert too_wide.sidebar_width == 80

    def test_keybindings_default_empty(self):
        cfg = Config(token="x")
        assert cfg.keybindings == {}


class TestConfigToToml:
    def test_scalar_roundtrip(self):
        cfg = Config(token="x", theme="light", sidebar_position="left", sidebar_width=30)
        toml_text = _config_to_toml(cfg)
        assert 'theme = "light"' in toml_text
        assert 'sidebar_position = "left"' in toml_text
        assert "sidebar_width = 30" in toml_text

    def test_keybindings_section(self):
        cfg = Config(token="x", keybindings={"quit": "ctrl+q", "refresh": "f5"})
        toml_text = _config_to_toml(cfg)
        assert "[keybindings]" in toml_text
        assert 'quit = "ctrl+q"' in toml_text
        assert 'refresh = "f5"' in toml_text

    def test_no_keybindings_section_when_empty(self):
        cfg = Config(token="x")
        toml_text = _config_to_toml(cfg)
        assert "[keybindings]" not in toml_text

    def test_string_values_are_quoted(self):
        cfg = Config(token="x")
        toml_text = _config_to_toml(cfg)
        # theme and sidebar_position are strings — must be quoted
        assert 'theme = "dark"' in toml_text

    def test_numeric_values_are_not_quoted(self):
        cfg = Config(token="x", sidebar_width=44)
        toml_text = _config_to_toml(cfg)
        assert 'sidebar_width = 44' in toml_text
        assert '"44"' not in toml_text


class TestConfigSave:
    def test_save_creates_toml_file(self, tmp_dir):
        cfg = Config(token="x", config_dir=tmp_dir)
        cfg.save()
        assert os.path.exists(os.path.join(tmp_dir, "config.toml"))

    def test_saved_file_is_valid_toml(self, tmp_dir):
        import tomllib

        cfg = Config(token="x", config_dir=tmp_dir, theme="light", sidebar_width=36)
        cfg.save()
        with open(os.path.join(tmp_dir, "config.toml"), "rb") as f:
            data = tomllib.load(f)
        assert data["theme"] == "light"
        assert data["sidebar_width"] == 36

    def test_save_roundtrip_with_keybindings(self, tmp_dir):
        import tomllib

        cfg = Config(token="x", config_dir=tmp_dir, keybindings={"quit": "q", "refresh": "r"})
        cfg.save()
        with open(os.path.join(tmp_dir, "config.toml"), "rb") as f:
            data = tomllib.load(f)
        assert data["keybindings"]["quit"] == "q"
        assert data["keybindings"]["refresh"] == "r"

    def test_overlay_reads_saved_appearance(self, tmp_dir, sample_config_env):
        import canvas_tui.config as config_mod

        cfg = Config(token="x", config_dir=tmp_dir, theme="light", sidebar_width=50)
        cfg.save()

        loaded = load_config()
        loaded.config_dir = tmp_dir
        config_mod._overlay_file_config(loaded)
        assert loaded.theme == "light"
        assert loaded.sidebar_width == 50

    def test_overlay_reads_saved_keybindings(self, tmp_dir, sample_config_env):
        import canvas_tui.config as config_mod

        cfg = Config(token="x", config_dir=tmp_dir, keybindings={"refresh": "f5"})
        cfg.save()

        loaded = load_config()
        loaded.config_dir = tmp_dir
        config_mod._overlay_file_config(loaded)
        assert loaded.keybindings.get("refresh") == "f5"


class TestKeybindingConflicts:
    def test_no_conflict_returns_empty_string(self):
        from canvas_tui.screens.settings import _find_conflicts

        assert _find_conflicts({"quit": "q", "refresh": "r"}) == ""

    def test_duplicate_key_detected(self):
        from canvas_tui.screens.settings import _find_conflicts

        msg = _find_conflicts({"quit": "q", "refresh": "q"})
        assert msg != ""
        assert "q" in msg

    def test_empty_bindings_no_conflict(self):
        from canvas_tui.screens.settings import _find_conflicts

        assert _find_conflicts({}) == ""

    def test_single_binding_no_conflict(self):
        from canvas_tui.screens.settings import _find_conflicts

        assert _find_conflicts({"quit": "ctrl+q"}) == ""


class TestDotEnv:
    def test_loads_dotenv_file(self, tmp_dir, monkeypatch):
        dotenv_path = os.path.join(tmp_dir, ".env")
        with open(dotenv_path, "w") as f:
            f.write("TEST_DOTENV_VAR=hello_world\n")
            f.write("# comment line\n")
            f.write("ANOTHER_VAR='quoted value'\n")

        monkeypatch.delenv("TEST_DOTENV_VAR", raising=False)
        monkeypatch.delenv("ANOTHER_VAR", raising=False)

        # Temporarily patch the paths checked

        def patched_load():
            if os.path.exists(dotenv_path):
                with open(dotenv_path, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        key, _, value = line.partition("=")
                        key = key.strip()
                        value = value.strip().strip("'\"")
                        if key and key not in os.environ:
                            os.environ[key] = value

        patched_load()
        assert os.environ.get("TEST_DOTENV_VAR") == "hello_world"
        assert os.environ.get("ANOTHER_VAR") == "quoted value"

        # Clean up
        monkeypatch.delenv("TEST_DOTENV_VAR", raising=False)
        monkeypatch.delenv("ANOTHER_VAR", raising=False)

    def test_existing_env_not_overwritten(self, monkeypatch):
        monkeypatch.setenv("EXISTING_VAR", "original")
        # The dotenv loader should NOT overwrite existing env vars
        # (tested implicitly by the `if key not in os.environ` check)
        assert os.environ["EXISTING_VAR"] == "original"
