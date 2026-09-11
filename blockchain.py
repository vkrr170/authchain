import os
import hashlib
from eth_account.messages import encode_defunct
try:
    from web3 import Web3
except ImportError:
    Web3 = None

WEB3_PROVIDER_URI = os.environ.get("WEB3_PROVIDER_URI", "").strip()
AUTHCHAIN_CONTRACT_ADDRESS = os.environ.get("AUTHCHAIN_CONTRACT_ADDRESS", "").strip()
ETH_PRIVATE_KEY = os.environ.get("ETH_PRIVATE_KEY", "").strip()

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

_local_w3 = None

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

def sign_block_hash(block_hash):
    global _local_w3
    if not ETH_PRIVATE_KEY or not encode_defunct:
        return "0x"
    msg = encode_defunct(hexstr=block_hash)
    if _local_w3 is None:
        _local_w3 = Web3()
    signed = _local_w3.eth.account.sign_message(msg, private_key=ETH_PRIVATE_KEY)
    return "0x" + signed.signature.hex()

def verify_server_signature(block_hash, signature):
    if not ETH_PRIVATE_KEY or not encode_defunct:
        return True # Fallback if web3 is disabled
    try:
        msg = encode_defunct(hexstr=block_hash)
        w3 = Web3()
        server_address = w3.eth.account.from_key(ETH_PRIVATE_KEY).address
        recovered_address = w3.eth.account.recover_message(msg, signature=signature)
        return recovered_address.lower() == server_address.lower()
    except Exception:
        return False
