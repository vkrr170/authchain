import os
import bcrypt
from pymongo import MongoClient
from dotenv import load_dotenv
import secrets
import string

load_dotenv()

# Use the same database name as app.py
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
client = MongoClient(MONGO_URI)
db = client["authchain"]
users_col = db["users"]

roles = ["Manufacturer", "Distributor", "Retailer", "Customer"]
users_data = []

# Common base URL for the local app
base_url = "http://localhost:5000/login"

print("Seeding users into MongoDB...")

def generate_secure_password(length=16):
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(secrets.choice(alphabet) for i in range(length))

for role in roles:
    prefix = role.lower()[:4] # mfg, dist, reta, cust
    if role == "Manufacturer": prefix = "mfg"
    
    for i in range(1, 4):
        username = f"{prefix}{i}"
        fullname = f"{role} {i}"
        
        # Check if user exists
        existing = users_col.find_one({"username": username})
        if not existing:
            secure_pwd = generate_secure_password()
            hashed = bcrypt.hashpw(secure_pwd.encode(), bcrypt.gensalt())
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
            print(f"Created user: {username} | Password: {secure_pwd}")
        else:
            print(f"User {username} already exists, skipping insertion.")
