"""Tests for structured data validation engine."""

from __future__ import annotations

from structured_data_validator.models import (
    IssueType,
    SchemaFormat,
    Severity,
    StructuredDataItem,
)
from structured_data_validator.validator import validate_item, validate_page


def _make_item(
    schema_type: str = "Product",
    properties: dict | None = None,
    schema_format: SchemaFormat = SchemaFormat.JSON_LD,
) -> StructuredDataItem:
    """Helper to create a StructuredDataItem for testing."""
    return StructuredDataItem(
        schema_format=schema_format,
        schema_type=schema_type,
        properties=properties or {},
    )


class TestValidateItem:
    """Tests for validate_item."""

    def test_valid_product(self) -> None:
        item = _make_item("Product", {"name": "Widget", "image": "https://example.com/img.jpg", "offers": {"price": "10.00"}})
        issues = validate_item(item)
        error_types = {i.issue_type for i in issues if i.severity == Severity.ERROR}
        assert IssueType.MISSING_REQUIRED_PROPERTY not in error_types

    def test_product_missing_name(self) -> None:
        item = _make_item("Product", {"price": "10.00"})
        issues = validate_item(item)
        error_types = {i.issue_type for i in issues if i.severity == Severity.ERROR}
        assert IssueType.MISSING_REQUIRED_PROPERTY in error_types

    def test_product_missing_image_warning(self) -> None:
        item = _make_item("Product", {"name": "Widget"})
        issues = validate_item(item)
        warn_types = {i.issue_type for i in issues if i.severity == Severity.WARNING}
        assert IssueType.MISSING_IMAGE in warn_types

    def test_product_missing_offers_warning(self) -> None:
        item = _make_item("Product", {"name": "Widget", "image": "https://example.com/img.jpg"})
        issues = validate_item(item)
        warn_types = {i.issue_type for i in issues if i.severity == Severity.WARNING}
        assert IssueType.MISSING_REQUIRED_PROPERTY in warn_types

    def test_malformed_jsonld(self) -> None:
        item = _make_item("MalformedJSON-LD")
        issues = validate_item(item)
        assert len(issues) == 1
        assert issues[0].issue_type == IssueType.MALFORMED_JSON_LD
        assert issues[0].severity == Severity.ERROR

    def test_missing_type(self) -> None:
        item = _make_item("Unknown")
        issues = validate_item(item)
        type_set = {i.issue_type for i in issues}
        assert IssueType.MISSING_SCHEMA_TYPE in type_set

    def test_empty_schema(self) -> None:
        item = _make_item("Product", {})
        issues = validate_item(item)
        type_set = {i.issue_type for i in issues}
        assert IssueType.EMPTY_SCHEMA in type_set

    def test_article_missing_required(self) -> None:
        item = _make_item("Article", {"name": "Test"})
        issues = validate_item(item)
        error_types = {i.issue_type for i in issues if i.severity == Severity.ERROR}
        assert IssueType.MISSING_REQUIRED_PROPERTY in error_types
        # Should flag missing headline, author, datePublished, image
        error_msgs = [i.message for i in issues if i.severity == Severity.ERROR]
        assert any("headline" in m for m in error_msgs)

    def test_article_missing_image_warning(self) -> None:
        item = _make_item("Article", {
            "headline": "Test", "author": "Me", "datePublished": "2026-01-01",
        })
        issues = validate_item(item)
        warn_types = {i.issue_type for i in issues if i.severity == Severity.WARNING}
        assert IssueType.MISSING_IMAGE in warn_types

    def test_offer_missing_price(self) -> None:
        item = _make_item("Offer", {})
        issues = validate_item(item)
        error_types = {i.issue_type for i in issues if i.severity == Severity.ERROR}
        assert IssueType.MISSING_REQUIRED_PROPERTY in error_types

    def test_faq_page_missing_main_entity(self) -> None:
        item = _make_item("FAQPage", {})
        issues = validate_item(item)
        error_types = {i.issue_type for i in issues if i.severity == Severity.ERROR}
        assert IssueType.MISSING_REQUIRED_PROPERTY in error_types

    def test_breadcrumb_list_missing_elements(self) -> None:
        item = _make_item("BreadcrumbList", {})
        issues = validate_item(item)
        error_types = {i.issue_type for i in issues if i.severity == Severity.ERROR}
        assert IssueType.MISSING_REQUIRED_PROPERTY in error_types

    def test_invalid_url_property(self) -> None:
        item = _make_item("Product", {"name": "Widget", "url": "not-a-url"})
        issues = validate_item(item)
        warn_types = {i.issue_type for i in issues if i.severity == Severity.WARNING}
        assert IssueType.INVALID_URL in warn_types

    def test_valid_url_property(self) -> None:
        item = _make_item("Product", {"name": "Widget", "url": "https://example.com/widget"})
        issues = validate_item(item)
        url_issues = [i for i in issues if i.issue_type == IssueType.INVALID_URL]
        assert len(url_issues) == 0

    def test_invalid_datetime(self) -> None:
        item = _make_item("Article", {
            "headline": "Test",
            "author": "Me",
            "datePublished": "January 1, 2026",
            "image": "https://example.com/img.jpg",
        })
        issues = validate_item(item)
        warn_types = {i.issue_type for i in issues if i.severity == Severity.WARNING}
        assert IssueType.INVALID_PROPERTY_TYPE in warn_types

    def test_valid_datetime(self) -> None:
        item = _make_item("Article", {
            "headline": "Test",
            "author": "Me",
            "datePublished": "2026-01-01",
            "image": "https://example.com/img.jpg",
        })
        issues = validate_item(item)
        date_issues = [i for i in issues if "ISO 8601" in i.message]
        assert len(date_issues) == 0

    def test_unsupported_type_info(self) -> None:
        item = _make_item("RandomCustomType", {"name": "Test"})
        issues = validate_item(item)
        info_types = {i.issue_type for i in issues if i.severity == Severity.INFO}
        assert IssueType.UNSUPPORTED_TYPE in info_types

    def test_google_guidelines_disabled(self) -> None:
        item = _make_item("Product", {})
        issues = validate_item(item, google_guidelines=False)
        # Should still check basic stuff but not Google-specific requirements
        error_types = {i.issue_type for i in issues if i.severity == Severity.ERROR}
        # Missing 'name' is a Google guideline check
        assert IssueType.MISSING_REQUIRED_PROPERTY not in error_types

    def test_event_missing_required(self) -> None:
        item = _make_item("Event", {})
        issues = validate_item(item)
        error_types = {i.issue_type for i in issues if i.severity == Severity.ERROR}
        assert IssueType.MISSING_REQUIRED_PROPERTY in error_types

    def test_job_posting_missing_required(self) -> None:
        item = _make_item("JobPosting", {})
        issues = validate_item(item)
        error_types = {i.issue_type for i in issues if i.severity == Severity.ERROR}
        assert IssueType.MISSING_REQUIRED_PROPERTY in error_types

    def test_valid_organization(self) -> None:
        item = _make_item("Organization", {"name": "Acme Corp"})
        issues = validate_item(item)
        error_types = {i.issue_type for i in issues if i.severity == Severity.ERROR}
        assert len(error_types) == 0

    def test_recipe_missing_name(self) -> None:
        item = _make_item("Recipe", {"image": "https://example.com/food.jpg"})
        issues = validate_item(item)
        error_types = {i.issue_type for i in issues if i.severity == Severity.ERROR}
        assert IssueType.MISSING_REQUIRED_PROPERTY in error_types


