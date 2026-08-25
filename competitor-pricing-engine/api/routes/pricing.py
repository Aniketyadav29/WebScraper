"""
api/routes/pricing.py
======================
FastAPI router for all ML pricing prediction endpoints.

Endpoints
---------
POST /api/v1/pricing/predict        — Single price prediction
POST /api/v1/pricing/predict/batch  — Batch price predictions (up to 100)
GET  /api/v1/pricing/model-info     — Model metadata and training metrics

Author : Aniket Yadav | BBD
Version: 1.0.0
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from api.schemas import (
    BatchPricePredictRequest,
    BatchPricePredictResponse,
    ModelInfoResponse,
    PricePredictRequest,
    PricePredictResponse,
)
from ml_engine.predictor import PricingInput, PricingPredictor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/pricing", tags=["Pricing"])

# ---------------------------------------------------------------------------
# Dependency: singleton PricingPredictor
# (loaded once at startup, reused across all requests)
# ---------------------------------------------------------------------------
_predictor: PricingPredictor | None = None


def get_predictor() -> PricingPredictor:
    """FastAPI dependency that returns the singleton PricingPredictor."""
    global _predictor
    if _predictor is None:
        try:
            _predictor = PricingPredictor()
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"ML model not loaded: {exc}. Run ml_engine/trainer.py first.",
            )
    return _predictor


PrediectorDep = Annotated[PricingPredictor, Depends(get_predictor)]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _build_revenue_change_str(optimal: float, current: float) -> str:
    """Estimate and format the potential revenue impact."""
    if current <= 0:
        return "N/A"
    change_pct = (optimal - current) / current * 100
    if abs(change_pct) < 1.0:
        return "Minimal change expected (<1%)"
    direction = "increase" if change_pct > 0 else "decrease"
    return f"Expected revenue {direction} of ~{abs(change_pct):.1f}% by adopting optimal price."


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/predict",
    response_model=PricePredictResponse,
    summary="Predict Optimal Price",
    description=(
        "Submit current market data to receive an ML-powered optimal price "
        "recommendation. Uses the trained XGBoost model."
    ),
)
async def predict_price(
    request: PricePredictRequest,
    predictor: PrediectorDep,
) -> PricePredictResponse:
    """
    Predict the revenue-maximising optimal price for a single product.

    Args:
        request  : Current market data including our price and all competitor prices.
        predictor: Injected :class:`PricingPredictor` singleton.

    Returns:
        :class:`PricePredictResponse` with optimal price and recommendation.
    """
    logger.info(
        "Prediction request — our_price=%.2f, competitors=[%.2f, %.2f, %.2f]",
        request.our_price,
        request.competitor_a_price,
        request.competitor_b_price,
        request.competitor_c_price,
    )

    try:
        inp = PricingInput(
            our_price=request.our_price,
            competitor_a_price=request.competitor_a_price,
            competitor_b_price=request.competitor_b_price,
            competitor_c_price=request.competitor_c_price,
            rating=request.rating,
            in_stock=request.in_stock,
            month=request.month,
            day_of_week=request.day_of_week,
            is_weekend=request.is_weekend,
        )
        result = predictor.predict(inp)
    except Exception as exc:
        logger.error("Prediction failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Prediction error: {exc}",
        )

    return PricePredictResponse(
        optimal_price=result.optimal_price,
        current_price=request.our_price,
        avg_competitor_price=result.avg_competitor_price,
        price_gap_pct=result.price_gap_pct,
        recommendation=result.recommendation,
        confidence=result.confidence,
        potential_revenue_change=_build_revenue_change_str(
            result.optimal_price, request.our_price
        ),
        predicted_at=datetime.now(timezone.utc),
    )


@router.post(
    "/predict/batch",
    response_model=BatchPricePredictResponse,
    summary="Batch Price Predictions",
    description="Submit up to 100 product observations for bulk optimal price prediction.",
)
async def predict_batch(
    request: BatchPricePredictRequest,
    predictor: PrediectorDep,
) -> BatchPricePredictResponse:
    """
    Predict optimal prices for a list of product observations in one call.

    Args:
        request  : Batch of up to 100 prediction request items.
        predictor: Injected :class:`PricingPredictor` singleton.

    Returns:
        :class:`BatchPricePredictResponse` with a prediction for each item.
    """
    logger.info("Batch prediction request — %d items", len(request.items))

    try:
        inputs = [
            PricingInput(
                our_price=item.our_price,
                competitor_a_price=item.competitor_a_price,
                competitor_b_price=item.competitor_b_price,
                competitor_c_price=item.competitor_c_price,
                rating=item.rating,
                in_stock=item.in_stock,
                month=item.month,
                day_of_week=item.day_of_week,
                is_weekend=item.is_weekend,
            )
            for item in request.items
        ]
        results = predictor.predict_batch(inputs)
    except Exception as exc:
        logger.error("Batch prediction failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch prediction error: {exc}",
        )

    now = datetime.now(timezone.utc)
    predictions = [
        PricePredictResponse(
            optimal_price=r.optimal_price,
            current_price=request.items[i].our_price,
            avg_competitor_price=r.avg_competitor_price,
            price_gap_pct=r.price_gap_pct,
            recommendation=r.recommendation,
            confidence=r.confidence,
            potential_revenue_change=_build_revenue_change_str(
                r.optimal_price, request.items[i].our_price
            ),
            predicted_at=now,
        )
        for i, r in enumerate(results)
    ]

    return BatchPricePredictResponse(
        predictions=predictions,
        total=len(predictions),
        processed_at=now,
    )


@router.get(
    "/model-info",
    response_model=ModelInfoResponse,
    summary="Model Metadata",
    description="Returns the trained model's feature list and evaluation metrics.",
)
async def get_model_info(predictor: PrediectorDep) -> ModelInfoResponse:
    """
    Retrieve metadata about the loaded ML pricing model.

    Args:
        predictor: Injected :class:`PricingPredictor` singleton.

    Returns:
        :class:`ModelInfoResponse` with metrics and feature columns.
    """
    info = predictor.get_model_info()
    return ModelInfoResponse(
        model_name=info["model_name"],
        feature_count=len(info["feature_cols"]),
        feature_cols=info["feature_cols"],
        metrics=info.get("metrics", {}),
    )
