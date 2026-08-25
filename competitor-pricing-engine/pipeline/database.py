"""
pipeline/database.py
=====================
SQLAlchemy-powered database ingestion layer.

Responsibilities
----------------
* Call ``init_db()`` to create the schema on first run.
* Ingest a cleaned :class:`pandas.DataFrame` into the database.
* Handle upsert logic for the ``products`` dimension table.
* Bulk-insert ``price_history`` fact rows efficiently.
* Log each ingestion as a ``scrape_run`` audit record.

Author : Aniket Yadav | BBD
Version: 1.0.0
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Ensure project root on sys.path
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.models import (  # noqa: E402
    PriceHistory,
    Product,
    ScrapeRun,
    SessionLocal,
    init_db,
)

logger = logging.getLogger(__name__)


class DatabaseIngestion:
    """
    Orchestrates the full ingestion of cleaned data into the SQLite database.

    Workflow
    --------
    1. Initialise the DB schema (idempotent).
    2. Open a ``ScrapeRun`` audit record.
    3. Upsert each unique product title into ``products``.
    4. Bulk-insert all price observations into ``price_history``.
    5. Close the ``ScrapeRun`` with status ``success`` (or ``failed``).

    Usage
    -----
    ::

        from pipeline.database import DatabaseIngestion
        ingestion = DatabaseIngestion()
        ingestion.ingest(clean_df, source_file="data/raw/scraped_20240101.csv")
    """

    def __init__(self) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)
        init_db()
        self.logger.info("Database schema initialised ✓")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ingest(
        self,
        df: pd.DataFrame,
        source_file: Optional[str] = None,
    ) -> int:
        """
        Ingest a cleaned DataFrame into the database.

        Args:
            df          : Cleaned DataFrame from :class:`DataCleaner`.
            source_file : Path to the source CSV (for audit purposes).

        Returns:
            Number of ``price_history`` rows inserted.

        Raises:
            Exception: Re-raises any unexpected DB errors after
                       marking the ``ScrapeRun`` as failed.
        """
        self.logger.info(
            "Starting DB ingestion — %d rows from '%s'", len(df), source_file
        )
        scrape_run = self._open_scrape_run(source_file, len(df))

        try:
            with SessionLocal() as session:
                # Step 1: Upsert products dimension
                product_map = self._upsert_products(session, df)

                # Step 2: Bulk insert price_history facts
                rows_inserted = self._insert_price_history(
                    session, df, product_map, scrape_run.id
                )

                # Step 3: Update the scrape_run with results
                self._close_scrape_run(
                    scrape_run,
                    records_cleaned=rows_inserted,
                    status="success",
                )

            self.logger.info(
                "Ingestion complete — %d price_history rows inserted.", rows_inserted
            )
            return rows_inserted

        except Exception as exc:
            self.logger.error("Ingestion failed: %s", exc, exc_info=True)
            self._close_scrape_run(scrape_run, status="failed", error=str(exc))
            raise

    def get_latest_prices(self, limit: int = 100) -> pd.DataFrame:
        """
        Query the most recent price observation per product per competitor.

        Args:
            limit: Maximum number of rows to return.

        Returns:
            :class:`pandas.DataFrame` with columns:
            ``title``, ``competitor``, ``price_gbp``, ``rating``,
            ``in_stock``, ``scraped_at``.
        """
        sql = """
            SELECT
                p.title,
                ph.competitor,
                ph.price_gbp,
                ph.price_usd,
                ph.price_eur,
                ph.rating,
                ph.in_stock,
                ph.scraped_at
            FROM price_history ph
            JOIN products p ON ph.product_id = p.id
            WHERE ph.id IN (
                SELECT MAX(id)
                FROM price_history
                GROUP BY product_id, competitor
            )
            ORDER BY ph.scraped_at DESC
            LIMIT :limit
        """
        from pipeline.models import engine
        return pd.read_sql(sql, con=engine, params={"limit": limit})

    def get_price_history(self, title: str) -> pd.DataFrame:
        """
        Retrieve full price history for a specific product title.

        Args:
            title: Exact product title string.

        Returns:
            :class:`pandas.DataFrame` with all price observations.
        """
        sql = """
            SELECT
                p.title,
                ph.competitor,
                ph.price_gbp,
                ph.price_usd,
                ph.price_eur,
                ph.rating,
                ph.in_stock,
                ph.scraped_at
            FROM price_history ph
            JOIN products p ON ph.product_id = p.id
            WHERE p.title = :title
            ORDER BY ph.scraped_at ASC
        """
        from pipeline.models import engine
        return pd.read_sql(sql, con=engine, params={"title": title})

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _open_scrape_run(
        self, source_file: Optional[str], records_scraped: int
    ) -> ScrapeRun:
        """
        Create and persist an open ``ScrapeRun`` audit record.

        Args:
            source_file     : CSV file path string.
            records_scraped : Number of raw rows to be ingested.

        Returns:
            Persisted :class:`ScrapeRun` ORM instance.
        """
        with SessionLocal() as session:
            run = ScrapeRun(
                started_at=datetime.now(timezone.utc),
                records_scraped=records_scraped,
                source_file=str(source_file) if source_file else None,
                status="running",
            )
            session.add(run)
            session.commit()
            session.refresh(run)
            # Detach from session to use outside context
            run_id = run.id

        # Re-fetch as a detached object
        with SessionLocal() as session:
            run = session.get(ScrapeRun, run_id)
            session.expunge(run)
        return run

    def _close_scrape_run(
        self,
        run: ScrapeRun,
        status: str = "success",
        records_cleaned: int = 0,
        error: Optional[str] = None,
    ) -> None:
        """
        Update an existing ``ScrapeRun`` with completion status.

        Args:
            run             : The :class:`ScrapeRun` to update.
            status          : ``"success"`` or ``"failed"``.
            records_cleaned : Number of rows actually inserted.
            error           : Error message if status is ``"failed"``.
        """
        with SessionLocal() as session:
            db_run = session.get(ScrapeRun, run.id)
            if db_run:
                db_run.completed_at = datetime.now(timezone.utc)
                db_run.status = status
                db_run.records_cleaned = records_cleaned
                db_run.error_message = error
                session.commit()

    def _upsert_products(
        self, session: Session, df: pd.DataFrame
    ) -> dict[str, int]:
        """
        Upsert unique product titles into the ``products`` table.

        For each unique title:
        * If it already exists → update ``avg_rating`` and return its ID.
        * If it's new → create a new record.

        Args:
            session : Active SQLAlchemy session.
            df      : Cleaned DataFrame.

        Returns:
            Dict mapping ``title → product.id``.
        """
        product_map: dict[str, int] = {}
        unique_products = (
            df.groupby("title")["rating"]
            .mean()
            .reset_index()
            .rename(columns={"rating": "avg_rating"})
        )

        for _, row in unique_products.iterrows():
            title: str = row["title"]
            avg_rating: float = round(float(row["avg_rating"]), 2)

            # Check if product already exists
            existing = (
                session.query(Product).filter(Product.title == title).first()
            )
            if existing:
                existing.avg_rating = avg_rating
                existing.updated_at = datetime.now(timezone.utc)
                session.flush()
                product_map[title] = existing.id
            else:
                product = Product(title=title, avg_rating=avg_rating)
                session.add(product)
                try:
                    session.flush()
                    product_map[title] = product.id
                except IntegrityError:
                    session.rollback()
                    # Race condition: another process inserted first
                    existing = (
                        session.query(Product)
                        .filter(Product.title == title)
                        .first()
                    )
                    if existing:
                        product_map[title] = existing.id

        session.commit()
        self.logger.info(
            "Upserted %d unique products into 'products' table.",
            len(product_map),
        )
        return product_map

    def _insert_price_history(
        self,
        session: Session,
        df: pd.DataFrame,
        product_map: dict[str, int],
        scrape_run_id: int,
    ) -> int:
        """
        Bulk-insert all price observations into ``price_history``.

        Constructs ORM objects in batches of 500 for memory efficiency.

        Args:
            session       : Active SQLAlchemy session.
            df            : Cleaned DataFrame.
            product_map   : ``title → product_id`` mapping.
            scrape_run_id : ID of the current :class:`ScrapeRun`.

        Returns:
            Number of rows successfully inserted.
        """
        BATCH_SIZE = 500
        records: list[PriceHistory] = []
        skipped = 0

        for _, row in df.iterrows():
            product_id = product_map.get(row["title"])
            if product_id is None:
                skipped += 1
                continue

            # Parse scraped_at — may be Timestamp or string
            scraped_at = row.get("scraped_at")
            if pd.isna(scraped_at) if isinstance(scraped_at, float) else False:
                scraped_at = datetime.now(timezone.utc)
            elif isinstance(scraped_at, pd.Timestamp):
                scraped_at = scraped_at.to_pydatetime()

            record = PriceHistory(
                product_id=product_id,
                scrape_run_id=scrape_run_id,
                competitor=str(row.get("competitor", "Unknown")),
                price_gbp=float(row.get("price_gbp", 0.0)),
                price_usd=float(row.get("price_usd", 0.0)),
                price_eur=float(row.get("price_eur", 0.0)),
                rating=float(row.get("rating", 0.0)),
                in_stock=bool(row.get("in_stock", True)),
                source_url=str(row.get("source_url", "")) or None,
                scraped_at=scraped_at,
            )
            records.append(record)

            # Flush in batches
            if len(records) >= BATCH_SIZE:
                session.add_all(records)
                session.flush()
                records = []

        # Flush remaining
        if records:
            session.add_all(records)

        session.commit()

        inserted = len(df) - skipped
        if skipped:
            self.logger.warning(
                "Skipped %d rows (no product_id found).", skipped
            )
        return inserted


# ---------------------------------------------------------------------------
# Standalone entry-point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    from utils.logger import setup_logger
    from pipeline.cleaner import DataCleaner

    setup_logger()

    # Step 1: Clean raw data
    cleaner = DataCleaner()
    clean_df = cleaner.run()
    cleaner.summary(clean_df)

    # Step 2: Ingest into DB
    ingestion = DatabaseIngestion()
    rows = ingestion.ingest(clean_df)

    print(f"\n✅ Ingested {rows} rows into the database.\n")

    # Step 3: Preview latest prices from DB
    print("── Latest prices from DB (top 10) ──")
    latest = ingestion.get_latest_prices(limit=10)
    print(latest.to_string(index=False))
