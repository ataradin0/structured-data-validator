"""Extract structured data (JSON-LD, Microdata, RDFa) from HTML pages."""

from __future__ import annotations

import json
import logging
from typing import Any

from bs4 import BeautifulSoup

from .models import SchemaFormat, StructuredDataItem

logger = logging.getLogger(__name__)

# Common JSON-LD @context values
SCHEMA_ORG_CONTEXTS = {"https://schema.org", "http://schema.org", "schema.org"}

# Microdata itemtype prefix
MICRODATA_SCHEMA_PREFIX = "https://schema.org/"


def extract_jsonld(html: str, source_url: str = "") -> list[StructuredDataItem]:
    """Extract JSON-LD structured data from HTML.

    Handles <script type="application/ld+json"> blocks, including @graph arrays.

    Args:
        html: Raw HTML content.
        source_url: URL of the source page for context.

    Returns:
        List of StructuredDataItem objects.
    """
    items: list[StructuredDataItem] = []
    soup = BeautifulSoup(html, "lxml")

    for script in soup.find_all("script", type="application/ld+json"):
        raw_text = script.string
        if not raw_text or not raw_text.strip():
            continue

        try:
            data = json.loads(raw_text)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.debug("Malformed JSON-LD on %s: %s", source_url, exc)
            # Return a marker item so the validator can flag it
            items.append(
                StructuredDataItem(
                    schema_format=SchemaFormat.JSON_LD,
                    schema_type="MalformedJSON-LD",
                    raw=raw_text,
                    source_url=source_url,
                )
            )
            continue

        items.extend(_parse_jsonld_data(data, source_url))

    return items


def _parse_jsonld_data(data: Any, source_url: str) -> list[StructuredDataItem]:
    """Parse JSON-LD data (may be a dict, list, or @graph).

    Args:
        data: Parsed JSON-LD data.
        source_url: Source URL for context.

    Returns:
        List of StructuredDataItem objects.
    """
    items: list[StructuredDataItem] = []

    if isinstance(data, list):
        for entry in data:
            if isinstance(entry, dict):
                items.extend(_parse_jsonld_data(entry, source_url))
        return items

    if not isinstance(data, dict):
        return items

    context = data.get("@context", None)
    if isinstance(context, list):
        context = " ".join(str(c) for c in context)

    # Handle @graph arrays
    if "@graph" in data and isinstance(data["@graph"], list):
        for entry in data["@graph"]:
            if isinstance(entry, dict):
                item = _jsonld_dict_to_item(entry, source_url, context, is_graph=True)
                if item:
                    items.append(item)
        return items

    # Single schema object
    item = _jsonld_dict_to_item(data, source_url, context, is_graph=False)
    if item:
        items.append(item)

    return items


def _jsonld_dict_to_item(
    data: dict[str, Any],
    source_url: str,
    context: Any,
    is_graph: bool,
) -> StructuredDataItem | None:
    """Convert a JSON-LD dict to a StructuredDataItem.

    Args:
        data: A single JSON-LD object.
        source_url: Source URL.
        context: @context value.
        is_graph: Whether this was part of a @graph.

    Returns:
        StructuredDataItem or None if no @type found.
    """
    schema_type = data.get("@type", "")
    if isinstance(schema_type, list):
        schema_type = ", ".join(str(t) for t in schema_type)

    # Extract properties (everything except @type, @context, @graph, @id)
    properties = {
        k: v for k, v in data.items() if not k.startswith("@") or k == "@id"
    }

    return StructuredDataItem(
        schema_format=SchemaFormat.JSON_LD,
        schema_type=str(schema_type) if schema_type else "Unknown",
        properties=properties,
        raw=data,
        source_url=source_url,
        context=str(context) if context else None,
        is_graph_item=is_graph,
    )


def extract_microdata(html: str, source_url: str = "") -> list[StructuredDataItem]:
    """Extract Microdata from HTML using itemscope/itemprop/itemtype attributes.

    Args:
        html: Raw HTML content.
        source_url: URL of the source page.

    Returns:
        List of StructuredDataItem objects.
    """
    items: list[StructuredDataItem] = []
    soup = BeautifulSoup(html, "lxml")

    # Find all itemscope elements that have an itemtype
    for scope in soup.find_all(attrs={"itemscope": True}):
        itemtype = scope.get("itemtype", "")
        if not itemtype:
            continue

        # Extract schema type from URL
        schema_type = _extract_schema_type(str(itemtype))
        properties = _extract_microdata_properties(scope)

        items.append(
            StructuredDataItem(
                schema_format=SchemaFormat.MICRODATA,
                schema_type=schema_type,
                properties=properties,
                raw={"itemtype": str(itemtype), "properties": properties},
                source_url=source_url,
            )
        )

    return items


def _extract_schema_type(itemtype: str) -> str:
    """Extract schema type name from itemtype URL.

    Args:
        itemtype: Full itemtype URL (e.g., "https://schema.org/Product").

    Returns:
        Schema type name (e.g., "Product").
    """
    # Handle multiple itemtypes (space-separated)
    types = []
    for t in itemtype.split():
        t = t.strip()
        if MICRODATA_SCHEMA_PREFIX in t:
            types.append(t.split("/")[-1])
        elif "/" not in t and "." not in t:
            types.append(t)  # Already a plain type name
        else:
            types.append(t.rsplit("/", 1)[-1])
    return ", ".join(types) if types else itemtype


