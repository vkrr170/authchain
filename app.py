from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, jsonify
from pymongo import MongoClient, UpdateOne
import bcrypt
import uuid
import hashlib
import qrcode
import os
import time
import json
import csv
import re
from difflib import SequenceMatcher
from werkzeug.utils import secure_filename
from datetime import datetime, date
from functools import wraps
from dotenv import load_dotenv
from authlib.integrations.flask_client import OAuth

load_dotenv()

try:
    from web3 import Web3
    from eth_account.messages import encode_defunct
except ImportError:
    Web3 = None
    encode_defunct = None

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(24).hex()

oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=os.environ.get("GOOGLE_CLIENT_ID"),
    client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

# Ensure static subdirs exist
os.makedirs(os.path.join(app.root_path, "static", "qrcodes"),        exist_ok=True)
os.makedirs(os.path.join(app.root_path, "static", "product_images"), exist_ok=True)

@app.template_filter('ts')
def timestamp_filter(ts):
    try:
        return datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M")
    except:
        return str(ts)

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
client = MongoClient(MONGO_URI)
db = client["authchain"]
users_col        = db["users"]
products_col     = db["products"]
transactions_col = db["transactions"]
blocks_col       = db["blocks"]
blueprints_col   = db["blueprints"]

# Ensure database indexes exist for query performance
try:
    users_col.create_index("username", unique=True)
    products_col.create_index("suid", unique=True)
    products_col.create_index("puid")
    products_col.create_index("owner")
    blocks_col.create_index([("suid", 1), ("index", 1)])
    transactions_col.create_index("suid")
except Exception as e:
    app.logger.warning(f"Could not create database indexes: {e}")

WEB3_PROVIDER_URI = os.environ.get("WEB3_PROVIDER_URI", "").strip()
AUTHCHAIN_CONTRACT_ADDRESS = os.environ.get("AUTHCHAIN_CONTRACT_ADDRESS", "").strip()
ETH_PRIVATE_KEY = os.environ.get("ETH_PRIVATE_KEY", "").strip()
ETH_CHAIN_ID = int(os.environ.get("ETH_CHAIN_ID", "11155111"))
ETH_NETWORK_NAME = os.environ.get("ETH_NETWORK_NAME", "Sepolia")
METAMASK_CHAIN_ID_HEX = os.environ.get("METAMASK_CHAIN_ID_HEX", hex(ETH_CHAIN_ID))

