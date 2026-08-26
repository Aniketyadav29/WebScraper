"""
seed_100k_catalog.py
====================
High-performance generator and database seeder creating 100,000+ realistic
cross-platform product price comparisons between Amazon India and Flipkart.

Covers 10 major departments:
1. Groceries & Eatables (20,000 items)
2. Clothes, Fashion & Shoes (20,000 items)
3. Electronics & Smartphones (15,000 items)
4. Laptops & Computers (10,000 items)
5. Audio & Headphones (10,000 items)
6. Smartwatches & Wearables (8,000 items)
7. Home, Kitchen & Appliances (7,000 items)
8. Beauty & Personal Care (5,000 items)
9. Gaming & Toys (3,000 items)
10. Sports & Fitness (2,000 items)

Total: 100,000+ items.

Author : Aniket Yadav | BBD
Version: 1.0.0
"""

from __future__ import annotations

import json
import logging
import math
import os
import random
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.logger import setup_logger

logger = logging.getLogger(__name__)

DB_PATH = PROJECT_ROOT / "data" / "db" / "pricing_engine.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
CACHE_FILE = PROJECT_ROOT / "data" / "ecommerce_100k_catalog.json"

# Department templates with realistic Indian & global brands, base price ranges, and unit templates
DEPARTMENTS = {
    "grocery": {
        "catName": "🥦 Eatables & Grocery",
        "brands": ["Fortune", "Daawat", "Tata Sampann", "Saffola", "Aashirvaad", "Cadbury", "Nestle", "Happilo", "Kellogg's", "Amul", "Dabur", "MDH", "Catch", "Nutraj", "Patanjali", "Ferrero", "Haldiram's", "Bikaji", "Raw Pressery", "Britannia"],
        "items": [
            ("Basmati Rice Premium Long Grain", 350, 950, "5 Kg"),
            ("Sharbati Whole Wheat Atta", 220, 480, "5 Kg"),
            ("Refined Sunflower Cooking Oil", 650, 920, "5 Litre Can"),
            ("Cold Pressed Pure Mustard Oil", 180, 320, "1 Litre"),
            ("Premium CTC Leaf Tea", 240, 560, "1 Kg"),
            ("Rich Blend Instant Coffee Powder", 280, 650, "200g Jar"),
            ("California Almonds Kernels", 380, 850, "500g"),
            ("Raw Walnut Halves & Pieces", 420, 980, "500g"),
            ("Cashew Nuts W320 Grade", 390, 890, "500g"),
            ("Organic Pure Honey Jar", 199, 450, "500g"),
            ("Crunchy Muesli with Fruit & Nut", 340, 680, "1 Kg Box"),
            ("Rolled White Oats Fibre Rich", 140, 290, "1 Kg"),
            ("Assorted Chocolate Gift Pack", 299, 850, "Pack of 3"),
            ("Desi Cow Ghee Bilona Method", 550, 1400, "1 Litre Tin"),
            ("Organic Green Tea Herbal Infusion", 180, 390, "100 Tea Bags"),
        ]
    },
    "clothes": {
        "catName": "👕 Clothes & Fashion",
        "brands": ["Levi's", "U.S. Polo Assn", "Puma", "Nike", "Adidas", "Tommy Hilfiger", "Allen Solly", "Peter England", "Woodland", "Biba", "W for Woman", "FabIndia", "Van Heusen", "Wrangler", "Pepe Jeans", "Flying Machine", "Arrow", "Mufti", "Zara", "H&M"],
        "items": [
            ("Mid Rise Slim Fit Denim Jeans", 1299, 3999, "Stretchable"),
            ("Pure Cotton Regular Fit Casual Shirt", 899, 2499, "Full Sleeve"),
            ("Printed Graphic Cotton T-Shirt", 499, 1499, "Round Neck"),
            ("Running & Training Athletic Shoes", 1999, 8999, "Lightweight Cushion"),
            ("Casual Low Top Sneaker Shoes", 1499, 4999, "Comfort Sole"),
            ("Ethnic Anarkali Kurta Set with Dupatta", 1599, 4999, "Rayon Fabric"),
            ("Genuine Leather Adventure Boot", 2499, 6499, "Rugged Sole"),
            ("Lightweight Quilted Puffer Winter Jacket", 2999, 7999, "Insulated"),
            ("Fleece Lined Pullover Sweatshirt Hoodie", 1199, 2999, "Kangaroo Pocket"),
            ("Formal Slim Fit Trousers Pants", 1099, 2799, "Poly-Viscose"),
            ("Classic Leather Formal Oxford Shoes", 1899, 4999, "Lace Up"),
            ("Traditional Handloom Silk Saree", 2499, 9999, "With Blouse Piece"),
        ]
    },
    "smartphones": {
        "catName": "📱 Electronics & Mobiles",
        "brands": ["Apple", "Samsung", "OnePlus", "Xiaomi", "Realme", "Google", "Motorola", "iQOO", "Vivo", "Oppo", "Poco", "Nothing", "Infinix", "Honor"],
        "items": [
            ("Flagship 5G Smartphone with AI Camera", 49999, 134999, "256GB / 512GB"),
            ("Mid-Range 5G Smartphone with 120Hz AMOLED", 19999, 39999, "128GB / 8GB RAM"),
            ("Budget Value 5G Smartphone with 5000mAh Battery", 9999, 17999, "128GB / 6GB RAM"),
            ("Pro Edition Ultra Slim Flagship Phone", 69999, 149999, "256GB / Titanium"),
            ("Gaming Focused Smartphone with Liquid Cooling", 28999, 46999, "256GB / 12GB RAM"),
        ]
    },
    "laptops": {
        "catName": "💻 Laptops & Computers",
        "brands": ["Apple", "ASUS", "Dell", "HP", "Lenovo", "Acer", "MSI", "Samsung", "LG", "Infinix"],
        "items": [
            ("Ultra Slim Lightweight Laptop (Intel i5 / M2)", 48990, 94990, "16GB RAM / 512GB SSD"),
            ("High Performance Gaming Laptop RTX 4060", 79990, 149990, "165Hz FHD / 1TB SSD"),
            ("Business Productivity Notebook Laptop", 54990, 89990, "Intel i7 / 16GB RAM"),
            ("Budget Student Laptop Intel i3 / Ryzen 3", 28990, 42990, "8GB RAM / 512GB SSD"),
            ("Creator Workstation Laptop 4K OLED", 119990, 229990, "32GB RAM / 2TB SSD"),
        ]
    },
    "audio": {
        "catName": "🎧 Audio & Earbuds",
        "brands": ["Sony", "Apple", "Bose", "JBL", "boAt", "Sennheiser", "Noise", "Boult", "Marshall", "OnePlus", "Realme"],
        "items": [
            ("Wireless Over-Ear ANC Noise Cancelling Headphones", 8999, 29990, "40h Battery"),
            ("Truly Wireless Earbuds TWS with ANC & Spatial Audio", 2999, 21990, "IPX5 Water Resistant"),
            ("Budget Wireless Earbuds with Fast Charging", 999, 2499, "30h Playtime"),
            ("Portable Waterproof Bluetooth Speaker", 1999, 14990, "Deep Bass"),
            ("High Power Home Theatre Soundbar with Subwoofer", 6999, 24990, "Dolby Atmos 5.1"),
        ]
    },
    "smartwatches": {
        "catName": "⌚ Smartwatches & Wearables",
        "brands": ["Apple", "Samsung", "Noise", "Fire-Boltt", "Garmin", "boAt", "Amazfit", "Fitbit", "Titan", "Fastrack"],
        "items": [
            ("Premium AMOLED Smartwatch with Bluetooth Calling", 2499, 7999, "1.96 Inch Display"),
            ("Flagship Smartwatch GPS + Cellular LTE", 26999, 44990, "Health Sensor Suite"),
            ("Rugged Outdoor GPS Multisport Smartwatch", 14990, 39990, "Heart Rate / SpO2"),
            ("Fitness Activity Tracker Band", 1499, 3999, "OLED Touch Display"),
        ]
    },
    "appliances": {
        "catName": "🏠 Home & Kitchen Appliances",
        "brands": ["LG", "Samsung", "Philips", "Dyson", "Prestige", "Kent", "Bajaj", "Havells", "Voltas", "Whirlpool", "IFB", "Crompton", "Panasonic"],
        "items": [
            ("4K Ultra HD Smart OLED / QLED TV 55 Inch", 42990, 139990, "Dolby Vision & Atmos"),
            ("Digital Touchscreen Air Fryer with Rapid Air Tech", 4999, 12999, "4.2 Litre Capacity"),
            ("750W Heavy Duty Kitchen Mixer Grinder Juicer", 2499, 6499, "3 Stainless Steel Jars"),
            ("Multi-Stage RO+UV+UF Alkaline Water Purifier", 9999, 18999, "10 Litre Storage"),
            ("Cordless Laser Stick Vacuum Cleaner", 19990, 54990, "Cyclone Suction"),
            ("Inverter Split Air Conditioner 1.5 Ton 5 Star", 34990, 51990, "Copper Condenser"),
        ]
    },
    "beauty": {
        "catName": "💄 Beauty & Personal Care",
        "brands": ["L'Oreal", "Minimalist", "Philips", "Maybelline", "Nivea", "Neutrogena", "The Derma Co", "Beardo", "Mamaearth", "Biotique", "Cetaphil"],
        "items": [
            ("Hyaluronic Acid & Niacinamide Glowing Face Serum", 499, 999, "30ml Dropper"),
            ("Fast Charging Cordless Beard & Hair Trimmer", 1299, 2999, "Stainless Steel Blades"),
            ("SPF 50+ PA++++ Ultra Light Matte Sunscreen", 399, 799, "50g Tube"),
            ("Long Lasting Matte Finish Liquid Lipstick", 399, 899, "Smudgeproof"),
            ("Hair Growth & Nourishing Scalp Redensyl Serum", 699, 1499, "50ml"),
        ]
    },
    "gaming": {
        "catName": "🎮 Gaming & Toys",
        "brands": ["Sony", "Microsoft", "Nintendo", "LEGO", "Logitech", "Razer", "Hot Wheels", "Funskool", "Hasbro"],
        "items": [
            ("Next-Gen Gaming Console 1TB SSD System", 39990, 54990, "4K 120FPS Gaming"),
            ("Wireless Haptic Feedback Gamepad Controller", 4499, 6399, "Bluetooth / Type-C"),
            ("RGB Mechanical Gaming Keyboard with Linear Switches", 2499, 9999, "Anti-Ghosting"),
            ("Precision Wireless Optical Gaming Mouse 20000 DPI", 1899, 6999, "Ultra-Lightweight"),
            ("Building Blocks Creator Dinosaur / Space Set", 999, 3999, "Multi-Model Kit"),
        ]
    },
    "sports": {
        "catName": "🏋️ Sports & Fitness",
        "brands": ["Decathlon", "Yonex", "Cosco", "Nivia", "Boldfit", "Kore", "Strauss", "Vector X", "Puma Sports"],
        "items": [
            ("Adjustable PVC / Rubber Home Gym Dumbbells Set", 1299, 4999, "20 Kg Combo"),
            ("High Density Non-Slip Yoga Exercise Mat", 599, 1699, "6mm Thick with Strap"),
            ("Full Graphite Badminton Racket with High Tension String", 1499, 4999, "Lightweight G4"),
            ("Match Grade FIFA Standard Football Size 5", 699, 1899, "PU Hand Stitched"),
        ]
    }
}


