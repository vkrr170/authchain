"""
seed_products.py — Seeds product catalog directly for Manufacturers.

Usage:
  python seed_products.py [manufacturer_username]

If no username is provided, the first Manufacturer account found is used.
This is purely a data seeding helper — no Admin role required.
"""
import os
import sys
import uuid
import time
import hashlib
import json
import bcrypt
from difflib import SequenceMatcher
from pymongo import MongoClient

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
client = MongoClient(MONGO_URI)
db = client["authchain"]
products_col     = db["products"]
transactions_col = db["transactions"]
blocks_col       = db["blocks"]
users_col        = db["users"]

BASE_DIR = os.path.dirname(__file__)
IMG_DIR  = os.path.join(BASE_DIR, "static", "product_images")
os.makedirs(IMG_DIR, exist_ok=True)

# ── Image matching helpers ────────────────────────────────
MANUAL_OVERRIDES = {
    "desk lap": "Desk Lamp LED",
    "padlock":  "Padlock 50mm",
}

def _norm(s):
    return s.lower().replace("\u2019", "").replace("'", "").replace("-", " ").strip()

def _sim(a, b):
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()

def _find_image(name):
    exts = (".jpg", ".jpeg", ".png", ".gif", ".webp")
    files = [f for f in os.listdir(IMG_DIR)
             if os.path.splitext(f)[1].lower() in exts
             and not f.startswith("P-")]
    best_file, best_score = None, 0
    for f in files:
        stem     = os.path.splitext(f)[0]
        override = MANUAL_OVERRIDES.get(stem)
        score    = 1.0 if override == name else _sim(stem, name)
        if score > best_score:
            best_score, best_file = score, f
    if best_file and best_score >= 0.6:
        return os.path.join(IMG_DIR, best_file), os.path.splitext(best_file)[1].lstrip(".")
    return None, ""

# ── ID generators (mirrors app.py) ───────────────────────
def generate_puid():
    return "P-" + str(uuid.uuid4()).replace("-", "")[:8].upper()

def generate_suid():
    return "S-" + str(uuid.uuid4()).replace("-", "")[:8].upper()

def generate_batch():
    return "B-" + str(uuid.uuid4()).replace("-", "")[:10].upper()

