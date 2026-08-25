"""
ml_engine/predictor.py
=======================
Real-time inference wrapper for the trained pricing model.

Loads the persisted joblib artifact and exposes a clean API for
the FastAPI backend to call during price prediction requests.

Author : Aniket Yadav | BBD
Version: 1.0.0
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)

MODEL_DIR:  Path = Path(os.getenv("MODEL_DIR", "models/"))
MODEL_NAME: str  = os.getenv("MODEL_NAME", "pricing_model.joblib")


@dataclass
class PricingInput:
    """
    Input schema for a single price prediction request.

    All competitor prices are in GBP. The predictor will derive
    all engineered features (price_gap_pct, season, etc.) internally.

    Attributes
    ----------
    our_price           : Our current listed price (GBP).
    competitor_a_price  : CompetitorA's observed price (GBP).
    competitor_b_price  : CompetitorB's observed price (GBP).
    competitor_c_price  : CompetitorC's observed price (GBP).
    rating              : Product star rating [0.0–5.0].
    in_stock            : Whether the product is currently in stock.
    month               : Month of prediction (1–12).
    day_of_week         : Day of week (0=Monday … 6=Sunday).
    is_weekend          : Whether today is a weekend.
    """
    our_price:          float
    competitor_a_price: float
    competitor_b_price: float
    competitor_c_price: float
    rating:             float
    in_stock:           bool  = True
    month:              int   = 1
    day_of_week:        int   = 0
    is_weekend:         bool  = False


@dataclass
class PricingOutput:
    """
    Output schema for a single price prediction response.

    Attributes
    ----------
    optimal_price       : ML-predicted revenue-maximising price (GBP).
    avg_competitor_price: Mean of competitor prices (GBP).
    price_gap_pct       : How much our optimal price differs from competitor avg.
    recommendation      : Human-readable pricing action string.
    confidence          : Model confidence score [0.0–1.0] (based on R²).
    """
    optimal_price:        float
    avg_competitor_price: float
    price_gap_pct:        float
    recommendation:       str
    confidence:           float


class PricingPredictor:
    """
    Inference wrapper around the saved XGBoost pricing pipeline.

    Loads the ``pricing_model.joblib`` artifact once on initialisation
    and exposes :meth:`predict` for single/batch inference.

    Usage
    -----
    ::

        predictor = PricingPredictor()

        result = predictor.predict(PricingInput(
            our_price=29.99,
            competitor_a_price=27.50,
            competitor_b_price=31.00,
            competitor_c_price=32.50,
            rating=4.2,
            in_stock=True,
            month=12,
            day_of_week=5,
            is_weekend=True,
        ))
        print(result.optimal_price)       # e.g. 28.74
        print(result.recommendation)     # e.g. "Lower price by 4.2% to maximise revenue"
    """

    def __init__(self) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)
        self._artifact = self._load_model()
        self._pipeline  = self._artifact["pipeline"]
        self._feat_cols = self._artifact["feature_cols"]
        self._metrics   = self._artifact.get("metrics", {})
        self._confidence_base = self._metrics.get("r2", 0.85)
        self.logger.info(
            "PricingPredictor loaded — R2=%.4f, features=%d",
            self._confidence_base, len(self._feat_cols),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def predict(self, inp: PricingInput) -> PricingOutput:
        """
        Predict the optimal price for a single product observation.

        Args:
            inp: :class:`PricingInput` with current market data.

        Returns:
            :class:`PricingOutput` with optimal price and recommendation.
        """
        feature_row = self._build_features(inp)
        X = feature_row[self._feat_cols].values.reshape(1, -1)
        optimal_price = float(self._pipeline.predict(X)[0])
        optimal_price = max(0.01, round(optimal_price, 2))

        avg_comp = np.mean([
            inp.competitor_a_price,
            inp.competitor_b_price,
            inp.competitor_c_price,
        ])
        price_gap_pct = round(
            (optimal_price - avg_comp) / avg_comp * 100 if avg_comp else 0.0, 2
        )

        recommendation = self._generate_recommendation(
            optimal_price=optimal_price,
            current_price=inp.our_price,
            avg_comp=avg_comp,
        )

        return PricingOutput(
            optimal_price=optimal_price,
            avg_competitor_price=round(avg_comp, 2),
            price_gap_pct=price_gap_pct,
            recommendation=recommendation,
            confidence=round(max(0.0, min(1.0, self._confidence_base)), 4),
        )

    def predict_batch(self, inputs: list[PricingInput]) -> list[PricingOutput]:
        """
        Predict optimal prices for a batch of inputs efficiently.

        Args:
            inputs: List of :class:`PricingInput` objects.

        Returns:
            List of :class:`PricingOutput` objects in the same order.
        """
        rows = [self._build_features(inp) for inp in inputs]
        df = pd.DataFrame(rows)[self._feat_cols]
        predictions = self._pipeline.predict(df.values)

        outputs = []
        for inp, pred in zip(inputs, predictions):
            optimal_price = float(max(0.01, round(pred, 2)))
            avg_comp = np.mean([
                inp.competitor_a_price,
                inp.competitor_b_price,
                inp.competitor_c_price,
            ])
            price_gap_pct = round(
                (optimal_price - avg_comp) / avg_comp * 100 if avg_comp else 0.0, 2
            )
            outputs.append(PricingOutput(
                optimal_price=optimal_price,
                avg_competitor_price=round(avg_comp, 2),
                price_gap_pct=price_gap_pct,
                recommendation=self._generate_recommendation(
                    optimal_price, inp.our_price, avg_comp
                ),
                confidence=round(max(0.0, min(1.0, self._confidence_base)), 4),
            ))
        return outputs

    def get_model_info(self) -> dict:
        """
        Return metadata about the loaded model.

        Returns:
            Dictionary with model metrics and feature list.
        """
        return {
            "model_name":  MODEL_NAME,
            "feature_cols": self._feat_cols,
            "metrics":     self._metrics,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_model(self) -> dict:
        """
        Load the joblib model artifact from disk.

        Returns:
            Model artifact dictionary.

        Raises:
            FileNotFoundError: If the model file does not exist.
        """
        model_path = MODEL_DIR / MODEL_NAME
        if not model_path.exists():
            raise FileNotFoundError(
                f"Model not found: {model_path}. "
                "Run ml_engine/trainer.py first."
            )
        artifact = joblib.load(model_path)
        self.logger.info("Model loaded from: %s", model_path)
        return artifact

    def _build_features(self, inp: PricingInput) -> pd.Series:
        """
        Derive all engineered features from a :class:`PricingInput`.

        Replicates exactly the feature engineering done during training
        so that train/inference feature spaces match.

        Args:
            inp: Raw pricing input.

        Returns:
            :class:`pandas.Series` with all feature columns.
        """
        avg_comp = np.mean([
            inp.competitor_a_price,
            inp.competitor_b_price,
            inp.competitor_c_price,
        ])

        price_gap_pct = (
            (inp.our_price - avg_comp) / avg_comp if avg_comp else 0.0
        )

        season_map = {
            12: 1, 1: 1, 2: 1,
             3: 2, 4: 2, 5: 2,
             6: 3, 7: 3, 8: 3,
             9: 4, 10: 4, 11: 4,
        }
        season = season_map.get(inp.month, 1)

        seasonal_demand_map = [
            1.15, 0.90, 0.95, 1.00, 1.05, 0.95,
            0.88, 0.92, 1.10, 1.20, 1.35, 1.50,
        ]
        seasonal_demand = seasonal_demand_map[inp.month - 1]

        # Replicate demand_score heuristic from data_generator
        price_ratio = inp.our_price / avg_comp if avg_comp else 1.0
        elasticity  = price_ratio ** -1.8
        rating_fac  = 0.8 + (inp.rating / 5.0) * 0.4
        weekend_fac = 1.15 if inp.is_weekend else 1.0
        demand_score = elasticity * rating_fac * seasonal_demand * weekend_fac

        price_vs_rating = (
            inp.our_price / inp.rating if inp.rating else inp.our_price
        )

        return pd.Series({
            "our_price":            inp.our_price,
            "avg_competitor_price": round(avg_comp, 4),
            "competitor_a_price":   inp.competitor_a_price,
            "competitor_b_price":   inp.competitor_b_price,
            "competitor_c_price":   inp.competitor_c_price,
            "price_gap_pct":        round(price_gap_pct, 4),
            "rating":               inp.rating,
            "in_stock":             int(inp.in_stock),
            "month":                inp.month,
            "day_of_week":          inp.day_of_week,
            "is_weekend":           int(inp.is_weekend),
            "season":               season,
            "seasonal_demand":      seasonal_demand,
            "demand_score":         round(demand_score, 4),
            "price_vs_rating":      round(price_vs_rating, 4),
        })

    @staticmethod
    def _generate_recommendation(
        optimal_price: float,
        current_price: float,
        avg_comp: float,
    ) -> str:
        """
        Generate a human-readable pricing action recommendation.

        Args:
            optimal_price : ML-predicted optimal price.
            current_price : Our current listed price.
            avg_comp      : Average competitor price.

        Returns:
            Recommendation string.
        """
        diff_pct = (optimal_price - current_price) / current_price * 100 if current_price else 0

        if abs(diff_pct) < 1.0:
            return "Price is optimal — no change needed."
        elif diff_pct > 0:
            return (
                f"Raise price by {diff_pct:.1f}% to GBP {optimal_price:.2f} "
                f"to maximise revenue."
            )
        else:
            return (
                f"Lower price by {abs(diff_pct):.1f}% to GBP {optimal_price:.2f} "
                f"to stay competitive and maximise revenue."
            )


# ---------------------------------------------------------------------------
# Standalone entry-point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from utils.logger import setup_logger
    setup_logger()

    predictor = PricingPredictor()

    # Sample prediction
    sample = PricingInput(
        our_price=35.00,
        competitor_a_price=30.50,
        competitor_b_price=33.00,
        competitor_c_price=37.50,
        rating=4.2,
        in_stock=True,
        month=12,        # December — peak holiday season
        day_of_week=5,
        is_weekend=True,
    )

    result = predictor.predict(sample)

    print("\n" + "=" * 52)
    print("  DYNAMIC PRICING PREDICTION")
    print("=" * 52)
    print(f"  Current Price        : GBP {sample.our_price:.2f}")
    print(f"  Avg Competitor Price : GBP {result.avg_competitor_price:.2f}")
    print(f"  Optimal Price (ML)   : GBP {result.optimal_price:.2f}")
    print(f"  Price Gap vs Market  : {result.price_gap_pct:+.2f}%")
    print(f"  Confidence           : {result.confidence * 100:.1f}%")
    print(f"  Recommendation       : {result.recommendation}")
    print("=" * 52)
    print("\nModel Info:")
    for k, v in predictor.get_model_info().items():
        if k != "feature_cols":
            print(f"  {k}: {v}")
