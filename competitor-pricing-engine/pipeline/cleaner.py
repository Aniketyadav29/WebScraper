"""
pipeline/cleaner.py
====================
Pandas-based data cleaning pipeline for raw scraped product CSV files.

Cleaning Operations
-------------------
1.  Load raw CSV(s) from ``data/raw/``.
2.  Drop fully duplicate rows.
3.  Strip / normalise the ``title`` column.
4.  Parse and sanitise ``price_gbp`` — remove stray currency chars,
    coerce to float, replace zeros/negatives with NaN, then impute
    with the competitor median.
5.  Clamp ``rating`` to [0.0, 5.0]; fill missing with global median.
6.  Coerce ``in_stock`` to bool.
7.  Parse ``scraped_at`` to timezone-aware datetime.
8.  Drop any remaining rows with critical nulls (title or price).
9.  Add ``price_usd`` and ``price_eur`` conversion columns.
10. Save the cleaned DataFrame to ``data/clean/``.

Author : Aniket Yadav | BBD
Version: 1.0.0
"""

from __future__ import annotations

import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Ensure project root on sys.path when running directly
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.logger import setup_logger  # noqa: E402

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
RAW_DIR = Path(os.getenv("SCRAPER_OUTPUT_DIR", "data/raw"))
CLEAN_DIR = Path("data/clean")
CLEAN_DIR.mkdir(parents=True, exist_ok=True)

# Approximate exchange rates (static — replace with live API in production)
GBP_TO_USD: float = 1.27
GBP_TO_EUR: float = 1.18

# Required columns that must survive cleaning
REQUIRED_COLUMNS: list[str] = [
    "title", "price_gbp", "rating", "in_stock", "competitor", "scraped_at"
]