class TestValidatePage:
    """Tests for validate_page."""

    def test_empty_page(self) -> None:
        errors, warnings, info = validate_page([])
        assert len(errors) == 0
        assert len(warnings) == 0
        assert len(info) == 0

    def test_page_with_valid_items(self) -> None:
        item = _make_item("Organization", {"name": "Acme"})
        errors, warnings, info = validate_page([item])
        error_issues = [e for e in errors if e.issue_type != IssueType.UNSUPPORTED_TYPE]
        assert len(error_issues) == 0

    def test_conflicting_schemas_detected(self) -> None:
        item1 = _make_item("Product", {"name": "Widget A"})
        item2 = _make_item("Product", {"name": "Widget B"})
        errors, warnings, info = validate_page([item1, item2])
        conflict_warnings = [w for w in warnings if w.issue_type == IssueType.CONFLICTING_SCHEMA]
        assert len(conflict_warnings) == 1
        assert "Multiple" in conflict_warnings[0].message

    def test_no_conflict_different_types(self) -> None:
        item1 = _make_item("Product", {"name": "Widget"})
        item2 = _make_item("Organization", {"name": "Acme"})
        _, warnings, _ = validate_page([item1, item2])
        conflict_warnings = [w for w in warnings if w.issue_type == IssueType.CONFLICTING_SCHEMA]
        assert len(conflict_warnings) == 0

    def test_page_issues_by_severity(self) -> None:
        # Malformed JSON-LD = error, unsupported type = info
        item1 = _make_item("MalformedJSON-LD")
        item2 = _make_item("RandomType", {"name": "Test"})
        errors, warnings, info = validate_page([item1, item2])
        assert len(errors) >= 1
        assert len(info) >= 1
