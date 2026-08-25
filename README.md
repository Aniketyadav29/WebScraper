# 🏷️ Competitor Intelligence & Dynamic Pricing Engine

> A full-stack, production-grade system for scraping competitor prices,
> cleaning data, training an ML pricing model, and serving insights
> through an interactive FastAPI + Chart.js dashboard.

**Author:** Aniket Yadav | BBD

---

## 🏗️ Architecture

```
Scraper → Raw CSV → Cleaning Pipeline → SQLite DB → ML Model → FastAPI → Dashboard
```

## 📁 Project Structure

```
competitor-pricing-engine/
├── scraper/          # Web scraping module (OOP, Playwright/BS4)
├── pipeline/         # Data cleaning & DB ingestion (Pandas + SQLAlchemy)
├── ml_engine/        # XGBoost pricing model training & inference
├── api/              # FastAPI REST backend
├── frontend/         # HTML/CSS/JS Dashboard with Chart.js
├── data/
│   ├── raw/          # Raw CSV output from scraper
│   ├── clean/        # Cleaned/processed CSV
│   └── db/           # SQLite database
├── models/           # Saved ML model artifacts
├── logs/             # Rotating log files
├── utils/            # Shared utilities (logging, config)
├── .env.example      # Environment variable template
├── requirements.txt  # Pinned Python dependencies
└── README.md
```

## 🚀 Quickstart

### 1. Clone & Setup

```bash
git clone <repo-url>
cd competitor-pricing-engine
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your settings
```

### 3. Run the Scraper (Phase 1)

```bash
python -m scraper.product_scraper
```

### 4. Run the Data Pipeline (Phase 2)

```bash
python -m pipeline.cleaner
```

### 5. Train the ML Model (Phase 3)

```bash
python -m ml_engine.trainer
```

### 6. Start the API (Phase 4)

```bash
uvicorn api.main:app --reload
```

### 7. Open the Dashboard (Phase 5)

Open `frontend/index.html` in your browser, or serve with:
```bash
python -m http.server 5500 --directory frontend
```

## ⚙️ Tech Stack

| Layer           | Technology                          |
|-----------------|-------------------------------------|
| Scraping        | Python, BeautifulSoup, Requests     |
| Data Processing | Pandas, NumPy                       |
| Database        | SQLite, SQLAlchemy 2.0              |
| ML              | XGBoost, Scikit-learn, Joblib       |
| Backend         | FastAPI, Uvicorn, Pydantic          |
| Frontend        | HTML5, CSS3, Vanilla JS, Chart.js   |
| Logging         | Python logging, Rich                |

## 📊 Phases

| Phase | Status | Description                          |
|-------|--------|--------------------------------------|
| 1     | ✅ Done | Project setup & automated scraper   |
| 2     | 🔒     | Data cleaning & DB architecture      |
| 3     | 🔒     | ML dynamic pricing model             |
| 4     | 🔒     | FastAPI backend integration          |
| 5     | 🔒     | Eye-catching frontend dashboard      |

---

*Developed by Aniket Yadav | BBD*