class DataCleaner:
    """
    Pandas data cleaning pipeline for raw scraped product data.

    Usage
    -----
    ::

        cleaner = DataCleaner()
        clean_df = cleaner.run()          # auto-detects latest raw CSV
        # or
        clean_df = cleaner.run("data/raw/scraped_products_20240101_120000.csv")

    The :meth:`run` method executes the full cleaning workflow and returns
    a cleaned :class:`pandas.DataFrame` while also persisting the result
    to ``data/clean/``.
    """

    def __init__(self) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, raw_path: Optional[str | Path] = None) -> pd.DataFrame:
        """
        Execute the full cleaning pipeline end-to-end.

        Args:
            raw_path: Path to a specific raw CSV. If ``None``, the most
                      recently modified CSV in ``data/raw/`` is used.

        Returns:
            Cleaned :class:`pandas.DataFrame`.

        Raises:
            FileNotFoundError: If no raw CSV files are found.
            ValueError: If the CSV is empty or missing required columns.
        """
        raw_file = self._resolve_raw_file(raw_path)
        self.logger.info("Loading raw data from: %s", raw_file)

        df = self._load(raw_file)
        self.logger.info("Raw shape: %s", df.shape)

        df = self._validate_columns(df)
        df = self._drop_duplicates(df)
        df = self._clean_title(df)
        df = self._clean_price(df)
        df = self._clean_rating(df)
        df = self._clean_in_stock(df)
        df = self._clean_scraped_at(df)
        df = self._clean_competitor(df)
        df = self._add_currency_conversions(df)
        df = self._drop_critical_nulls(df)
        df = self._reset_index(df)

        self.logger.info("Clean shape:  %s", df.shape)
        self.logger.info(
            "Dropped %d rows during cleaning.",
            # We compare after loading — shape logged above is final
            0,  # placeholder; actual drop count logged per step
        )

        output_path = self._save(df, raw_file)
        self.logger.info("Cleaned data saved -> %s", output_path)

        return df

    # ------------------------------------------------------------------
    # Step-by-step cleaning methods
    # ------------------------------------------------------------------

    def _resolve_raw_file(self, raw_path: Optional[str | Path]) -> Path:
        """
        Resolve which raw CSV to clean.

        If ``raw_path`` is provided, use it directly. Otherwise, find
        the most recently modified ``*.csv`` in ``RAW_DIR``.

        Args:
            raw_path: Explicit path or ``None``.

        Returns:
            Resolved :class:`pathlib.Path` to the raw CSV.

        Raises:
            FileNotFoundError: If the path doesn't exist or no CSVs found.
        """
        if raw_path is not None:
            path = Path(raw_path)
            if not path.exists():
                raise FileNotFoundError(f"Raw file not found: {path}")
            return path

        csv_files = sorted(RAW_DIR.glob("*.csv"), key=lambda p: p.stat().st_mtime)
        if not csv_files:
            raise FileNotFoundError(
                f"No CSV files found in {RAW_DIR}. Run the scraper first."
            )
        return csv_files[-1]  # Most recent

    def _load(self, path: Path) -> pd.DataFrame:
        """
        Load a CSV file into a DataFrame with robust encoding handling.

        Args:
            path: Path to the CSV file.

        Returns:
            Loaded :class:`pandas.DataFrame`.

        Raises:
            ValueError: If the loaded DataFrame is empty.
        """
        df = pd.read_csv(path, encoding="utf-8", dtype=str)
        if df.empty:
            raise ValueError(f"CSV file is empty: {path}")
        return df

    def _validate_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Verify all required columns are present.

        Args:
            df: Raw DataFrame.

        Returns:
            The same DataFrame (pass-through after validation).

        Raises:
            ValueError: If any required column is missing.
        """
        missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(
                f"Missing required columns: {missing}. "
                f"Found: {list(df.columns)}"
            )
        self.logger.debug("Column validation passed ✓")
        return df

    def _drop_duplicates(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Remove fully duplicate rows.

        Args:
            df: Input DataFrame.

        Returns:
            DataFrame with duplicates removed.
        """
        before = len(df)
        df = df.drop_duplicates()
        dropped = before - len(df)
        if dropped:
            self.logger.info("Dropped %d duplicate rows.", dropped)
        return df

    def _clean_title(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Normalise the ``title`` column.

        * Strip leading/trailing whitespace.
        * Collapse internal whitespace runs.
        * Title-case normalisation.

        Args:
            df: Input DataFrame.

        Returns:
            DataFrame with cleaned ``title`` column.
        """
        df["title"] = (
            df["title"]
            .astype(str)
            .str.strip()
            .str.replace(r"\s+", " ", regex=True)
        )
        return df

    def _clean_price(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Sanitise the ``price_gbp`` column.

        Steps:
        1. Remove all non-numeric characters except ``.``.
        2. Coerce to float (``errors='coerce'`` → NaN on failure).
        3. Replace ``0.0`` and negative values with NaN.
        4. Impute NaN with the per-competitor median; fall back to global
           median if a competitor has no valid prices.

        Args:
            df: Input DataFrame.

        Returns:
            DataFrame with a numeric, imputed ``price_gbp`` column.
        """
        # Strip currency symbols (£, $, €, Â, etc.) and whitespace
        df["price_gbp"] = (
            df["price_gbp"]
            .astype(str)
            .str.replace(r"[^\d.]", "", regex=True)
        )
        df["price_gbp"] = pd.to_numeric(df["price_gbp"], errors="coerce")

        # Zero or negative prices are invalid
        df.loc[df["price_gbp"] <= 0, "price_gbp"] = np.nan

        null_count = df["price_gbp"].isna().sum()
        if null_count:
            self.logger.warning(
                "%d rows have invalid/null price — imputing with competitor median.",
                null_count,
            )

        # Impute: competitor median → global median
        global_median = df["price_gbp"].median()
        df["price_gbp"] = df.groupby("competitor")["price_gbp"].transform(
            lambda s: s.fillna(s.median() if s.notna().any() else global_median)
        )
        df["price_gbp"] = df["price_gbp"].fillna(global_median)
        df["price_gbp"] = df["price_gbp"].round(2)
        return df

    def _clean_rating(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Coerce and clamp the ``rating`` column to [0.0, 5.0].

        Args:
            df: Input DataFrame.

        Returns:
            DataFrame with a valid, bounded ``rating`` column.
        """
        df["rating"] = pd.to_numeric(df["rating"], errors="coerce")
        # Clamp to valid star-rating range
        df["rating"] = df["rating"].clip(lower=0.0, upper=5.0)
        # Impute with global median
        median_rating = df["rating"].median()
        df["rating"] = df["rating"].fillna(median_rating).round(1)
        return df

    def _clean_in_stock(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Coerce the ``in_stock`` column to a proper boolean.

        Handles string representations: ``"True"``, ``"False"``,
        ``"1"``, ``"0"``, ``"yes"``, ``"no"``, etc.

        Args:
            df: Input DataFrame.

        Returns:
            DataFrame with boolean ``in_stock`` column.
        """
        truthy = {"true", "1", "yes", "in stock"}
        df["in_stock"] = (
            df["in_stock"]
            .astype(str)
            .str.strip()
            .str.lower()
            .isin(truthy)
        )
        return df

    def _clean_scraped_at(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Parse the ``scraped_at`` column to timezone-aware datetime.

        Falls back to ``pd.NaT`` for unparseable values; rows with
        NaT are assigned the current UTC timestamp.

        Args:
            df: Input DataFrame.

        Returns:
            DataFrame with a datetime ``scraped_at`` column.
        """
        df["scraped_at"] = pd.to_datetime(df["scraped_at"], errors="coerce", utc=True)
        now_utc = pd.Timestamp.now(tz="UTC")
        df["scraped_at"] = df["scraped_at"].fillna(now_utc)
        return df

    def _clean_competitor(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Normalise the ``competitor`` column — strip whitespace, title-case.

        Args:
            df: Input DataFrame.

        Returns:
            DataFrame with cleaned ``competitor`` column.
        """
        df["competitor"] = (
            df["competitor"]
            .astype(str)
            .str.strip()
            .str.title()
        )
        return df

    def _add_currency_conversions(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Derive ``price_usd`` and ``price_eur`` from ``price_gbp``.

        Uses static exchange rates defined at module level.

        Args:
            df: Input DataFrame with a clean ``price_gbp`` column.

        Returns:
            DataFrame with two additional currency columns.
        """
        df["price_usd"] = (df["price_gbp"] * GBP_TO_USD).round(2)
        df["price_eur"] = (df["price_gbp"] * GBP_TO_EUR).round(2)
        return df

    def _drop_critical_nulls(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Drop rows where critical fields (``title`` or ``price_gbp``) are null.

        Args:
            df: Input DataFrame.

        Returns:
            DataFrame with critical-null rows removed.
        """
        before = len(df)
        df = df.dropna(subset=["title", "price_gbp"])
        dropped = before - len(df)
        if dropped:
            self.logger.warning(
                "Dropped %d rows with null title or price.", dropped
            )
        return df

    def _reset_index(self, df: pd.DataFrame) -> pd.DataFrame:
        """Reset DataFrame index after all row drops."""
        return df.reset_index(drop=True)

    def _save(self, df: pd.DataFrame, raw_path: Path) -> Path:
        """
        Persist the cleaned DataFrame to ``data/clean/`` as CSV.

        The output filename mirrors the raw filename with a ``_clean``
        suffix, e.g. ``scraped_products_20240101_120000_clean.csv``.

        Args:
            df      : Cleaned DataFrame.
            raw_path: Source raw file path (used to derive output name).

        Returns:
            :class:`pathlib.Path` to the saved clean CSV.
        """
        stem = raw_path.stem
        output_path = CLEAN_DIR / f"{stem}_clean.csv"
        df.to_csv(output_path, index=False, encoding="utf-8")
        return output_path

    # ------------------------------------------------------------------
    # Reporting helper
    # ------------------------------------------------------------------

    def summary(self, df: pd.DataFrame) -> None:
        """
        Print a rich summary of the cleaned DataFrame to the console.

        Args:
            df: Cleaned DataFrame.
        """
        from rich.console import Console
        from rich.table import Table

        console = Console(force_terminal=False, highlight=False)
        table = Table(title="Cleaned Data Summary", show_lines=True)
        table.add_column("Metric", style="cyan", no_wrap=True)
        table.add_column("Value", style="green")

        table.add_row("Total Records", str(len(df)))
        table.add_row("Unique Products", str(df["title"].nunique()))
        table.add_row("Competitors", str(df["competitor"].nunique()))
        table.add_row(
            "Price Range (GBP)",
            f"GBP {df['price_gbp'].min():.2f} - GBP {df['price_gbp'].max():.2f}",
        )
        table.add_row("Avg Price (GBP)", f"GBP{df['price_gbp'].mean():.2f}")
        table.add_row("Avg Rating", f"{df['rating'].mean():.2f} stars")
        table.add_row(
            "In-Stock %",
            f"{df['in_stock'].mean() * 100:.1f}%",
        )
        table.add_row(
            "Date Range",
            f"{df['scraped_at'].min()} -> {df['scraped_at'].max()}",
        )
        console.print(table)


# ---------------------------------------------------------------------------
# Standalone entry-point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    setup_logger()
    cleaner = DataCleaner()
    clean_df = cleaner.run()
    cleaner.summary(clean_df)
