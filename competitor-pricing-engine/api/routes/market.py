"""
api/routes/market.py
=====================
FastAPI router for competitor market data endpoints.

Endpoints
---------
GET /api/v1/market/competitors          — Latest price per product per competitor
GET /api/v1/market/summary              — Aggregated market statistics
GET /api/v1/market/products             — Paginated list of tracked products
GET /api/v1/market/price-history/{title}— Full price history for one product

Author : Aniket Yadav | BBD
Version: 1.0.0
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Query, status

from api.schemas import (
    CompetitorPriceRecord,
    CompetitorSummary,
    EcommerceTrackRequest,
    EcommerceTrackResponse,
    MarketSummaryResponse,
    PriceHistoryRecord,
    PriceHistoryResponse,
    ProductListResponse,
)
from pipeline.database import DatabaseIngestion

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/market", tags=["Market"])

# Singleton DB accessor
_db = DatabaseIngestion()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/competitors",
    response_model=list[CompetitorPriceRecord],
    summary="Latest Competitor Prices",
    description=(
        "Returns the most recent price observation per product per competitor. "
        "Use ``limit`` to control the number of records returned."
    ),
)
async def get_competitor_prices(
    limit: int = Query(default=100, ge=1, le=500, description="Max records to return."),
) -> list[CompetitorPriceRecord]:
    """
    Fetch the latest competitor price data from the database.

    Args:
        limit: Maximum number of records to return (1–500).

    Returns:
        List of :class:`CompetitorPriceRecord` objects.
    """
    try:
        df = _db.get_latest_prices(limit=limit)
    except Exception as exc:
        logger.error("Failed to fetch competitor prices: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {exc}",
        )

    records = []
    for _, row in df.iterrows():
        records.append(CompetitorPriceRecord(
            title=str(row.get("title", "")),
            competitor=str(row.get("competitor", "")),
            price_gbp=float(row.get("price_gbp", 0.0)),
            price_usd=float(row.get("price_usd", 0.0)),
            price_eur=float(row.get("price_eur", 0.0)),
            rating=float(row.get("rating", 0.0)),
            in_stock=bool(row.get("in_stock", True)),
            scraped_at=str(row.get("scraped_at", "")),
        ))
    return records


@router.get(
    "/summary",
    response_model=MarketSummaryResponse,
    summary="Market Summary",
    description="Returns aggregated market statistics across all competitors.",
)
async def get_market_summary() -> MarketSummaryResponse:
    """
    Compute and return aggregated market-level statistics.

    Returns:
        :class:`MarketSummaryResponse` with per-competitor summaries.
    """
    try:
        df = _db.get_latest_prices(limit=500)
    except Exception as exc:
        logger.error("Failed to fetch market summary data: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {exc}",
        )

    if df.empty:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No market data found. Run the scraper and pipeline first.",
        )

    competitors: list[CompetitorSummary] = []
    for comp, group in df.groupby("competitor"):
        competitors.append(CompetitorSummary(
            competitor=str(comp),
            avg_price_gbp=round(float(group["price_gbp"].mean()), 2),
            min_price_gbp=round(float(group["price_gbp"].min()), 2),
            max_price_gbp=round(float(group["price_gbp"].max()), 2),
            product_count=int(len(group)),
            in_stock_pct=round(float(group["in_stock"].mean()) * 100, 1),
        ))

    avg_by_comp = {c.competitor: c.avg_price_gbp for c in competitors}
    cheapest = min(avg_by_comp, key=avg_by_comp.get)
    most_expensive = max(avg_by_comp, key=avg_by_comp.get)

    return MarketSummaryResponse(
        total_products=int(df["title"].nunique()),
        total_competitors=int(df["competitor"].nunique()),
        avg_market_price_gbp=round(float(df["price_gbp"].mean()), 2),
        cheapest_competitor=cheapest,
        most_expensive_competitor=most_expensive,
        competitors=competitors,
        generated_at=datetime.now(timezone.utc),
    )


@router.get(
    "/products",
    response_model=ProductListResponse,
    summary="List Products",
    description="Returns a paginated list of all tracked product titles.",
)
async def list_products(
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)."),
    page_size: int = Query(default=20, ge=1, le=100, description="Records per page."),
) -> ProductListResponse:
    """
    Return a paginated list of unique product titles in the database.

    Args:
        page     : Page number (1-indexed).
        page_size: Number of products per page.

    Returns:
        :class:`ProductListResponse` with paginated product titles.
    """
    try:
        df = _db.get_latest_prices(limit=500)
    except Exception as exc:
        logger.error("Failed to fetch product list: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {exc}",
        )

    all_titles = sorted(df["title"].unique().tolist())
    total = len(all_titles)
    start = (page - 1) * page_size
    end = start + page_size
    page_titles = all_titles[start:end]

    return ProductListResponse(
        products=page_titles,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/price-history/{title}",
    response_model=PriceHistoryResponse,
    summary="Product Price History",
    description=(
        "Returns the full price history for a specific product title "
        "across all competitors."
    ),
)
async def get_price_history(title: str) -> PriceHistoryResponse:
    """
    Retrieve complete price history for a single product.

    Args:
        title: URL-encoded product title string.

    Returns:
        :class:`PriceHistoryResponse` with all historical observations.

    Raises:
        HTTPException 404: If no history found for the given title.
    """
    decoded_title = unquote(title)
    logger.info("Price history request for: '%s'", decoded_title)

    try:
        df = _db.get_price_history(decoded_title)
    except Exception as exc:
        logger.error("Failed to fetch price history: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {exc}",
        )

    if df.empty:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No price history found for product: '{decoded_title}'",
        )

    records = [
        PriceHistoryRecord(
            title=str(row.get("title", "")),
            competitor=str(row.get("competitor", "")),
            price_gbp=float(row.get("price_gbp", 0.0)),
            rating=float(row.get("rating", 0.0)),
            in_stock=bool(row.get("in_stock", True)),
            scraped_at=str(row.get("scraped_at", "")),
        )
        for _, row in df.iterrows()
    ]

    return PriceHistoryResponse(
        title=decoded_title,
        records=records,
        total=len(records),
    )


@router.post(
    "/track-ecommerce",
    response_model=EcommerceTrackResponse,
    summary="Track Amazon & Flipkart Prices",
    description="Scrapes Amazon India and Flipkart for a given search query and returns matched comparisons.",
)
async def track_ecommerce_market(
    payload: EcommerceTrackRequest,
) -> EcommerceTrackResponse:
    """
    Search and track live competitor prices across Amazon and Flipkart.
    """
    from scraper.ecommerce_tracker import EcommerceTracker
    try:
        tracker = EcommerceTracker()
        result = tracker.track(query=payload.query, limit=payload.limit)
        return EcommerceTrackResponse(**result)
    except Exception as exc:
        logger.error("Failed ecommerce tracking: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Tracking failed: {exc}",
        )


@router.get(
    "/ecommerce-catalog",
    response_model=EcommerceTrackResponse,
    summary="Get Complete Amazon vs Flipkart Multi-Goods Catalog",
    description="Returns pre-tracked cross-platform product comparisons across all major categories.",
)
async def get_ecommerce_catalog(
    category: Optional[str] = Query(None, description="Optional category filter (e.g. Smartphones, Laptops, Audio)")
) -> EcommerceTrackResponse:
    """
    Fetch comprehensive side-by-side comparisons of popular goods across Amazon & Flipkart.
    """
    from scraper.ecommerce_tracker import EcommerceTracker
    tracker = EcommerceTracker()
    
    # Track diverse product queries
    catalog_queries = ["iPhone 15", "Samsung Galaxy S24", "MacBook Air M2", "Sony WH-1000XM5", "Apple Watch Series 9", "PlayStation 5", "iPad Air"]
    all_comparisons = []
    
    for q in catalog_queries:
        res = tracker.track(query=q, limit=2)
        all_comparisons.extend(res.get("comparisons", []))
    
    return EcommerceTrackResponse(
        query="All Goods Catalog",
        tracked_at=datetime.now(timezone.utc).isoformat(),
        amazon_count=len(all_comparisons),
        flipkart_count=len(all_comparisons),
        matched_pairs_count=len(all_comparisons),
        comparisons=all_comparisons,
        raw_file=None,
    )


