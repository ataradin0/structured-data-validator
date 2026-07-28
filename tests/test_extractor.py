"""Tests for structured data extraction."""

from __future__ import annotations

from structured_data_validator.extractor import (
    extract_all,
    extract_jsonld,
    extract_microdata,
    extract_rdfa,
)
from structured_data_validator.models import SchemaFormat


class TestExtractJsonLD:
    """Tests for JSON-LD extraction."""

    def test_basic_product(self) -> None:
        html = """
        <html><head>
        <script type="application/ld+json">
        {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": "Widget Pro",
            "price": "29.99",
            "priceCurrency": "USD"
        }
        </script>
        </head><body></body></html>
        """
        items = extract_jsonld(html, "https://example.com/product")
        assert len(items) == 1
        assert items[0].schema_type == "Product"
        assert items[0].schema_format == SchemaFormat.JSON_LD
        assert items[0].properties["name"] == "Widget Pro"
        assert items[0].source_url == "https://example.com/product"
        assert items[0].context == "https://schema.org"

    def test_graph_array(self) -> None:
        html = """
        <script type="application/ld+json">
        {
            "@context": "https://schema.org",
            "@graph": [
                {"@type": "WebPage", "name": "Home"},
                {"@type": "Organization", "name": "Acme"}
            ]
        }
        </script>
        """
        items = extract_jsonld(html)
        assert len(items) == 2
        assert items[0].schema_type == "WebPage"
        assert items[0].is_graph_item is True
        assert items[1].schema_type == "Organization"
        assert items[1].is_graph_item is True

    def test_multiple_scripts(self) -> None:
        html = """
        <script type="application/ld+json">{"@type": "Product", "name": "A"}</script>
        <script type="application/ld+json">{"@type": "Article", "headline": "B"}</script>
        """
        items = extract_jsonld(html)
        assert len(items) == 2
        types = {i.schema_type for i in items}
        assert "Product" in types
        assert "Article" in types

    def test_malformed_json(self) -> None:
        html = '<script type="application/ld+json">{invalid json!!!}</script>'
        items = extract_jsonld(html)
        assert len(items) == 1
        assert items[0].schema_type == "MalformedJSON-LD"

    def test_empty_script_tag(self) -> None:
        html = '<script type="application/ld+json"></script>'
        items = extract_jsonld(html)
        assert len(items) == 0

    def test_no_jsonld(self) -> None:
        html = "<html><body><p>No structured data here</p></body></html>"
        items = extract_jsonld(html)
        assert len(items) == 0

    def test_list_of_schemas(self) -> None:
        html = """
        <script type="application/ld+json">
        [
            {"@type": "Product", "name": "A"},
            {"@type": "Product", "name": "B"}
        ]
        </script>
        """
        items = extract_jsonld(html)
        assert len(items) == 2

    def test_type_as_list(self) -> None:
        html = """
        <script type="application/ld+json">
        {"@type": ["Product", "Thing"], "name": "Widget"}
        </script>
        """
        items = extract_jsonld(html)
        assert len(items) == 1
        assert "Product" in items[0].schema_type
        assert "Thing" in items[0].schema_type

    def test_context_as_list(self) -> None:
        html = """
        <script type="application/ld+json">
        {"@context": ["https://schema.org", "https://example.com/ns"], "@type": "Thing"}
        </script>
        """
        items = extract_jsonld(html)
        assert len(items) == 1
        assert items[0].context is not None
        assert "schema.org" in items[0].context

    def test_nested_object_preserved_in_properties(self) -> None:
        html = """
        <script type="application/ld+json">
        {
            "@type": "Product",
            "name": "Widget",
            "offers": {"@type": "Offer", "price": "10.00"}
        }
        </script>
        """
        items = extract_jsonld(html)
        assert len(items) == 1
        assert isinstance(items[0].properties["offers"], dict)


