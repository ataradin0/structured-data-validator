"""Report generation for structured data validation results."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from .models import PageResult, ReportSummary, Severity


def build_report_summary(pages: list[PageResult]) -> ReportSummary:
    """Build aggregate summary statistics from page results.

    Args:
        pages: List of PageResult objects.

    Returns:
        ReportSummary with aggregated counts.
    """
    if not pages:
        return ReportSummary()

    total_errors = sum(len(p.errors) for p in pages)
    total_warnings = sum(len(p.warnings) for p in pages)
    total_info = sum(len(p.info) for p in pages)
    pages_with_schema = sum(1 for p in pages if p.structured_data)
    pages_with_errors = sum(1 for p in pages if p.has_errors)

    schema_type_counts: dict[str, int] = {}
    format_counts: dict[str, int] = {}

    for page in pages:
        for item in page.structured_data:
            schema_type_counts[item.schema_type] = (
                schema_type_counts.get(item.schema_type, 0) + 1
            )
            format_counts[item.schema_format.value] = (
                format_counts.get(item.schema_format.value, 0) + 1
            )

    total_schemas = sum(schema_type_counts.values())
    pages_without = len(pages) - pages_with_schema
    pass_rate = (
        ((len(pages) - pages_with_errors) / len(pages) * 100) if pages else 0.0
    )

    return ReportSummary(
        total_pages=len(pages),
        pages_with_schema=pages_with_schema,
        pages_without_schema=pages_without,
        pages_with_errors=pages_with_errors,
        total_schemas=total_schemas,
        total_errors=total_errors,
        total_warnings=total_warnings,
        total_info=total_info,
        schema_type_counts=schema_type_counts,
        format_counts=format_counts,
        pass_rate=round(pass_rate, 1),
    )


def report_to_json(
    pages: list[PageResult],
    summary: ReportSummary | None = None,
    pretty: bool = True,
) -> str:
    """Generate JSON report.

    Args:
        pages: List of PageResult objects.
        summary: Optional pre-computed summary.
        pretty: Pretty-print JSON.

    Returns:
        JSON string.
    """
    if summary is None:
        summary = build_report_summary(pages)

    data = {
        "summary": json.loads(summary.model_dump_json()),
        "pages": [json.loads(p.model_dump_json()) for p in pages],
    }

    if pretty:
        return json.dumps(data, indent=2, default=str)
    return json.dumps(data, default=str)


def report_to_csv(pages: list[PageResult]) -> str:
    """Generate CSV report of all issues across pages.

    Args:
        pages: List of PageResult objects.

    Returns:
        CSV string.
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "url", "severity", "issue_type", "message", "path", "schema_ref",
        "schema_type", "schema_format",
    ])

    for page in pages:
        if page.fetch_error:
            writer.writerow([
                page.url, "error", "fetch_error", page.fetch_error,
                "", "", "", "",
            ])
            continue

        for severity_field, severity_name in [
            ("errors", "error"), ("warnings", "warning"), ("info", "info"),
        ]:
            for issue in getattr(page, severity_field):
                writer.writerow([
                    page.url,
                    severity_name,
                    issue.issue_type.value,
                    issue.message,
                    issue.path or "",
                    issue.schema_ref or "",
                    "",
                    "",
                ])

        # Also list schemas found
        for item in page.structured_data:
            writer.writerow([
                page.url,
                "schema_found",
                "",
                f"Found {item.schema_type} ({item.schema_format.value})",
                "",
                "",
                item.schema_type,
                item.schema_format.value,
            ])

    return output.getvalue()


def report_summary_to_text(summary: ReportSummary) -> str:
    """Generate a plain-text summary for terminal display.

    Args:
        summary: ReportSummary object.

    Returns:
        Formatted text string.
    """
    lines = [
        "═══ Structured Data Validation Report ═══",
        "",
        f"  Pages crawled:        {summary.total_pages}",
        f"  Pages with schema:    {summary.pages_with_schema}",
        f"  Pages without schema: {summary.pages_without_schema}",
        f"  Pages with errors:    {summary.pages_with_errors}",
        f"  Pass rate:            {summary.pass_rate}%",
        "",
        f"  Total schemas found:  {summary.total_schemas}",
        f"  Total errors:         {summary.total_errors}",
        f"  Total warnings:       {summary.total_warnings}",
        f"  Total info:           {summary.total_info}",
    ]

    if summary.schema_type_counts:
        lines.append("")
        lines.append("  Schema Types:")
        for stype, count in sorted(
            summary.schema_type_counts.items(), key=lambda x: -x[1]
        ):
            lines.append(f"    {stype}: {count}")

    if summary.format_counts:
        lines.append("")
        lines.append("  Formats:")
        for fmt, count in sorted(
            summary.format_counts.items(), key=lambda x: -x[1]
        ):
            lines.append(f"    {fmt}: {count}")

    return "\n".join(lines)
