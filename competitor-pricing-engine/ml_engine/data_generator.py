"""
ml_engine/data_generator.py
============================
Synthetic historical sales dataset generator for the ML Pricing Engine.

Generates a realistic 365-day dataset combining:
* Scraped competitor prices (from the SQLite DB)
* Simulated demand / sales volume (price-elasticity model)
* Seasonal demand multipliers (holiday peaks, summer slumps)
* Random-walk competitor price drift
* Engineered features ready for XGBoost training

Output columns
--------------
date, product_id, title, our_price, competitor_a_price,
competitor_b_price, competitor_c_price, avg_competitor_price,
price_gap_pct, rating, in_stock, season, month, day_of_week,
is_weekend, demand_score, sales_volume, revenue, optimal_price

Author : Aniket Yadav | BBD
Version: 1.0.0
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
RANDOM_STATE: int = int(os.getenv("RANDOM_STATE", 42))
DAYS: int = 365
PRICE_ELASTICITY: float = -1.8   # 1% price increase → ~1.8% demand drop
BASE_DAILY_SALES: int = 50       # Baseline daily unit sales per product

# Monthly demand multipliers  (Jan=idx0 … Dec=idx11)
SEASONAL_DEMAND: list[float] = [
    1.15, 0.90, 0.95, 1.00,   # Jan–Apr
    1.05, 0.95, 0.88, 0.92,   # May–Aug
    1.10, 1.20, 1.35, 1.50,   # Sep–Dec (holiday peak)
]

# Competitor pricing strategy biases
COMPETITOR_BIAS: dict[str, float] = {
    "CompetitorA": -0.05,   # usually 5% cheaper
    "CompetitorB":  0.00,   # tracks market price
    "CompetitorC":  0.08,   # premium pricing (+8%)
}

CLEAN_DIR = Path("data/clean")
OUTPUT_DIR = Path("data")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


class SyntheticDataGenerator:
    """
    Generates a synthetic historical sales dataset for model training.

    The dataset simulates a realistic e-commerce pricing environment:
    * Products sourced from the cleaned scrape data (50 books)
    * 365 daily observations per product → 18,250 total rows
    * Competitor prices drift daily via a Gaussian random walk
    * Sales volume is driven by a price-elasticity demand model
    * Optimal price is the revenue-maximising price per day

    Usage
    -----
    ::

        gen = SyntheticDataGenerator()
        df  = gen.generate()
        gen.save(df)
    """

    def __init__(self) -> None:
        self.rng = np.random.default_rng(RANDOM_STATE)
        self.logger = logging.getLogger(self.__class__.__name__)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self) -> pd.DataFrame:
        """
        Run the full synthetic dataset generation pipeline.

        Returns:
            :class:`pandas.DataFrame` with all training features and
            the ``optimal_price`` target column.
        """
        self.logger.info("Loading base product data from clean CSV...")
        products_df = self._load_products()

        self.logger.info(
            "Generating %d days x %d products = %d observations...",
            DAYS, len(products_df), DAYS * len(products_df),
        )

        records = []
        date_range = pd.date_range(
            end=pd.Timestamp.today(), periods=DAYS, freq="D"
        )

        for _, product in products_df.iterrows():
            product_records = self._simulate_product_history(product, date_range)
            records.extend(product_records)

        df = pd.DataFrame(records)
        df = self._engineer_features(df)

        self.logger.info(
            "Synthetic dataset ready: %s rows, %s columns",
            len(df), len(df.columns),
        )
        return df

    def save(self, df: pd.DataFrame, filename: str = "historical_sales.csv") -> Path:
        """
        Persist the synthetic dataset as a CSV file.

        Args:
            df      : Generated DataFrame.
            filename: Output filename (saved into ``data/``).

        Returns:
            Path to the saved file.
        """
        path = OUTPUT_DIR / filename
        df.to_csv(path, index=False, encoding="utf-8")
        self.logger.info("Saved synthetic dataset -> %s  (%d rows)", path, len(df))
        return path

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_products(self) -> pd.DataFrame:
        """
        Load unique products from the most recent clean CSV.

        Returns:
            DataFrame with columns: ``title``, ``price_gbp``, ``rating``.

        Raises:
            FileNotFoundError: If no clean CSV exists.
        """
        csvs = sorted(CLEAN_DIR.glob("*_clean.csv"), key=lambda p: p.stat().st_mtime)
        if not csvs:
            raise FileNotFoundError(
                "No clean CSV found. Run pipeline/cleaner.py first."
            )
        df = pd.read_csv(csvs[-1])
        products = (
            df.groupby("title")
            .agg(price_gbp=("price_gbp", "mean"), rating=("rating", "mean"))
            .reset_index()
        )
        return products

    def _simulate_product_history(
        self,
        product: pd.Series,
        date_range: pd.DatetimeIndex,
    ) -> list[dict]:
        """
        Simulate 365 daily price/sales observations for a single product.

        Args:
            product    : Series with ``title``, ``price_gbp``, ``rating``.
            date_range : DatetimeIndex of 365 dates.

        Returns:
            List of daily observation dicts.
        """
        base_price: float = float(product["price_gbp"])
        rating: float = float(product["rating"])
        title: str = str(product["title"])

        records = []

        # Initialise competitor prices with their bias
        comp_prices: dict[str, float] = {
            comp: base_price * (1 + bias)
            for comp, bias in COMPETITOR_BIAS.items()
        }

        for date in date_range:
            month_idx = date.month - 1
            seasonal_mult = SEASONAL_DEMAND[month_idx]
            is_weekend = date.dayofweek >= 5

            # --- Drift competitor prices with random walk ---------------
            for comp in comp_prices:
                drift = self.rng.normal(0, 0.005)   # ±0.5% daily drift
                comp_prices[comp] = max(
                    base_price * 0.5,
                    comp_prices[comp] * (1 + drift)
                )

            avg_comp_price = np.mean(list(comp_prices.values()))

            # --- Our price: track market with slight premium -------------
            our_price = avg_comp_price * self.rng.uniform(0.95, 1.10)
            our_price = round(float(our_price), 2)

            # --- Demand model (price elasticity) ------------------------
            # Demand falls as our price rises above competitor average
            price_ratio = our_price / avg_comp_price if avg_comp_price > 0 else 1.0
            elasticity_factor = price_ratio ** PRICE_ELASTICITY

            # Rating boosts demand
            rating_factor = 0.8 + (rating / 5.0) * 0.4  # [0.8, 1.2]

            # Weekend + seasonal boosts
            weekend_factor = 1.15 if is_weekend else 1.0

            demand_score = (
                elasticity_factor * rating_factor * seasonal_mult * weekend_factor
            )
            sales_volume = max(0, int(BASE_DAILY_SALES * demand_score
                                      + self.rng.normal(0, 3)))

            revenue = round(our_price * sales_volume, 2)

            # --- Optimal price: revenue-maximising price -----------------
            optimal_price = self._find_optimal_price(
                base_price=our_price,
                avg_comp_price=avg_comp_price,
                rating=rating,
                seasonal_mult=seasonal_mult,
            )

            # --- Stock status: occasionally goes out of stock -----------
            in_stock = self.rng.random() > 0.12  # 88% chance in stock

            records.append({
                "date": date.date().isoformat(),
                "title": title,
                "our_price": our_price,
                "competitor_a_price": round(comp_prices["CompetitorA"], 2),
                "competitor_b_price": round(comp_prices["CompetitorB"], 2),
                "competitor_c_price": round(comp_prices["CompetitorC"], 2),
                "avg_competitor_price": round(avg_comp_price, 2),
                "rating": round(rating, 1),
                "in_stock": int(in_stock),
                "month": date.month,
                "day_of_week": date.dayofweek,
                "is_weekend": int(is_weekend),
                "seasonal_demand": round(seasonal_mult, 3),
                "demand_score": round(float(demand_score), 4),
                "sales_volume": sales_volume,
                "revenue": revenue,
                "optimal_price": round(optimal_price, 2),
            })

        return records

    def _find_optimal_price(
        self,
        base_price: float,
        avg_comp_price: float,
        rating: float,
        seasonal_mult: float,
    ) -> float:
        """
        Compute the revenue-maximising (optimal) price via grid search.

        Tests 50 price points in [0.7x, 1.4x] of the competitor average
        and returns the price that yields the highest simulated revenue.

        Args:
            base_price      : Our current price.
            avg_comp_price  : Current average competitor price.
            rating          : Product star rating.
            seasonal_mult   : Seasonal demand multiplier.

        Returns:
            Optimal price as a float.
        """
        if avg_comp_price <= 0:
            return base_price

        price_grid = np.linspace(
            avg_comp_price * 0.70,
            avg_comp_price * 1.40,
            50,
        )
        rating_factor = 0.8 + (rating / 5.0) * 0.4
        best_revenue = -1.0
        best_price = base_price

        for p in price_grid:
            ratio = p / avg_comp_price
            demand = (ratio ** PRICE_ELASTICITY) * rating_factor * seasonal_mult
            rev = p * max(0, BASE_DAILY_SALES * demand)
            if rev > best_revenue:
                best_revenue = rev
                best_price = float(p)

        return best_price

    def _engineer_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add derived feature columns for the ML model.

        New columns:
        * ``price_gap_pct``    — (our_price - avg_competitor_price) / avg_competitor_price
        * ``season``           — 1=Winter, 2=Spring, 3=Summer, 4=Autumn
        * ``price_vs_rating``  — our_price / rating (value-for-money proxy)

        Args:
            df: Raw generated DataFrame.

        Returns:
            DataFrame with additional feature columns.
        """
        # Price gap vs competitor (positive = we're more expensive)
        df["price_gap_pct"] = (
            (df["our_price"] - df["avg_competitor_price"])
            / df["avg_competitor_price"].replace(0, np.nan)
        ).round(4)

        # Season encoding: 1=Winter 2=Spring 3=Summer 4=Autumn
        season_map = {
            12: 1, 1: 1, 2: 1,
             3: 2, 4: 2, 5: 2,
             6: 3, 7: 3, 8: 3,
             9: 4, 10: 4, 11: 4,
        }
        df["season"] = df["month"].map(season_map)

        # Value-for-money proxy
        df["price_vs_rating"] = (
            df["our_price"] / df["rating"].replace(0, np.nan)
        ).round(2)

        return df


# ---------------------------------------------------------------------------
# Standalone entry-point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from utils.logger import setup_logger
    setup_logger()

    gen = SyntheticDataGenerator()
    df = gen.generate()
    path = gen.save(df)

    print(f"\n[OK] Generated {len(df):,} rows -> {path}")
    print("\nFeature preview (5 rows):")
    print(df[["date", "title", "our_price", "avg_competitor_price",
              "optimal_price", "sales_volume", "revenue"]].head())
