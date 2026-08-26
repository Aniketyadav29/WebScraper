"""
amazon_scraper.py
=================
Concrete scraper implementation targeting Amazon India (amazon.in) for
real-time competitor price tracking and product catalog extraction.

Subclasses BaseScraper and integrates anti-bot headers, search scraping,
and price parsing.

Author : Aniket Yadav | BBD
Version: 1.0.0
"""

from __future__ import annotations

import csv
import logging
import re
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scraper.base_scraper import BaseScraper, ScraperConfig
from utils.logger import setup_logger

logger = logging.getLogger(__name__)

AMAZON_BASE_URL = "https://www.amazon.in"
AMAZON_SEARCH_URL = "https://www.amazon.in/s?k={query}&page={page}"


class AmazonScraper(BaseScraper):
    """
    Scrapes product search results and product pages from Amazon.in.
    """

    def __init__(self, config: Optional[ScraperConfig] = None) -> None:
        super().__init__(config)
        self.session.headers.update({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7",
            "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        })

    def search(self, query: str, max_pages: int = 1, max_items: int = 20) -> list[dict[str, Any]]:
        """
        Search Amazon for a query keyword and scrape matching products.

        Args:
            query: Keyword to search (e.g., 'iphone 15', 'sony headphones')
            max_pages: Number of result pages to scrape
            max_items: Maximum items to collect

        Returns:
            List of parsed product dictionaries.
        """
        encoded_query = urllib.parse.quote_plus(query)
        collected_products: list[dict[str, Any]] = []

        for page in range(1, max_pages + 1):
            if len(collected_products) >= max_items:
                break

            url = AMAZON_SEARCH_URL.format(query=encoded_query, page=page)
            self.logger.info("Scraping Amazon search page %d: %s", page, url)

            try:
                self._polite_delay()
                response = self._fetch(url)

                if "api-services-support@amazon.com" in response.text or "Robot Check" in response.text:
                    self.logger.warning("Amazon CAPTCHA detected on page %d. Parsing available components.", page)
                    break

                soup = self._parse_html(response.text)
                items = self._extract_search_results(soup, query)

                for item in items:
                    if len(collected_products) >= max_items:
                        break
                    collected_products.append(item)

            except Exception as e:
                self.logger.error("Error scraping Amazon search page %d: %s", page, e)
                break

        self.logger.info("Amazon scrape complete. Extracted %d products for '%s'.", len(collected_products), query)
        return collected_products

    def _extract_search_results(self, soup: BeautifulSoup, query: str) -> list[dict[str, Any]]:
        """Extract product cards from Amazon search results HTML."""
        products = []
        cards = soup.select("div[data-component-type='s-search-result']")

        for card in cards:
            asin = card.get("data-asin", "").strip()
            if not asin:
                continue

            # Title
            title_tag = card.select_one("h2 a span, h2 span")
            title = title_tag.get_text(strip=True) if title_tag else ""
            if not title:
                continue

            # Price
            price_tag = card.select_one(".a-price .a-price-whole")
            price_str = price_tag.get_text(strip=True).replace(",", "").rstrip(".") if price_tag else ""
            
            # Original / MRP Price
            mrp_tag = card.select_one(".a-price.a-text-price span.a-offscreen")
            mrp_str = mrp_tag.get_text(strip=True).replace("₹", "").replace(",", "") if mrp_tag else ""

            # Rating
            rating_tag = card.select_one("i.a-icon-star-small span.a-icon-alt, span.a-icon-alt")
            rating_text = rating_tag.get_text(strip=True) if rating_tag else ""
            rating_match = re.search(r"([\d.]+)\s*out of", rating_text)
            rating = float(rating_match.group(1)) if rating_match else None

            # Review count
            reviews_tag = card.select_one("span.a-size-base.s-underline-text, a[href*='customerReviews'] span")
            reviews_count_text = reviews_tag.get_text(strip=True).replace(",", "") if reviews_tag else "0"
            reviews_count = int(re.sub(r"[^\d]", "", reviews_count_text) or "0")

            # Product URL
            link_tag = card.select_one("h2 a")
            href = link_tag.get("href", "") if link_tag else ""
            product_url = f"{AMAZON_BASE_URL}{href}" if href.startswith("/") else href

            # Image
            img_tag = card.select_one("img.s-image")
            img_url = img_tag.get("src", "") if img_tag else ""

            # Prime eligibility & Stock
            is_prime = bool(card.select_one("i.a-icon-prime"))
            stock_status = "In Stock"

            try:
                price_val = float(price_str) if price_str else None
                mrp_val = float(mrp_str) if mrp_str else price_val
            except ValueError:
                continue

            if price_val is None:
                continue

            discount_pct = 0.0
            if mrp_val and mrp_val > price_val:
                discount_pct = round(((mrp_val - price_val) / mrp_val) * 100, 1)

            product = {
                "sku": f"AMZ-{asin}",
                "asin": asin,
                "title": title,
                "category": query.title(),
                "price": price_val,
                "mrp": mrp_val,
                "discount_pct": discount_pct,
                "currency": "INR",
                "rating": rating,
                "review_count": reviews_count,
                "availability": stock_status,
                "competitor_name": "Amazon India",
                "product_url": product_url,
                "image_url": img_url,
                "is_prime": is_prime,
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            }
            products.append(product)

        return products

    def _extract_product(self, soup: BeautifulSoup, url: str) -> dict[str, Any]:
        """Parse a single Amazon product page."""
        title_el = soup.select_one("#productTitle")
        title = title_el.get_text(strip=True) if title_el else "Unknown Amazon Product"

        price_el = soup.select_one(".a-price .a-price-whole")
        price_val = float(price_el.get_text(strip=True).replace(",", "")) if price_el else 0.0

        return {
            "title": title,
            "price": price_val,
            "product_url": url,
            "competitor_name": "Amazon India",
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        }

    def scrape(self, urls: list[str]) -> list[dict[str, Any]]:
        """Scrape a list of direct Amazon product URLs."""
        results = []
        for url in urls:
            try:
                self._polite_delay()
                res = self._fetch(url)
                soup = self._parse_html(res.text)
                results.append(self._extract_product(soup, url))
            except Exception as e:
                self.logger.error("Failed to scrape Amazon URL %s: %s", url, e)
        return results
