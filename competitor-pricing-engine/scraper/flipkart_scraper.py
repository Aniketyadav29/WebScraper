"""
flipkart_scraper.py
===================
Concrete scraper implementation targeting Flipkart (flipkart.com) for
real-time competitor price tracking and product catalog extraction.

Subclasses BaseScraper and integrates realistic browser headers, search
query extraction, and exact price parsing.

Author : Aniket Yadav | BBD
Version: 2.0.0
"""

from __future__ import annotations

import csv
import json
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

FLIPKART_BASE_URL = "https://www.flipkart.com"
FLIPKART_SEARCH_URL = "https://www.flipkart.com/search?q={query}&page={page}"

FLIPKART_HEADER_PROFILES = [
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-IN,en-US;q=0.9,en;q=0.8",
        "Sec-Ch-Ua": '"Google Chrome";v="129", "Not=A?Brand";v="8", "Chromium";v="129"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    },
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Upgrade-Insecure-Requests": "1",
    },
    {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-IN,en;q=0.9",
    }
]


class FlipkartScraper(BaseScraper):
    """
    Scrapes live product search results and product pages from Flipkart.com.
    """

    def __init__(self, config: Optional[ScraperConfig] = None) -> None:
        super().__init__(config)
        self.session.headers.update(FLIPKART_HEADER_PROFILES[0])

    def search(self, query: str, max_pages: int = 1, max_items: int = 20) -> list[dict[str, Any]]:
        """
        Search Flipkart for a query keyword and scrape matching products with exact prices.

        Args:
            query: Keyword to search (e.g., 'iphone 15', 'smartwatch')
            max_pages: Number of result pages to scrape
            max_items: Maximum items to collect

        Returns:
            List of parsed product dictionaries.
        """
        encoded_query = urllib.parse.quote_plus(query.strip())
        collected_products: list[dict[str, Any]] = []

        for page in range(1, max_pages + 1):
            if len(collected_products) >= max_items:
                break

            url = FLIPKART_SEARCH_URL.format(query=encoded_query, page=page)
            self.logger.info("Scraping Flipkart search page %d: %s", page, url)

            response_text = ""
            for h_idx, headers in enumerate(FLIPKART_HEADER_PROFILES):
                try:
                    s = requests.Session()
                    resp = s.get(url, headers=headers, timeout=self.config.timeout)
                    if resp.status_code == 200 and len(resp.text) > 30000:
                        response_text = resp.text
                        break
                except Exception as e:
                    self.logger.debug("Flipkart header %d failed: %s", h_idx, e)

            if not response_text:
                self.logger.warning("Flipkart request challenge or empty response for '%s'", query)
                break

            try:
                soup = self._parse_html(response_text)
                items = self._extract_search_results(soup, query)
                for item in items:
                    if len(collected_products) >= max_items:
                        break
                    collected_products.append(item)
            except Exception as e:
                self.logger.error("Error parsing Flipkart search page %d: %s", page, e)
                break

        self.logger.info("Flipkart scrape complete. Extracted %d products for '%s'.", len(collected_products), query)
        return collected_products

    def _extract_search_results(self, soup: BeautifulSoup, query: str) -> list[dict[str, Any]]:
        """Extract product items from Flipkart search results page across all layout variants."""
        products = []

        cards = soup.select("div[data-id]")
        if not cards:
            cards = soup.select("div._1AtVbE, div._75nlfW, div.slAVV4, div._2kHMtA, div.tUxRFH, div._1sdMkc")

        for card in cards:
            fsn = card.get("data-id", "").strip()

            # Product Title
            title = ""
            title_tag = card.select_one(
                "div.RG5Slk, div.KzDlHZ, div._4rR01T, a.wjcEIp, a.IRpwTa, div.DByuf4, a[title]"
            )
            if title_tag:
                title = title_tag.get("title") or title_tag.get_text(strip=True)
            if not title:
                for a in card.select("a, div"):
                    t = a.get("title", "")
                    if t and len(t) > 5:
                        title = t
                        break
            if not title or len(title) < 4:
                continue

            # Exact Live Price
            price_val = None
            price_tag = card.select_one("div.hZ3P6w, div.Nx9bqj, div._30jeq3, div.hl05eU div")
            if price_tag:
                p_text = price_tag.get_text(strip=True).replace("₹", "").replace(",", "")
                try:
                    price_val = float(p_text)
                except ValueError:
                    pass

            if price_val is None:
                for el in card.find_all(string=re.compile(r"₹\s*[\d,]+")):
                    m = re.search(r"₹\s*([\d,]+)", el)
                    if m:
                        try:
                            price_val = float(m.group(1).replace(",", ""))
                            break
                        except ValueError:
                            pass

            if price_val is None:
                continue

            # MRP / Original Price
            mrp_val = None
            mrp_tag = card.select_one("div.yRaY8j, div._3I9_wc, div.k6tDYS, div._27tl2u")
            if mrp_tag:
                m_text = mrp_tag.get_text(strip=True).replace("₹", "").replace(",", "")
                try:
                    mrp_val = float(m_text)
                except ValueError:
                    pass

            if mrp_val is None or mrp_val < price_val:
                mrp_val = price_val

            # Rating
            rating = 4.2
            rating_tag = card.select_one("div.XQDdHH, div._3LWZlK, span._1lRcqv")
            if rating_tag:
                try:
                    rating = float(rating_tag.get_text(strip=True))
                except ValueError:
                    pass

            # Rating / Review count
            reviews_count = 0
            reviews_tag = card.select_one("span.Wphh3Z, span._2_R_DZ")
            if reviews_tag:
                rev_text = reviews_tag.get_text(strip=True)
                rev_digits = re.findall(r"[\d,]+", rev_text)
                if rev_digits:
                    try:
                        reviews_count = int(rev_digits[0].replace(",", ""))
                    except ValueError:
                        pass

            # Product URL
            link_tag = card.select_one("a[href*='/p/'], a.CGtC5Q, a._1fQZEK, a[href*='flipkart.com']")
            href = link_tag.get("href", "") if link_tag else ""
            if href.startswith("/"):
                product_url = f"{FLIPKART_BASE_URL}{href}"
            elif href.startswith("http"):
                product_url = href
            else:
                product_url = f"{FLIPKART_BASE_URL}/search?q={urllib.parse.quote_plus(title)}"

            # Image
            img_tag = card.select_one(
                "img.DByuf4, img._396cs4, img._2r_T1I, img[src*='flixcart.com'], img[src*='rukminim']"
            )
            img_url = img_tag.get("src", "") if img_tag else ""

            discount_pct = 0.0
            if mrp_val and mrp_val > price_val:
                discount_pct = round(((mrp_val - price_val) / mrp_val) * 100, 1)

            sku_val = f"FLP-{fsn}" if fsn else f"FLP-{abs(hash(title)) % 1000000}"

            product = {
                "sku": sku_val,
                "fsn": fsn,
                "title": title,
                "category": query.title(),
                "price": price_val,
                "mrp": mrp_val,
                "discount_pct": discount_pct,
                "currency": "INR",
                "rating": rating,
                "review_count": reviews_count,
                "availability": "In Stock",
                "competitor_name": "Flipkart",
                "product_url": product_url,
                "image_url": img_url,
                "is_plus": bool(card.select_one("img[src*='plus']")),
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            }
            products.append(product)

        return products

    def _extract_product(self, soup: BeautifulSoup, url: str) -> dict[str, Any]:
        """Parse a single Flipkart product page."""
        title_el = soup.select_one("span.B_NuCI, h1.ProductTitle, span.VU-ZEz")
        title = title_el.get_text(strip=True) if title_el else "Unknown Flipkart Product"

        price_el = soup.select_one("div.Nx9bqj, div._30jeq3, div.hZ3P6w")
        price_val = float(price_el.get_text(strip=True).replace("₹", "").replace(",", "")) if price_el else 0.0

        return {
            "title": title,
            "price": price_val,
            "product_url": url,
            "competitor_name": "Flipkart",
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        }

    def scrape(self, urls: list[str]) -> list[dict[str, Any]]:
        """Scrape a list of direct Flipkart product URLs."""
        results = []
        for url in urls:
            try:
                self._polite_delay()
                res = self.session.get(url, timeout=self.config.timeout)
                if res.status_code == 200:
                    soup = self._parse_html(res.text)
                    results.append(self._extract_product(soup, url))
            except Exception as e:
                self.logger.error("Failed to scrape Flipkart URL %s: %s", url, e)
        return results