def calculate_block_hash(block):
    block_data = {
        "index":         block["index"],
        "timestamp":     block["timestamp"],
        "puid":          block["puid"],
        "suid":          block["suid"],
        "action":        block["action"],
        "from_user":     block.get("from_user", ""),
        "to_user":       block.get("to_user", ""),
        "previous_hash": block["previous_hash"],
    }
    encoded = json.dumps(block_data, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.blake2b(encoded, digest_size=32).hexdigest()

# ── Resolve target Manufacturer ───────────────────────────
TARGET_USERNAME = (sys.argv[1].strip() if len(sys.argv) > 1 else "").strip()
if not TARGET_USERNAME:
    TARGET_USERNAME = os.environ.get("TARGET_MANUFACTURER_USERNAME", "").strip()

if TARGET_USERNAME:
    manufacturer_doc = users_col.find_one({"username": TARGET_USERNAME})
    if not manufacturer_doc:
        # Auto-create a demo manufacturer account
        hashed = bcrypt.hashpw(b"Manuf@123", bcrypt.gensalt())
        users_col.insert_one({
            "fullname": "Demo Manufacturer",
            "email":    "",
            "phone":    "",
            "company":  "DemoMfg Co.",
            "address":  "",
            "username": TARGET_USERNAME,
            "password": hashed,
            "role":     "Manufacturer",
        })
        manufacturer_doc = users_col.find_one({"username": TARGET_USERNAME})
        print(f"[OK] Created demo Manufacturer account: {TARGET_USERNAME}")
    elif manufacturer_doc.get("role") != "Manufacturer":
        print(f"[WARN] User '{TARGET_USERNAME}' exists but role is '{manufacturer_doc.get('role')}', not Manufacturer.")
else:
    manufacturer_doc = users_col.find_one({"role": "Manufacturer"})
    if not manufacturer_doc:
        print("[ERROR] No Manufacturer account found. Create one first or pass username as argument.")
        print("        Usage: python seed_products.py <manufacturer_username>")
        sys.exit(1)

MANUFACTURER = manufacturer_doc["username"]
print(f"\n[OK] Seeding products for Manufacturer: {MANUFACTURER}")
print("     Each product gets 1 unit with a MANUFACTURED genesis block.\n")

PRODUCTS = {
    "Medicine": [
        ("Paracetamol 500mg",  "HealthPlus",  "2025-01-10","2027-01-10","45",  "Pain relief and fever reduction tablets. 10 tablets per strip."),
        ("Amoxicillin 250mg",  "MedCure",     "2025-02-01","2026-08-01","120", "Antibiotic capsules for bacterial infections. 6 capsules per pack."),
        ("Vitamin C 1000mg",   "NutriShield", "2025-01-15","2027-01-15","80",  "Immunity booster effervescent tablets. Lemon flavour. 20 tablets."),
        ("Cetirizine 10mg",    "AllerFree",   "2025-03-01","2027-03-01","35",  "Antihistamine for allergy relief. 10 tablets per strip."),
        ("Omeprazole 20mg",    "GastroCare",  "2025-02-10","2026-12-10","95",  "Proton pump inhibitor for acidity and GERD. 14 capsules."),
    ],
    "Electronics": [
        ("Wireless Earbuds Pro",   "SoundWave",  "2025-01-05","2028-01-05","2499","True wireless earbuds with ANC, 30hr battery, IPX5 waterproof."),
        ("USB-C Fast Charger 65W", "ChargePlus", "2025-02-01","2028-02-01","999", "GaN 65W USB-C charger with PD 3.0. Compatible with laptops and phones."),
        ("Bluetooth Speaker Mini", "BoomBox",    "2025-01-10","2028-01-10","1599","Portable waterproof Bluetooth speaker. 12hr playback, 360 sound."),
        ("Smart LED Bulb 9W",      "LumiHome",   "2025-03-01","2030-03-01","349", "Wi-Fi smart LED bulb, 16M colours, voice control compatible."),
        ("Power Bank 20000mAh",    "ChargeStore","2025-02-15","2028-02-15","1299","20000mAh slim power bank with 22.5W fast charging. Dual output."),
    ],
    "Food & Beverage": [
        ("Organic Green Tea 100g", "TeaLeaf",   "2025-01-01","2026-01-01","299", "Premium Darjeeling organic green tea. 50 pyramid bags."),
        ("Cold Pressed Olive Oil", "GoldOlive", "2025-02-01","2026-08-01","699", "Extra virgin cold pressed olive oil 500ml. Imported from Spain."),
        ("Raw Honey 500g",         "HivePure",  "2025-01-15","2027-01-15","449", "100% raw unfiltered honey from Himalayan bee farms. 500g jar."),
    ],
    "Cosmetics": [
        ("Vitamin C Face Serum",   "GlowLab",  "2025-01-10","2026-07-10","599", "10% Vitamin C brightening serum with hyaluronic acid. 30ml."),
        ("SPF 50 Sunscreen 50g",   "SunGuard", "2025-02-01","2027-02-01","349", "Matte finish broad spectrum SPF50+ PA++++ sunscreen. Oil-free."),
    ],
}

# ── Seed: 1 product unit per entry ───────────────────────
total_inserted = 0
now = int(time.time())

for category, items in PRODUCTS.items():
    for name, brand, mfg, exp, price, desc in items:
        src_path, _ = _find_image(name)
        image_filename = os.path.basename(src_path) if src_path else ""

        puid  = generate_puid()
        suid  = generate_suid()
        batch = generate_batch()

        block = {
            "block_id":      "BC-" + str(uuid.uuid4()).replace("-", "")[:12].upper(),
            "index":         1,
            "timestamp":     now,
            "puid":          puid,
            "suid":          suid,
            "uid":           suid,
            "action":        "MANUFACTURED",
            "from_user":     "",   # genesis — no sender
            "to_user":       MANUFACTURER,
            "previous_hash": "GENESIS",
        }
        block["block_hash"] = calculate_block_hash(block)
        blocks_col.insert_one(block)

        products_col.insert_one({
            "puid":           puid,
            "suid":           suid,
            "uid":            suid,
            "name":           name,
            "brand":          brand,
            "category":       category,
            "batch":          batch,
            "mfg_date":       mfg,
            "exp_date":       exp,
            "price_per_unit": price,
            "description":    desc,
            "image":          image_filename,
            "manufacturer":   MANUFACTURER,
            "owner":          MANUFACTURER,
            "status":         "active",
            "scans":          0,
        })

        transactions_col.insert_one({
            "suid":       suid,
            "uid":        suid,
            "puid":       puid,
            "from_user":  "",
            "to_user":    MANUFACTURER,
            "quantity":   1,
            "timestamp":  now,
            "action":     "MANUFACTURED",
            "block_id":   block["block_id"],
            "block_hash": block["block_hash"],
            "ethereum_tx": "",
        })

        total_inserted += 1
        img_tag = f"[IMAGE] {image_filename}" if image_filename else "[WARN] no image"
        print(f"  [+] [{category}] {name} | PUID: {puid} | SUID: {suid} | {img_tag}")

print(f"\n[OK] Done! {total_inserted} product unit(s) seeded for Manufacturer '{MANUFACTURER}'.")
print(f"     Login as {MANUFACTURER} to view, transfer, or recall these products.")
client.close()
