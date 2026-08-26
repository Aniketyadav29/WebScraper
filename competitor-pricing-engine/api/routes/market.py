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
from typing import Any, Optional
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
    response_model=dict,
    summary="Get 100,000+ Amazon vs Flipkart Goods Catalog",
    description="Returns fast paginated comparisons across 100,000+ goods in SQLite database.",
)
async def get_ecommerce_catalog(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(25, ge=1, le=100, description="Items per page"),
    category: Optional[str] = Query(None, description="Category filter (e.g. grocery, clothes, smartphones)"),
    search: Optional[str] = Query(None, description="Search query keyword"),
    sort_by: Optional[str] = Query("gap_desc", description="Sort criteria: gap_desc, gap_asc, price_asc, price_desc"),
) -> dict:
    """
    Fetch paginated, filtered, and sorted comparisons from the 100,000+ goods database.
    """
    import sqlite3
    from pathlib import Path
    db_path = Path(__file__).resolve().parent.parent.parent / "data" / "db" / "pricing_engine.db"
    
    if not db_path.exists():
        raise HTTPException(status_code=500, detail="Database not initialized. Please run seed script.")

    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    where_clauses = ["1=1"]
    params: list[Any] = []

    if category and category != "all":
        where_clauses.append("category = ?")
        params.append(category)

    if search:
        where_clauses.append("(title LIKE ? OR brand LIKE ? OR cat_name LIKE ?)")
        term = f"%{search.strip()}%"
        params.extend([term, term, term])

    where_sql = " AND ".join(where_clauses)

    # 1. Total Count
    count_cursor = conn.cursor()
    count_cursor.execute(f"SELECT COUNT(*) FROM ecommerce_goods WHERE {where_sql}", params)
    total_records = count_cursor.fetchone()[0]

    # 2. Summary stats for the filter
    stats_cursor = conn.cursor()
    stats_cursor.execute(f"""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN cheaper_store = 'Amazon India' THEN 1 ELSE 0 END) as amz_cheaper,
            SUM(CASE WHEN cheaper_store = 'Flipkart' THEN 1 ELSE 0 END) as flp_cheaper,
            AVG(price_diff) as avg_diff
        FROM ecommerce_goods 
        WHERE {where_sql}
    """, params)
    stat_row = stats_cursor.fetchone()

    # 3. Sorting
    sort_map = {
        "gap_desc": "price_diff DESC",
        "gap_asc": "price_diff ASC",
        "price_asc": "amazon_price ASC",
        "price_desc": "amazon_price DESC",
        "discount_desc": "diff_percentage DESC",
    }
    order_clause = sort_map.get(sort_by or "gap_desc", "price_diff DESC")

    offset = (page - 1) * page_size
    query_params = list(params) + [page_size, offset]

    cursor.execute(f"""
        SELECT id, sku, category, cat_name, brand, title,
               amazon_price, flipkart_price, mrp, price_diff, diff_percentage,
               cheaper_store, optimal_price, rating_amz, rating_flp,
               amazon_url, flipkart_url
        FROM ecommerce_goods
        WHERE {where_sql}
        ORDER BY {order_clause}
        LIMIT ? OFFSET ?
    """, query_params)

    rows = cursor.fetchall()
    conn.close()

    items = []
    for r in rows:
        items.append({
            "id": r["id"],
            "sku": r["sku"],
            "category": r["category"],
            "catName": r["cat_name"],
            "brand": r["brand"],
            "title": r["title"],
            "product_name": r["title"],
            "amz": r["amazon_price"],
            "flp": r["flipkart_price"],
            "mrp": r["mrp"],
            "price_diff": r["price_diff"],
            "diff_percentage": r["diff_percentage"],
            "cheaper_store": r["cheaper_store"],
            "optimal_price": r["optimal_price"],
            "ratingA": r["rating_amz"],
            "ratingF": r["rating_flp"],
            "amazon_url": r["amazon_url"],
            "flipkart_url": r["flipkart_url"],
            "amazon": {
                "title": f"Amazon: {r['title']}",
                "price": r["amazon_price"],
                "mrp": r["mrp"],
                "rating": r["rating_amz"],
                "url": r["amazon_url"],
            },
            "flipkart": {
                "title": f"Flipkart: {r['title']}",
                "price": r["flipkart_price"],
                "mrp": r["mrp"],
                "rating": r["rating_flp"],
                "url": r["flipkart_url"],
            }
        })

    total_pages = max(1, (total_records + page_size - 1) // page_size)

    return {
        "status": "ok",
        "total_goods": total_records,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "category": category or "all",
        "search": search or "",
        "stats": {
            "total": stat_row["total"] or 0,
            "amz_cheaper": stat_row["amz_cheaper"] or 0,
            "flp_cheaper": stat_row["flp_cheaper"] or 0,
            "avg_gap": round(stat_row["avg_diff"] or 0.0, 2),
        },
        "items": items,
    }



