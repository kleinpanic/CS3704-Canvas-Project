"""Tests for CLI argument parsing."""

from __future__ import annotations

import pytest

from canvas_tui.cli import parse_args


class TestParseArgs:
    def test_defaults(self):
        args = parse_args([])
        assert args.no_cache is False
        assert args.debug is False
        assert args.export_ics is False
        assert args.prefetch is False
        assert args.prefetch_daemon is False
        assert args.prefetch_interval == 300
        assert args.prefetch_no_grades is False
        assert args.theme == "dark"
        assert args.config is None

    def test_no_cache(self):
        args = parse_args(["--no-cache"])
        assert args.no_cache is True

    def test_debug(self):
        args = parse_args(["--debug"])
        assert args.debug is True

    def test_export_ics(self):
        args = parse_args(["--export-ics"])
        assert args.export_ics is True

    def test_prefetch(self):
        args = parse_args(["--prefetch"])
        assert args.prefetch is True

    def test_prefetch_daemon_options(self):
        args = parse_args(["--prefetch-daemon", "--prefetch-interval", "120", "--prefetch-no-grades"])
        assert args.prefetch_daemon is True
        assert args.prefetch_interval == 120
        assert args.prefetch_no_grades is True

    def test_theme_light(self):
        args = parse_args(["--theme", "light"])
        assert args.theme == "light"

    def test_days_ahead(self):
        args = parse_args(["--days-ahead", "14"])
        assert args.days_ahead == 14

    def test_past_hours(self):
        args = parse_args(["--past-hours", "48"])
        assert args.past_hours == 48

    def test_config_path(self):
        args = parse_args(["--config", "/tmp/myconfig"])
        assert args.config == "/tmp/myconfig"

    def test_version(self):
        with pytest.raises(SystemExit):
            parse_args(["--version"])
