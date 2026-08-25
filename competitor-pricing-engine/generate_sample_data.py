"""
generate_sample_data.py
========================
Generates a realistic synthetic raw CSV in the format produced by
the ProductScraper — so Phase 2 can be tested immediately without
running the actual web scraper.

Generates 150 records across 3 competitors and 50 unique book titles.

Author : Aniket Yadav | BBD
"""

import csv
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

random.seed(42)

BOOKS = [
    "A Light in the Attic", "Tipping the Velvet", "Soumission",
    "Sharp Objects", "Sapiens", "The Requiem Red", "The Dirty Little Secrets",
    "The Coming Woman", "The Boys in the Boat", "The Black Maria",
    "Starving Hearts", "Shakespeare's Sonnets", "Set Me Free",
    "Scott Pilgrim's Precious", "Rip it Up and Start Again",
    "Our Band Could Be Your Life", "Olio", "Mesaerion", "Libertarianism",
    "It's Only the Himalayas", "In Her Wake", "How Music Works",
    "Foolproof Preserving", "Chase Me", "Black Dust", "Birdsong",
    "America's Cradle of Quarterbacks", "Aladdin", "Worlds Elsewhere",
    "Wall and Piece", "The Four Agreements", "Atomic Habits",
    "Deep Work", "Thinking Fast and Slow", "The Lean Startup",
    "Zero to One", "Good to Great", "The Hard Thing",
    "Start with Why", "Shoe Dog", "The Innovators",
    "Creativity Inc", "The Alchemist", "Meditations",
    "Man's Search for Meaning", "The Power of Now", "Stillness is the Key",
    "Essentialism", "Digital Minimalism", "Make Time",
]

COMPETITORS = ["CompetitorA", "CompetitorB", "CompetitorC"]
BASE_PRICES = {book: round(random.uniform(10.0, 55.0), 2) for book in BOOKS}
BASE_RATINGS = {book: round(random.uniform(1.0, 5.0), 1) for book in BOOKS}

Path("data/raw").mkdir(parents=True, exist_ok=True)

rows = []
base_time = datetime.now(timezone.utc) - timedelta(hours=2)

for competitor in COMPETITORS:
    for book in BOOKS:
        base_price = BASE_PRICES[book]
        # Each competitor varies price by ±15%
        variance = random.uniform(-0.15, 0.15)
        price = round(base_price * (1 + variance), 2)

        # Randomly introduce some messy data for cleaner to handle
        price_str = f"£{price}"
        if random.random() < 0.03:
            price_str = ""          # Missing price
        elif random.random() < 0.02:
            price_str = f"Â£{price}"  # Encoding artifact

        rating = BASE_RATINGS[book]
        in_stock = random.random() > 0.15  # 85% in stock

        scraped_at = (base_time + timedelta(seconds=random.randint(0, 7200))).isoformat()

        rows.append({
            "title": book,
            "price_gbp": price_str,
            "rating": rating,
            "in_stock": in_stock,
            "competitor": competitor,
            "source_url": f"https://books.toscrape.com/catalogue/{book.lower().replace(' ', '-')}_1/index.html",
            "scraped_at": scraped_at,
        })

# Shuffle to simulate real scrape order
random.shuffle(rows)

# Add a few fully duplicate rows to test deduplication
rows.extend(rows[:3])

ts = datetime.now().strftime("%Y%m%d_%H%M%S")
out_path = f"data/raw/scraped_products_{ts}.csv"

with open(out_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)

print(f"[OK] Generated {len(rows)} raw records -> {out_path}")
