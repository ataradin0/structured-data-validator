"""Data models for structured data validation."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class Severity(str, Enum):
    """Issue severity level."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class SchemaFormat(str, Enum):
    """Structured data format type."""

    JSON_LD = "json-ld"
    MICRODATA = "microdata"
    RDFA = "rdfa"


class IssueType(str, Enum):
    """Category of validation issue."""

    MISSING_REQUIRED_PROPERTY = "missing_required_property"
    INVALID_PROPERTY_TYPE = "invalid_property_type"
    DEPRECATED_TYPE = "deprecated_type"
    DEPRECATED_PROPERTY = "deprecated_property"
    CONFLICTING_SCHEMA = "conflicting_schema"
    MALFORMED_JSON_LD = "malformed_json_ld"
    EMPTY_SCHEMA = "empty_schema"
    MISSING_SCHEMA_TYPE = "missing_schema_type"
    INVALID_URL = "invalid_url"
    MISSING_NAME = "missing_name"
    MISSING_IMAGE = "missing_image"
    NON_INDEXABLE_SCHEMA = "non_indexable_schema"
    UNSUPPORTED_TYPE = "unsupported_type"
    GRAPH_ITEM_ERROR = "graph_item_error"


class StructuredDataItem(BaseModel):
    """A single piece of structured data extracted from a page."""

    schema_format: SchemaFormat
    schema_type: str  # e.g. "Product", "Article", "FAQPage"
    properties: dict[str, Any] = Field(default_factory=dict)
    raw: Any = None  # Original extracted data
    source_url: str = ""
    context: Optional[str] = None  # @context value for JSON-LD
    is_graph_item: bool = False  # Part of a @graph array


class ValidationResult(BaseModel):
    """A single validation issue found for a structured data item."""

    issue_type: IssueType
    severity: Severity
    message: str
    path: Optional[str] = None  # Property path, e.g. "author.name"
    schema_ref: Optional[str] = None  # Reference to Schema.org type


class PageResult(BaseModel):
    """Validation results for a single page."""

    url: str
    structured_data: list[StructuredDataItem] = Field(default_factory=list)
    errors: list[ValidationResult] = Field(default_factory=list)
    warnings: list[ValidationResult] = Field(default_factory=list)
    info: list[ValidationResult] = Field(default_factory=list)
    fetch_error: Optional[str] = None

    @property
    def total_issues(self) -> int:
        """Total number of issues across all severities."""
        return len(self.errors) + len(self.warnings) + len(self.info)

    @property
    def has_errors(self) -> bool:
        """True if there are any error-severity issues."""
        return len(self.errors) > 0


class ReportSummary(BaseModel):
    """Aggregate statistics across all crawled pages."""

    total_pages: int = 0
    pages_with_schema: int = 0
    pages_without_schema: int = 0
    pages_with_errors: int = 0
    total_schemas: int = 0
    total_errors: int = 0
    total_warnings: int = 0
    total_info: int = 0
    schema_type_counts: dict[str, int] = Field(default_factory=dict)
    format_counts: dict[str, int] = Field(default_factory=dict)
    pass_rate: float = 0.0  # Percentage of pages with no errors
