"""
ml_engine/trainer.py
=====================
XGBoost model training pipeline for the Dynamic Pricing Engine.

Workflow
--------
1. Load the synthetic historical sales dataset.
2. Feature selection and preprocessing (scaling, encoding).
3. Train/test split with time-series awareness.
4. Tune and train an XGBoost Regressor.
5. Evaluate on test set (MAE, RMSE, R², MAPE).
6. Persist the trained model + preprocessor via joblib.
7. Output a feature importance report.

Author : Aniket Yadav | BBD
Version: 1.0.0
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBRegressor

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.logger import setup_logger  # noqa: E402

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
RANDOM_STATE: int  = int(os.getenv("RANDOM_STATE", 42))
TEST_SIZE: float   = float(os.getenv("TEST_SIZE", 0.2))
MODEL_DIR: Path    = Path(os.getenv("MODEL_DIR", "models/"))
MODEL_NAME: str    = os.getenv("MODEL_NAME", "pricing_model.joblib")
MODEL_DIR.mkdir(parents=True, exist_ok=True)

# Feature columns fed to the model
FEATURE_COLS: list[str] = [
    "our_price",
    "avg_competitor_price",
    "competitor_a_price",
    "competitor_b_price",
    "competitor_c_price",
    "price_gap_pct",
    "rating",
    "in_stock",
    "month",
    "day_of_week",
    "is_weekend",
    "season",
    "seasonal_demand",
    "demand_score",
    "price_vs_rating",
]

TARGET_COL: str = "optimal_price"


class PricingModelTrainer:
    """
    End-to-end XGBoost training pipeline for dynamic price prediction.

    The trainer builds a scikit-learn :class:`Pipeline` combining a
    :class:`StandardScaler` and an :class:`XGBRegressor`. This pipeline
    is persisted as a single ``.joblib`` artifact and can be loaded
    directly by :class:`PricingPredictor` for inference.

    Attributes
    ----------
    pipeline : sklearn.pipeline.Pipeline
        Fitted preprocessing + model pipeline (available after ``train()``).
    feature_cols : list[str]
        Ordered list of feature column names.
    metrics : dict
        Evaluation metrics computed on the held-out test set.
    """

    def __init__(self) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)
        self.pipeline: Pipeline | None = None
        self.feature_cols: list[str] = FEATURE_COLS
        self.metrics: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, data_path: str | Path = "data/historical_sales.csv") -> dict:
        """
        Execute the complete train → evaluate → save workflow.

        Args:
            data_path: Path to the synthetic historical sales CSV.

        Returns:
            Dictionary of evaluation metrics.
        """
        df = self._load_data(data_path)
        X_train, X_test, y_train, y_test = self._prepare_splits(df)
        self.pipeline = self._build_pipeline()

        self.logger.info("Training XGBoost pricing model...")
        self.pipeline.fit(X_train, y_train)

        self.metrics = self._evaluate(X_test, y_test)
        self._log_metrics()
        self._feature_importance_report()
        self._save_model()

        return self.metrics

    def run_cross_validation(
        self, data_path: str | Path = "data/historical_sales.csv", cv: int = 5
    ) -> dict:
        """
        Run k-fold cross-validation and return mean/std metrics.

        Args:
            data_path: Path to the historical sales CSV.
            cv       : Number of cross-validation folds.

        Returns:
            Dictionary with CV RMSE mean and std.
        """
        df = self._load_data(data_path)
        X = df[self.feature_cols].values
        y = df[TARGET_COL].values

        pipeline = self._build_pipeline()
        neg_mse_scores = cross_val_score(
            pipeline, X, y,
            cv=cv,
            scoring="neg_mean_squared_error",
            n_jobs=-1,
        )
        rmse_scores = np.sqrt(-neg_mse_scores)

        cv_metrics = {
            "cv_rmse_mean": float(rmse_scores.mean().round(4)),
            "cv_rmse_std": float(rmse_scores.std().round(4)),
        }
        self.logger.info(
            "CV RMSE: %.4f (+/- %.4f)", cv_metrics["cv_rmse_mean"],
            cv_metrics["cv_rmse_std"],
        )
        return cv_metrics

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_data(self, path: str | Path) -> pd.DataFrame:
        """
        Load and validate the historical sales CSV.

        Args:
            path: Path to the CSV file.

        Returns:
            Validated :class:`pandas.DataFrame`.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If required columns are missing.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(
                f"Dataset not found: {path}. "
                "Run ml_engine/data_generator.py first."
            )
        df = pd.read_csv(path)
        missing = [c for c in FEATURE_COLS + [TARGET_COL] if c not in df.columns]
        if missing:
            raise ValueError(f"Missing required columns: {missing}")

        self.logger.info("Dataset loaded: %d rows, %d columns", len(df), len(df.columns))
        return df

    def _prepare_splits(
        self, df: pd.DataFrame
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """
        Prepare train/test splits using chronological ordering.

        Uses the last ``TEST_SIZE`` fraction of rows (by date) as the
        test set to prevent data leakage from future observations.

        Args:
            df: Full historical sales DataFrame.

        Returns:
            (X_train, X_test, y_train, y_test) numpy arrays.
        """
        # Sort by date to preserve temporal order (no data leakage)
        if "date" in df.columns:
            df = df.sort_values("date").reset_index(drop=True)

        X = df[self.feature_cols].fillna(0).values
        y = df[TARGET_COL].values

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=TEST_SIZE, random_state=RANDOM_STATE, shuffle=False
        )

        self.logger.info(
            "Train: %d rows | Test: %d rows", len(X_train), len(X_test)
        )
        return X_train, X_test, y_train, y_test

    def _build_pipeline(self) -> Pipeline:
        """
        Build the scikit-learn Pipeline with scaler + XGBoost model.

        XGBoost hyperparameters are tuned for this pricing regression task:
        * ``n_estimators=500``   — enough trees for stable convergence
        * ``learning_rate=0.05`` — slow learning rate with more trees
        * ``max_depth=6``        — moderate depth to prevent overfitting
        * ``subsample=0.8``      — row subsampling for regularisation
        * ``colsample_bytree``   — feature subsampling per tree

        Returns:
            Unfitted :class:`sklearn.pipeline.Pipeline`.
        """
        xgb_model = XGBRegressor(
            n_estimators=500,
            learning_rate=0.05,
            max_depth=6,
            min_child_weight=3,
            subsample=0.8,
            colsample_bytree=0.8,
            gamma=0.1,
            reg_alpha=0.05,
            reg_lambda=1.0,
            random_state=RANDOM_STATE,
            n_jobs=-1,
            verbosity=0,
            early_stopping_rounds=None,
        )

        pipeline = Pipeline([
            ("scaler", StandardScaler()),
            ("model", xgb_model),
        ])
        return pipeline

    def _evaluate(
        self, X_test: np.ndarray, y_test: np.ndarray
    ) -> dict[str, float]:
        """
        Evaluate the trained pipeline on the held-out test set.

        Computes:
        * MAE  — Mean Absolute Error (in GBP)
        * RMSE — Root Mean Squared Error (in GBP)
        * R²   — Coefficient of Determination
        * MAPE — Mean Absolute Percentage Error

        Args:
            X_test : Test feature matrix.
            y_test : True optimal prices.

        Returns:
            Dictionary of metric name → value.
        """
        y_pred = self.pipeline.predict(X_test)

        mae  = float(mean_absolute_error(y_test, y_pred))
        rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))
        r2   = float(r2_score(y_test, y_pred))
        # MAPE — avoid divide-by-zero on zero true values
        non_zero = y_test != 0
        mape = float(
            np.mean(np.abs((y_test[non_zero] - y_pred[non_zero]) / y_test[non_zero]))
            * 100
        )

        return {
            "mae":  round(mae, 4),
            "rmse": round(rmse, 4),
            "r2":   round(r2, 4),
            "mape": round(mape, 4),
        }

    def _log_metrics(self) -> None:
        """Log evaluation metrics in a formatted table."""
        self.logger.info("=" * 50)
        self.logger.info("  Model Evaluation Results")
        self.logger.info("=" * 50)
        self.logger.info("  MAE  : GBP %.4f", self.metrics["mae"])
        self.logger.info("  RMSE : GBP %.4f", self.metrics["rmse"])
        self.logger.info("  R2   : %.4f", self.metrics["r2"])
        self.logger.info("  MAPE : %.4f%%", self.metrics["mape"])
        self.logger.info("=" * 50)

    def _feature_importance_report(self) -> None:
        """
        Log the top-10 feature importances from the XGBoost model.

        Uses the ``feature_importances_`` attribute of the underlying
        XGBoost estimator extracted from the fitted pipeline.
        """
        try:
            model = self.pipeline.named_steps["model"]
            importances = model.feature_importances_
            feat_imp = sorted(
                zip(self.feature_cols, importances),
                key=lambda x: x[1],
                reverse=True,
            )
            self.logger.info("Top 10 Feature Importances:")
            for rank, (feat, imp) in enumerate(feat_imp[:10], 1):
                bar = "#" * int(imp * 50)
                self.logger.info("  %2d. %-25s %.4f  %s", rank, feat, imp, bar)
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("Could not compute feature importances: %s", exc)

    def _save_model(self) -> Path:
        """
        Persist the fitted pipeline (scaler + model) to disk via joblib.

        Also saves a metadata JSON alongside the model for traceability.

        Returns:
            Path to the saved model file.
        """
        import json
        from datetime import datetime, timezone

        model_path = MODEL_DIR / MODEL_NAME
        joblib.dump(
            {
                "pipeline": self.pipeline,
                "feature_cols": self.feature_cols,
                "target_col": TARGET_COL,
                "metrics": self.metrics,
            },
            model_path,
        )

        # Save companion metadata file
        meta = {
            "model_name": MODEL_NAME,
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "feature_cols": self.feature_cols,
            "target_col": TARGET_COL,
            "metrics": self.metrics,
            "xgboost_params": {
                "n_estimators": 500,
                "learning_rate": 0.05,
                "max_depth": 6,
            },
        }
        meta_path = MODEL_DIR / "model_metadata.json"
        with meta_path.open("w", encoding="utf-8") as fh:
            json.dump(meta, fh, indent=2)

        self.logger.info("Model saved -> %s", model_path)
        self.logger.info("Metadata   -> %s", meta_path)
        return model_path


# ---------------------------------------------------------------------------
# Standalone entry-point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    setup_logger()

    trainer = PricingModelTrainer()

    # Cross-validation first
    print("\n[Phase 3a] Running 5-Fold Cross-Validation...")
    cv_metrics = trainer.run_cross_validation()
    print(f"  CV RMSE: {cv_metrics['cv_rmse_mean']:.4f} +/- {cv_metrics['cv_rmse_std']:.4f}")

    # Full train + save
    print("\n[Phase 3b] Training final model on full dataset...")
    metrics = trainer.run()

    print("\n" + "=" * 50)
    print("  FINAL MODEL METRICS")
    print("=" * 50)
    print(f"  MAE  : GBP {metrics['mae']:.4f}")
    print(f"  RMSE : GBP {metrics['rmse']:.4f}")
    print(f"  R2   : {metrics['r2']:.4f}")
    print(f"  MAPE : {metrics['mape']:.4f}%")
    print("=" * 50)
    print(f"\n[OK] Model saved -> models/{os.getenv('MODEL_NAME', 'pricing_model.joblib')}")
