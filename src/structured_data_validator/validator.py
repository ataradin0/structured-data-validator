"""Validation engine for structured data against Schema.org and Google guidelines."""

from __future__ import annotations

import logging
import re
from typing import Any

from .models import (
    IssueType,
    SchemaFormat,
    Severity,
    StructuredDataItem,
    ValidationResult,
)

logger = logging.getLogger(__name__)

# Schema.org types that Google supports for rich results
GOOGLE_RICH_RESULT_TYPES = {
    "Article",
    "NewsArticle",
    "BlogPosting",
    "Product",
    "Offer",
    "AggregateOffer",
    "FAQPage",
    "HowTo",
    "HowToStep",
    "BreadcrumbList",
    "ListItem",
    "Organization",
    "Person",
    "LocalBusiness",
    "Restaurant",
    "Review",
    "AggregateRating",
    "Event",
    "VideoObject",
    "ImageObject",
    "JobPosting",
    "Course",
    "Book",
    "Movie",
    "MusicAlbum",
    "MusicRecording",
    "Recipe",
    "SoftwareApplication",
    "WebPage",
    "WebSite",
    "SearchAction",
    "SiteNavigationElement",
    "ContactPage",
    "AboutPage",
    "ItemList",
    "ListItem",
    "Dataset",
    "SpecialAnnouncement",
    "ClaimReview",
    "EmployerAggregateRating",
}

# Required properties per Google rich result type
GOOGLE_REQUIRED_PROPERTIES: dict[str, list[str]] = {
    "Product": ["name"],
    "Offer": ["price", "priceCurrency"],
    "AggregateOffer": ["lowPrice"],
    "Article": ["headline", "author", "datePublished", "image"],
    "NewsArticle": ["headline", "author", "datePublished", "image"],
    "BlogPosting": ["headline", "author", "datePublished"],
    "FAQPage": [],  # Must have mainEntity with Question/Answer
    "HowTo": ["name", "step"],
    "BreadcrumbList": [],  # Must have itemListElement
    "Organization": ["name"],
    "LocalBusiness": ["name", "address"],
    "Event": ["name", "startDate", "location"],
    "VideoObject": ["name", "description", "thumbnailUrl", "uploadDate"],
    "JobPosting": ["title", "description", "datePosted", "hiringOrganization"],
    "Recipe": ["name", "image"],
    "Review": ["itemReviewed", "author"],
    "AggregateRating": ["ratingValue"],
    "Course": ["name", "description"],
    "Dataset": ["name", "description"],
    "SearchAction": ["target", "query-input"],
    "WebSite": ["name"],
    "ImageObject": ["contentUrl"],
}

# Deprecated Schema.org types
DEPRECATED_TYPES = {
    "EntryRating",
    "ratingValue",  # Not a type but commonly misused
    "PaymentChargeSpecification",
}

# URL properties that should be valid URLs
URL_PROPERTIES = {
    "url", "image", "logo", "thumbnailUrl", "contentUrl", "embedUrl",
    "sameAs", "mainEntityOfPage", "target", "href", "link",
}

# DateTime properties
DATETIME_PROPERTIES = {
    "datePublished", "dateModified", "dateCreated", "startDate", "endDate",
    "datePosted", "uploadDate", "expires",
}

# Valid URL pattern
URL_PATTERN = re.compile(
    r"^https?://"  # http:// or https://
    r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"  # domain
    r"localhost|"  # localhost
    r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  # IP
    r"(?::\d+)?(?:/?|[/?]\S+)$",
    re.IGNORECASE,
)


def validate_item(
    item: StructuredDataItem,
    google_guidelines: bool = True,
) -> list[ValidationResult]:
    """Validate a single structured data item.

    Args:
        item: The structured data item to validate.
        google_guidelines: Whether to check Google rich result guidelines.

    Returns:
        List of validation issues.
    """
    results: list[ValidationResult] = []

    # Check for missing/empty type
    if not item.schema_type or item.schema_type in ("Unknown", "MalformedJSON-LD"):
        if item.schema_type == "MalformedJSON-LD":
            results.append(
                ValidationResult(
                    issue_type=IssueType.MALFORMED_JSON_LD,
                    severity=Severity.ERROR,
                    message="JSON-LD block contains invalid JSON",
                    schema_ref=item.schema_type,
                )
            )
        else:
            results.append(
                ValidationResult(
                    issue_type=IssueType.MISSING_SCHEMA_TYPE,
                    severity=Severity.WARNING,
                    message="Structured data has no @type defined",
                )
            )
        return results

    # Check empty properties
    if not item.properties:
        results.append(
            ValidationResult(
                issue_type=IssueType.EMPTY_SCHEMA,
                severity=Severity.WARNING,
                message=f"Schema '{item.schema_type}' has no properties",
                schema_ref=item.schema_type,
            )
        )

    # Check deprecated types
    if item.schema_type in DEPRECATED_TYPES:
        results.append(
            ValidationResult(
                issue_type=IssueType.DEPRECATED_TYPE,
                severity=Severity.WARNING,
                message=f"Schema type '{item.schema_type}' is deprecated",
                schema_ref=item.schema_type,
            )
        )

    # Validate URL properties
    results.extend(_validate_url_properties(item))

    # Validate DateTime properties
    results.extend(_validate_datetime_properties(item))

    # Google rich result guidelines
    if google_guidelines:
        results.extend(_validate_google_guidelines(item))

    return results


