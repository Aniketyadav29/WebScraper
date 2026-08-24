"""
base_scraper.py
================
Abstract Base Class for all web scrapers in the Competitor Pricing Engine.

Design Pattern: Template Method Pattern — defines the scraping skeleton
while deferring concrete implementation to subclasses.

Author : Aniket Yadav | BBD
Version: 1.0.0
"""

import logging
import random
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)


# ---------------------------------------------------------------------------
# Module-level logger — each subclass will inherit & extend this logger.
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)


class ScraperConfig:
    """
    Immutable configuration container for scraper parameters.

    Centralises all tunable knobs so that concrete scrapers remain
    free of hardcoded constants.
    """

    def __init__(
        self,
        delay_min: float = 1.5,
        delay_max: float = 3.5,
        max_retries: int = 3,
        timeout: int = 30,
        headless: bool = True,
        output_dir: str = "data/raw",
    ) -> None:
        """
        Initialise the scraper configuration.

        Args:
            delay_min   : Minimum polite delay between requests (seconds).
            delay_max   : Maximum polite delay between requests (seconds).
            max_retries : Maximum number of retry attempts per request.
            timeout     : HTTP request / page-load timeout (seconds).
            headless    : Whether to run the browser in headless mode.
            output_dir  : Directory where raw CSV output will be saved.
        """
        self.delay_min = delay_min
        self.delay_max = delay_max
        self.max_retries = max_retries
        self.timeout = timeout
        self.headless = headless
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def __repr__(self) -> str:
        return (
            f"ScraperConfig(delay={self.delay_min}-{self.delay_max}s, "
            f"retries={self.max_retries}, timeout={self.timeout}s)"
        )


class BaseScraper(ABC):
    """
    Abstract base class that every concrete scraper must subclass.

    Responsibilities
    ----------------
    * Manages a rotating ``UserAgent`` pool to avoid bot-detection.
    * Provides a polite, randomised ``_polite_delay()`` between requests.
    * Wraps HTTP fetching in exponential-backoff retry logic via Tenacity.
    * Enforces the ``scrape()`` contract through an abstract method.
    * Offers a ``_parse_html()`` helper that returns a BeautifulSoup tree.

    Subclasses MUST implement
    --------------------------
    * ``scrape(urls)`` — orchestrate the full scraping workflow.
    * ``_extract_product(soup, url)`` — parse a single page into a dict.
    """

    def __init__(self, config: Optional[ScraperConfig] = None) -> None:
        """
        Initialise the base scraper.

        Args:
            config: A ``ScraperConfig`` instance. Defaults to sensible values.
        """
        self.config: ScraperConfig = config or ScraperConfig()
        self._ua: UserAgent = UserAgent()
        self.session: requests.Session = self._build_session()
        self.logger: logging.Logger = logging.getLogger(
            self.__class__.__name__
        )
        self.logger.info(
            "Scraper initialised with config: %s", self.config
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_session(self) -> requests.Session:
        """
        Create a ``requests.Session`` with default headers.

        Returns:
            A configured :class:`requests.Session` instance.
        """
        session = requests.Session()
        session.headers.update(self._get_headers())
        return session

    def _get_headers(self) -> dict[str, str]:
        """
        Generate a realistic browser header dict using a random User-Agent.

        Returns:
            Dictionary of HTTP request headers.
        """
        return {
            "User-Agent": self._ua.random,
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;"
                "q=0.9,image/avif,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "max-age=0",
        }

    def _polite_delay(self) -> None:
        """
        Sleep for a randomised duration between ``delay_min`` and
        ``delay_max`` to respect the target server's rate limits.
        """
        delay = random.uniform(
            self.config.delay_min, self.config.delay_max
        )
        self.logger.debug("Polite delay: %.2f seconds", delay)
        time.sleep(delay)

    @retry(
        retry=retry_if_exception_type(
            (requests.ConnectionError, requests.Timeout)
        ),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def _fetch(self, url: str) -> requests.Response:
        """
        Perform an HTTP GET request with exponential-backoff retries.

        Rotates the User-Agent header on every attempt to reduce
        fingerprinting risk.

        Args:
            url: The target URL to fetch.

        Returns:
            A :class:`requests.Response` object with status code 200.

        Raises:
            requests.HTTPError: If the server returns a non-2xx status.
            requests.ConnectionError: If the network connection fails.
            requests.Timeout: If the request exceeds the configured timeout.
        """
        # Rotate the User-Agent on every call
        self.session.headers.update({"User-Agent": self._ua.random})

        self.logger.debug("Fetching URL: %s", url)
        response = self.session.get(
            url, timeout=self.config.timeout
        )
        response.raise_for_status()
        return response

    def _parse_html(self, html: str) -> BeautifulSoup:
        """
        Parse an HTML string into a BeautifulSoup document tree.

        Args:
            html: Raw HTML content as a string.

        Returns:
            A :class:`BeautifulSoup` object using the ``lxml`` parser.
        """
        return BeautifulSoup(html, "lxml")

    def _safe_get_text(
        self,
        soup: BeautifulSoup,
        selector: str,
        attribute: Optional[str] = None,
        default: Any = None,
    ) -> Any:
        """
        Safely extract text (or an attribute value) from a CSS-selected
        element. Returns ``default`` instead of raising an exception when
        the element is absent — critical for robust scraping.

        Args:
            soup      : The BeautifulSoup context to search within.
            selector  : CSS selector string.
            attribute : If provided, return this attribute's value instead
                        of the element's text content.
            default   : Fallback value when the element is not found.

        Returns:
            Extracted text / attribute value, or ``default``.
        """
        try:
            element = soup.select_one(selector)
            if element is None:
                return default
            if attribute:
                return element.get(attribute, default)
            return element.get_text(strip=True)
        except Exception as exc:  # noqa: BLE001
            self.logger.warning(
                "Failed to extract '%s': %s", selector, exc
            )
            return default

    # ------------------------------------------------------------------
    # Public interface — Template Method pattern
    # ------------------------------------------------------------------

    def fetch_page(self, url: str) -> Optional[BeautifulSoup]:
        """
        High-level method: fetch a URL and return its parsed DOM.

        Combines ``_fetch()``, ``_parse_html()``, and ``_polite_delay()``
        into a single, safe call. Logs and returns ``None`` on failure
        instead of crashing the entire scraping run.

        Args:
            url: The target page URL.

        Returns:
            Parsed :class:`BeautifulSoup` DOM, or ``None`` on failure.
        """
        try:
            response = self._fetch(url)
            self._polite_delay()
            return self._parse_html(response.text)
        except RetryError as exc:
            self.logger.error(
                "All retries exhausted for URL '%s': %s", url, exc
            )
        except requests.HTTPError as exc:
            self.logger.error(
                "HTTP error for URL '%s': %s", url, exc
            )
        except Exception as exc:  # noqa: BLE001
            self.logger.error(
                "Unexpected error fetching '%s': %s", url, exc
            )
        return None

    @abstractmethod
    def scrape(self, urls: list[str]) -> list[dict[str, Any]]:
        """
        Orchestrate the full scraping workflow across all target URLs.

        Args:
            urls: List of target page URLs to scrape.

        Returns:
            List of product data dictionaries.
        """
        ...

    @abstractmethod
    def _extract_product(
        self, soup: BeautifulSoup, url: str
    ) -> Optional[dict[str, Any]]:
        """
        Extract structured product data from a single parsed page.

        Args:
            soup: Parsed BeautifulSoup DOM for the page.
            url : Source URL (used for provenance tracking).

        Returns:
            Dictionary of product fields, or ``None`` if extraction fails.
        """
        ...
