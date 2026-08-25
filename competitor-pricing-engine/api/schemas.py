"""
api/schemas.py
===============
Pydantic v2 request and response schemas for the Pricing Engine API.

All monetary values are in GBP unless stated otherwise.

Author : Aniket Yadav | BBD
Version: 1.0.0
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Shared / Base
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    """API health-check response."""
    status: str = Field(..., example="ok")
    version: str = Field(..., example="1.0.0")
    timestamp: datetime
    model_loaded: bool
    db_connected: bool


# ---------------------------------------------------------------------------
# Pricing — Request / Response
# ---------------------------------------------------------------------------

class PricePredictRequest(BaseModel):
    """
    Request body for a single dynamic price prediction.

    All prices must be positive GBP values.
    """
    our_price: float = Field(
        ..., gt=0, description="Our current listed price in GBP.", example=35.00
    )
    competitor_a_price: float = Field(
        ..., gt=0, description="CompetitorA's observed price in GBP.", example=30.50
    )
    competitor_b_price: float = Field(
        ..., gt=0, description="CompetitorB's observed price in GBP.", example=33.00
    )
    competitor_c_price: float = Field(
        ..., gt=0, description="CompetitorC's observed price in GBP.", example=37.50
    )
    rating: float = Field(
        ..., ge=0.0, le=5.0, description="Product star rating [0–5].", example=4.2
    )
    in_stock: bool = Field(True, description="Whether the product is in stock.")
    month: int = Field(
        ..., ge=1, le=12, description="Month of prediction (1=Jan … 12=Dec).", example=12
    )
    day_of_week: int = Field(
        ..., ge=0, le=6, description="Day of week (0=Monday … 6=Sunday).", example=5
    )
    is_weekend: bool = Field(False, description="Whether today is a weekend.")

    @field_validator("rating")
    @classmethod
    def round_rating(cls, v: float) -> float:
        return round(v, 1)


class PricePredictResponse(BaseModel):
    """Response for a single price prediction."""
    optimal_price: float = Field(..., description="ML-predicted optimal price (GBP).")
    current_price: float = Field(..., description="Our input price (GBP).")
    avg_competitor_price: float = Field(..., description="Average competitor price (GBP).")
    price_gap_pct: float = Field(..., description="Optimal vs competitor avg gap (%).")
    recommendation: str = Field(..., description="Human-readable pricing action.")
    confidence: float = Field(..., description="Model confidence score [0–1].")
    potential_revenue_change: str = Field(
        ..., description="Estimated revenue impact of applying optimal price."
    )
    predicted_at: datetime


class BatchPricePredictRequest(BaseModel):
    """Request body for batch price predictions."""
    items: list[PricePredictRequest] = Field(
        ..., min_length=1, max_length=100, description="List of up to 100 prediction requests."
    )


class BatchPricePredictResponse(BaseModel):
    """Response for batch price predictions."""
    predictions: list[PricePredictResponse]
    total: int
    processed_at: datetime


class ModelInfoResponse(BaseModel):
    """ML model metadata and training metrics."""
    model_name: str
    feature_count: int
    feature_cols: list[str]
    metrics: dict[str, float]
    trained_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Market / Competitor — Response Schemas
# ---------------------------------------------------------------------------

class CompetitorPriceRecord(BaseModel):
    """A single competitor price observation."""
    title: str
    competitor: str
    price_gbp: float
    price_usd: float
    price_eur: float
    rating: float
    in_stock: bool
    scraped_at: Optional[str] = None


class CompetitorSummary(BaseModel):
    """Aggregated stats for one competitor."""
    competitor: str
    avg_price_gbp: float
    min_price_gbp: float
    max_price_gbp: float
    product_count: int
    in_stock_pct: float


class MarketSummaryResponse(BaseModel):
    """Top-level market overview statistics."""
    total_products: int
    total_competitors: int
    avg_market_price_gbp: float
    cheapest_competitor: str
    most_expensive_competitor: str
    competitors: list[CompetitorSummary]
    generated_at: datetime


class PriceHistoryRecord(BaseModel):
    """Single entry in a product's price history."""
    title: str
    competitor: str
    price_gbp: float
    rating: float
    in_stock: bool
    scraped_at: Optional[str] = None


class PriceHistoryResponse(BaseModel):
    """Full price history for a specific product."""
    title: str
    records: list[PriceHistoryRecord]
    total: int


class ProductListResponse(BaseModel):
    """Paginated list of tracked products."""
    products: list[str]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Error Schema
# ---------------------------------------------------------------------------

class ErrorResponse(BaseModel):
    """Standard error response envelope."""
    error: str
    detail: Optional[Any] = None
    timestamp: datetime
