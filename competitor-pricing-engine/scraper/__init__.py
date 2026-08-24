"""
Scraper Package Initializer
============================
Exposes the main scraper classes for external import.
"""

from .base_scraper import BaseScraper
from .product_scraper import ProductScraper

__all__ = ["BaseScraper", "ProductScraper"]
