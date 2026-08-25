"""
api/main.py
============
FastAPI application entry point for the Competitor Intelligence &
Dynamic Pricing Engine.

Startup sequence
----------------
1. Load environment variables from ``.env``.
2. Configure structured logging.
3. Initialise the database schema (idempotent).
4. Pre-warm the ML model (loaded once, reused across requests).
5. Register all API routers with versioned prefixes.
6. Register CORS middleware and global exception handlers.

Running locally
---------------
::

    uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

Author : Aniket Yadav | BBD
Version: 1.0.0
"""

from __future__ import annotations

import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator

from dotenv import load_dotenv
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load .env before importing any project modules
load_dotenv(PROJECT_ROOT / ".env")

from utils.logger import setup_logger        # noqa: E402
from pipeline.models import init_db          # noqa: E402
from api.routes import pricing, market       # noqa: E402
from api.schemas import HealthResponse       # noqa: E402

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
setup_logger()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App Metadata
# ---------------------------------------------------------------------------
APP_NAME    = os.getenv("APP_NAME", "Competitor Intelligence & Dynamic Pricing Engine")
APP_VERSION = "1.0.0"
API_HOST    = os.getenv("API_HOST", "0.0.0.0")
API_PORT    = int(os.getenv("API_PORT", 8000))

CORS_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:5500,http://localhost:5500"
    ).split(",")
]

# ---------------------------------------------------------------------------
# Startup / Shutdown lifecycle
# ---------------------------------------------------------------------------
_startup_time: float = 0.0
_model_loaded: bool = False
_db_connected: bool = False


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager — runs startup and shutdown logic.

    Startup:
    * Initialise DB schema
    * Pre-warm ML model predictor
    """
    global _startup_time, _model_loaded, _db_connected
    _startup_time = time.time()

    logger.info("=" * 60)
    logger.info("  %s  v%s", APP_NAME, APP_VERSION)
    logger.info("  Starting up...")
    logger.info("=" * 60)

    # --- Initialise database ---
    try:
        init_db()
        _db_connected = True
        logger.info("Database schema ready.")
    except Exception as exc:
        logger.error("DB initialisation failed: %s", exc)

    # --- Pre-warm ML model ---
    try:
        from ml_engine.predictor import PricingPredictor
        _predictor = PricingPredictor()
        # Inject into pricing router's singleton cache
        from api.routes.pricing import _predictor as _route_pred  # noqa: F401
        import api.routes.pricing as pricing_module
        pricing_module._predictor = _predictor
        _model_loaded = True
        logger.info("ML model pre-warmed and ready.")
    except FileNotFoundError:
        logger.warning(
            "ML model not found — /predict endpoints will return 503 "
            "until the model is trained."
        )
    except Exception as exc:
        logger.error("ML model pre-warm failed: %s", exc)

    elapsed = time.time() - _startup_time
    logger.info("Startup complete in %.2fs — listening on %s:%s", elapsed, API_HOST, API_PORT)

    yield  # Application runs here

    # --- Shutdown ---
    logger.info("Shutting down %s...", APP_NAME)


# ---------------------------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------------------------
app = FastAPI(
    title=APP_NAME,
    description=(
        "A production-grade competitor intelligence and dynamic pricing engine. "
        "Scrapes competitor prices, cleans and stores data in SQLite, trains an "
        "XGBoost model, and serves real-time optimal price predictions via REST API."
    ),
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    contact={
        "name": "Aniket Yadav | BBD",
        "url": "https://github.com/Aniketyadav29/WebScraper",
    },
)

# ---------------------------------------------------------------------------
# CORS Middleware
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # Permits the JS dashboard to call the API
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Global Exception Handler
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler — returns a structured JSON error for any unhandled exception."""
    logger.error(
        "Unhandled exception on %s %s: %s",
        request.method, request.url.path, exc, exc_info=True,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "detail": str(exc),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )

# ---------------------------------------------------------------------------
# Request Timing Middleware
# ---------------------------------------------------------------------------
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Adds X-Process-Time header to every response for latency monitoring."""
    start = time.time()
    response = await call_next(request)
    process_time = round((time.time() - start) * 1000, 2)
    response.headers["X-Process-Time-Ms"] = str(process_time)
    return response

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(pricing.router)
app.include_router(market.router)

# ---------------------------------------------------------------------------
# Root / Health Endpoints
# ---------------------------------------------------------------------------

@app.get(
    "/",
    tags=["Root"],
    summary="API Root",
    include_in_schema=True,
)
async def root() -> dict:
    """Welcome endpoint with links to documentation."""
    return {
        "message": f"Welcome to the {APP_NAME} API",
        "version": APP_VERSION,
        "docs": "/docs",
        "redoc": "/redoc",
        "health": "/health",
        "author": "Aniket Yadav | BBD",
    }


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["Root"],
    summary="Health Check",
    description="Returns API health status, including DB and ML model readiness.",
)
async def health_check() -> HealthResponse:
    """
    Comprehensive health check for monitoring and load-balancer probes.

    Returns:
        :class:`HealthResponse` with status flags for DB and ML model.
    """
    return HealthResponse(
        status="ok",
        version=APP_VERSION,
        timestamp=datetime.now(timezone.utc),
        model_loaded=_model_loaded,
        db_connected=_db_connected,
    )


# ---------------------------------------------------------------------------
# Dev entry-point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host=API_HOST,
        port=API_PORT,
        reload=True,
        log_level="info",
    )
