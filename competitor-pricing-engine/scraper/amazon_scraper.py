"""
amazon_scraper.py
=================
Concrete scraper implementation targeting Amazon India (amazon.in) for
real-time competitor price tracking and product catalog extraction.

Subclasses BaseScraper and integrates anti-bot headers, search scraping,
and exact price parsing.

Author : Aniket Yadav | BBD
Version: 2.1.0
"""

from __future__ import annotations

import csv
import logging
import random
import re
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scraper.base_scraper import BaseScraper, ScraperConfig
from utils.logger import setup_logger

logger = logging.getLogger(__name__)

AMAZON_BASE_URL = "https://www.amazon.in"
AMAZON_SEARCH_URL = "https://www.amazon.in/s?k={query}&page={page}"

HEADER_PROFILES = [
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-IN,en;q=0.9",
        "Referer": "https://www.google.com/",
        "Sec-Ch-Ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "cross-site",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    },
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": "https://www.google.com/",
        "Upgrade-Insecure-Requests": "1",
    },
    {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-IN,en;q=0.9",
        "Referer": "https://www.google.com/",
        "Sec-Ch-Ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"macOS"',
        "Upgrade-Insecure-Requests": "1",
    },
]


class AmazonScraper(BaseScraper):
    """
    Scrapes live product search results and product pages from Amazon.in.
    """

    def __init__(self, config: Optional[ScraperConfig] = None) -> None:
        super().__init__(config)
        self.session.headers.update(HEADER_PROFILES[0])

    def search(self, query: str, max_pages: int = 1, max_items: int = 20) -> list[dict[str, Any]]:
        """
        Search Amazon for a query keyword and scrape matching products with exact prices.

        Args:
            query: Keyword to search (e.g., 'Fortune oil', 'iphone 15', 'sony headphones')
            max_pages: Number of result pages to scrape
            max_items: Maximum items to collect

        Returns:
            List of parsed product dictionaries with exact prices.
        """
        encoded_query = urllib.parse.quote_plus(query.strip())
        collected_products: list[dict[str, Any]] = []

        for page in range(1, max_pages + 1):
            if len(collected_products) >= max_items:
                break

            url = AMAZON_SEARCH_URL.format(query=encoded_query, page=page)
            self.logger.info("Scraping Amazon search page %d: %s", page, url)

            response_text = ""
            for h_idx, headers in enumerate(HEADER_PROFILES):
                try:
                    s = requests.Session()
                    resp = s.get(url, headers=headers, timeout=self.config.timeout)
                    if (
                        resp.status_code == 200
                        and "Robot Check" not in resp.text
                        and "api-services-support@amazon.com" not in resp.text
                        and len(resp.text) > 40000
                    ):
                        response_text = resp.text
                        break
                except Exception as e:
                    self.logger.debug("Amazon header %d failed: %s", h_idx, e)

            if not response_text:
                self.logger.warning("Amazon returned challenge or empty response for '%s'", query)
                break

            try:
                soup = self._parse_html(response_text)
                items = self._extract_search_results(soup, query)

                for item in items:
                    if len(collected_products) >= max_items:
                        break
                    collected_products.append(item)

            except Exception as e:
                self.logger.error("Error parsing Amazon search page %d: %s", page, e)
                break

        self.logger.info("Amazon scrape complete. Extracted %d products for '%s'.", len(collected_products), query)
        return collected_products

    def _extract_search_results(self, soup: BeautifulSoup, query: str) -> list[dict[str, Any]]:
        """Extract product cards from Amazon search results HTML with exact prices and clean titles."""
        products = []
        cards = soup.select("div[data-component-type='s-search-result']")
        query_words = [w.lower() for w in query.strip().split() if len(w) > 2]

        for card in cards:
            asin = card.get("data-asin", "").strip()
            if not asin:
                continue

            # 1. Title Extraction
            brand_el = card.select_one(".s-title-instructions-style h2 .a-size-base-plus, h2.a-size-mini span")
            brand = brand_el.get_text(strip=True) if brand_el else ""

            title = ""
            img_el = card.select_one("img.s-image")
            img_alt = img_el.get("alt", "").strip() if img_el else ""
            img_src = img_el.get("src", "").strip() if img_el else ""

            # Check h2 aria-label
            h2_aria = card.select_one(".s-title-instructions-style a h2[aria-label], h2[aria-label]")
            if h2_aria and h2_aria.get("aria-label"):
                title = h2_aria.get("aria-label").strip()

            if not title and img_alt and len(img_alt) > 6:
                title = img_alt

            if not title or len(title) < 6:
                for sel in [
                    "h2 a.a-link-normal span",
                    "a.a-link-normal span.a-text-normal",
                    "span.a-size-medium.a-text-normal",
                    "span.a-size-base-plus.a-text-normal",
                    "h2 span",
                ]:
                    el = card.select_one(sel)
                    if el and len(el.get_text(strip=True)) > len(title):
                        title = el.get_text(strip=True)

            # Clean sponsored ad prefixes
            title = re.sub(r"^Sponsored Ad\s*-\s*", "", title, flags=re.IGNORECASE).strip()
            title = re.sub(r"^Sponsored\s*", "", title, flags=re.IGNORECASE).strip()

            if brand and title and not title.lower().startswith(brand.lower()):
                full_title = f"{brand} {title}"
            else:
                full_title = title or brand

            if len(full_title) < 3:
                continue

            # 2. Exact Live Price
            price_val = None
            price_tag = card.select_one(".a-price .a-price-whole")
            if price_tag:
                price_str = price_tag.get_text(strip=True).replace(",", "").rstrip(".")
                try:
                    price_val = float(price_str)
                except ValueError:
                    pass

            if price_val is None:
                offscreen = card.select_one(".a-price span.a-offscreen")
                if offscreen:
                    m = re.search(r"[\d,]+", offscreen.get_text())
                    if m:
                        try:
                            price_val = float(m.group(0).replace(",", ""))
                        except ValueError:
                            pass

            if price_val is None:
                continue

            # 3. MRP / Strike Price
            mrp_val = None
            mrp_tag = card.select_one(
                ".a-price.a-text-price span.a-offscreen, span.a-price[data-a-strike='true'] span.a-offscreen"
            )
            if mrp_tag:
                m = re.search(r"[\d,]+", mrp_tag.get_text())
                if m:
                    try:
                        mrp_val = float(m.group(0).replace(",", ""))
                    except ValueError:
                        pass

            if mrp_val is None or mrp_val < price_val:
                mrp_val = price_val

            # 4. Rating & Reviews
            rating = 4.2
            rating_tag = card.select_one("i.a-icon-star-small span.a-icon-alt, span.a-icon-alt")
            if rating_tag:
                rating_text = rating_tag.get_text(strip=True)
                rating_match = re.search(r"([\d.]+)\s*out of", rating_text)
                if rating_match:
                    try:
                        rating = float(rating_match.group(1))
                    except ValueError:
                        pass

            reviews_count = 0
            reviews_tag = card.select_one("span.a-size-base.s-underline-text, a[href*='customerReviews'] span")
            if reviews_tag:
                reviews_count_text = reviews_tag.get_text(strip=True).replace(",", "")
                m_rev = re.search(r"\d+", reviews_count_text)
                if m_rev:
                    try:
                        reviews_count = int(m_rev.group(0))
                    except ValueError:
                        pass

            # 5. Product URL
            link_tag = card.select_one("a.a-link-normal[href*='/dp/'], h2 a, a.a-link-normal.s-no-outline")
            href = link_tag.get("href", "") if link_tag else ""
            if href.startswith("/"):
                product_url = f"{AMAZON_BASE_URL}{href}"
            elif href.startswith("http"):
                product_url = href
            else:
                product_url = f"{AMAZON_BASE_URL}/dp/{asin}"

            discount_pct = 0.0
            if mrp_val and mrp_val > price_val:
                discount_pct = round(((mrp_val - price_val) / mrp_val) * 100, 1)

            # Check relevance score: boost if title contains main query keywords
            relevance = sum(1 for w in query_words if w in full_title.lower())

            product = {
                "sku": f"AMZ-{asin}",
                "asin": asin,
                "title": full_title,
                "category": query.title(),
                "price": price_val,
                "mrp": mrp_val,
                "discount_pct": discount_pct,
                "currency": "INR",
                "rating": rating,
                "review_count": reviews_count,
                "availability": "In Stock",
                "competitor_name": "Amazon India",
                "product_url": product_url,
                "image_url": img_src,
                "is_prime": bool(card.select_one("i.a-icon-prime")),
                "relevance": relevance,
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            }
            products.append(product)

        # Sort products by query keyword relevance so exact matches come first
        products.sort(key=lambda x: x.get("relevance", 0), reverse=True)
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
