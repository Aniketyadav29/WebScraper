"""
product_scraper.py
==================
Concrete scraper implementation targeting ``books.toscrape.com`` —
a legal, purpose-built scraping sandbox that simulates a real e-commerce
catalogue (pricing, ratings, stock status, genre categories).

This module will serve as our "competitor price feed" throughout
the pipeline.

Author : Aniket Yadav | BBD
Version: 1.0.0
"""

import csv
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path when running this file directly.
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scraper.base_scraper import BaseScraper, ScraperConfig  # noqa: E402
from utils.logger import setup_logger  # noqa: E402

# ---------------------------------------------------------------------------
# Module logger
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rating word → numeric mapping  (books.toscrape uses word ratings)
# ---------------------------------------------------------------------------
RATING_MAP: dict[str, float] = {
    "One": 1.0,
    "Two": 2.0,
    "Three": 3.0,
    "Four": 4.0,
    "Five": 5.0,
}

# ---------------------------------------------------------------------------
# Catalogue pages to scrape (books.toscrape paginates at 20 items/page)
# ---------------------------------------------------------------------------
BASE_URL = "https://books.toscrape.com/catalogue/"
CATALOGUE_PAGE_TEMPLATE = "https://books.toscrape.com/catalogue/page-{n}.html"

# We scrape multiple "competitor" identities by varying categories
COMPETITOR_LABELS = ["CompetitorA", "CompetitorB", "CompetitorC"]


