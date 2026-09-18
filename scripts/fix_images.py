import os
from dotenv import load_dotenv
from pymongo import MongoClient
import difflib

load_dotenv()
client = MongoClient(os.environ.get("MONGO_URI"))
db = client["authchain"]

img_dir = r"f:\authchain\static\product_images"
image_files = [f for f in os.listdir(img_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]

def norm(s):
    return s.lower().replace("'", "").replace("-", " ").strip()

for bp in db.blueprints.find():
    name = bp.get("name", "")
    best_match = None
    best_score = 0
    for img in image_files:
        stem = os.path.splitext(img)[0]
        score = difflib.SequenceMatcher(None, norm(name), norm(stem)).ratio()
        
        if stem.lower() == "desk lap" and norm(name) == "desk lamp led":
            score = 1.0
        if stem.lower() == "padlock" and norm(name) == "padlock 50mm":
            score = 1.0
            
        if score > best_score:
            best_score = score
            best_match = img
    
    if best_score > 0.6:
        print(f"Match: {name} -> {best_match} (score: {best_score})")
        db.blueprints.update_many({"name": name}, {"$set": {"image": best_match}})
        db.products.update_many({"name": name}, {"$set": {"image": best_match}})
    else:
        print(f"No match for {name}")
