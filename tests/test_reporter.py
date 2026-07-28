"""Tests for report generation."""

from __future__ import annotations

import json

from structured_data_validator.models import (
    IssueType,
    PageResult,
    SchemaFormat,
    Severity,
    StructuredDataItem,
    ValidationResult,
)
from structured_data_validator.reporter import (
    build_report_summary,
    report_summary_to_text,
    report_to_csv,
    report_to_json,
)


def _make_page(
    url: str = "https://example.com",
    items: list[StructuredDataItem] | None = None,
    errors: list[ValidationResult] | None = None,
    warnings: list[ValidationResult] | None = None,
) -> PageResult:
    return PageResult(
        url=url,
        structured_data=items or [],
        errors=errors or [],
        warnings=warnings or [],
    )


class TestBuildReportSummary:
    """Tests for build_report_summary."""

    def test_empty_pages(self) -> None:
        summary = build_report_summary([])
        assert summary.total_pages == 0

    def test_basic_summary(self) -> None:
        item = StructuredDataItem(
            schema_format=SchemaFormat.JSON_LD,
            schema_type="Product",
            properties={"name": "Widget"},
        )
        pages = [_make_page(items=[item])]
        summary = build_report_summary(pages)
        assert summary.total_pages == 1
        assert summary.pages_with_schema == 1
        assert summary.total_schemas == 1
        assert summary.schema_type_counts["Product"] == 1
        assert summary.format_counts["json-ld"] == 1

    def test_pass_rate(self) -> None:
        err = ValidationResult(
            issue_type=IssueType.MISSING_REQUIRED_PROPERTY,
            severity=Severity.ERROR,
            message="Missing name",
        )
        pages = [
            _make_page("https://example.com/1"),
            _make_page("https://example.com/2", errors=[err]),
        ]
        summary = build_report_summary(pages)
        assert summary.pages_with_errors == 1
        assert summary.pass_rate == 50.0

    def test_multiple_schema_types(self) -> None:
        items = [
            StructuredDataItem(schema_format=SchemaFormat.JSON_LD, schema_type="Product"),
            StructuredDataItem(schema_format=SchemaFormat.MICRODATA, schema_type="Organization"),
        ]
        pages = [_make_page(items=items)]
        summary = build_report_summary(pages)
        assert summary.total_schemas == 2
        assert summary.schema_type_counts["Product"] == 1
        assert summary.schema_type_counts["Organization"] == 1


class TestReportToJson:
    """Tests for report_to_json."""

    def test_valid_json(self) -> None:
        pages = [_make_page()]
        output = report_to_json(pages)
        data = json.loads(output)
        assert "summary" in data
        assert "pages" in data
        assert data["summary"]["total_pages"] == 1

    def test_pretty_print(self) -> None:
        pages = [_make_page()]
        pretty = report_to_json(pages, pretty=True)
        compact = report_to_json(pages, pretty=False)
        assert len(pretty) > len(compact)


class TestReportToCSV:
    """Tests for report_to_csv."""

    def test_csv_has_header(self) -> None:
        pages = [_make_page()]
        output = report_to_csv(pages)
        lines = output.strip().split("\n")
        assert "url" in lines[0]
        assert "severity" in lines[0]
        assert "issue_type" in lines[0]

    def test_csv_with_issues(self) -> None:
        err = ValidationResult(
            issue_type=IssueType.MISSING_REQUIRED_PROPERTY,
            severity=Severity.ERROR,
            message="Missing name",
        )
        pages = [_make_page(errors=[err])]
        output = report_to_csv(pages)
        lines = output.strip().split("\n")
        assert len(lines) == 2  # Header + 1 issue
        assert "missing_required_property" in lines[1]

    def test_csv_with_fetch_error(self) -> None:
        pages = [PageResult(url="https://example.com", fetch_error="Timeout")]
        output = report_to_csv(pages)
        assert "fetch_error" in output
        assert "Timeout" in output


class TestReportSummaryToText:
    """Tests for report_summary_to_text."""

    def test_basic_text(self) -> None:
        summary = build_report_summary([_make_page()])
        text = report_summary_to_text(summary)
        assert "Pages crawled" in text
        assert "1" in text

    def test_text_with_schema_types(self) -> None:
        item = StructuredDataItem(schema_format=SchemaFormat.JSON_LD, schema_type="Product")
        summary = build_report_summary([_make_page(items=[item])])
        text = report_summary_to_text(summary)
        assert "Product" in text