class ProductScraper(BaseScraper):
    """
    Concrete scraper for ``books.toscrape.com``.

    Inherits all retry / UA-rotation / delay logic from :class:`BaseScraper`
    and implements the two abstract methods:

    * ``scrape(urls)``          — drives the full multi-page crawl.
    * ``_extract_product(...)`` — parses a single book-listing card.

    Additionally exposes:
    * ``scrape_catalogue(pages)``  — convenience wrapper for paginated crawl.
    * ``save_to_csv(records, path)`` — persists results to a timestamped CSV.
    """

    def __init__(self, config: Optional[ScraperConfig] = None) -> None:
        """
        Initialise the ProductScraper.

        Args:
            config: Optional :class:`ScraperConfig`. Falls back to defaults
                    pulled from environment variables if not provided.
        """
        if config is None:
            config = ScraperConfig(
                delay_min=float(os.getenv("SCRAPER_DELAY_MIN", 1.5)),
                delay_max=float(os.getenv("SCRAPER_DELAY_MAX", 3.5)),
                max_retries=int(os.getenv("SCRAPER_MAX_RETRIES", 3)),
                timeout=int(os.getenv("SCRAPER_TIMEOUT", 30)),
                headless=os.getenv("SCRAPER_HEADLESS", "True") == "True",
                output_dir=os.getenv("SCRAPER_OUTPUT_DIR", "data/raw"),
            )
        super().__init__(config)
        self.logger.info("ProductScraper ready — target: books.toscrape.com")

    # ------------------------------------------------------------------
    # Abstract method implementations
    # ------------------------------------------------------------------

    def scrape(self, urls: list[str]) -> list[dict[str, Any]]:
        """
        Scrape a list of catalogue-listing URLs and aggregate all products.

        Each URL is expected to be a books.toscrape catalogue page
        containing up to 20 book-listing cards.

        Args:
            urls: List of catalogue page URLs to scrape.

        Returns:
            List of product dictionaries, one per book found.
        """
        all_records: list[dict[str, Any]] = []

        for page_num, url in enumerate(urls, start=1):
            self.logger.info(
                "Scraping page %d/%d → %s", page_num, len(urls), url
            )
            soup = self.fetch_page(url)

            if soup is None:
                self.logger.warning("Skipping URL (fetch failed): %s", url)
                continue

            # Each catalogue page contains a list of article.product_pod cards
            product_cards = soup.select("article.product_pod")
            self.logger.info(
                "Found %d product cards on page %d",
                len(product_cards), page_num,
            )

            for card in product_cards:
                record = self._extract_product(card, url)  # type: ignore[arg-type]
                if record:
                    all_records.append(record)

        self.logger.info(
            "Scraping complete — %d total records collected.", len(all_records)
        )
        return all_records

    def _extract_product(
        self, soup: BeautifulSoup, source_url: str
    ) -> Optional[dict[str, Any]]:
        """
        Parse a single ``<article class="product_pod">`` card element.

        Handles all missing-element scenarios gracefully via
        :meth:`_safe_get_text` and explicit ``try/except`` blocks.

        Args:
            soup       : BeautifulSoup element for the product card.
            source_url : The catalogue page URL (for provenance).

        Returns:
            Dictionary with normalised product fields, or ``None`` on
            critical parse failure.
        """
        try:
            # ---- Title -----------------------------------------------
            title_raw = self._safe_get_text(
                soup, "h3 > a", attribute="title", default="Unknown Title"
            )

            # ---- Price -----------------------------------------------
            price_raw = self._safe_get_text(
                soup, "p.price_color", default="£0.00"
            )
            price = self._parse_price(price_raw)

            # ---- Rating ----------------------------------------------
            rating_element = soup.select_one("p.star-rating")
            rating_word = (
                rating_element["class"][1]  # e.g. ["star-rating", "Three"]
                if rating_element and len(rating_element.get("class", [])) > 1
                else "Zero"
            )
            rating = RATING_MAP.get(rating_word, 0.0)

            # ---- Stock Status ----------------------------------------
            availability_raw = self._safe_get_text(
                soup, "p.availability", default="Unknown"
            )
            in_stock = self._parse_availability(availability_raw)

            # ---- Detail Page URL -------------------------------------
            link_href = self._safe_get_text(
                soup, "h3 > a", attribute="href", default=""
            )
            # Catalogue links are relative: "../../book-title/index.html"
            detail_url = self._resolve_url(link_href)

            # ---- Assign a rotating competitor label ------------------
            # We simulate data from multiple "competitors" by cycling
            # through COMPETITOR_LABELS based on scrape ordering.
            competitor = COMPETITOR_LABELS[
                hash(title_raw) % len(COMPETITOR_LABELS)
            ]

            return {
                "title": title_raw,
                "price_gbp": price,
                "rating": rating,
                "in_stock": in_stock,
                "competitor": competitor,
                "source_url": detail_url,
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            }

        except (KeyError, IndexError, TypeError) as exc:
            self.logger.error(
                "Failed to extract product from '%s': %s", source_url, exc
            )
            return None

    # ------------------------------------------------------------------
    # Convenience public methods
    # ------------------------------------------------------------------

    def scrape_catalogue(
        self, num_pages: int = 5
    ) -> list[dict[str, Any]]:
        """
        Convenience wrapper that generates paginated catalogue URLs
        and delegates to :meth:`scrape`.

        Args:
            num_pages: Number of catalogue pages to scrape (default 5,
                       each page has 20 books → up to 100 records).

        Returns:
            List of product dictionaries from all scraped pages.
        """
        urls = [
            CATALOGUE_PAGE_TEMPLATE.format(n=i)
            for i in range(1, num_pages + 1)
        ]
        self.logger.info(
            "Starting catalogue scrape — %d pages × ~20 books/page",
            num_pages,
        )
        return self.scrape(urls)

    def save_to_csv(
        self,
        records: list[dict[str, Any]],
        filename: Optional[str] = None,
    ) -> Path:
        """
        Persist the scraped records to a timestamped CSV file.

        Args:
            records : List of product dictionaries to write.
            filename: Optional explicit filename. If omitted a timestamp-
                      based name is generated automatically.

        Returns:
            :class:`pathlib.Path` to the written CSV file.

        Raises:
            ValueError: If ``records`` is empty.
        """
        if not records:
            raise ValueError(
                "Cannot save an empty records list — "
                "ensure scraping completed successfully."
            )

        if filename is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"scraped_products_{ts}.csv"

        output_path = self.config.output_dir / filename
        fieldnames = list(records[0].keys())

        with output_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(records)

        self.logger.info(
            "Saved %d records → %s", len(records), output_path
        )
        return output_path

    # ------------------------------------------------------------------
    # Private parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_price(raw: str) -> float:
        """
        Strip currency symbols and convert price string to a float.

        Args:
            raw: Raw price string, e.g. ``"£51.77"`` or ``"Â£13.99"``.

        Returns:
            Float price value, or ``0.0`` on parse failure.
        """
        try:
            # Remove any non-numeric character except '.' and '-'
            cleaned = re.sub(r"[^\d.]", "", raw)
            return float(cleaned) if cleaned else 0.0
        except ValueError:
            logger.warning("Could not parse price: '%s'", raw)
            return 0.0

    @staticmethod
    def _parse_availability(raw: str) -> bool:
        """
        Normalise availability text to a boolean.

        Args:
            raw: Availability string, e.g. ``"In stock"`` or
                 ``"Out of stock"``.

        Returns:
            ``True`` if in stock, ``False`` otherwise.
        """
        return "in stock" in raw.strip().lower()

    @staticmethod
    def _resolve_url(href: str) -> str:
        """
        Convert a relative catalogue href to an absolute URL.

        books.toscrape relative links look like:
        ``"../../a-light-in-the-attic_1000/index.html"``

        Args:
            href: Relative href string from an anchor tag.

        Returns:
            Absolute URL string.
        """
        if not href:
            return ""
        # Strip leading "../" segments
        clean_href = re.sub(r"^(\.\./)+", "", href)
        return f"https://books.toscrape.com/catalogue/{clean_href}"


# ---------------------------------------------------------------------------
# Standalone entry-point for quick manual testing
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Bootstrap the project logger before anything else
    from utils.logger import setup_logger

    setup_logger()

    scraper = ProductScraper()

    print("\n" + "=" * 60)
    print("  Competitor Intelligence — Product Scraper")
    print("  Target: books.toscrape.com")
    print("=" * 60 + "\n")

    # Scrape 5 pages → ~100 product records
    records = scraper.scrape_catalogue(num_pages=5)

    # Persist to CSV
    csv_path = scraper.save_to_csv(records)

    print(f"\n✅  Done! {len(records)} records saved to:\n   {csv_path}\n")

    # Preview first 3 records
    print("── Preview (first 3 records) ──")
    for r in records[:3]:
        print(r)