def _validate_url_properties(item: StructuredDataItem) -> list[ValidationResult]:
    """Check that URL properties contain valid URLs.

    Args:
        item: Structured data item to check.

    Returns:
        List of validation issues for invalid URLs.
    """
    results: list[ValidationResult] = []

    for prop_name, prop_value in item.properties.items():
        if prop_name.lower() not in URL_PROPERTIES:
            continue
        if not isinstance(prop_value, str):
            continue
        if not prop_value.strip():
            continue
        if not URL_PATTERN.match(prop_value):
            results.append(
                ValidationResult(
                    issue_type=IssueType.INVALID_URL,
                    severity=Severity.WARNING,
                    message=f"Property '{prop_name}' has invalid URL: '{prop_value}'",
                    path=f"{item.schema_type}.{prop_name}",
                    schema_ref=item.schema_type,
                )
            )

    return results


def _validate_datetime_properties(item: StructuredDataItem) -> list[ValidationResult]:
    """Check that DateTime properties are in ISO 8601 format.

    Args:
        item: Structured data item to check.

    Returns:
        List of validation issues for invalid dates.
    """
    results: list[ValidationResult] = []

    iso_date_pattern = re.compile(
        r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2})?([+-]\d{2}:?\d{2}|Z)?)?$"
    )

    for prop_name, prop_value in item.properties.items():
        if prop_name not in DATETIME_PROPERTIES:
            continue
        if not isinstance(prop_value, str):
            continue
        if not prop_value.strip():
            continue
        if not iso_date_pattern.match(prop_value):
            results.append(
                ValidationResult(
                    issue_type=IssueType.INVALID_PROPERTY_TYPE,
                    severity=Severity.WARNING,
                    message=(
                        f"Property '{prop_name}' value '{prop_value}' "
                        f"is not ISO 8601 format"
                    ),
                    path=f"{item.schema_type}.{prop_name}",
                    schema_ref=item.schema_type,
                )
            )

    return results


def _validate_google_guidelines(item: StructuredDataItem) -> list[ValidationResult]:
    """Validate against Google's rich result guidelines.

    Args:
        item: Structured data item to check.

    Returns:
        List of validation issues.
    """
    results: list[ValidationResult] = []

    # Check for supported rich result type
    if item.schema_type not in GOOGLE_RICH_RESULT_TYPES:
        # Handle comma-separated types (JSON-LD multi-type)
        types = [t.strip() for t in item.schema_type.split(",")]
        supported = [t for t in types if t in GOOGLE_RICH_RESULT_TYPES]
        if not supported:
            results.append(
                ValidationResult(
                    issue_type=IssueType.UNSUPPORTED_TYPE,
                    severity=Severity.INFO,
                    message=(
                        f"Schema type '{item.schema_type}' is not a recognized "
                        f"Google rich result type"
                    ),
                    schema_ref=item.schema_type,
                )
            )
            return results

    # Check required properties for the type
    base_type = item.schema_type.split(",")[0].strip()
    required = GOOGLE_REQUIRED_PROPERTIES.get(base_type, [])

    for prop in required:
        if prop not in item.properties:
            results.append(
                ValidationResult(
                    issue_type=IssueType.MISSING_REQUIRED_PROPERTY,
                    severity=Severity.ERROR,
                    message=(
                        f"Google rich results require '{prop}' for {base_type}"
                    ),
                    path=f"{base_type}.{prop}",
                    schema_ref=base_type,
                )
            )

    # Type-specific validations
    if base_type == "FAQPage":
        results.extend(_validate_faq_page(item))
    elif base_type == "BreadcrumbList":
        results.extend(_validate_breadcrumb_list(item))
    elif base_type in ("Article", "NewsArticle", "BlogPosting"):
        results.extend(_validate_article(item))
    elif base_type == "Product":
        results.extend(_validate_product(item))

    # Check for missing name (common requirement)
    if "name" not in item.properties and base_type not in (
        "ListItem", "SearchAction", "SiteNavigationElement",
    ):
        if base_type in GOOGLE_RICH_RESULT_TYPES and base_type not in (
            "ImageObject", "VideoObject",
        ):
            results.append(
                ValidationResult(
                    issue_type=IssueType.MISSING_NAME,
                    severity=Severity.WARNING,
                    message=f"Schema '{base_type}' should have a 'name' property",
                    path=f"{base_type}.name",
                    schema_ref=base_type,
                )
            )

    return results


