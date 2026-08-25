"""
pipeline/models.py
==================
SQLAlchemy ORM models for the Competitor Pricing Engine database.

Tables
------
* ``products``      — Master catalogue of scraped products.
* ``price_history`` — Time-series price records per product per competitor.
* ``scrape_runs``   — Audit log of each scraping session.

Author : Aniket Yadav | BBD
Version: 1.0.0
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    MappedColumn,
    mapped_column,
    relationship,
    sessionmaker,
)


# ---------------------------------------------------------------------------
# Database URL — read from env, fall back to local SQLite
# ---------------------------------------------------------------------------
DATABASE_URL: str = os.getenv(
    "DATABASE_URL", "sqlite:///./data/db/pricing_engine.db"
)
DB_ECHO: bool = os.getenv("DB_ECHO", "False").lower() == "true"


# ---------------------------------------------------------------------------
# Engine & Session Factory
# ---------------------------------------------------------------------------
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # Required for SQLite
    echo=DB_ECHO,
)

# Enable WAL mode for better SQLite concurrency
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):  # type: ignore[no-untyped-def]
    """Enable WAL mode and foreign key enforcement on every connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


# ---------------------------------------------------------------------------
# Declarative Base
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
    pass


# ---------------------------------------------------------------------------
# ORM Models
# ---------------------------------------------------------------------------

class ScrapeRun(Base):
    """
    Audit record for each scraping session.

    Stores metadata about when a scrape ran, how many records were
    collected, and whether it succeeded — enabling full traceability.
    """

    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    records_scraped: Mapped[int] = mapped_column(Integer, default=0)
    records_cleaned: Mapped[int] = mapped_column(Integer, default=0)
    source_file: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default="running"
    )  # running | success | failed
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    price_records: Mapped[list["PriceHistory"]] = relationship(
        "PriceHistory", back_populates="scrape_run", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<ScrapeRun id={self.id} status={self.status!r} "
            f"records={self.records_scraped}>"
        )


class Product(Base):
    """
    Master product catalogue.

    One row per unique product title. Acts as the dimension table
    that ``PriceHistory`` records reference.
    """

    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("title", name="uq_product_title"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    avg_rating: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    price_history: Mapped[list["PriceHistory"]] = relationship(
        "PriceHistory", back_populates="product", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Product id={self.id} title={self.title[:40]!r}>"


class PriceHistory(Base):
    """
    Time-series fact table recording every competitor price observation.

    Each row represents one price data point scraped from one competitor
    at one point in time. This is the primary table consumed by the ML
    pricing engine and the analytics dashboard.
    """

    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Foreign Keys
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scrape_run_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("scrape_runs.id", ondelete="SET NULL"), nullable=True
    )

    # Core price observation fields
    competitor: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    price_gbp: Mapped[float] = mapped_column(Float, nullable=False)
    price_usd: Mapped[float] = mapped_column(Float, default=0.0)
    price_eur: Mapped[float] = mapped_column(Float, default=0.0)
    rating: Mapped[float] = mapped_column(Float, default=0.0)
    in_stock: Mapped[bool] = mapped_column(Boolean, default=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)

    # Timestamp of the original scrape (from CSV) vs when inserted into DB
    scraped_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    inserted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    product: Mapped["Product"] = relationship("Product", back_populates="price_history")
    scrape_run: Mapped[Optional["ScrapeRun"]] = relationship(
        "ScrapeRun", back_populates="price_records"
    )

    def __repr__(self) -> str:
        return (
            f"<PriceHistory product_id={self.product_id} "
            f"competitor={self.competitor!r} price={self.price_gbp:.2f}>"
        )


# ---------------------------------------------------------------------------
# Schema creation helper
# ---------------------------------------------------------------------------

def init_db() -> None:
    """
    Create all database tables if they do not already exist.

    Safe to call multiple times — uses ``CREATE TABLE IF NOT EXISTS``
    semantics via SQLAlchemy's ``checkfirst=True`` behaviour.
    """
    # Ensure the data/db directory exists
    import re
    from pathlib import Path

    match = re.search(r"sqlite:///(.+)", DATABASE_URL)
    if match:
        db_path = Path(match.group(1))
        db_path.parent.mkdir(parents=True, exist_ok=True)

    Base.metadata.create_all(bind=engine)
