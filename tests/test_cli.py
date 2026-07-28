"""Tests for CLI argument parsing."""

from __future__ import annotations

import pytest

from structured_data_validator.cli import parse_args


class TestParseArgs:
    """Tests for parse_args."""

    def test_basic_url(self) -> None:
        args = parse_args(["validate", "https://example.com"])
        assert args.url == "https://example.com"
        assert args.command == "validate"
        assert args.sitemap is False
        assert args.depth == 3
        assert args.max_pages == 100

    def test_sitemap_flag(self) -> None:
        args = parse_args(["validate", "https://example.com/sitemap.xml", "--sitemap"])
        assert args.sitemap is True

    def test_custom_depth(self) -> None:
        args = parse_args(["validate", "https://example.com", "--depth", "5"])
        assert args.depth == 5

    def test_custom_max_pages(self) -> None:
        args = parse_args(["validate", "https://example.com", "--max-pages", "50"])
        assert args.max_pages == 50

    def test_output_json(self) -> None:
        args = parse_args(["validate", "https://example.com", "--output", "json"])
        assert args.output == "json"

    def test_output_csv(self) -> None:
        args = parse_args(["validate", "https://example.com", "-o", "csv"])
        assert args.output == "csv"

    def test_severity_filter(self) -> None:
        args = parse_args(["validate", "https://example.com", "--severity", "error"])
        assert args.severity == "error"

    def test_type_filter(self) -> None:
        args = parse_args(["validate", "https://example.com", "--type", "Product,Article"])
        assert args.schema_types == "Product,Article"

    def test_no_google(self) -> None:
        args = parse_args(["validate", "https://example.com", "--no-google"])
        assert args.no_google is True

    def test_no_robots(self) -> None:
        args = parse_args(["validate", "https://example.com", "--no-robots"])
        assert args.no_robots is True

    def test_cross_domain(self) -> None:
        args = parse_args(["validate", "https://example.com", "--cross-domain"])
        assert args.cross_domain is True

    def test_verbose_flag(self) -> None:
        args = parse_args(["validate", "https://example.com", "--verbose"])
        assert args.verbose is True

    def test_quiet_flag(self) -> None:
        args = parse_args(["validate", "https://example.com", "-q"])
        assert args.quiet is True

    def test_concurrency(self) -> None:
        args = parse_args(["validate", "https://example.com", "--concurrency", "10"])
        assert args.concurrency == 10

    def test_timeout(self) -> None:
        args = parse_args(["validate", "https://example.com", "--timeout", "60"])
        assert args.timeout == 60.0

    def test_delay(self) -> None:
        args = parse_args(["validate", "https://example.com", "--delay", "1.0"])
        assert args.delay == 1.0

    def test_config_command(self) -> None:
        args = parse_args(["config", "--output", "test.yaml"])
        assert args.command == "config"
        assert args.output == "test.yaml"

    def test_no_command_exits(self) -> None:
        with pytest.raises(SystemExit):
            parse_args([])
