"""Web crawler for structured data validation across multiple pages."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx

from .extractor import extract_all
from .models import PageResult, StructuredDataItem
from .validator import validate_page

logger = logging.getLogger(__name__)

DEFAULT_MAX_PAGES = 100
DEFAULT_CONCURRENCY = 5
DEFAULT_MAX_DEPTH = 3
DEFAULT_TIMEOUT = 30.0
DEFAULT_DELAY = 0.5


class Crawler:
    """Async web crawler that extracts and validates structured data."""

    def __init__(
        self,
        start_url: str,
        max_pages: int = DEFAULT_MAX_PAGES,
        concurrency: int = DEFAULT_CONCURRENCY,
        max_depth: int = DEFAULT_MAX_DEPTH,
        timeout: float = DEFAULT_TIMEOUT,
        delay: float = DEFAULT_DELAY,
        same_domain: bool = True,
        respect_robots: bool = True,
        google_guidelines: bool = True,
        user_agent: str = "structured-data-validator/0.1.0",
    ) -> None:
        self.start_url = start_url
        self.max_pages = max_pages
        self.concurrency = concurrency
        self.max_depth = max_depth
        self.timeout = timeout
        self.delay = delay
        self.same_domain = same_domain
        self.respect_robots = respect_robots
        self.google_guidelines = google_guidelines
        self.user_agent = user_agent

        parsed = urlparse(start_url)
        self.base_domain = parsed.netloc
        self.base_scheme = parsed.scheme

        self.visited: set[str] = set()
        self.page_results: list[PageResult] = []
        self._semaphore = asyncio.Semaphore(concurrency)
        self._client: Optional[httpx.AsyncClient] = None
        self._robots_parser: Optional[RobotFileParser] = None
        self._lock = asyncio.Lock()

    async def crawl(self) -> list[PageResult]:
        """Run the crawler and return all page results.

        Returns:
            List of PageResult objects with structured data and validation issues.
        """
        self._client = httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            headers={"User-Agent": self.user_agent},
        )

        try:
            # Check robots.txt
            if self.respect_robots:
                await self._load_robots()

            # Crawl starting URL
            await self._crawl_url(self.start_url, depth=0)
        finally:
            await self._client.aclose()

        return self.page_results

    async def _load_robots(self) -> None:
        """Load and parse robots.txt."""
        robots_url = f"{self.base_scheme}://{self.base_domain}/robots.txt"
        try:
            assert self._client is not None
            resp = await self._client.get(robots_url)
            if resp.status_code == 200:
                self._robots_parser = RobotFileParser()
                self._robots_parser.parse(resp.text.splitlines())
                logger.debug("Loaded robots.txt from %s", robots_url)
        except Exception as exc:
            logger.debug("Could not load robots.txt: %s", exc)

    def _is_allowed(self, url: str) -> bool:
        """Check if URL is allowed by robots.txt.

        Args:
            url: URL to check.

        Returns:
            True if allowed or no robots.txt loaded.
        """
        if not self._robots_parser:
            return True
        return self._robots_parser.can_fetch(self.user_agent, url)

    async def _crawl_url(self, url: str, depth: int) -> None:
        """Crawl a single URL, extract structured data, and discover links.

        Args:
            url: URL to crawl.
            depth: Current crawl depth.
        """
        normalized = url.split("#")[0].rstrip("/")
        if normalized in self.visited:
            return
        if len(self.visited) >= self.max_pages:
            return
        if depth > self.max_depth:
            return

        # Check robots.txt
        if not self._is_allowed(normalized):
            logger.debug("Blocked by robots.txt: %s", normalized)
            return

        self.visited.add(normalized)

        # Rate limiting
        if self.delay > 0:
            await asyncio.sleep(self.delay)

        async with self._semaphore:
            try:
                if self._client is None:
                    raise RuntimeError("Client not initialized")
                resp = await self._client.get(normalized)
            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                logger.warning("Failed to fetch %s: %s", normalized, exc)
                page = PageResult(url=normalized, fetch_error=str(exc))
                async with self._lock:
                    self.page_results.append(page)
                return

            if resp.status_code != 200:
                logger.debug("Non-200 for %s: %d", normalized, resp.status_code)
                return

            content_type = resp.headers.get("content-type", "")
            if "text/html" not in content_type:
                return

            html = resp.text

        # Extract and validate structured data
        items = extract_all(html, normalized)
        errors, warnings, info = validate_page(
            items, google_guidelines=self.google_guidelines
        )

        page = PageResult(
            url=normalized,
            structured_data=items,
            errors=errors,
            warnings=warnings,
            info=info,
        )
        async with self._lock:
            self.page_results.append(page)

        # Discover links for further crawling
        if depth < self.max_depth:
            links = self._extract_links(html, normalized)
            tasks = []
            for link in links:
                if link not in self.visited and len(self.visited) < self.max_pages:
                    if self.same_domain:
                        if urlparse(link).netloc != self.base_domain:
                            continue
                    tasks.append(self._crawl_url(link, depth + 1))
            if tasks:
                await asyncio.gather(*tasks)

    def _extract_links(self, html: str, base_url: str) -> list[str]:
        """Extract same-domain links from HTML.

        Args:
            html: Raw HTML content.
            base_url: Base URL for resolving relative links.

        Returns:
            List of absolute URLs to crawl.
        """
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        links: list[str] = []

        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"].strip()
            if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue

            absolute = urljoin(base_url, href).split("#")[0]

            if self.same_domain:
                if urlparse(absolute).netloc != self.base_domain:
                    continue

            # Skip non-HTML resources
            path = urlparse(absolute).path.lower()
            if any(
                path.endswith(ext)
                for ext in (
                    ".css", ".js", ".png", ".jpg", ".jpeg", ".gif",
                    ".svg", ".pdf", ".zip", ".xml", ".txt",
                )
            ):
                continue

            links.append(absolute)

        return links


async def crawl_sitemap(
    sitemap_url: str,
    timeout: float = DEFAULT_TIMEOUT,
    user_agent: str = "structured-data-validator/0.1.0",
    google_guidelines: bool = True,
) -> list[PageResult]:
    """Validate structured data from all URLs in a sitemap.

    Args:
        sitemap_url: URL of the sitemap.xml.
        timeout: HTTP request timeout.
        user_agent: User-Agent string.
        google_guidelines: Whether to check Google guidelines.

    Returns:
        List of PageResult objects.
    """
    from xml.etree import ElementTree

    client = httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": user_agent},
    )

    try:
        resp = await client.get(sitemap_url)
        resp.raise_for_status()

        # Parse sitemap XML
        root = ElementTree.fromstring(resp.text)
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

        # Check if it's a sitemap index
        sub_sitemaps = root.findall(".//sm:sitemap/sm:loc", ns)
        urls: list[str] = []

        if sub_sitemaps:
            for loc in sub_sitemaps:
                sub_url = loc.text.strip() if loc.text else ""
                if sub_url:
                    sub_resp = await client.get(sub_url)
                    if sub_resp.status_code == 200:
                        sub_root = ElementTree.fromstring(sub_resp.text)
                        for url_elem in sub_root.findall(".//sm:url/sm:loc", ns):
                            if url_elem.text:
                                urls.append(url_elem.text.strip())
        else:
            for url_elem in root.findall(".//sm:url/sm:loc", ns):
                if url_elem.text:
                    urls.append(url_elem.text.strip())

        logger.info("Found %d URLs in sitemap %s", len(urls), sitemap_url)

        # Validate each URL
        results: list[PageResult] = []
        for url in urls:
            try:
                page_resp = await client.get(url)
                if page_resp.status_code != 200:
                    results.append(PageResult(url=url, fetch_error=f"HTTP {page_resp.status_code}"))
                    continue

                content_type = page_resp.headers.get("content-type", "")
                if "text/html" not in content_type:
                    continue

                items = extract_all(page_resp.text, url)
                errors, warnings, info = validate_page(items, google_guidelines=google_guidelines)
                results.append(
                    PageResult(
                        url=url,
                        structured_data=items,
                        errors=errors,
                        warnings=warnings,
                        info=info,
                    )
                )
            except Exception as exc:
                logger.warning("Failed to validate %s: %s", url, exc)
                results.append(PageResult(url=url, fetch_error=str(exc)))

        return results

    finally:
        await client.aclose()
