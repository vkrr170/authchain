import os
import random
import csv
from datetime import datetime, timedelta

IMG_DIR = r"f:\authchain\static\product_images"
CSV_PATH = r"f:\authchain\static\sample_products.csv"

# Keyword to category mappings
CATEGORIES = {
    "Medicine": ["amoxicillin", "vitamin", "syrup", "vaccine", "ointment", "cetirizine", "omeprazole", "ibuprofen", "metformin", "azithromycin", "paracetamol"],
    "Electronics": ["cable", "camera", "speaker", "charger", "earbuds", "keyboard", "webcam", "bulb", "bank", "cooling pad"],
    "Automotive": ["car", "brake", "engine oil", "tyre", "windshield", "jump starter", "dash"],
    "Cosmetics": ["serum", "sunscreen", "moisturiser", "balm", "cleansing", "toner", "cream", "mask", "frizz"],
    "Clothing": ["jacket", "shirt", "raincoat", "shorts", "kurti", "pants", "hoodie", "scarf", "socks"],
    "Food & Beverage": ["tea", "olive oil", "honey", "butter", "seeds", "chocolate", "milk", "bar", "vinegar"],
    "Other": ["toothbrush", "notebook", "mat", "bags", "candle", "bands", "bottle", "padlock", "cleaning"]
}

# Brands mapping
BRANDS = {
    "Medicine": ["HealthPlus", "MedCure", "NutriShield", "AllerFree", "PharmaLife", "GastroCare"],
    "Electronics": ["TechPro", "SoundWave", "ChargePlus", "BoomBox", "LumiHome", "ChargeStore", "GearUp"],
    "Automotive": ["AutoCare", "DriveSafe", "MotoPlus", "SpeedMax"],
    "Cosmetics": ["GlowLab", "DermaCare", "SunGuard", "BeautyEssence", "PureSkin"],
    "Clothing": ["StyleBrand", "UrbanWear", "FitPro", "ComfyTex", "FashionPlus"],
    "Food & Beverage": ["NatureBites", "GoldOlive", "HivePure", "TeaLeaf", "OrganicFarms", "HealthFoods"],
    "Other": ["EverydayEssentials", "HomePlus", "ActiveLife", "EcoGoods"]
}

import re

def guess_category(name):
    lower_name = name.lower()
    for cat, keywords in CATEGORIES.items():
        for kw in keywords:
            if re.search(r'\b' + re.escape(kw) + r'\b', lower_name):
                return cat
    return "Other"

def generate_csv():
    images = [f for f in os.listdir(IMG_DIR) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]
    
    with open(CSV_PATH, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["Category", "Name", "Brand", "Price Per Unit", "Shelf Life", "Description"])
        
        for img in images:
            # Extract product name from image filename
            name = os.path.splitext(img)[0]
            
            # Map manual overrides (like 'desk lap' -> 'Desk Lamp LED')
            if name.lower() == "desk lap":
                name = "Desk Lamp LED"
            elif name.lower() == "padlock":
                name = "Padlock 50mm"
                
            category = guess_category(name)
            brand = random.choice(BRANDS[category])
            
            # Generate random realistic prices based on category
            price_map = {
                "Medicine": random.randint(30, 500),
                "Electronics": random.randint(500, 5000),
                "Automotive": random.randint(200, 2500),
                "Cosmetics": random.randint(250, 1500),
                "Clothing": random.randint(400, 3000),
                "Food & Beverage": random.randint(100, 800),
                "Other": random.randint(50, 1000)
            }
            price = price_map.get(category, 500)
            
            # Generate realistic Shelf Life in Days
            if category in ["Electronics", "Clothing", "Automotive", "Other"]:
                shelf_life = "N/A"
            else:
                shelf_life = random.randint(365, 365*3)
                
            desc = f"Premium quality {name.lower()} by {brand}."
            
            writer.writerow([category, name, brand, price, shelf_life, desc])

    print(f"Successfully generated {CSV_PATH} with {len(images)} blueprints.")

if __name__ == "__main__":
    generate_csv()