def _validate_faq_page(item: StructuredDataItem) -> list[ValidationResult]:
    """Validate FAQPage structure.

    Args:
        item: FAQPage structured data item.

    Returns:
        Validation issues.
    """
    results: list[ValidationResult] = []

    main_entity = item.properties.get("mainEntity")
    if not main_entity:
        results.append(
            ValidationResult(
                issue_type=IssueType.MISSING_REQUIRED_PROPERTY,
                severity=Severity.ERROR,
                message="FAQPage requires 'mainEntity' with Question/Answer pairs",
                path="FAQPage.mainEntity",
                schema_ref="FAQPage",
            )
        )
    elif isinstance(main_entity, list):
        for i, entity in enumerate(main_entity):
            if isinstance(entity, dict):
                if entity.get("@type") not in ("Question", None):
                    results.append(
                        ValidationResult(
                            issue_type=IssueType.INVALID_PROPERTY_TYPE,
                            severity=Severity.WARNING,
                            message=(
                                f"FAQPage.mainEntity[{i}] should be of type 'Question'"
                            ),
                            path=f"FAQPage.mainEntity[{i}]",
                            schema_ref="FAQPage",
                        )
                    )

    return results


def _validate_breadcrumb_list(item: StructuredDataItem) -> list[ValidationResult]:
    """Validate BreadcrumbList structure.

    Args:
        item: BreadcrumbList structured data item.

    Returns:
        Validation issues.
    """
    results: list[ValidationResult] = []

    list_elements = item.properties.get("itemListElement")
    if not list_elements:
        results.append(
            ValidationResult(
                issue_type=IssueType.MISSING_REQUIRED_PROPERTY,
                severity=Severity.ERROR,
                message="BreadcrumbList requires 'itemListElement'",
                path="BreadcrumbList.itemListElement",
                schema_ref="BreadcrumbList",
            )
        )

    return results


def _validate_article(item: StructuredDataItem) -> list[ValidationResult]:
    """Validate Article structure.

    Args:
        item: Article structured data item.

    Returns:
        Validation issues.
    """
    results: list[ValidationResult] = []

    # Check for image presence (important for rich results)
    if "image" not in item.properties:
        results.append(
            ValidationResult(
                issue_type=IssueType.MISSING_IMAGE,
                severity=Severity.WARNING,
                message=(
                    f"{item.schema_type} should have an 'image' property "
                    f"for rich results"
                ),
                path=f"{item.schema_type}.image",
                schema_ref=item.schema_type,
            )
        )

    return results


def _validate_product(item: StructuredDataItem) -> list[ValidationResult]:
    """Validate Product structure.

    Args:
        item: Product structured data item.

    Returns:
        Validation issues.
    """
    results: list[ValidationResult] = []

    # Product should have an image for rich results
    if "image" not in item.properties:
        results.append(
            ValidationResult(
                issue_type=IssueType.MISSING_IMAGE,
                severity=Severity.WARNING,
                message="Product should have an 'image' property for rich results",
                path="Product.image",
                schema_ref="Product",
            )
        )

    # Product should have offers or price
    if "offers" not in item.properties and "price" not in item.properties:
        results.append(
            ValidationResult(
                issue_type=IssueType.MISSING_REQUIRED_PROPERTY,
                severity=Severity.WARNING,
                message="Product should have 'offers' or 'price' for rich results",
                path="Product.offers",
                schema_ref="Product",
            )
        )

    return results


def validate_page(
    items: list[StructuredDataItem],
    google_guidelines: bool = True,
) -> tuple[list[ValidationResult], list[ValidationResult], list[ValidationResult]]:
    """Validate all structured data items on a page.

    Args:
        items: All structured data items from a page.
        google_guidelines: Whether to check Google guidelines.

    Returns:
        Tuple of (errors, warnings, info) lists.
    """
    errors: list[ValidationResult] = []
    warnings: list[ValidationResult] = []
    info: list[ValidationResult] = []

    for item in items:
        issues = validate_item(item, google_guidelines=google_guidelines)
        for issue in issues:
            if issue.severity == Severity.ERROR:
                errors.append(issue)
            elif issue.severity == Severity.WARNING:
                warnings.append(issue)
            else:
                info.append(issue)

    # Check for conflicting schemas (same type but different values)
    if len(items) > 1:
        conflicts = _detect_conflicts(items)
        warnings.extend(conflicts)

    return errors, warnings, info


def _detect_conflicts(items: list[StructuredDataItem]) -> list[ValidationResult]:
    """Detect conflicting schemas of the same type on a page.

    Args:
        items: All structured data items from a page.

    Returns:
        List of conflict warnings.
    """
    results: list[ValidationResult] = []

    # Group by schema type (ignoring multi-type comma-separated)
    type_groups: dict[str, list[StructuredDataItem]] = {}
    for item in items:
        primary_type = item.schema_type.split(",")[0].strip()
        type_groups.setdefault(primary_type, []).append(item)

    for schema_type, group in type_groups.items():
        if len(group) <= 1:
            continue
        # Multiple schemas of same type may conflict
        if schema_type in ("Product", "Organization", "WebSite", "LocalBusiness"):
            results.append(
                ValidationResult(
                    issue_type=IssueType.CONFLICTING_SCHEMA,
                    severity=Severity.WARNING,
                    message=(
                        f"Multiple '{schema_type}' schemas found "
                        f"({len(group)} instances) — may cause confusion"
                    ),
                    schema_ref=schema_type,
                )
            )

    return results