class TestExtractMicrodata:
    """Tests for Microdata extraction."""

    def test_basic_product(self) -> None:
        html = """
        <div itemscope itemtype="https://schema.org/Product">
            <span itemprop="name">Widget</span>
            <span itemprop="price">$9.99</span>
        </div>
        """
        items = extract_microdata(html)
        assert len(items) == 1
        assert items[0].schema_type == "Product"
        assert items[0].schema_format == SchemaFormat.MICRODATA
        assert items[0].properties["name"] == "Widget"
        assert items[0].properties["price"] == "$9.99"

    def test_microdata_with_link(self) -> None:
        html = """
        <div itemscope itemtype="https://schema.org/Article">
            <a itemprop="url" href="https://example.com/article">Link</a>
            <h1 itemprop="headline">Title</h1>
        </div>
        """
        items = extract_microdata(html)
        assert len(items) == 1
        assert items[0].properties["url"] == "https://example.com/article"
        assert items[0].properties["headline"] == "Title"

    def test_microdata_with_image(self) -> None:
        html = """
        <div itemscope itemtype="https://schema.org/Article">
            <img itemprop="image" src="https://example.com/img.jpg" />
        </div>
        """
        items = extract_microdata(html)
        assert len(items) == 1
        assert items[0].properties["image"] == "https://example.com/img.jpg"

    def test_microdata_with_meta_tag(self) -> None:
        html = """
        <div itemscope itemtype="https://schema.org/Event">
            <meta itemprop="startDate" content="2026-01-01">
            <span itemprop="name">Conference</span>
        </div>
        """
        items = extract_microdata(html)
        assert len(items) == 1
        assert items[0].properties["startDate"] == "2026-01-01"

    def test_microdata_with_time_tag(self) -> None:
        html = """
        <div itemscope itemtype="https://schema.org/Event">
            <time itemprop="startDate" datetime="2026-07-01">July 1</time>
        </div>
        """
        items = extract_microdata(html)
        assert len(items) == 1
        assert items[0].properties["startDate"] == "2026-07-01"

    def test_no_microdata(self) -> None:
        html = "<html><body><p>No microdata</p></body></html>"
        items = extract_microdata(html)
        assert len(items) == 0

    def test_nested_scopes_not_confused(self) -> None:
        html = """
        <div itemscope itemtype="https://schema.org/Product">
            <span itemprop="name">Widget</span>
            <div itemscope itemtype="https://schema.org/Offer">
                <span itemprop="price">$9.99</span>
            </div>
        </div>
        """
        items = extract_microdata(html)
        assert len(items) == 2
        product = [i for i in items if i.schema_type == "Product"][0]
        offer = [i for i in items if i.schema_type == "Offer"][0]
        assert product.properties["name"] == "Widget"
        assert offer.properties["price"] == "$9.99"
        # price should NOT be in product's properties
        assert "price" not in product.properties

    def test_multiple_values(self) -> None:
        html = """
        <div itemscope itemtype="https://schema.org/Product">
            <span itemprop="name">Widget</span>
            <span itemprop="color">Red</span>
            <span itemprop="color">Blue</span>
        </div>
        """
        items = extract_microdata(html)
        assert len(items) == 1
        assert isinstance(items[0].properties["color"], list)
        assert "Red" in items[0].properties["color"]
        assert "Blue" in items[0].properties["color"]


class TestExtractRdfa:
    """Tests for RDFa extraction."""

    def test_basic_rdfa(self) -> None:
        html = """
        <div vocab="https://schema.org/" typeof="Product">
            <span property="name">Widget</span>
            <span property="price">9.99</span>
        </div>
        """
        items = extract_rdfa(html)
        assert len(items) == 1
        assert items[0].schema_type == "Product"
        assert items[0].schema_format == SchemaFormat.RDFA
        assert items[0].properties["name"] == "Widget"

    def test_rdfa_with_link_property(self) -> None:
        html = """
        <div vocab="https://schema.org/" typeof="Organization">
            <a property="url" href="https://example.com">Example</a>
        </div>
        """
        items = extract_rdfa(html)
        assert len(items) == 1
        assert items[0].properties["url"] == "https://example.com"

    def test_rdfa_standalone_properties(self) -> None:
        html = """
        <span property="name">Global Name</span>
        <span property="description">Global Desc</span>
        """
        items = extract_rdfa(html)
        assert len(items) == 1
        assert items[0].schema_type == "Unknown"
        assert items[0].properties["name"] == "Global Name"

    def test_no_rdfa(self) -> None:
        html = "<html><body><p>No RDFa</p></body></html>"
        items = extract_rdfa(html)
        assert len(items) == 0


class TestExtractAll:
    """Tests for the combined extract_all function."""

    def test_all_formats_combined(self) -> None:
        html = """
        <html><head>
        <script type="application/ld+json">
        {"@type": "Organization", "name": "Acme"}
        </script>
        </head>
        <body>
        <div itemscope itemtype="https://schema.org/Product">
            <span itemprop="name">Widget</span>
        </div>
        <div vocab="https://schema.org/" typeof="WebPage">
            <span property="name">Home</span>
        </div>
        </body></html>
        """
        items = extract_all(html, "https://example.com")
        formats = {i.schema_format for i in items}
        assert SchemaFormat.JSON_LD in formats
        assert SchemaFormat.MICRODATA in formats
        assert SchemaFormat.RDFA in formats
        assert len(items) >= 3

    def test_no_structured_data(self) -> None:
        html = "<html><body><p>Plain page</p></body></html>"
        items = extract_all(html)
        assert len(items) == 0
