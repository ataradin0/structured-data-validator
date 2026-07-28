# Structured Data Validator

CLI tool to extract and validate structured data (JSON-LD, Microdata, RDFa) against Schema.org specs and Google rich result guidelines.

## Installation

```bash
pip install -e .
```

## Usage

```bash
# Validate a single page
structured-data-validator validate https://example.com

# Validate from sitemap
structured-data-validator validate https://example.com --sitemap

# Crawl with depth
structured-data-validator validate https://example.com --depth 3

# Output formats
structured-data-validator validate https://example.com --output json
structured-data-validator validate https://example.com --output csv
structured-data-validator validate https://example.com --output table

# Filter by severity
structured-data-validator validate https://example.com --severity error

# Filter by schema type
structured-data-validator validate https://example.com --type Product,Article
```

## Features

- Extracts JSON-LD, Microdata, and RDFa structured data
- Validates against Schema.org type definitions
- Checks Google rich result guidelines
- Batch processing from URL or sitemap input
- Configurable depth, concurrency, and rate limiting
- Output in table, JSON, or CSV formats