AUTHCHAIN_CONTRACT_ABI = [
    {
        "inputs": [
            {"internalType": "string", "name": "blockId", "type": "string"},
            {"internalType": "string", "name": "puid", "type": "string"},
            {"internalType": "string", "name": "suid", "type": "string"},
            {"internalType": "string", "name": "action", "type": "string"},
            {"internalType": "string", "name": "fromUser", "type": "string"},
            {"internalType": "string", "name": "toUser", "type": "string"},
            {"internalType": "bytes32", "name": "blockHash", "type": "bytes32"},
            {"internalType": "string", "name": "previousHash", "type": "string"},
        ],
        "name": "recordEvent",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "string", "name": "blockId", "type": "string"}],
        "name": "getEvent",
        "outputs": [
            {"internalType": "string", "name": "puid", "type": "string"},
            {"internalType": "string", "name": "suid", "type": "string"},
            {"internalType": "string", "name": "action", "type": "string"},
            {"internalType": "string", "name": "fromUser", "type": "string"},
            {"internalType": "string", "name": "toUser", "type": "string"},
            {"internalType": "bytes32", "name": "blockHash", "type": "bytes32"},
            {"internalType": "string", "name": "previousHash", "type": "string"},
            {"internalType": "uint256", "name": "timestamp", "type": "uint256"},
            {"internalType": "bool", "name": "exists", "type": "bool"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
]

# ── Strict supply chain flow: M → D → R → C ─────────────
# Each stage can only pass to the immediately next stage.
# Manufacturers → Distributors only.
# Distributors → Retailers only.
# Retailers → Customers only.
SUPPLY_CHAIN_NEXT = {
    "Manufacturer": ["Distributor"],
    "Distributor":  ["Retailer"],
    "Retailer":     ["Customer"],
}

CATEGORIES = ["Medicine", "Electronics", "Food & Beverage", "Cosmetics",
              "Clothing", "Automotive"]

def get_dynamic_categories():
    db_cats = blueprints_col.distinct("category")
    db_prod_cats = products_col.distinct("category")
    all_c = set(CATEGORIES + db_cats + db_prod_cats)
    if "" in all_c:
        all_c.remove("")
    cats = sorted(list(all_c))
    if "Other" in cats:
        cats.remove("Other")
        cats.append("Other")
    return cats

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

# ── Helpers ──────────────────────────────────────────────
def allowed_file(f):
    return "." in f and f.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

MANUAL_OVERRIDES = {
    "desk lap": "Desk Lamp LED",
    "padlock":  "Padlock 50mm",
}

def _norm(s):
    return s.lower().replace("\u2019", "").replace("'", "").replace("-", " ").strip()

def _sim(a, b):
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()

def _find_image(name):
    img_dir = os.path.join(app.root_path, "static", "product_images")
    exts = (".jpg", ".jpeg", ".png", ".gif", ".webp")
    if not os.path.exists(img_dir):
        return ""
    files = [f for f in os.listdir(img_dir)
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
        return best_file
    return ""

def generate_puid():
    return "P-" + str(uuid.uuid4()).replace("-", "")[:8].upper()

def generate_suid():
    return "S-" + str(uuid.uuid4()).replace("-", "")[:8].upper()

def generate_batch():
    return "B-" + str(uuid.uuid4()).replace("-", "")[:10].upper()

def ethereum_contract():
    if not Web3 or not WEB3_PROVIDER_URI or not AUTHCHAIN_CONTRACT_ADDRESS:
        return None, None
    web3 = Web3(Web3.HTTPProvider(WEB3_PROVIDER_URI))
    if not web3.is_connected():
        return None, None
    address = web3.to_checksum_address(AUTHCHAIN_CONTRACT_ADDRESS)
    return web3, web3.eth.contract(address=address, abi=AUTHCHAIN_CONTRACT_ABI)

def suid_to_token_id(suid):
    return str(int(hashlib.sha256(suid.encode()).hexdigest(), 16) % (2**256 - 1))

# Global Web3 instance for signing, initialized lazily or once
_local_w3 = None

def sign_block_hash(block_hash):
    global _local_w3
    if not ETH_PRIVATE_KEY or not encode_defunct:
        return "0x"
    msg = encode_defunct(hexstr=block_hash)
    if _local_w3 is None:
        _local_w3 = Web3()
    signed = _local_w3.eth.account.sign_message(msg, private_key=ETH_PRIVATE_KEY)
    return "0x" + signed.signature.hex()

def record_block_on_ethereum(block):
    # Backend no longer records blocks directly.
    # All transactions are signed by the backend and executed by the client.
    return None

def ethereum_block_matches(block):
    web3, contract = ethereum_contract()
    if not web3 or not contract:
        return not AUTHCHAIN_CONTRACT_ADDRESS

    # 1. Try checking on-chain contract state (for mined events)
    try:
        event = contract.functions.getEvent(block["block_id"]).call()
        exists = event[8]
        if exists:
            chain_hash = event[5].hex()
            return event[0] == block["puid"] and event[1] == block["suid"] and chain_hash == block["block_hash"]
    except Exception:
        pass

    # 2. Fallback: check if transaction is pending in the mempool
    tx_hash = block.get("ethereum_tx")
    if tx_hash:
        try:
            tx = web3.eth.get_transaction(tx_hash)
            if tx:
                # A pending tx is presumed valid if it hasn't reverted
                return True
        except Exception:
            pass

    return False

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

def latest_block(suid=None):
    query = {"suid": suid} if suid else {}
    return blocks_col.find_one(query, sort=[("index", -1), ("timestamp", -1)])

def add_block(puid, suid, action, from_user, to_user, timestamp=None):
    timestamp = timestamp or int(time.time())
    previous = latest_block(suid)
    block = {
        "block_id":      "BC-" + str(uuid.uuid4()).replace("-", "")[:12].upper(),
        "index":         blocks_col.count_documents({"suid": suid}) + 1,
        "timestamp":     timestamp,
        "puid":          puid,
        "suid":          suid,
        "uid":           suid,
        "action":        action,
        "from_user":     from_user,
        "to_user":       to_user,
        "previous_hash": previous["block_hash"] if previous else "GENESIS",
    }
    block["block_hash"] = calculate_block_hash(block)
    blocks_col.insert_one(block)
    try:
        tx_hash = record_block_on_ethereum(block)
        if tx_hash:
            block["ethereum_tx"] = tx_hash
            blocks_col.update_one(
                {"block_id": block["block_id"]},
                {"$set": {"ethereum_tx": tx_hash}}
            )
    except Exception as exc:
        blocks_col.update_one(
            {"block_id": block["block_id"]},
            {"$set": {"ethereum_error": str(exc)}}
        )
    return block

def validate_unit_chain(suid):
    chain = list(blocks_col.find({"suid": suid}).sort("index", 1))
    if not chain:
        return False

    previous_hash = "GENESIS"
    for expected_index, block in enumerate(chain, start=1):
        if block.get("index") != expected_index:
            return False
        if block.get("previous_hash") != previous_hash:
            return False
        if block.get("block_hash") != calculate_block_hash(block):
            return False
        if not ethereum_block_matches(block):
            return False
        previous_hash = block["block_hash"]
    return True

def generate_qr(puid, suid, block_id=None):
    if not block_id:
        block = blocks_col.find_one({
            "puid": puid,
            "suid": suid,
            "action": {"$in": ["MANUFACTURED", "REGISTERED"]},
        })
        block_id = block["block_id"] if block else ""
    data = f"BC:{puid}:{suid}:{block_id}"
    img  = qrcode.make(data)
    img.save(os.path.join(app.root_path, "static", "qrcodes", f"{suid}.png"))

def verify_qr_data(qr_data):
    try:
        parts = qr_data.strip().split(":")
        if len(parts) == 4 and parts[0] == "BC":
            _, puid, suid, block_id = parts
            block = blocks_col.find_one({
                "block_id": block_id,
                "puid":     puid,
                "suid":     suid,
                "action":   {"$in": ["MANUFACTURED", "REGISTERED"]},
            })
            if block and validate_unit_chain(suid):
                return puid, suid
            return None, None
        return None, None
    except:
        return None, None

def enrich_product(product):
    try:
        price = float(product.get("price_per_unit") or product.get("price") or 0)
        product["price_per_unit"] = price
        product["total_price"]    = price
    except (ValueError, TypeError):
        product["price_per_unit"] = 0
        product["total_price"]    = 0
    
    suid = product.get("suid") or product.get("uid") or ""
    if suid:
        product["token_id"] = suid_to_token_id(suid)
        
    owner_username = product.get("owner")
    if owner_username:
        owner_doc = users_col.find_one({"username": owner_username})
        if owner_doc:
            product["owner_fullname"] = owner_doc.get("fullname", "")
            product["owner_role"] = owner_doc.get("role", "")
            product["owner_company"] = owner_doc.get("company", "")
            
    return product

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if session.get("role") not in roles:
                flash("Access denied.", "danger")
                return redirect(url_for("dashboard"))
            return f(*args, **kwargs)
        return decorated
    return decorator

def category_filter_query():
    cat = request.args.get("category", "").strip()
    return {"category": cat} if cat else {}

# ── Auth ─────────────────────────────────────────────────
@app.route("/")
def index():
    return redirect(url_for("login"))

# ── QR serving ────────────────────────────────────────────
@app.route("/qr/<suid>")
def serve_qr(suid):
    qr_dir  = os.path.join(app.root_path, "static", "qrcodes")
    os.makedirs(qr_dir, exist_ok=True)
    qr_path = os.path.join(qr_dir, f"{suid}.png")

    if not os.path.exists(qr_path):
        product = products_col.find_one(
            {"$or": [{"suid": suid}, {"uid": suid}]},
            {"puid": 1, "suid": 1, "uid": 1}
        )
        if product:
            puid_val = product.get("puid", "")
            suid_val = product.get("suid") or product.get("uid") or suid
            if puid_val and suid_val:
                generate_qr(puid_val, suid_val)

    if os.path.exists(qr_path):
        return send_file(qr_path, mimetype="image/png")

    return ("QR not found", 404)

@app.route("/check_field", methods=["POST"])
def check_field():
    """AJAX endpoint to check if username, email, or phone already exists."""
    data = request.get_json()
    field = data.get("field")
    value = data.get("value", "").strip()
    if field == "username":
        exists = bool(users_col.find_one({"username": value}))
    elif field == "email":
        exists = bool(users_col.find_one({"email": value}))
    elif field == "phone":
        exists = bool(users_col.find_one({"phone": value}))
    else:
        return jsonify({"error": "unknown field"}), 400
    return jsonify({"exists": exists})

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        fullname = request.form.get("fullname", "").strip()
        username = request.form.get("username", "").strip()
        email    = request.form.get("email", "").strip()
        phone    = request.form.get("phone", "").strip()
        company  = request.form.get("company", "").strip()
        address  = request.form.get("address", "").strip()
        role     = request.form.get("role", "").strip()
        password = request.form.get("password", "")
        confirm  = request.form.get("confirm", "")

        # ── Mandatory field checks ────────────────────────
        if not fullname:
            flash("Full name is required.", "danger")
            return redirect(url_for("register"))
        if not username:
            flash("Username is required.", "danger")
            return redirect(url_for("register"))
        if not email:
            flash("Email is required.", "danger")
            return redirect(url_for("register"))
        if not phone:
            flash("Phone number is required.", "danger")
            return redirect(url_for("register"))
        if not company and role != "Customer":
            flash("Company is required.", "danger")
            return redirect(url_for("register"))
        if not address:
            flash("Address is required.", "danger")
            return redirect(url_for("register"))
        if not role:
            flash("Role is required.", "danger")
            return redirect(url_for("register"))
        if not password:
            flash("Password is required.", "danger")
            return redirect(url_for("register"))
        if password != confirm:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("register"))

        # ── Password strength validation ──────────────────────
        password_pattern = r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9]).+$"
        if not re.match(password_pattern, password):
            flash("Password must contain at least one uppercase letter, one lowercase letter, one number, and one special character.", "danger")
            return redirect(url_for("register"))

        # ── Email format validation ───────────────────────
        email_pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
        if not re.match(email_pattern, email):
            flash("Invalid email address format.", "danger")
            return redirect(url_for("register"))

        # ── Duplicate checks ─────────────────────────────
        if users_col.find_one({"username": username}):
            flash("Username already taken. Please choose another.", "danger")
            return redirect(url_for("register"))
        if users_col.find_one({"email": email}):
            flash("An account with this email already exists.", "danger")
            return redirect(url_for("register"))
        if users_col.find_one({"phone": phone}):
            flash("An account with this phone number already exists.", "danger")
            return redirect(url_for("register"))

        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
        users_col.insert_one({
            "fullname": fullname,
            "email":    email,
            "phone":    phone,
            "company":  company,
            "address":  address,
            "username": username,
            "password": hashed,
            "role":     role
        })
        flash("Registered successfully! Please login.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = users_col.find_one({"username": request.form["username"]})
        if user and bcrypt.checkpw(request.form["password"].encode(), user["password"]):
            session["username"] = user["username"]
            session["role"]     = user["role"]
            session["fullname"] = user["fullname"]
            session["wallet"]   = user.get("wallet", "")
            return redirect(url_for("dashboard"))
        flash("Invalid credentials.", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/login/google")
def login_google():
    redirect_uri = url_for('authorize_google', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route("/login/google/authorize")
def authorize_google():
    try:
        token = google.authorize_access_token()
    except Exception as e:
        flash(f"OAuth error: {str(e)}", "danger")
        return redirect(url_for('login'))
        
    user_info = token.get('userinfo')
    if not user_info:
        flash("Failed to get user info from Google.", "danger")
        return redirect(url_for('login'))
        
    email = user_info.get("email")
    name = user_info.get("name")
    
    user = users_col.find_one({"email": email})
    if user:
        session["username"] = user["username"]
        session["role"]     = user["role"]
        session["fullname"] = user["fullname"]
        session["wallet"]   = user.get("wallet", "")
        flash("Logged in successfully via Google.", "success")
        return redirect(url_for("dashboard"))
    
    session["google_temp_info"] = {
        "email": email,
        "name": name
    }
    return redirect(url_for("complete_profile"))

@app.route("/complete_profile", methods=["GET", "POST"])
def complete_profile():
    google_info = session.get("google_temp_info")
    if not google_info:
        return redirect(url_for("login"))
        
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        phone    = request.form.get("phone", "").strip()
        company  = request.form.get("company", "").strip()
        address  = request.form.get("address", "").strip()
        role     = request.form.get("role", "").strip()

        if not username or not phone or not address or not role:
            flash("All fields are required.", "danger")
            return render_template("complete_profile.html", google_info=google_info)
            
        if not company and role != "Customer":
            flash("Company is required.", "danger")
            return render_template("complete_profile.html", google_info=google_info)
        
        if users_col.find_one({"username": username}):
            flash("Username already exists.", "danger")
            return render_template("complete_profile.html", google_info=google_info)
            
        hashed = bcrypt.hashpw(os.urandom(24).hex().encode(), bcrypt.gensalt())
        
        users_col.insert_one({
            "fullname": google_info["name"],
            "email":    google_info["email"],
            "phone":    phone,
            "company":  company,
            "address":  address,
            "username": username,
            "password": hashed,
            "role":     role,
            "google_auth": True
        })
        
        session["username"] = username
        session["role"]     = request.form["role"]
        session["fullname"] = google_info["name"]
        session["wallet"]   = ""
        session.pop("google_temp_info", None)
        flash("Account created successfully! Welcome to AuthChain.", "success")
        return redirect(url_for("dashboard"))
        
    return render_template("complete_profile.html", google_info=google_info)

@app.route("/wallet/connect", methods=["POST"])
@login_required
def connect_wallet():
    # Deprecated for DB updates. Just sets session wallet if not set.
    data   = request.get_json(silent=True) or {}
    wallet = data.get("wallet", "").strip()
    if not wallet:
        return jsonify({"ok": False, "message": "Wallet address is required."}), 400

    if not session.get("wallet"):
        session["wallet"] = wallet
    return jsonify({"ok": True, "wallet": session.get("wallet")})

@app.route("/api/wallet/link", methods=["POST"])
@login_required
def link_wallet():
    data   = request.get_json(silent=True) or {}
    wallet = data.get("wallet", "").strip()
    if not wallet:
        return jsonify({"ok": False, "error": "Wallet address is required."}), 400

    # Strictly bind wallet to user account in DB and Session
    users_col.update_one({"username": session["username"]}, {"$set": {"wallet": wallet}})
    session["wallet"] = wallet
    return jsonify({"ok": True, "wallet": wallet})

@app.route("/wallet/disconnect", methods=["POST"])
@login_required
def disconnect_wallet():
    session.pop("wallet", None)
    return jsonify({"ok": True})

@app.route("/blockchain/status")
@login_required
def blockchain_status():
    web3, contract = ethereum_contract()
    latest_block_number = None
    connected = bool(web3 and contract)
    if connected:
        latest_block_number = web3.eth.block_number

    return jsonify({
        "connected":        connected,
        "network":          ETH_NETWORK_NAME,
        "chain_id":         ETH_CHAIN_ID,
        "contract_address": AUTHCHAIN_CONTRACT_ADDRESS,
        "latest_block":     latest_block_number,
        "web3_installed":   Web3 is not None,
    })

@app.context_processor
def inject_blockchain_config():
    return {
        "eth_network_name":             ETH_NETWORK_NAME,
        "metamask_chain_id":            METAMASK_CHAIN_ID_HEX,
        "authchain_contract_address":   AUTHCHAIN_CONTRACT_ADDRESS,
    }

# ── Dashboard ─────────────────────────────────────────────
@app.route("/dashboard")
@login_required
def dashboard():
    cat_filter = category_filter_query()
    active_cat = request.args.get("category", "")

    if session.get("role") == "Manufacturer":
        total_units = products_col.count_documents({"manufacturer": session.get("username")})
        total_txns  = transactions_col.count_documents({"$or": [{"from_user": session.get("username")}, {"to_user": session.get("username")}]})
    else:
        total_units = products_col.count_documents({"owner": session.get("username")})
        total_txns  = transactions_col.count_documents({"$or": [{"from_user": session.get("username")}, {"to_user": session.get("username")}]})

    page = int(request.args.get("page", 1))
    per_page = 20

    if session.get("role") == "Manufacturer":
        cat_counts = {c["_id"]: c["count"] for c in products_col.aggregate([
            {"$match": {"manufacturer": session.get("username")}},
            {"$group": {"_id": "$category", "count": {"$sum": 1}}}
        ])}

        match_query = cat_filter.copy()
        match_query["manufacturer"] = session.get("username")

        pipeline = [
            {"$match": match_query},
            {"$group": {
                "_id":          {"name": "$name", "brand": "$brand", "category": "$category"},
                "name":         {"$first": "$name"},
                "brand":        {"$first": "$brand"},
                "category":     {"$first": "$category"},
                "manufacturer": {"$first": "$manufacturer"},
                "image":        {"$first": "$image"},
                "total_units":  {"$sum": 1},
                "batch_count":  {"$addToSet": "$batch"},
                "latest_puid":  {"$last":  "$puid"},
                "latest_batch": {"$last":  "$batch"},
                "sample_suid":  {"$first": {"$ifNull": ["$suid", "$uid"]}},
            }},
            {"$sort": {"name": 1}}
        ]
        grouped = list(products_col.aggregate(pipeline))
        for p in grouped:
            p["batch_count"] = len(p["batch_count"])

        total_pages = max(1, -(-len(grouped) // per_page))
        page_data   = grouped[(page-1)*per_page : page*per_page]
    else:
        cat_counts = {}
        grouped = []
        total_pages = 1
        page_data = []

    return render_template("dashboard.html",
                           total_products=total_units,
                           total_txns=total_txns,
                           products=page_data,
                           page=page,
                           total_pages=total_pages,
                           categories=get_dynamic_categories(),
                           active_cat=active_cat,
                           cat_counts=cat_counts)

# ── Inventory (View Manufactured Products) ──
@app.route("/inventory")
@login_required
@role_required("Manufacturer", "Distributor", "Retailer", "Customer")
def inventory():
    cat_filter = category_filter_query()
    active_cat = request.args.get("category", "")

    base_match = {"owner": session.get("username")}
    if session.get("role") == "Customer":
        base_match["scans"] = {"$gte": 1}

    cat_counts = {c["_id"]: c["count"] for c in products_col.aggregate([
        {"$match": base_match},
        {"$group": {"_id": "$category", "count": {"$sum": 1}}}
    ])}

    match_query = base_match.copy()
    match_query.update(cat_filter)
    
    search_query = request.args.get("search", "").strip()
    if search_query:
        match_query["$or"] = [
            {"name": {"$regex": search_query, "$options": "i"}},
            {"brand": {"$regex": search_query, "$options": "i"}}
        ]

    pipeline = [
        {"$match": match_query},
        {"$group": {
            "_id":          {"name": "$name", "brand": "$brand", "category": "$category"},
            "name":         {"$first": "$name"},
            "brand":        {"$first": "$brand"},
            "category":     {"$first": "$category"},
            "image":        {"$first": "$image"},
            "price_per_unit":{"$first": "$price_per_unit"},
            "total_units":  {"$sum": 1},
            "batch_count":  {"$addToSet": "$batch"},
            "latest_puid":  {"$first": "$puid"}
        }},
        {"$sort": {"name": 1}}
    ]
    grouped = list(products_col.aggregate(pipeline))
    for p in grouped:
        p["batch_count"] = len(p["batch_count"])
        
    return render_template("inventory.html", products=grouped,
                           categories=CATEGORIES,
                           active_cat=active_cat,
                           cat_counts=cat_counts)

# Backward-compatibility redirects
@app.route("/add_product")
@login_required
@role_required("Manufacturer")
def add_product():
    return redirect(url_for("create_product"))

@app.route("/manufacture")
@login_required
@role_required("Manufacturer")
def manufacture():
    return redirect(url_for("create_product"))

# ── Image upload helper (used by create_product JS flow) ──
@app.route("/api/product/upload_image", methods=["POST"])
@login_required
@role_required("Manufacturer")
def api_product_upload_image():
    if "image" not in request.files:
        return jsonify({"ok": True, "filename": ""})
    file = request.files["image"]
    if not file or not file.filename or not allowed_file(file.filename):
        return jsonify({"ok": True, "filename": ""})
    filename = secure_filename(file.filename)
    file.save(os.path.join(app.root_path, "static", "product_images", filename))
    return jsonify({"ok": True, "filename": filename})

# ── Prepare signed block data for MetaMask minting ────────
@app.route("/api/product/prepare", methods=["POST"])
@login_required
@role_required("Manufacturer")
def api_product_prepare():
    username = session["username"]
    data     = request.get_json() or {}

    name     = data.get("name",          "").strip()
    brand    = data.get("brand",         "").strip()
    category = data.get("category",      "").strip()
    mfg_date = data.get("mfg_date",      "").strip()
    exp_date = data.get("exp_date",      "").strip()
    price    = data.get("price_per_unit","").strip()
    desc     = data.get("description",   "").strip()
    try:
        qty = max(1, int(data.get("quantity", 1)))
    except Exception:
        qty = 1

    if not all([name, brand, category, mfg_date, exp_date, price]):
        return jsonify({"ok": False, "error": "All required fields must be filled."}), 400

    user_doc = users_col.find_one({"username": username})
    if not user_doc or not user_doc.get("wallet"):
        return jsonify({"ok": False, "error": "Connect a MetaMask wallet to manufacture products (NFT minting requires a wallet)."}), 400
    wallet = user_doc["wallet"]

    puid  = generate_puid()
    batch = generate_batch()
    now   = int(time.time())

    prepared_blocks = []
    for _ in range(qty):
        suid = generate_suid()
        block = {
            "block_id":      "BC-" + str(uuid.uuid4()).replace("-", "")[:12].upper(),
            "index":         1,
            "timestamp":     now,
            "puid":          puid,
            "suid":          suid,
            "action":        "MANUFACTURED",
            "from_user":     "",          # no sender — this is a genesis/creation event
            "to_user":       username,
            "previous_hash": "GENESIS",
            "token_id":      suid_to_token_id(suid),
            "to_wallet":     wallet,
            # product metadata passed through to confirm
            "_name":     name,
            "_brand":    brand,
            "_category": category,
            "_mfg_date": mfg_date,
            "_exp_date": exp_date,
            "_price":    price,
            "_desc":     desc,
            "_batch":    batch,
        }
        block["block_hash"] = calculate_block_hash(block)
        block["signature"]  = sign_block_hash(block["block_hash"])
        prepared_blocks.append(block)

    return jsonify({"ok": True, "blocks": prepared_blocks, "puid": puid, "batch": batch, "qty": qty})

# ── Prepare signed block data for Blueprint minting ────────
@app.route("/api/product/blueprint_prepare", methods=["POST"])
@login_required
@role_required("Manufacturer")
def api_product_blueprint_prepare():
    username = session["username"]
    data     = request.get_json() or {}
    bp_id    = data.get("bp_id")
    try:
        qty = max(1, int(data.get("quantity", 1)))
    except Exception:
        qty = 1

    if not bp_id:
        return jsonify({"ok": False, "error": "Blueprint ID is required."}), 400

    bp = blueprints_col.find_one({"_id": bp_id, "manufacturer": username})
    if not bp:
        return jsonify({"ok": False, "error": "Blueprint not found."}), 404

    user_doc = users_col.find_one({"username": username})
    if not user_doc or not user_doc.get("wallet"):
        return jsonify({"ok": False, "error": "Connect a MetaMask wallet to manufacture products (NFT minting requires a wallet)."}), 400
    wallet = user_doc["wallet"]

    import datetime
    today = datetime.date.today()
    mfg_date = today.strftime("%Y-%m-%d")
    
    cat = bp.get("category", "")
    shelf_life = bp.get("shelf_life_days")
    
    if shelf_life == "N/A" or not shelf_life:
        exp_date = "N/A"
    elif str(shelf_life).strip().isdigit():
        days = int(str(shelf_life).strip())
        exp_date = (today + datetime.timedelta(days=days)).strftime("%Y-%m-%d")
    elif cat in ["Electronics", "Clothing", "Automotive", "Other"]:
        exp_date = "N/A"
    elif cat == "Medicine":
        exp_date = (today + datetime.timedelta(days=730)).strftime("%Y-%m-%d")
    elif cat == "Food & Beverage":
        exp_date = (today + datetime.timedelta(days=180)).strftime("%Y-%m-%d")
    else:
        exp_date = (today + datetime.timedelta(days=365)).strftime("%Y-%m-%d")

    puid  = generate_puid()
    batch = generate_batch()
    now   = int(time.time())

    prepared_blocks = []
    for _ in range(qty):
        suid = generate_suid()
        block = {
            "block_id":      "BC-" + str(uuid.uuid4()).replace("-", "")[:12].upper(),
            "index":         1,
            "timestamp":     now,
            "puid":          puid,
            "suid":          suid,
            "action":        "MANUFACTURED",
            "from_user":     "",
            "to_user":       username,
            "previous_hash": "GENESIS",
            "token_id":      suid_to_token_id(suid),
            "to_wallet":     wallet,
            "_name":         bp.get("name", ""),
            "_brand":        bp.get("brand", ""),
            "_category":     bp.get("category", ""),
            "_mfg_date":     mfg_date,
            "_exp_date":     exp_date,
            "_price":        str(bp.get("price_per_unit", "")),
            "_desc":         bp.get("description", ""),
            "_batch":        batch,
            "_image":        bp.get("image", "")
        }
        block["block_hash"] = calculate_block_hash(block)
        block["signature"]  = sign_block_hash(block["block_hash"])
        prepared_blocks.append(block)

    return jsonify({"ok": True, "blocks": prepared_blocks, "puid": puid, "batch": batch, "qty": qty})

# ── Confirm after MetaMask tx confirmed ───────────────────
@app.route("/api/product/confirm", methods=["POST"])
@login_required
@role_required("Manufacturer")
def api_product_confirm():
    username = session["username"]
    data     = request.get_json()
    blocks   = data.get("blocks", [])
    tx_hash  = data.get("tx_hash", "")
    image_filename = data.get("image", "")

    if not blocks or not tx_hash:
        return jsonify({"ok": False, "error": "Invalid confirmation data."}), 400

    if Web3 and WEB3_PROVIDER_URI:
        try:
            w3      = Web3(Web3.HTTPProvider(WEB3_PROVIDER_URI))
            receipt = w3.eth.get_transaction_receipt(tx_hash)
            if not receipt or receipt.status != 1:
                return jsonify({"ok": False, "error": "Blockchain transaction failed or not found."}), 400
        except Exception as e:
            return jsonify({"ok": False, "error": f"Error verifying tx: {str(e)}"}), 400

    puid = blocks[0]["puid"] if blocks else generate_puid()
    now  = int(time.time())

    blocks_to_insert = []
    products_to_insert = []
    transactions_to_insert = []

    for block in blocks:
        block["uid"]         = block["suid"]
        block["ethereum_tx"] = tx_hash
        # Extract metadata before saving the block
        name     = block.pop("_name",     "")
        brand    = block.pop("_brand",    "")
        category = block.pop("_category", "")
        mfg_date = block.pop("_mfg_date", "")
        exp_date = block.pop("_exp_date", "")
        price    = block.pop("_price",    "")
        desc     = block.pop("_desc",     "")
        batch    = block.pop("_batch",    "")
        b_image  = block.pop("_image",    "")

        blocks_to_insert.append(block)
        suid = block["suid"]

        products_to_insert.append({
            "puid":           puid,
            "suid":           suid,
            "uid":            suid,
            "name":           name,
            "brand":          brand,
            "category":       category,
            "batch":          batch,
            "mfg_date":       mfg_date,
            "exp_date":       exp_date,
            "price_per_unit": price,
            "description":    desc,
            "image":          image_filename or b_image,
            "manufacturer":   username,
            "owner":          username,
            "status":         "active",
            "scans":          0,
        })

        transactions_to_insert.append({
            "suid":       suid,
            "uid":        suid,
            "puid":       puid,
            "from_user":  "",
            "to_user":    username,
            "quantity":   1,
            "timestamp":  now,
            "action":     "MANUFACTURED",
            "block_id":   block["block_id"],
            "block_hash": block["block_hash"],
            "ethereum_tx": tx_hash,
        })

    if blocks_to_insert:
        blocks_col.insert_many(blocks_to_insert)
    if products_to_insert:
        products_col.insert_many(products_to_insert)
    if transactions_to_insert:
        transactions_col.insert_many(transactions_to_insert)

    return jsonify({"ok": True, "message": f"{len(blocks)} unit(s) manufactured successfully!", "puid": puid})

# ── Add Stock (restock existing product line) ─────────────
@app.route("/add_stock/<puid>", methods=["GET", "POST"])
@login_required
@role_required("Manufacturer")
def add_stock(puid):
    sample = products_col.find_one({"puid": puid, "manufacturer": session["username"]})
    if not sample:
        flash("Product not found or access denied.", "danger")
        return redirect(url_for("dashboard"))

    return redirect(url_for("create_product", 
                            name=sample.get("name", ""),
                            brand=sample.get("brand", ""),
                            category=sample.get("category", ""),
                            price_per_unit=sample.get("price_per_unit", ""),
                            description=sample.get("description", "")))

@app.route("/batch/<puid>")
@login_required
def batch_units(puid):
    units = [enrich_product(p) for p in
             products_col.find({"puid": puid}).sort("suid", 1)]
    if not units:
        units = [enrich_product(p) for p in
                 products_col.find({"batch": puid}).sort("uid", 1)]

    owned_only = request.args.get("owned_only") == "1"
    if session.get("role") != "Manufacturer" or owned_only:
        units = [u for u in units if u.get("owner") == session.get("username")]
        
    if session.get("role") == "Customer":
        units = [u for u in units if u.get("scans", 0) >= 1]

    if not units:
        flash("Product not found or not owned by you.", "danger")
        return redirect(url_for("dashboard"))

    owner_names = list({u["owner"] for u in units})
    owner_roles = {u["username"]: u["role"]
                   for u in users_col.find({"username": {"$in": owner_names}},
                                           {"username": 1, "role": 1})}

    sample = units[0]
    
    match_query = {"name": sample["name"], "category": sample["category"]}
    if owned_only:
        match_query["owner"] = session.get("username")
        
    all_batches = list(products_col.aggregate([
        {"$match": match_query},
        {"$group": {"_id": "$batch",
                    "puid":       {"$first": "$puid"},
                    "batch":      {"$first": "$batch"},
                    "mfg_date":   {"$first": "$mfg_date"},
                    "exp_date":   {"$first": "$exp_date"},
                    "unit_count": {"$sum": 1}}},
        {"$sort": {"_id": 1}}
    ]))

    return render_template("batch_units.html", units=units, puid=puid,
                           owner_roles=owner_roles, all_batches=all_batches,
                           current_batch=sample.get("batch", ""))

@app.route("/api/product/edit_blueprint/<bp_id>", methods=["POST"])
@login_required
@role_required("Manufacturer")
def api_product_edit_blueprint(bp_id):
    username = session["username"]
    
    bp = blueprints_col.find_one({"_id": bp_id, "manufacturer": username})
    if not bp:
        return jsonify({"ok": False, "error": "Blueprint not found or access denied"}), 404

    old_name = bp.get("name")
    old_brand = bp.get("brand")
    old_category = bp.get("category")

    name = request.form.get("name", "").strip()
    brand = request.form.get("brand", "").strip()
    category = request.form.get("category", "").strip()
    price = request.form.get("price_per_unit", "").strip()
    desc = request.form.get("description", "").strip()
    
    sl_y = request.form.get("shelf_life_y", "").strip()
    sl_m = request.form.get("shelf_life_m", "").strip()
    sl_d = request.form.get("shelf_life_d", "").strip()
    total_days = 0
    has_sl = False
    if sl_y.isdigit():
        total_days += int(sl_y) * 365
        has_sl = True
    if sl_m.isdigit():
        total_days += int(sl_m) * 30
        has_sl = True
    if sl_d.isdigit():
        total_days += int(sl_d)
        has_sl = True
    shelf_life = str(total_days) if has_sl else "N/A"

    if not all([name, brand, category, price]):
        return jsonify({"ok": False, "error": "Missing required fields"}), 400

    update_fields = {
        "name": name,
        "brand": brand,
        "category": category,
        "price_per_unit": price,
        "description": desc,
        "shelf_life_days": shelf_life
    }

    file = request.files.get("image")
    if file and file.filename and allowed_file(file.filename):
        image_filename = secure_filename(file.filename)
        file.save(os.path.join(app.root_path, "static", "product_images", image_filename))
        update_fields["image"] = image_filename

    # Update blueprint
    blueprints_col.update_one({"_id": bp_id}, {"$set": update_fields})

    # Retroactively update all existing products that were manufactured from this blueprint
    products_col.update_many(
        {
            "name": old_name, 
            "brand": old_brand, 
            "category": old_category, 
            "manufacturer": username
        },
        {"$set": update_fields}
    )

    return jsonify({"ok": True})

@app.route("/product/<suid>")
@login_required
def product_details(suid):
    product = products_col.find_one({"suid": suid})
    if not product:
        product = products_col.find_one({"uid": suid})
    if not product:
        flash("Product not found.", "danger")
        return redirect(url_for("dashboard"))
    txns = list(transactions_col.find({"suid": suid}).sort("timestamp", 1))
    if not txns:
        txns = list(transactions_col.find({"uid": suid}).sort("timestamp", 1))

    # ── Authorization Check ──────────────────────────────────
    username = session.get("username")
    is_involved = False
    if product.get("manufacturer") == username or product.get("owner") == username:
        is_involved = True
    else:
        for txn in txns:
            if txn.get("from_user") == username or txn.get("to_user") == username:
                is_involved = True
                break

    if not is_involved:
        flash("You are not authorized to view this product.", "danger")
        return redirect(url_for("dashboard"))
    puid        = product.get("puid", product.get("batch", ""))
    batch_count = products_col.count_documents({"puid": puid}) if puid else 0

    all_batches = list(products_col.aggregate([
        {"$match": {"name": product["name"], "category": product["category"]}},
        {"$group": {"_id": "$batch",
                    "puid":       {"$first": "$puid"},
                    "batch":      {"$first": "$batch"},
                    "mfg_date":   {"$first": "$mfg_date"},
                    "exp_date":   {"$first": "$exp_date"},
                    "unit_count": {"$sum": 1}}},
        {"$sort": {"_id": 1}}
    ]))

    return render_template("product_details.html",
                           product=enrich_product(product),
                           txns=txns,
                           batch_count=batch_count,
                           all_batches=all_batches)

# ── Recall Batch ──────────────────────────────────────────
@app.route("/recall/<puid>", methods=["GET", "POST"])
@app.route("/recall/<puid>", methods=["GET"])
@login_required
@role_required("Manufacturer")
def recall_batch(puid):
    sample = products_col.find_one({"puid": puid, "manufacturer": session["username"]})
    if not sample:
        flash("Batch not found or access denied.", "danger")
        return redirect(url_for("dashboard"))

    unit_count = products_col.count_documents({"puid": puid, "manufacturer": session["username"], "status": {"$ne": "recalled"}})

    return render_template("recall_confirm.html",
                           product=enrich_product(sample),
                           unit_count=unit_count,
                           puid=puid)

@app.route("/api/recall/prepare", methods=["POST"])
@login_required
@role_required("Manufacturer")
def api_recall_prepare():
    data = request.get_json()
    puid = data.get("puid", "").strip()
    username = session["username"]
    
    user_doc = users_col.find_one({"username": username})
    if not user_doc or not user_doc.get("wallet"):
        return jsonify({"ok": False, "error": "Connect a MetaMask wallet to recall products."}), 400
    wallet = user_doc["wallet"]

    units = list(products_col.find({"puid": puid, "manufacturer": username, "status": {"$ne": "recalled"}}))
    if not units:
        return jsonify({"ok": False, "error": "No valid units found to recall in this batch."}), 400

    now = int(time.time())
    prepared_blocks = []
    
    suids_to_process = [u.get("suid", u.get("uid", "")) for u in units]
    suid_blocks = {}
    if suids_to_process:
        blocks_cursor = blocks_col.find({"suid": {"$in": suids_to_process}})
        for b in blocks_cursor:
            suid = b["suid"]
            if suid not in suid_blocks:
                suid_blocks[suid] = []
            suid_blocks[suid].append(b)
        for suid in suid_blocks:
            suid_blocks[suid].sort(key=lambda x: x["index"])
    
    for unit in units:
        suid = unit.get("suid", unit.get("uid", ""))
        unit_history = suid_blocks.get(suid, [])
        previous = unit_history[-1] if unit_history else None
        count = len(unit_history)
        
        block = {
            "block_id":      "BC-" + str(uuid.uuid4()).replace("-", "")[:12].upper(),
            "index":         count + 1,
            "timestamp":     now,
            "puid":          puid,
            "suid":          suid,
            "action":        "RECALLED",
            "from_user":     username,
            "to_user":       "",
            "previous_hash": previous["block_hash"] if previous else "GENESIS",
            "token_id":      suid_to_token_id(suid),
            "to_wallet":     wallet
        }
        block["block_hash"] = calculate_block_hash(block)
        block["signature"]  = sign_block_hash(block["block_hash"])
        prepared_blocks.append(block)

    return jsonify({"ok": True, "blocks": prepared_blocks})

@app.route("/api/recall/confirm", methods=["POST"])
@login_required
@role_required("Manufacturer")
def api_recall_confirm():
    username = session["username"]
    data     = request.get_json()
    blocks   = data.get("blocks", [])
    tx_hash  = data.get("tx_hash", "")

    if not blocks or not tx_hash:
        return jsonify({"ok": False, "error": "Invalid confirmation data."}), 400

    recalled_count = 0
    puid = blocks[0]["puid"] if blocks else ""
    
    blocks_to_insert = []
    transactions_to_insert = []
    product_updates = []

    for block in blocks:
        block["uid"]         = block["suid"]
        block["ethereum_tx"] = tx_hash
        
        blocks_to_insert.append(block)
        
        product_updates.append(
            UpdateOne(
                {"suid": block["suid"]},
                {"$set": {"status": "recalled"}}
            )
        )
        
        transactions_to_insert.append({
            "suid":       block["suid"],
            "uid":        block["suid"],
            "puid":       block["puid"],
            "from_user":  block["from_user"],
            "to_user":    "",
            "quantity":   1,
            "timestamp":  block["timestamp"],
            "action":     "RECALLED",
            "block_id":   block["block_id"],
            "block_hash": block["block_hash"],
            "ethereum_tx": tx_hash,
        })
        recalled_count += 1
        
    if blocks_to_insert:
        blocks_col.insert_many(blocks_to_insert)
    if product_updates:
        products_col.bulk_write(product_updates)
    if transactions_to_insert:
        transactions_col.insert_many(transactions_to_insert)
        
    flash(f"Batch recalled: {recalled_count} unit(s) marked as recalled and logged on the blockchain ledger.", "warning")
    return jsonify({"ok": True, "redirect": url_for("batch_units", puid=puid)})


# ── Transfer ──────────────────────────────────────────────
@app.route("/transfer", methods=["GET"])
@login_required
@role_required("Manufacturer", "Distributor", "Retailer")
def transfer_product():
    role     = session["role"]
    username = session["username"]
    active_cat = request.args.get("category", "")
    cat_filter = {"category": active_cat} if active_cat else {}

    cat_counts = {c["_id"]: c["count"] for c in products_col.aggregate([
        {"$match": {"owner": username}},
        {"$group": {"_id": "$category", "count": {"$sum": 1}}}
    ])}

    # Flexible multi-hop supply chain: fetch users for all allowed next roles
    next_roles = SUPPLY_CHAIN_NEXT.get(role, [])
    next_role_users_by_role = {}
    for nr in next_roles:
        next_role_users_by_role[nr] = list(users_col.find(
            {"role": nr}, {"_id": 0, "username": 1, "fullname": 1, "company": 1}
        ))

    pipeline = [
        {"$match": {"owner": username, **cat_filter}},
        {"$group": {
            "_id":            "$puid",
            "puid":           {"$first": "$puid"},
            "name":           {"$first": "$name"},
            "brand":          {"$first": "$brand"},
            "category":       {"$first": "$category"},
            "batch":          {"$first": "$batch"},
            "image":          {"$first": "$image"},
            "price_per_unit": {"$first": "$price_per_unit"},
            "available":      {"$sum": 1},
        }},
        {"$sort": {"name": 1, "batch": 1}}
    ]
    my_products = list(products_col.aggregate(pipeline))
    for p in my_products:
        enrich_product(p)

    return render_template("transfer_product.html",
                           products=my_products,
                           next_roles=next_roles,
                           next_role_users_by_role=next_role_users_by_role,
                           categories=CATEGORIES,
                           active_cat=active_cat,
                           cat_counts=cat_counts,
                           authchain_contract_address=AUTHCHAIN_CONTRACT_ADDRESS)

@app.route("/api/transfer/prepare", methods=["POST"])
@login_required
@role_required("Manufacturer", "Distributor", "Retailer")
def api_transfer_prepare():
    data    = request.get_json()
    to_user = data.get("to_user", "").strip()
    to_role = data.get("to_role", "").strip()
    items   = data.get("items", [])

    username           = session["username"]
    role               = session["role"]
    allowed_next_roles = SUPPLY_CHAIN_NEXT.get(role, [])

    if to_role not in allowed_next_roles:
        return jsonify({"ok": False, "error": f"Cannot transfer to {to_role} from {role}."}), 400

    next_user_doc = users_col.find_one({"username": to_user, "role": to_role})
    if not next_user_doc:
        return jsonify({"ok": False, "error": f"Invalid recipient. {to_user} is not a registered {to_role}."}), 400

    next_wallet = next_user_doc.get("wallet")
    if not next_wallet:
        return jsonify({"ok": False, "error": f"Recipient {to_user} has no connected wallet. They must connect MetaMask to receive NFTs."}), 400

    next_user = next_user_doc["username"]
    now = int(time.time())

    prepared_blocks = []
    
    suids_to_process = []
    units_to_process = []
    for item in items:
        puid = item.get("puid")
        try:
            qty = int(item.get("qty", 0))
        except (ValueError, TypeError):
            qty = 0

        if qty < 1:
            continue

        units = list(products_col.find({"puid": puid, "owner": username}).sort("_id", -1).limit(qty))
        units_to_process.extend(units)
        suids_to_process.extend([u.get("suid", u.get("uid", "")) for u in units])

    # Pre-fetch all blocks for these SUIDs to avoid N database queries in the loop
    suid_blocks = {}
    if suids_to_process:
        blocks_cursor = blocks_col.find({"suid": {"$in": suids_to_process}})
        for b in blocks_cursor:
            suid = b["suid"]
            if suid not in suid_blocks:
                suid_blocks[suid] = []
            suid_blocks[suid].append(b)
        for suid in suid_blocks:
            suid_blocks[suid].sort(key=lambda x: x["index"])

    for unit in units_to_process:
        suid     = unit.get("suid", unit.get("uid", ""))
        unit_history = suid_blocks.get(suid, [])
        previous = unit_history[-1] if unit_history else None
        count = len(unit_history)
        
        block    = {
            "block_id":      "BC-" + str(uuid.uuid4()).replace("-", "")[:12].upper(),
            "index":         count + 1,
            "timestamp":     now,
            "puid":          unit.get("puid"),
            "suid":          suid,
            "action":        "TRANSFERRED",
            "from_user":     username,
            "to_user":       next_user,
            "previous_hash": previous["block_hash"] if previous else "GENESIS",
        }
        block["block_hash"] = calculate_block_hash(block)
        block["signature"]  = sign_block_hash(block["block_hash"])
        block["token_id"]   = suid_to_token_id(suid)
        block["to_wallet"]  = next_wallet
        prepared_blocks.append(block)

    if not prepared_blocks:
        return jsonify({"ok": False, "error": "No units selected."}), 400

    return jsonify({"ok": True, "blocks": prepared_blocks})


@app.route("/api/transfer/confirm", methods=["POST"])
@login_required
@role_required("Manufacturer", "Distributor", "Retailer")
def api_transfer_confirm():
    data    = request.get_json()
    blocks  = data.get("blocks", [])
    tx_hash = data.get("tx_hash", "")

    if not blocks or not tx_hash:
        return jsonify({"ok": False, "error": "Invalid confirmation data."}), 400

    if Web3 and WEB3_PROVIDER_URI:
        try:
            w3      = Web3(Web3.HTTPProvider(WEB3_PROVIDER_URI))
            receipt = None
            for _ in range(10):  # retry up to 10 times (30 seconds total)
                receipt = w3.eth.get_transaction_receipt(tx_hash)
                if receipt is not None:
                    break
                import time as _time
                _time.sleep(3)
            if not receipt or receipt.status != 1:
                return jsonify({"ok": False, "error": "Blockchain transaction failed or not yet confirmed. Please try again in a moment."}), 400
        except Exception as e:
            return jsonify({"ok": False, "error": f"Error verifying transaction: {str(e)}"}), 400

    username    = session["username"]
    transferred = 0
    already_done = 0
    
    blocks_to_insert = []
    transactions_to_insert = []
    product_updates = []

    for block in blocks:
        block["uid"]         = block["suid"]
        block["ethereum_tx"] = tx_hash

        # ── Idempotency: skip blocks already recorded (same block_id or same tx already processed) ──
        if blocks_col.find_one({"block_id": block["block_id"]}):
            already_done += 1
            continue
        # Also skip if this suid is already owned by the recipient (DB already updated)
        product_doc = products_col.find_one({"suid": block["suid"]})
        if product_doc and product_doc.get("owner") == block["to_user"]:
            already_done += 1
            continue
        
        blocks_to_insert.append(block)

        product_updates.append(
            UpdateOne(
                {"suid": block["suid"], "owner": username},
                {"$set": {"owner": block["to_user"]}}
            )
        )

        transactions_to_insert.append({
            "suid":       block["suid"],
            "uid":        block["suid"],
            "puid":       block["puid"],
            "from_user":  block["from_user"],
            "to_user":    block["to_user"],
            "quantity":   1,
            "timestamp":  block["timestamp"],
            "action":     "TRANSFERRED",
            "block_id":   block["block_id"],
            "block_hash": block["block_hash"],
            "ethereum_tx": tx_hash,
        })
        transferred += 1

    if blocks_to_insert:
        blocks_col.insert_many(blocks_to_insert)
    if product_updates:
        products_col.bulk_write(product_updates)
    if transactions_to_insert:
        transactions_col.insert_many(transactions_to_insert)

    if transferred == 0 and already_done > 0:
        return jsonify({"ok": True, "message": f"Transfer already recorded. {already_done} unit(s) were previously processed."})

    return jsonify({"ok": True, "message": f"{transferred} unit(s) transferred successfully!" + (f" ({already_done} already done.)" if already_done else "")})


@app.route("/api/transfer/recover", methods=["POST"])
@login_required
@role_required("Manufacturer", "Distributor", "Retailer")
def api_transfer_recover():
    """Recover a stuck transfer: re-apply DB updates for a confirmed tx_hash.
    Call this when the blockchain tx succeeded but the page refreshed before /confirm was called."""
    data    = request.get_json()
    tx_hash = data.get("tx_hash", "").strip()
    blocks  = data.get("blocks", [])

    if not tx_hash or not blocks:
        return jsonify({"ok": False, "error": "tx_hash and blocks are required."}), 400

    if Web3 and WEB3_PROVIDER_URI:
        try:
            w3 = Web3(Web3.HTTPProvider(WEB3_PROVIDER_URI))
            receipt = w3.eth.get_transaction_receipt(tx_hash)
            if not receipt or receipt.status != 1:
                return jsonify({"ok": False, "error": "Transaction not confirmed on-chain yet or it failed."}), 400
        except Exception as e:
            return jsonify({"ok": False, "error": f"Could not verify tx: {str(e)}"}), 400

    # Re-use the confirm logic via internal call
    from flask import Request
    import json as _json
    with app.test_request_context(
        '/api/transfer/confirm',
        method='POST',
        data=_json.dumps({"blocks": blocks, "tx_hash": tx_hash}),
        content_type='application/json'
    ):
        pass  # Just piggyback on confirm endpoint below

    username = session["username"]
    transferred = 0
    already_done = 0
    blocks_to_insert = []
    transactions_to_insert = []
    product_updates = []

    for block in blocks:
        block["uid"]         = block.get("suid", block.get("uid", ""))
        block["ethereum_tx"] = tx_hash

        if blocks_col.find_one({"block_id": block["block_id"]}):
            already_done += 1
            continue
        product_doc = products_col.find_one({"suid": block["suid"]})
        if product_doc and product_doc.get("owner") == block["to_user"]:
            already_done += 1
            continue

        blocks_to_insert.append(block)
        product_updates.append(
            UpdateOne(
                {"suid": block["suid"]},
                {"$set": {"owner": block["to_user"]}}
            )
        )
        transactions_to_insert.append({
            "suid":        block["suid"],
            "uid":         block["suid"],
            "puid":        block["puid"],
            "from_user":   block["from_user"],
            "to_user":     block["to_user"],
            "quantity":    1,
            "timestamp":   block["timestamp"],
            "action":      "TRANSFERRED",
            "block_id":    block["block_id"],
            "block_hash":  block["block_hash"],
            "ethereum_tx": tx_hash,
        })
        transferred += 1

    if blocks_to_insert:
        blocks_col.insert_many(blocks_to_insert)
    if product_updates:
        products_col.bulk_write(product_updates)
    if transactions_to_insert:
        transactions_col.insert_many(transactions_to_insert)

    total = transferred + already_done
    return jsonify({"ok": True, "transferred": transferred, "already_done": already_done,
                    "message": f"Recovery complete. {transferred} unit(s) updated, {already_done} already done (total {total})."})


@app.route("/scan")
@login_required
@role_required("Customer")
def scan():
    return render_template("scan.html")

@app.route("/verify", methods=["GET", "POST"])
@login_required
@role_required("Customer")
def verify():
    puid = suid = None

    if request.method == "POST":
        uid_input  = request.form.get("uid_input", "").strip()
        puid_input = request.form.get("puid_input", "").strip().upper()
        suid_input = request.form.get("suid_input", "").strip().upper()

        if uid_input:
            if ":" in uid_input:
                puid, suid = verify_qr_data(uid_input)
                if not suid:
                    flash("Invalid or tampered QR code — blockchain verification failed.", "danger")
                    return redirect(url_for("scan"))
            else:
                suid = uid_input.upper()
        elif suid_input:
            suid = suid_input
            puid = puid_input if puid_input else None
        else:
            flash("Please enter a SUID to verify.", "warning")
            return redirect(url_for("scan"))
    else:
        suid = request.args.get("uid", "").upper()

    if not suid:
        return redirect(url_for("scan"))

    product = products_col.find_one({"$or": [{"suid": suid}, {"uid": suid}]})
    if not product:
        flash("Product not found.", "danger")
        return redirect(url_for("scan"))

    # ── Check 1: PUID mismatch → counterfeit ──────────────
    if puid and product.get("puid") and puid != product["puid"]:
        flash("QR code is invalid — Product ID mismatch. Possible counterfeit!", "danger")
        return render_template("verify.html",
                               product=enrich_product(product),
                               fail_heading="Possible Counterfeit",
                               fail_emoji="🚨",
                               fail_reason="Possible counterfeit: PUID mismatch — this unit does not belong to the scanned product.",
                               is_recalled=False, is_expired=False)

    # ── Check 2: Recalled ─────────────────────────────────
    if product.get("status") == "recalled":
        products_col.update_one({"_id": product["_id"]}, {"$inc": {"scans": 1}})
        return render_template("verify.html",
                               product=enrich_product(products_col.find_one({"_id": product["_id"]})),
                               fail_reason=None,
                               is_recalled=True,
                               is_expired=False)

    # ── Check 3: Expired ──────────────────────────────────
    is_expired = False
    try:
        exp_date_val = datetime.strptime(product["exp_date"], "%Y-%m-%d").date()
        if exp_date_val < date.today():
            is_expired = True
    except Exception:
        pass

    if is_expired:
        products_col.update_one({"_id": product["_id"]}, {"$inc": {"scans": 1}})
        return render_template("verify.html",
                               product=enrich_product(products_col.find_one({"_id": product["_id"]})),
                               fail_reason=None,
                               is_recalled=False,
                               is_expired=True)

    # ── Check 4: Blockchain chain integrity ───────────────
    if not validate_unit_chain(suid):
        flash("Blockchain ledger is missing or tampered. Cannot verify this product.", "danger")
        return render_template("verify.html",
                               product=enrich_product(product),
                               fail_heading="Ledger Tampered",
                               fail_emoji="⚠️",
                               fail_reason="Blockchain ledger validation failed for this unit.",
                               is_recalled=False, is_expired=False)

    # ── Check 5: Must be owned by Customer to show Genuine ─
    # If the product has not completed the full supply chain
    # (M → D → R → C) and reached a Customer, it is flagged as
    # counterfeit — this is exactly how fake products spread:
    # they are sold outside official channels, bypassing the chain.
    owner_doc = users_col.find_one({"username": product["owner"]})
    owner_role = owner_doc["role"] if owner_doc else "Unknown"

    if owner_role != "Customer":
        return render_template("verify.html",
                               product=enrich_product(product),
                               fail_heading="Supply Chain Incomplete",
                               fail_emoji="🛑",
                               fail_reason="This product has not completed the supply chain.",
                               is_recalled=False, is_expired=False)

    # ── Check 6: Duplicate scan ───────────────────────────
    if product.get("scans", 0) > 0:
        products_col.update_one({"_id": product["_id"]}, {"$inc": {"scans": 1}})
        return render_template("verify.html",
                               product=enrich_product(products_col.find_one({"_id": product["_id"]})),
                               fail_heading="Duplicate Product",
                               fail_emoji="⚠️",
                               fail_reason="This product has been scanned more than once, indicating it might be a duplicate or counterfeit.",
                               is_recalled=False, is_expired=False)

    # Owner is Customer — product has completed the full supply chain
    products_col.update_one({"_id": product["_id"]}, {"$inc": {"scans": 1}})
    product = enrich_product(products_col.find_one({"_id": product["_id"]}))
    return render_template("verify.html", product=product,
                           fail_reason=None, is_recalled=False, is_expired=False)

# ── Search ────────────────────────────────────────────────
@app.route("/search", methods=["GET", "POST"])
@login_required
@role_required("Manufacturer")
def search():
    product = None
    if request.method == "POST":
        raw = request.form["uid"].strip().upper()
        product = products_col.find_one({"suid": raw})
        if not product:
            product = products_col.find_one({"puid": raw})
        if not product:
            product = products_col.find_one({"uid": raw})
        if product:
            if product.get("manufacturer") != session.get("username"):
                product = None
                flash("Product not found or you are not authorized to view it.", "warning")
            else:
                product = enrich_product(product)
        else:
            flash("Product not found.", "warning")
    return render_template("search.html", product=product)

# ── Audit Ledger ──────────────────────────────────────────
@app.route("/ledger")
@login_required
@role_required("Manufacturer", "Distributor", "Retailer", "Customer")
def ledger_view():
    page     = int(request.args.get("page", 1))
    per_page = 50
    
    query = {"$or": [{"from_user": session.get("username")}, {"to_user": session.get("username")}]}
        
    total    = transactions_col.count_documents(query)
    txns     = list(transactions_col.find(query)
                    .sort("timestamp", -1)
                    .skip((page - 1) * per_page)
                    .limit(per_page))
    total_pages = max(1, -(-total // per_page))
    return render_template("ledger.html", txns=txns, page=page,
                           total_pages=total_pages, total=total)

# ── Profile ───────────────────────────────────────────────
@app.route("/profile")
@login_required
def profile():
    user       = users_col.find_one({"username": session["username"]})
    active_cat = request.args.get("category", "")
    cat_filter = {"category": active_cat} if active_cat else {}

    my_batches = []
    cat_counts = {}

    if session["role"] == "Manufacturer":
        match_q  = {"manufacturer": session["username"], **cat_filter}
        pipeline = [
            {"$match": match_q},
            {"$group": {
                "_id":         {"$ifNull": ["$puid", "$batch"]},
                "puid":        {"$first": {"$ifNull": ["$puid", "$batch"]}},
                "name":        {"$first": "$name"},
                "category":    {"$first": "$category"},
                "batch":       {"$first": "$batch"},
                "total_units": {"$sum": 1},
                "sample_suid": {"$first": {"$ifNull": ["$suid", "$uid"]}},
            }},
            {"$sort": {"batch": 1}}
        ]
        my_batches = list(products_col.aggregate(pipeline))
        cat_counts = {c["_id"]: c["count"] for c in products_col.aggregate([
            {"$match": {"manufacturer": session["username"]}},
            {"$group": {"_id": "$category", "count": {"$sum": 1}}}
        ])}

    return render_template("profile.html",
                           user=user,
                           my_batches=my_batches,
                           categories=CATEGORIES,
                           active_cat=active_cat,
                           cat_counts=cat_counts)

# ── Edit Profile ──────────────────────────────────────────
@app.route("/edit_profile", methods=["POST"])
@login_required
def edit_profile():
    users_col.update_one(
        {"username": session["username"]},
        {"$set": {
            "fullname": request.form.get("fullname", "").strip(),
            "email":    request.form.get("email",    "").strip(),
            "phone":    request.form.get("phone",    "").strip(),
            "company":  request.form.get("company",  "").strip(),
            "address":  request.form.get("address",  "").strip(),
        }}
    )
    session["fullname"] = request.form.get("fullname", "").strip()
    flash("Profile updated successfully.", "success")
    return redirect(url_for("profile"))

# ── Analytics (role-scoped — every role sees their own data) ──
@app.route("/analytics")
@login_required
def analytics():
    role     = session["role"]
    username = session["username"]

    stats          = {}
    categories     = []
    total_products = 0

    if role == "Manufacturer":
        total_products = products_col.count_documents({"manufacturer": username})
        stats = {
            "total_manufactured": total_products,
            "currently_owned":    products_col.count_documents({"manufacturer": username, "owner": username}),
            "total_transferred":  transactions_col.count_documents({"from_user": username, "action": "TRANSFERRED"}),
            "recalled":           products_col.count_documents({"manufacturer": username, "status": "recalled"}),
        }

    elif role in ["Distributor", "Retailer"]:
        total_products = products_col.count_documents({"owner": username})
        stats = {
            "received":        transactions_col.count_documents({"to_user": username, "action": "TRANSFERRED"}),
            "currently_owned": total_products,
            "forwarded":       transactions_col.count_documents({"from_user": username, "action": "TRANSFERRED"}),
        }

    elif role == "Customer":
        total_products = products_col.count_documents({"owner": username})
        total_scans    = sum(p.get("scans", 0) for p in products_col.find({"owner": username}))
        stats = {
            "owned":       total_products,
            "total_scans": total_scans,
        }

    # Calculate category distribution for the user
    match_q = {"manufacturer": username} if role == "Manufacturer" else {"owner": username}
    pipeline = [
        {"$match": match_q},
        {"$group": {"_id": "$category", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    categories_data = list(products_col.aggregate(pipeline))

    return render_template("analytics.html", role=session.get("role"),
                           stats=stats,
                           categories=categories_data,
                           total_products=total_products)

# ── Bulk Create Products (CSV) ───────────────────────────
@app.route("/bulk_create_products")
@login_required
@role_required("Manufacturer")
def bulk_create_products():
    return render_template("bulk_create.html")

@app.route("/blueprints")
@login_required
@role_required("Manufacturer")
def blueprints():
    cat_filter = category_filter_query()
    active_cat = request.args.get("category", "")

    cat_counts = {c["_id"]: c["count"] for c in blueprints_col.aggregate([
        {"$match": {"manufacturer": session.get("username")}},
        {"$group": {"_id": "$category", "count": {"$sum": 1}}}
    ])}

    match_query = {"manufacturer": session.get("username")}
    match_query.update(cat_filter)
    
    search_query = request.args.get("search", "").strip()
    if search_query:
        match_query["$or"] = [
            {"name": {"$regex": search_query, "$options": "i"}},
            {"brand": {"$regex": search_query, "$options": "i"}}
        ]

    bps = list(blueprints_col.find(match_query).sort("timestamp", -1))
    return render_template("blueprints.html", blueprints=bps,
                           categories=get_dynamic_categories(),
                           active_cat=active_cat,
                           cat_counts=cat_counts)

@app.route("/api/product/delete_blueprint/<bp_id>", methods=["POST"])
@login_required
@role_required("Manufacturer")
def delete_blueprint(bp_id):
    blueprints_col.delete_one({"_id": bp_id, "manufacturer": session["username"]})
    return jsonify({"ok": True})

@app.route("/api/product/blueprint_create", methods=["POST"])
@login_required
@role_required("Manufacturer")
def api_product_blueprint_create():
    username = session["username"]
    
    name = request.form.get("name", "").strip()
    brand = request.form.get("brand", "").strip()
    category = request.form.get("category", "").strip()
    price = request.form.get("price_per_unit", "").strip()
    desc = request.form.get("description", "").strip()
    
    sl_na = request.form.get("shelf_life_na")
    sl_y = request.form.get("shelf_life_y", "").strip()
    sl_m = request.form.get("shelf_life_m", "").strip()
    sl_d = request.form.get("shelf_life_d", "").strip()
    
    if sl_na:
        shelf_life = "N/A"
    else:
        total_days = 0
        has_sl = False
        if sl_y.isdigit():
            total_days += int(sl_y) * 365
            has_sl = True
        if sl_m.isdigit():
            total_days += int(sl_m) * 30
            has_sl = True
        if sl_d.isdigit():
            total_days += int(sl_d)
            has_sl = True
        if not has_sl:
            return jsonify({"ok": False, "error": "Shelf life is required. Provide duration or select N/A."}), 400
        shelf_life = str(total_days)

    if not all([name, brand, category, price, desc]):
        return jsonify({"ok": False, "error": "Missing required fields"}), 400

    image_filename = ""
    file = request.files.get("image")
    if file and file.filename and allowed_file(file.filename):
        image_filename = secure_filename(file.filename)
        file.save(os.path.join(app.root_path, "static", "product_images", image_filename))
    else:
        return jsonify({"ok": False, "error": "Valid product image is required"}), 400

    bp_id = "BP-" + str(uuid.uuid4()).replace("-", "")[:8].upper()
    now = int(time.time())

    blueprints_col.insert_one({
        "_id": bp_id,
        "manufacturer": username,
        "name": name,
        "brand": brand,
        "category": category,
        "price_per_unit": price,
        "description": desc,
        "shelf_life_days": shelf_life,
        "image": image_filename,
        "timestamp": now
    })

    return jsonify({"ok": True, "bp_id": bp_id})

@app.route("/api/product/bulk_blueprints", methods=["POST"])
@login_required
@role_required("Manufacturer")
def api_product_bulk_blueprints():
    username = session["username"]
    data = request.get_json() or {}
    products = data.get("products", [])
    
    if not products:
        return jsonify({"ok": False, "error": "No blueprints provided."}), 400

    now = int(time.time())
    inserted = 0
    
    for prod in products:
        name = prod.get("name", "").strip()
        brand = prod.get("brand", "").strip()
        category = prod.get("category", "").strip()
        price = str(prod.get("price_per_unit", "")).strip()
        shelf_life = str(prod.get("shelf_life", "")).strip()
        desc = prod.get("description", "").strip()

        if not all([name, brand, category, price]):
            continue

        image_filename = _find_image(name)
        bp_id = "BP-" + str(uuid.uuid4()).replace("-", "")[:8].upper()

        blueprints_col.insert_one({
            "_id": bp_id,
            "manufacturer": username,
            "name": name,
            "brand": brand,
            "category": category,
            "price_per_unit": price,
            "shelf_life_days": shelf_life,
            "description": desc,
            "image": image_filename,
            "timestamp": now
        })
        inserted += 1

    return jsonify({"ok": True, "message": f"{inserted} blueprints saved successfully!"})

if __name__ == "__main__":
    os.makedirs(os.path.join(app.root_path, "static", "qrcodes"), exist_ok=True)
    os.makedirs(os.path.join(app.root_path, "static", "product_images"), exist_ok=True)
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
