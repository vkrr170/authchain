import os
import bcrypt
import csv
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

# Use the same database name as app.py
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
client = MongoClient(MONGO_URI)
db = client["authchain"]
users_col = db["users"]

roles = ["Manufacturer", "Distributor", "Retailer", "Customer"]
users_data = []

csv_data = [["url", "username", "password", "name"]]
password = "password123"

# Common base URL for the local app
base_url = "http://localhost:5000/login"

print("Seeding users into MongoDB...")

for role in roles:
    prefix = role.lower()[:4] # mfg, dist, reta, cust
    if role == "Manufacturer": prefix = "mfg"
    
    for i in range(1, 4):
        username = f"{prefix}{i}"
        fullname = f"{role} {i}"
        
        # Check if user exists
        existing = users_col.find_one({"username": username})
        if not existing:
            hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
            users_col.insert_one({
                "fullname": fullname,
                "email": f"{username}@example.com",
                "phone": f"555000{i}{i}{i}{i}",
                "company": f"{role} Corp {i}",
                "address": f"123 {role} St",
                "username": username,
                "password": hashed,
                "role": role,
                "wallet": ""
            })
            print(f"Created user: {username}")
        else:
            print(f"User {username} already exists, skipping insertion.")
            
        csv_data.append([base_url, username, password, f"AuthChain - {fullname}"])

csv_file_path = os.path.abspath("brave_passwords.csv")
with open(csv_file_path, mode="w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerows(csv_data)

print(f"\nCSV file successfully generated at: {csv_file_path}")
