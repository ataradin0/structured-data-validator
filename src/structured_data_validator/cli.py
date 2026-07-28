"""CLI interface for Structured Data Validator."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from typing import Sequence

from .crawler import Crawler, crawl_sitemap
from .extractor import extract_all
from .models import PageResult, Severity
from .reporter import (
    build_report_summary,
    report_summary_to_text,
    report_to_csv,
    report_to_json,
)
from .validator import validate_page

logger = logging.getLogger(__name__)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Command-line arguments (defaults to sys.argv).

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        prog="structured-data-validator",
        description="Extract and validate structured data (JSON-LD, Microdata, RDFa) from web pages.",
    )

    subparsers = parser.add_subparsers(dest="command")

    # validate subcommand
    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate structured data on a URL or sitemap",
    )
    validate_parser.add_argument(
        "url",
        help="URL to validate (page URL or sitemap URL with --sitemap)",
    )
    validate_parser.add_argument(
        "--sitemap",
        action="store_true",
        help="Treat URL as sitemap.xml and validate all listed pages",
    )
    validate_parser.add_argument(
        "--depth",
        type=int,
        default=3,
        help="Maximum crawl depth (default: 3)",
    )
    validate_parser.add_argument(
        "--max-pages",
        type=int,
        default=100,
        help="Maximum pages to crawl (default: 100)",
    )
    validate_parser.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help="Number of concurrent requests (default: 5)",
    )
    validate_parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="HTTP request timeout in seconds (default: 30)",
    )
    validate_parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Delay between requests in seconds (default: 0.5)",
    )
    validate_parser.add_argument(
        "--output",
        "-o",
        choices=["table", "json", "csv"],
        default="table",
        help="Output format (default: table)",
    )
    validate_parser.add_argument(
        "--severity",
        choices=["error", "warning", "info"],
        default=None,
        help="Filter issues by minimum severity level",
    )
    validate_parser.add_argument(
        "--type",
        dest="schema_types",
        default=None,
        help="Comma-separated schema types to filter (e.g., Product,Article)",
    )
    validate_parser.add_argument(
        "--no-google",
        action="store_true",
        help="Disable Google rich result guidelines checks",
    )
    validate_parser.add_argument(
        "--no-robots",
        action="store_true",
        help="Ignore robots.txt",
    )
    validate_parser.add_argument(
        "--cross-domain",
        action="store_true",
        help="Allow crawling across different domains",
    )
    validate_parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    validate_parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress summary output",
    )

    # config subcommand
    config_parser = subparsers.add_parser(
        "config",
        help="Generate a sample configuration file",
    )
    config_parser.add_argument(
        "--output",
        "-o",
        default="structured-data-validator.yaml",
        help="Output path for config file",
    )

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    return args


def _setup_logging(verbose: bool) -> None:
    """Configure logging based on verbosity.

    Args:
        verbose: Whether to enable debug logging.
    """
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _filter_pages(
    pages: list[PageResult],
    severity: str | None,
    schema_types: str | None,
) -> list[PageResult]:
    """Filter page results by severity and schema type.

    Args:
        pages: All page results.
        severity: Minimum severity to include.
        schema_types: Comma-separated schema types to include.

    Returns:
        Filtered page results.
    """
    if not severity and not schema_types:
        return pages

    filtered: list[PageResult] = []

    type_filter = None
    if schema_types:
        type_filter = {t.strip() for t in schema_types.split(",")}

    severity_levels = {"error": 3, "warning": 2, "info": 1}
    min_level = severity_levels.get(severity, 0) if severity else 0

    for page in pages:
        # Filter by schema type
        if type_filter:
            page_types = {item.schema_type for item in page.structured_data}
            if not page_types.intersection(type_filter):
                continue

        # Filter issues by severity
        filtered_errors = [
            e for e in page.errors
            if severity_levels.get(e.severity.value, 0) >= min_level
        ] if min_level <= 3 else []
        filtered_warnings = [
            w for w in page.warnings
            if severity_levels.get(w.severity.value, 0) >= min_level
        ] if min_level <= 2 else []
        filtered_info = [
            i for i in page.info
            if severity_levels.get(i.severity.value, 0) >= min_level
        ] if min_level <= 1 else []

        if filtered_errors or filtered_warnings or filtered_info:
            filtered.append(
                PageResult(
                    url=page.url,
                    structured_data=page.structured_data,
                    errors=filtered_errors,
                    warnings=filtered_warnings,
                    info=filtered_info,
                    fetch_error=page.fetch_error,
                )
            )

    return filtered


def _print_table(pages: list[PageResult], summary_text: str, quiet: bool) -> None:
    """Print results as a formatted table.

    Args:
        pages: Page results to display.
        summary_text: Summary text to display.
        quiet: If True, skip summary.
    """
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()

        if not quiet:
            console.print(f"\n{summary_text}\n")

        # Issues table
        table = Table(title="Validation Issues", show_lines=True)
        table.add_column("URL", style="cyan", max_width=50)
        table.add_column("Severity", style="bold")
        table.add_column("Issue Type")
        table.add_column("Message", max_width=60)

        severity_styles = {
            "error": "[bold red]ERROR[/bold red]",
            "warning": "[yellow]WARNING[/yellow]",
            "info": "[blue]INFO[/blue]",
        }

        for page in pages:
            if page.fetch_error:
                table.add_row(
                    page.url[:50],
                    severity_styles["error"],
                    "fetch_error",
                    page.fetch_error,
                )
                continue

            for field, sev in [("errors", "error"), ("warnings", "warning"), ("info", "info")]:
                for issue in getattr(page, field):
                    table.add_row(
                        page.url[:50],
                        severity_styles[sev],
                        issue.issue_type.value,
                        issue.message,
                    )

        if table.row_count > 0:
            console.print(table)
        else:
            console.print("[green]No issues found![/green]")

    except ImportError:
        # Fallback to plain text
        if not quiet:
            print(f"\n{summary_text}\n")

        for page in pages:
            if page.fetch_error:
                print(f"  ERROR  {page.url}: {page.fetch_error}")
                continue
            for field, sev in [("errors", "ERROR"), ("warnings", "WARN"), ("info", "INFO")]:
                for issue in getattr(page, field):
                    print(f"  {sev:7s} {page.url}: {issue.message}")


async def _run_validate(args: argparse.Namespace) -> int:
    """Run the validate command.

    Args:
        args: Parsed arguments.

    Returns:
        Exit code (0=pass, 1=errors found, 2=crawl failure).
    """
    _setup_logging(args.verbose)

    try:
        if args.sitemap:
            pages = await crawl_sitemap(
                args.url,
                timeout=args.timeout,
                google_guidelines=not args.no_google,
            )
        else:
            crawler = Crawler(
                start_url=args.url,
                max_pages=args.max_pages,
                concurrency=args.concurrency,
                max_depth=args.depth,
                timeout=args.timeout,
                delay=args.delay,
                same_domain=not args.cross_domain,
                respect_robots=not args.no_robots,
                google_guidelines=not args.no_google,
            )
            pages = await crawler.crawl()
    except Exception as exc:
        msg = str(exc)
        # Provide friendlier messages for common connection errors
        if "ConnectError" in type(exc).__name__ or "connect" in msg.lower():
            msg = f"Could not connect to host. Please check the URL and ensure the server is reachable."
        elif "ConnectTimeout" in type(exc).__name__ or "timeout" in msg.lower():
            msg = f"Connection timed out. The server took too long to respond."
        elif "TaskGroup" in msg or "sub-exception" in msg:
            msg = f"Crawl failed — one or more requests could not be completed. Use --verbose for details."
        print(f"Crawl failed: {msg}", file=sys.stderr)
        return 2

    if not pages:
        print("No pages were crawled.", file=sys.stderr)
        return 2

    # Apply filters
    pages = _filter_pages(pages, args.severity, args.schema_types)

    # Build summary
    summary = build_report_summary(pages)
    summary_text = report_summary_to_text(summary)

    # Output
    if args.output == "json":
        print(report_to_json(pages, summary))
    elif args.output == "csv":
        print(report_to_csv(pages))
    else:
        _print_table(pages, summary_text, args.quiet)

    # Exit code
    if summary.pages_with_errors > 0:
        return 1
    return 0


def _run_config(args: argparse.Namespace) -> int:
    """Generate a sample configuration file.

    Args:
        args: Parsed arguments.

    Returns:
        Exit code.
    """
    config_content = """# Structured Data Validator Configuration
# Copy this file and customize as needed.

# Crawl settings
max_pages: 100
max_depth: 3
concurrency: 5
timeout: 30.0
delay: 0.5
same_domain: true
respect_robots: true

# Validation settings
google_guidelines: true

# Output settings
output_format: table  # table, json, csv
severity_filter: null  # error, warning, info
schema_type_filter: null  # e.g., Product,Article
"""
    with open(args.output, "w") as f:
        f.write(config_content)

    print(f"Sample config written to {args.output}")
    return 0


def main(argv: Sequence[str] | None = None) -> None:
    """Main entry point for the CLI.

    Args:
        argv: Command-line arguments (defaults to sys.argv).
    """
    args = parse_args(argv)

    if args.command == "validate":
        exit_code = asyncio.run(_run_validate(args))
    elif args.command == "config":
        exit_code = _run_config(args)
    else:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        exit_code = 1

    sys.exit(exit_code)
