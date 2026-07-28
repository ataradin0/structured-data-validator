"""Tests for data models."""

from __future__ import annotations

import json

from structured_data_validator.models import (
    IssueType,
    PageResult,
    ReportSummary,
    SchemaFormat,
    Severity,
    StructuredDataItem,
    ValidationResult,
)


class TestStructuredDataItem:
    """Tests for StructuredDataItem model."""

    def test_basic_json_ld_item(self) -> None:
        item = StructuredDataItem(
            schema_format=SchemaFormat.JSON_LD,
            schema_type="Product",
            properties={"name": "Widget", "price": "9.99"},
        )
        assert item.schema_format == SchemaFormat.JSON_LD
        assert item.schema_type == "Product"
        assert item.properties["name"] == "Widget"
        assert item.is_graph_item is False

    def test_microdata_item(self) -> None:
        item = StructuredDataItem(
            schema_format=SchemaFormat.MICRODATA,
            schema_type="Article",
            properties={"headline": "Test Article"},
            source_url="https://example.com/article",
        )
        assert item.schema_format == SchemaFormat.MICRODATA
        assert item.source_url == "https://example.com/article"

    def test_rdfa_item(self) -> None:
        item = StructuredDataItem(
            schema_format=SchemaFormat.RDFA,
            schema_type="Organization",
            properties={"name": "Acme Corp"},
        )
        assert item.schema_format == SchemaFormat.RDFA

    def test_graph_item_flag(self) -> None:
        item = StructuredDataItem(
            schema_format=SchemaFormat.JSON_LD,
            schema_type="WebPage",
            is_graph_item=True,
        )
        assert item.is_graph_item is True

    def test_serialization_roundtrip(self) -> None:
        item = StructuredDataItem(
            schema_format=SchemaFormat.JSON_LD,
            schema_type="Product",
            properties={"name": "Test"},
            context="https://schema.org",
        )
        data = json.loads(item.model_dump_json())
        restored = StructuredDataItem.model_validate(data)
        assert restored.schema_type == item.schema_type
        assert restored.context == item.context


class TestValidationResult:
    """Tests for ValidationResult model."""

    def test_error_result(self) -> None:
        result = ValidationResult(
            issue_type=IssueType.MISSING_REQUIRED_PROPERTY,
            severity=Severity.ERROR,
            message="Missing required property 'name'",
            path="Product",
            schema_ref="https://schema.org/Product",
        )
        assert result.severity == Severity.ERROR
        assert result.issue_type == IssueType.MISSING_REQUIRED_PROPERTY

    def test_warning_result(self) -> None:
        result = ValidationResult(
            issue_type=IssueType.DEPRECATED_TYPE,
            severity=Severity.WARNING,
            message="Schema type 'Review' is deprecated",
        )
        assert result.severity == Severity.WARNING
        assert result.path is None

    def test_all_issue_types_distinct(self) -> None:
        values = [t.value for t in IssueType]
        assert len(values) == len(set(values)), "Duplicate IssueType values"


class TestPageResult:
    """Tests for PageResult model."""

    def test_empty_page(self) -> None:
        page = PageResult(url="https://example.com")
        assert page.total_issues == 0
        assert page.has_errors is False
        assert page.fetch_error is None

    def test_page_with_errors(self) -> None:
        error = ValidationResult(
            issue_type=IssueType.MISSING_SCHEMA_TYPE,
            severity=Severity.ERROR,
            message="No @type found",
        )
        page = PageResult(url="https://example.com", errors=[error])
        assert page.has_errors is True
        assert page.total_issues == 1

    def test_page_with_mixed_issues(self) -> None:
        err = ValidationResult(
            issue_type=IssueType.MALFORMED_JSON_LD,
            severity=Severity.ERROR,
            message="Invalid JSON",
        )
        warn = ValidationResult(
            issue_type=IssueType.DEPRECATED_TYPE,
            severity=Severity.WARNING,
            message="Deprecated type",
        )
        info = ValidationResult(
            issue_type=IssueType.UNSUPPORTED_TYPE,
            severity=Severity.INFO,
            message="Unknown type",
        )
        page = PageResult(url="https://example.com", errors=[err], warnings=[warn], info=[info])
        assert page.total_issues == 3
        assert page.has_errors is True

    def test_page_with_fetch_error(self) -> None:
        page = PageResult(url="https://example.com", fetch_error="ConnectionTimeout")
        assert page.fetch_error == "ConnectionTimeout"

    def test_page_with_structured_data(self) -> None:
        item = StructuredDataItem(
            schema_format=SchemaFormat.JSON_LD,
            schema_type="Product",
            properties={"name": "Widget"},
        )
        page = PageResult(url="https://example.com", structured_data=[item])
        assert len(page.structured_data) == 1
        assert page.structured_data[0].schema_type == "Product"

    def test_serialization_roundtrip(self) -> None:
        item = StructuredDataItem(
            schema_format=SchemaFormat.JSON_LD,
            schema_type="Article",
            properties={"headline": "Test"},
        )
        err = ValidationResult(
            issue_type=IssueType.MISSING_NAME,
            severity=Severity.ERROR,
            message="Missing name",
        )
        page = PageResult(url="https://example.com", structured_data=[item], errors=[err])
        data = json.loads(page.model_dump_json())
        restored = PageResult.model_validate(data)
        assert restored.url == page.url
        assert len(restored.structured_data) == 1
        assert len(restored.errors) == 1


class TestReportSummary:
    """Tests for ReportSummary model."""

    def test_empty_summary(self) -> None:
        summary = ReportSummary()
        assert summary.total_pages == 0
        assert summary.pass_rate == 0.0

    def test_summary_with_counts(self) -> None:
        summary = ReportSummary(
            total_pages=10,
            pages_with_schema=8,
            pages_without_schema=2,
            pages_with_errors=3,
            total_schemas=15,
            total_errors=5,
            total_warnings=3,
            schema_type_counts={"Product": 5, "Article": 3},
            format_counts={"json-ld": 12, "microdata": 3},
            pass_rate=70.0,
        )
        assert summary.total_pages == 10
        assert summary.pass_rate == 70.0
        assert summary.schema_type_counts["Product"] == 5

    def test_summary_serialization(self) -> None:
        summary = ReportSummary(total_pages=5, pass_rate=80.0)
        data = json.loads(summary.model_dump_json())
        assert data["total_pages"] == 5
        assert data["pass_rate"] == 80.0
