# 🏷️ Competitor Intelligence & Dynamic Pricing Engine

> **A production-grade, full-stack AI system** that scrapes competitor prices, cleans and stores data in a relational database, trains an XGBoost machine learning model to predict revenue-maximising prices, and serves everything through a FastAPI backend and a premium interactive dashboard.

<div align="center">

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![XGBoost](https://img.shields.io/badge/XGBoost-2.0-FF6600?style=for-the-badge&logo=xgboost&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-3-003B57?style=for-the-badge&logo=sqlite&logoColor=white)
![Chart.js](https://img.shields.io/badge/Chart.js-4.4-FF6384?style=for-the-badge&logo=chartdotjs&logoColor=white)

**Developed by Aniket Yadav**

[![Live Demo](https://img.shields.io/badge/🚀%20Live%20Demo-PriceIQ-blue?style=for-the-badge)](https://web-scraper-nu-sandy.vercel.app/)

</div>

---

## 📌 Table of Contents

- [Overview](#-overview)
- [System Architecture](#-system-architecture)
- [Key Features](#-key-features)
- [Tech Stack](#-tech-stack)
- [Project Structure](#-project-structure)
- [Quickstart](#-quickstart)
- [Phase-by-Phase Guide](#-phase-by-phase-guide)
- [API Reference](#-api-reference)
- [Dashboard Features](#-dashboard-features)
- [ML Model Performance](#-ml-model-performance)
- [Configuration](#-configuration)
- [Author](#-author)

---

## 🔭 Overview

The **Competitor Intelligence & Dynamic Pricing Engine** is an end-to-end ML-powered pricing system built for e-commerce businesses. It automates competitor price monitoring, applies intelligent data cleaning, and uses a trained XGBoost model to recommend the **optimal, revenue-maximising price** for any product in real time.

### The Problem It Solves
Manual competitor price tracking is slow, error-prone, and doesn't scale. Static pricing leaves money on the table. This system provides:

- **Automated** competitor price scraping on demand
- **Clean, structured** price data stored in a relational database
- **AI-powered** price recommendations backed by ML (R² = 0.9999)
- **Real-time** market intelligence through an interactive dashboard

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                  Competitor Pricing Engine                      │
│                                                                 │
│  ┌──────────┐   Raw CSV   ┌──────────┐   Clean CSV   ┌────────┐ │
│  │ Scraper  │ ──────────► │ Cleaner  │ ────────────► │SQLite  │ │
│  │ (BS4 +   │             │ (Pandas) │               │   DB   │ │
│  │Requests) │             │10 steps  │               │(SQLAlch│ │
│  └──────────┘             └──────────┘               └────┬───┘ │
│                                                           │     │
│  ┌──────────────────────┐                           ┌────▼───┐  │
│  │   ML Pricing Model   │◄── Training data ─────────│ Query  │  │
│  │   (XGBoost + Scaler) │                           │ Layer  │  │
│  │   R² = 0.9999        │                           └────────┘  │
│  └──────────┬───────────┘                                       │
│             │ Inference                                         │
│  ┌──────────▼───────────┐    REST API    ┌────────────────────┐ │
│  │   FastAPI Backend    │ ◄────────────► │  Frontend Dashboard│ │
│  │   (Uvicorn + CORS)   │               │  (HTML+CSS+Chart.js)│ │
│  └──────────────────────┘               └────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## ✨ Key Features

### Data Scraper
- **OOP Template Method Pattern** — Abstract `BaseScraper` with pluggable concrete scrapers
- **Exponential backoff retries** via `tenacity` (3 attempts, 2–10s wait)
- **User-Agent rotation** using `fake_useragent` to avoid bot detection
- **Polite randomised delays** (1.5–3.5s) to respect server rate limits
- **Safe HTML extraction** — never crashes on missing elements
- **Competitor labelling** — simulates A/B/C competitive landscape

### Data Pipeline
- **10-step Pandas cleaning** — currency stripping, median imputation, clamping, deduplication
- **Multi-currency output** — GBP → USD/EUR conversion
- **3-table SQLAlchemy schema** — `products`, `price_history`, `scrape_runs`
- **ScrapeRun audit trail** — every ingestion tracked with status and timestamps
- **Batch inserts (500 rows)** for memory-efficient DB loading

### ML Pricing Engine
- **18,250-row synthetic dataset** — 365 days × 50 products
- **Price elasticity demand model** (elasticity = -1.8)
- **Seasonal demand multipliers** — 12-month patterns including holiday peaks
- **Grid-search optimal price** — revenue-maximising price per day
- **15 engineered features** — price_gap_pct, demand_score, season, price_vs_rating
- **XGBoost + StandardScaler** sklearn Pipeline saved via `joblib`
- **5-fold cross-validation** + full test-set evaluation

### FastAPI Backend
- **9 REST endpoints** with Pydantic v2 validation
- **Async lifespan** — DB init + model pre-warming at startup
- **CORS middleware** — open for dashboard JS calls
- **Request timing header** — `X-Process-Time-Ms` on every response
- **Global exception handler** — structured JSON errors always
- **Swagger UI** at `/docs`, ReDoc at `/redoc`

### Frontend Dashboard
- **Premium dark-mode design** with glassmorphism cards
- **3 Chart.js visualisations** — bar, donut, time-series line
- **AI Pricing Engine form** — live POST to `/predict` with animated result
- **Searchable + filterable** competitor price table (150 rows)
- **Auto-refresh** every 60 seconds
- **Toast notifications** and animated KPI counters
- **Fully responsive** (mobile → desktop)

---

## 🛠️ Tech Stack

| Layer              | Technology                            | Purpose                              |
|--------------------|---------------------------------------|--------------------------------------|
| **Scraping**       | Python, BeautifulSoup4, Requests      | Competitor price data extraction     |
| **Data Processing**| Pandas, NumPy                         | Cleaning, transformation, features   |
| **Database**       | SQLite, SQLAlchemy 2.0                | Relational storage, ORM models       |
| **ML**             | XGBoost, Scikit-learn, Joblib         | Price prediction model               |
| **Backend**        | FastAPI, Uvicorn, Pydantic v2         | REST API, validation, async serving  |
| **Frontend**       | HTML5, CSS3 (Vanilla), JavaScript     | Interactive dashboard UI             |
| **Visualisation**  | Chart.js 4.4                          | Bar, donut, line charts              |
| **Logging**        | Python logging, Rich                  | Colourised console + rotating files  |
| **Utilities**      | tenacity, fake_useragent, python-dotenv | Retries, UA rotation, config       |

---

## 📁 Project Structure

```
competitor-pricing-engine/
│
├── 📁 scraper/
│   ├── __init__.py
│   ├── base_scraper.py          # Abstract OOP base (retries, UA rotation, delays)
│   └── product_scraper.py       # Concrete scraper → books.toscrape.com
│
├── 📁 pipeline/
│   ├── __init__.py
│   ├── models.py                # SQLAlchemy ORM: products, price_history, scrape_runs
│   ├── cleaner.py               # 10-step Pandas cleaning pipeline
│   └── database.py              # DB ingestion, upserts, query helpers
│
├── 📁 ml_engine/
│   ├── __init__.py
│   ├── data_generator.py        # 18,250-row synthetic historical sales dataset
│   ├── trainer.py               # XGBoost training + CV + evaluation + joblib save
│   └── predictor.py             # Real-time inference wrapper (single + batch)
│
├── 📁 api/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app, lifespan, CORS, middleware
│   ├── schemas.py               # Pydantic v2 request/response models
│   └── routes/
│       ├── pricing.py           # POST /predict, POST /predict/batch, GET /model-info
│       └── market.py            # GET /competitors, /summary, /products, /price-history
│
├── 📁 frontend/
│   ├── index.html               # Dashboard layout (header, KPIs, charts, table, footer)
│   ├── style.css                # Premium dark-mode design system
│   └── dashboard.js             # Chart.js + API integration + auto-refresh
│
├── 📁 utils/
│   ├── __init__.py
│   └── logger.py                # Rich console + rotating file logger
│
├── 📁 data/
│   ├── raw/                     # Raw CSVs from scraper
│   ├── clean/                   # Cleaned CSVs from pipeline
│   ├── db/                      # SQLite database (pricing_engine.db)
│   └── historical_sales.csv     # Synthetic training dataset (18,250 rows)
│
├── 📁 models/
│   ├── pricing_model.joblib     # Trained XGBoost pipeline artifact
│   └── model_metadata.json      # Training metrics + feature list
│
├── 📁 logs/
│   └── pricing_engine.log       # Rotating structured log file
│
├── generate_sample_data.py      # Synthetic raw CSV generator (for testing)
├── .env                         # Active config (not committed)
├── .env.example                 # Config template with all variables documented
├── requirements.txt             # Pinned Python dependencies
└── README.md
```

---

## 🚀 Quickstart

### Prerequisites
- Python 3.10+
- Git

### 1. Clone the Repository

```bash
git clone https://github.com/Aniketyadav29/WebScraper.git
cd WebScraper/competitor-pricing-engine
```

### 2. Create & Activate Virtual Environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment

```bash
cp .env.example .env
# Edit .env if needed (defaults work out of the box)
```

---

## 📋 Phase-by-Phase Guide

### Phase 1 — Run the Scraper

```bash
# Generate synthetic test data (no browser required)
python generate_sample_data.py

# OR run the actual web scraper (scrapes books.toscrape.com)
set PYTHONIOENCODING=utf-8
python -m scraper.product_scraper
```

**Output:** `data/raw/scraped_products_<timestamp>.csv` (~100–150 rows)

---

### Phase 2 — Clean Data & Load Database

```bash
# Step 1: Run the cleaning pipeline
set PYTHONIOENCODING=utf-8
python -m pipeline.cleaner

# Step 2: Ingest clean data into SQLite
set PYTHONIOENCODING=utf-8
python -m pipeline.database
```

**Output:**
- `data/clean/scraped_products_<timestamp>_clean.csv`
- `data/db/pricing_engine.db` with 3 tables

---

### Phase 3 — Train the ML Model

```bash
# Step 1: Generate synthetic historical sales data
set PYTHONIOENCODING=utf-8
python ml_engine/data_generator.py

# Step 2: Train XGBoost model
set PYTHONIOENCODING=utf-8
python ml_engine/trainer.py

# Step 3: Test inference
set PYTHONIOENCODING=utf-8
python ml_engine/predictor.py
```

**Output:**
- `data/historical_sales.csv` (18,250 rows)
- `models/pricing_model.joblib`
- `models/model_metadata.json`

---

### Phase 4 — Start the FastAPI Backend

```bash
set PYTHONIOENCODING=utf-8
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:**      http://localhost:8000/redoc
- **Health:**     http://localhost:8000/health

---

### Phase 5 — Open the Dashboard

```bash
# Option A: Open directly in browser
start frontend/index.html

# Option B: Serve via Python HTTP server
python -m http.server 5500 --directory frontend
# Then open: http://localhost:5500
```

> ⚠️ The FastAPI server must be running on port 8000 for the dashboard to display live data.

---

## 📡 API Reference

### Health & Root

| Method | Endpoint   | Description                    |
|--------|------------|--------------------------------|
| `GET`  | `/`        | Welcome message + links        |
| `GET`  | `/health`  | API, DB, and ML model status   |

### Pricing Endpoints

| Method | Endpoint                        | Description                              |
|--------|---------------------------------|------------------------------------------|
| `POST` | `/api/v1/pricing/predict`       | Single dynamic price prediction          |
| `POST` | `/api/v1/pricing/predict/batch` | Batch predictions (up to 100 items)      |
| `GET`  | `/api/v1/pricing/model-info`    | Model metadata, features, and metrics    |

#### Sample Request — `/api/v1/pricing/predict`

```json
POST /api/v1/pricing/predict
{
  "our_price": 35.00,
  "competitor_a_price": 30.50,
  "competitor_b_price": 33.00,
  "competitor_c_price": 37.50,
  "rating": 4.2,
  "in_stock": true,
  "month": 12,
  "day_of_week": 5,
  "is_weekend": true
}
```

#### Sample Response

```json
{
  "optimal_price": 23.54,
  "current_price": 35.00,
  "avg_competitor_price": 33.67,
  "price_gap_pct": -30.08,
  "recommendation": "Lower price by 32.7% to GBP 23.54 to maximise revenue.",
  "confidence": 0.9999,
  "potential_revenue_change": "Expected revenue decrease of ~32.7% by adopting optimal price.",
  "predicted_at": "2026-08-25T17:07:50Z"
}
```

### Market Endpoints

| Method | Endpoint                                 | Description                              |
|--------|------------------------------------------|------------------------------------------|
| `GET`  | `/api/v1/market/competitors?limit=100`   | Latest price per product per competitor  |
| `GET`  | `/api/v1/market/summary`                 | Aggregated stats per competitor          |
| `GET`  | `/api/v1/market/products?page=1`         | Paginated product title list             |
| `GET`  | `/api/v1/market/price-history/{title}`   | Full price history for one product       |

---

## 📊 Dashboard Features

| Component             | Description                                              |
|-----------------------|----------------------------------------------------------|
| **KPI Cards (×4)**    | Total products, avg market price, cheapest competitor, ML confidence |
| **Bar Chart**         | Avg / Min / Max price per competitor                     |
| **Donut Chart**       | In-stock vs. out-of-stock distribution                   |
| **Line Chart**        | Price history over time per product (with dropdown)      |
| **AI Pricing Form**   | Enter prices → get real-time ML optimal price + recommendation |
| **Competitor Table**  | 150+ rows, live search, competitor filter                |
| **Auto-refresh**      | Every 60 seconds — always shows latest data              |

---

## 🤖 ML Model Performance

| Metric  | Value         | Interpretation                         |
|---------|---------------|----------------------------------------|
| **MAE** | GBP 0.0594    | Average prediction error of just 6p    |
| **RMSE**| GBP 0.0844    | Very low sensitivity to outliers       |
| **R²**  | **0.9999**    | Model explains 99.99% of price variance|
| **MAPE**| 0.3173%       | Less than 0.32% average percentage error|
| **CV RMSE** | 0.343 ± 0.118 | Robust across 5 cross-validation folds |

### Top Feature Importances

| Rank | Feature                | Importance |
|------|------------------------|------------|
| 1    | `competitor_c_price`   | 53.75%     |
| 2    | `avg_competitor_price` | 23.65%     |
| 3    | `competitor_a_price`   | 15.97%     |
| 4    | `our_price`            | 3.54%      |
| 5    | `competitor_b_price`   | 2.14%      |
| 6    | `rating`               | 0.81%      |

---

## ⚙️ Configuration

All settings are managed via the `.env` file. Copy `.env.example` to `.env` to get started.

| Variable              | Default                            | Description                          |
|-----------------------|------------------------------------|--------------------------------------|
| `APP_ENV`             | `development`                      | Environment: development/production  |
| `LOG_LEVEL`           | `INFO`                             | Logging verbosity                    |
| `SCRAPER_DELAY_MIN`   | `1.5`                              | Min polite delay between requests (s)|
| `SCRAPER_DELAY_MAX`   | `3.5`                              | Max polite delay between requests (s)|
| `SCRAPER_MAX_RETRIES` | `3`                                | Max retry attempts per page          |
| `SCRAPER_OUTPUT_DIR`  | `data/raw`                         | Raw CSV output directory             |
| `DATABASE_URL`        | `sqlite:///./data/db/pricing_engine.db` | SQLAlchemy DB connection string |
| `MODEL_DIR`           | `models/`                          | Directory for saved model artifacts  |
| `MODEL_NAME`          | `pricing_model.joblib`             | Saved model filename                 |
| `RANDOM_STATE`        | `42`                               | Reproducibility seed                 |
| `API_HOST`            | `0.0.0.0`                          | API server host                      |
| `API_PORT`            | `8000`                             | API server port                      |

---

## 📦 Dependencies

```
playwright==1.44.0          beautifulsoup4==4.12.3
requests==2.32.3            pandas==2.2.2
numpy==1.26.4               sqlalchemy==2.0.30
scikit-learn==1.5.0         xgboost==2.0.3
joblib==1.4.2               fastapi==0.111.0
uvicorn[standard]==0.30.1   pydantic==2.7.1
python-dotenv==1.0.1        rich==13.7.1
tenacity==8.3.0             fake-useragent==1.5.1
```

Full list: [`requirements.txt`](competitor-pricing-engine/requirements.txt)

---

## 🗺️ Phase Execution Summary

| Phase | Description                              | Key Output                           | Status |
|-------|------------------------------------------|--------------------------------------|--------|
| **1** | Project Setup & Automated Scraper        | Raw CSV, OOP scraper module          | ✅ Done |
| **2** | Data Cleaning & Database Architecture    | Clean CSV, SQLite DB (3 tables)      | ✅ Done |
| **3** | ML Dynamic Pricing Model                 | XGBoost model, R²=0.9999             | ✅ Done |
| **4** | FastAPI Backend Integration              | 9 REST endpoints, Swagger docs       | ✅ Done |
| **5** | Premium Frontend Dashboard               | Dark-mode dashboard, Chart.js visuals| ✅ Done |

---

## 👨‍💻 Author

<div align="center">

**Aniket Yadav**

[![GitHub](https://img.shields.io/badge/GitHub-Aniketyadav29-181717?style=for-the-badge&logo=github)](https://github.com/Aniketyadav29)

</div>

---

<div align="center">
  <sub>Built with Python · XGBoost · FastAPI · Chart.js · SQLAlchemy</sub>
</div>