def _extract_microdata_properties(scope: Any) -> dict[str, Any]:
    """Recursively extract itemprop properties from an itemscope element.

    Args:
        scope: BeautifulSoup element with itemscope.

    Returns:
        Dict of property name -> value.
    """
    props: dict[str, Any] = {}

    for child in scope.find_all(attrs={"itemprop": True}, recursive=True):
        prop_name = child.get("itemprop", "")
        if not prop_name:
            continue

        # Skip if this child belongs to a nested itemscope (not our scope)
        parent_scope = child.find_parent(attrs={"itemscope": True})
        if parent_scope is not scope:
            continue

        prop_value = _get_element_value(child)
        if prop_name in props:
            # Multiple values → make a list
            existing = props[prop_name]
            if isinstance(existing, list):
                existing.append(prop_value)
            else:
                props[prop_name] = [existing, prop_value]
        else:
            props[prop_name] = prop_value

    return props


def _get_element_value(element: Any) -> Any:
    """Extract the value from a microdata element based on its tag.

    Args:
        element: BeautifulSoup element with itemprop.

    Returns:
        Extracted value (string, URL, etc.).
    """
    tag = element.name
    if tag in ("meta",):
        return element.get("content", "")
    if tag in ("img", "audio", "video", "source"):
        return element.get("src", "")
    if tag == "a":
        return element.get("href", "")
    if tag == "link":
        return element.get("href", "")
    if tag in ("time",):
        return element.get("datetime", element.get_text(strip=True))
    if tag == "data":
        return element.get("value", element.get_text(strip=True))
    # Default: text content
    return element.get_text(strip=True)


def extract_rdfa(html: str, source_url: str = "") -> list[StructuredDataItem]:
    """Extract RDFa from HTML using vocab/typeof/property attributes.

    Args:
        html: Raw HTML content.
        source_url: URL of the source page.

    Returns:
        List of StructuredDataItem objects.
    """
    items: list[StructuredDataItem] = []
    soup = BeautifulSoup(html, "lxml")

    # Find all elements with typeof (RDFa typed entities)
    for elem in soup.find_all(attrs={"typeof": True}):
        typeof = elem.get("typeof", "")
        vocab = elem.get("vocab", "")

        # Try to find vocab from parent
        if not vocab:
            parent = elem.find_parent(attrs={"vocab": True})
            if parent:
                vocab = parent.get("vocab", "")

        schema_type = typeof
        if vocab and "schema.org" in vocab.lower():
            schema_type = typeof  # Already the type name

        properties = _extract_rdfa_properties(elem)

        items.append(
            StructuredDataItem(
                schema_format=SchemaFormat.RDFA,
                schema_type=schema_type,
                properties=properties,
                raw={"typeof": typeof, "vocab": vocab, "properties": properties},
                source_url=source_url,
                context=vocab if vocab else None,
            )
        )

    # Also find standalone property elements without typeof
    standalone = soup.find_all(attrs={"property": True})
    if standalone and not items:
        props: dict[str, Any] = {}
        for elem in standalone:
            prop = elem.get("property", "")
            if not prop:
                continue
            value = elem.get("content", elem.get("href", elem.get_text(strip=True)))
            if prop in props:
                existing = props[prop]
                if isinstance(existing, list):
                    existing.append(value)
                else:
                    props[prop] = [existing, value]
            else:
                props[prop] = value

        if props:
            items.append(
                StructuredDataItem(
                    schema_format=SchemaFormat.RDFA,
                    schema_type="Unknown",
                    properties=props,
                    raw={"properties": props},
                    source_url=source_url,
                )
            )

    return items


def _extract_rdfa_properties(elem: Any) -> dict[str, Any]:
    """Extract property attributes from an RDFa element and its children.

    Args:
        elem: BeautifulSoup element with typeof.

    Returns:
        Dict of property name -> value.
    """
    props: dict[str, Any] = {}

    # Properties on the element itself
    prop_attr = elem.get("property", "")
    if prop_attr:
        value = elem.get("content", elem.get("href", elem.get_text(strip=True)))
        props[prop_attr] = value

    # Properties on children
    for child in elem.find_all(attrs={"property": True}, recursive=True):
        if child is elem:
            continue
        # Don't cross into nested typeof scopes
        parent_typeof = child.find_parent(attrs={"typeof": True})
        if parent_typeof is not elem:
            continue
        prop_name = child.get("property", "")
        if not prop_name:
            continue
        value = child.get("content", child.get("href", child.get_text(strip=True)))
        if prop_name in props:
            existing = props[prop_name]
            if isinstance(existing, list):
                existing.append(value)
            else:
                props[prop_name] = [existing, value]
        else:
            props[prop_name] = value

    return props


def extract_all(html: str, source_url: str = "") -> list[StructuredDataItem]:
    """Extract all structured data formats from HTML.

    Args:
        html: Raw HTML content.
        source_url: URL of the source page.

    Returns:
        Combined list of StructuredDataItem from JSON-LD, Microdata, and RDFa.
    """
    items: list[StructuredDataItem] = []

    items.extend(extract_jsonld(html, source_url))
    items.extend(extract_microdata(html, source_url))
    items.extend(extract_rdfa(html, source_url))

    return items
