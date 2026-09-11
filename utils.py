import uuid
import json
import hashlib
from difflib import SequenceMatcher

def _norm(s):
    return s.lower().replace("\u2019", "").replace("'", "").replace("-", " ").strip()

def _sim(a, b):
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()

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