def create_100k_tables(conn: sqlite3.Connection) -> None:
    """Create optimized tables and indexes for 100,000 goods catalog."""
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ecommerce_goods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT UNIQUE NOT NULL,
            category TEXT NOT NULL,
            cat_name TEXT NOT NULL,
            brand TEXT NOT NULL,
            title TEXT NOT NULL,
            amazon_price REAL NOT NULL,
            flipkart_price REAL NOT NULL,
            mrp REAL NOT NULL,
            price_diff REAL NOT NULL,
            diff_percentage REAL NOT NULL,
            cheaper_store TEXT NOT NULL,
            optimal_price REAL NOT NULL,
            rating_amz REAL NOT NULL,
            rating_flp REAL NOT NULL,
            amazon_url TEXT NOT NULL,
            flipkart_url TEXT NOT NULL,
            in_stock INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ecom_category ON ecommerce_goods(category)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ecom_brand ON ecommerce_goods(brand)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ecom_title ON ecommerce_goods(title)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ecom_cheaper ON ecommerce_goods(cheaper_store)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ecom_price_diff ON ecommerce_goods(price_diff DESC)")
    conn.commit()


def generate_and_seed_100k(total_records: int = 100000) -> None:
    """Generate 100,000+ realistic cross-platform items and bulk insert into SQLite."""
    import urllib.parse
    logger.info("Starting generation of %d goods across 10 departments...", total_records)
    start_time = time.time()

    conn = sqlite3.connect(DB_PATH, timeout=60.0)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.cursor().execute("DROP TABLE IF EXISTS ecommerce_goods")
    conn.commit()
    create_100k_tables(conn)
    cursor = conn.cursor()

    rows = []
    compact_cache = []
    now_iso = datetime.now(timezone.utc).isoformat()

    categories = list(DEPARTMENTS.keys())
    # Distribute 100k records proportionately across categories
    weights = [20, 20, 15, 10, 10, 8, 7, 5, 3, 2]  # sum = 100

    item_id = 1
    for cat, weight in zip(categories, weights):
        cat_data = DEPARTMENTS[cat]
        cat_name = cat_data["catName"]
        brands = cat_data["brands"]
        item_templates = cat_data["items"]

        cat_target = int((weight / 100.0) * total_records)
        logger.info("Generating %d items for category: %s...", cat_target, cat_name)

        for i in range(cat_target):
            brand = random.choice(brands)
            template, min_p, max_p, extra = random.choice(item_templates)

            model_num = f"{random.randint(100, 999)}"
            variant = f"Series-{random.choice(['X', 'Pro', 'Ultra', 'Plus', 'Max', 'Neo', 'Prime', 'Air'])}"
            year = random.choice(["2024", "2025", "2026"])

            title = f"{brand} {variant} {template} ({extra}, {year} Model {model_num})"

            # Direct clickable store URLs
            encoded_title = urllib.parse.quote_plus(title)
            amazon_url = f"https://www.amazon.in/s?k={encoded_title}"
            flipkart_url = f"https://www.flipkart.com/search?q={encoded_title}"

            # Price modeling
            base_price = round(random.uniform(min_p, max_p), 2)
            mrp = round(base_price * random.uniform(1.15, 1.45), 2)

            # Realistic platform price variance (-6% to +6%)
            variance = random.uniform(-0.06, 0.06)
            if variance < 0:
                amz_price = round(base_price * (1.0 + variance), 2)
                flp_price = round(base_price, 2)
            else:
                amz_price = round(base_price, 2)
                flp_price = round(base_price * (1.0 - variance), 2)

            diff = round(abs(amz_price - flp_price), 2)
            max_p_val = max(amz_price, flp_price)
            min_p_val = min(amz_price, flp_price)
            diff_pct = round(((max_p_val - min_p_val) / max_p_val) * 100, 1) if max_p_val > 0 else 0.0

            if amz_price < flp_price:
                cheaper_store = "Amazon India"
            elif flp_price < amz_price:
                cheaper_store = "Flipkart"
            else:
                cheaper_store = "Equal"

            optimal_price = round(min_p_val * 0.98, 2)

            rating_amz = round(random.uniform(3.8, 4.9), 1)
            rating_flp = round(random.uniform(3.8, 4.9), 1)
            sku = f"ECOM-{cat[:3].upper()}-{item_id:06d}"

            record_tuple = (
                sku, cat, cat_name, brand, title,
                amz_price, flp_price, mrp, diff, diff_pct,
                cheaper_store, optimal_price, rating_amz, rating_flp,
                amazon_url, flipkart_url,
                1, now_iso
            )
            rows.append(record_tuple)

            # Store compact sample in cache (first 2,000 for ultra-fast instant UI rendering)
            if len(compact_cache) < 2000:
                compact_cache.append({
                    "id": item_id,
                    "sku": sku,
                    "category": cat,
                    "catName": cat_name,
                    "brand": brand,
                    "title": title,
                    "amz": amz_price,
                    "flp": flp_price,
                    "mrp": mrp,
                    "price_diff": diff,
                    "diff_percentage": diff_pct,
                    "cheaper_store": cheaper_store,
                    "optimal_price": optimal_price,
                    "ratingA": rating_amz,
                    "ratingF": rating_flp,
                    "amazon_url": amazon_url,
                    "flipkart_url": flipkart_url,
                })

            item_id += 1

            # Batch insert every 20,000 rows
            if len(rows) >= 20000:
                cursor.executemany("""
                    INSERT INTO ecommerce_goods (
                        sku, category, cat_name, brand, title,
                        amazon_price, flipkart_price, mrp, price_diff, diff_percentage,
                        cheaper_store, optimal_price, rating_amz, rating_flp,
                        amazon_url, flipkart_url,
                        in_stock, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, rows)
                conn.commit()
                rows.clear()
                logger.info("Inserted batch... total committed: %d rows", item_id - 1)

    if rows:
        cursor.executemany("""
            INSERT INTO ecommerce_goods (
                sku, category, cat_name, brand, title,
                amazon_price, flipkart_price, mrp, price_diff, diff_percentage,
                cheaper_store, optimal_price, rating_amz, rating_flp,
                amazon_url, flipkart_url,
                in_stock, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, rows)
        conn.commit()

    conn.close()

    # Save compact cache JSON
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "total_goods": total_records,
            "generated_at": now_iso,
            "sample_items": compact_cache
        }, f, indent=2)

    elapsed = time.time() - start_time
    logger.info("Successfully seeded %d goods into SQLite database in %.2f seconds!", total_records, elapsed)
    logger.info("Database file: %s (Size: %.2f MB)", DB_PATH, DB_PATH.stat().st_size / (1024 * 1024))


if __name__ == "__main__":
    setup_logger()
    generate_and_seed_100k(500000)
