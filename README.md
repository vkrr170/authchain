# 🔗 AuthChain — Blockchain Supply Chain Authenticity

> **Every product has a story. AuthChain puts it on the blockchain.**

**AuthChain** is a full-stack web application that tracks physical products through the entire supply chain — from manufacturer to consumer — using Ethereum NFTs as tamper-proof ownership records. By bridging the physical and digital worlds via dynamic QR codes, consumers get a live, blockchain-verified answer: *is this genuine?*

Built with **Flask**, **MongoDB**, **Ethereum (Sepolia)**, and a custom **ERC-721 smart contract**.

🔗 **Live**: [authchain.onrender.com](https://authchain.onrender.com)  
📦 **GitHub**: [github.com/vkrr170/authchain](https://github.com/vkrr170/authchain)

---

## 🎯 Problem & Solution

### The Problem
Counterfeit products are a [$4.2 trillion global crisis](https://www.oecd.org/en/topics/sub-issues/illicit-trade/trade-in-counterfeit-products.html). Fake medicines, electronics, and cosmetics flood supply chains every year because the chain of custody relies on paper records and centralized databases. These traditional tracking systems can be trivially altered or hacked, leaving buyers unsure if the physical product in their hands is genuine.

### The Solution
AuthChain gives every physical product unit a **blockchain identity**. Each unit is minted as an ERC-721 NFT at the point of manufacture. As it moves through the supply chain (Manufacturer → Distributor → Retailer → Customer), ownership transfers are recorded on-chain — permanently and publicly. A customer scanning a QR code gets an instant, independent verification backed by the Ethereum blockchain — not by the seller's word.

---

## 🏗️ Architecture & Technology Stack

| Layer | Technology |
|---|---|
| **Backend Framework** | Flask (Python 3.9+) with Jinja2 templating |
| **Database** | MongoDB Atlas — users, products, audit log, blueprints |
| **Blockchain Integration** | Ethereum Sepolia Testnet via Web3.py + ethers.js |
| **Smart Contract** | Solidity 0.8.20 — `AuthChainLedger` extending OpenZeppelin ERC-721 |
| **Authentication** | Google OAuth 2.0 (Authlib) + MetaMask ECDSA wallet signatures |
| **Cryptography** | BLAKE2b hash chain for tamper-evident off-chain audit logs |
| **Frontend** | HTML5, Vanilla CSS (glassmorphism dark mode), Vanilla JavaScript |
| **QR Codes** | `qrcode` + Pillow — auto-generated per product unit |
| **Deployment** | Render (Gunicorn, 2 workers) with `render.yaml` auto-deploy |

---

## ⚡ Key Features

- **Role-Based Supply Chain**: Four distinct roles — Manufacturer, Distributor, Retailer, Customer — each with strictly enforced permissions and a dedicated dashboard.
- **ERC-721 NFT per Product Unit**: Every physical unit is a unique NFT. Ownership on the blockchain is the single source of truth.
- **Batch Minting & Transfers**: Mint or transfer 50+ units in a single blockchain transaction for extreme gas cost efficiency.
- **Bulk CSV Onboarding**: Manufacturers upload product catalogues via CSV — the system previews and creates blueprints instantly.
- **BLAKE2b Audit Hash Chain**: Off-chain records are cryptographically linked — any tampering breaks the chain and is immediately detectable.
- **5-Point QR Verification**: Customers scan and get a verdict in seconds — Genuine, Incomplete, Counterfeit, or Not Found.
- **Product Recall**: Manufacturers can recall entire batches with a permanent on-chain record.
- **ECDSA Server Signatures**: Every blockchain transaction requires a valid server signature — no one can mint or transfer without authorization.

---

## 🔍 The Verification Model

When a customer scans a QR code (which embeds a Product ID / PUID and Serial ID / SUID), AuthChain runs a **5-point check** against both the blockchain and the off-chain database:

| Check | What It Validates | Failure Meaning |
|---|---|---|
| **1. Serial & Product ID** | SUID exists and matches the PUID on record | **Valid SUID / Mismatched PUID**: Label swapped (Counterfeit)<br>**Invalid SUID**: Fabricated product (Not Found) |
| **2. Recall Status** | Batch has not been recalled by the manufacturer | Recalled product in circulation |
| **3. Expiry Date** | Product is within its declared shelf life | Expired product |
| **4. Blockchain Ledger** | On-chain NFT record matches off-chain data | Data tampering detected |
| **5. Supply Chain Flow** | Product traveled the full M → D → R → C path | Product may be diverted or stolen |

> **Security First:** Nothing is fabricated. If a check cannot be verified, it fails — it is never assumed to pass.

---

## 🛡️ How Blockchain Verification Works (Technical)

```text
Client (Scanner)                Backend (Flask)               Blockchain (Sepolia)
  │                                │                              │
  ├─── Scans QR (SUID/PUID) ──────►│                              │
  │                                ├─── Fetch Off-chain Data      │
  │                                │                              │
  │                                ├─── Verify Hash Chain         │
  │                                │                              │
  │                                ├─── Query on-chain events ───►│
  │                                │◄── Return tx history ────────┤
  │                                │                              │
  │◄── 5-Point Verification Result─┤                              │
```

---

## 🚀 Execution Flow

AuthChain follows a multi-role lifecycle from product creation to consumer verification. 

For a comprehensive, step-by-step visual walkthrough of the system in action — including screenshots of the dashboards, MetaMask transactions, bulk CSV uploads, and the 5-point QR verification results — please refer to the **[Execution Flow Document](EXECUTION_FLOW.md)**.

---

## 📜 Smart Contract

The `AuthChainLedger` contract (`contracts/AuthChainLedger.sol`) extends OpenZeppelin ERC-721 with supply chain event recording:

```solidity
// Every mint and transfer requires a server-signed ECDSA signature
function mintProductBatch(address to, uint256[] calldata tokenIds, BlockData[] calldata dataArray) external
function transferProductBatch(address to, uint256[] calldata tokenIds, BlockData[] calldata dataArray) external

// Read any supply chain event by block ID
function getEvent(string calldata blockId) external view returns (ProductEvent memory)
```

**Security guarantees built into the contract:**
- Every state-changing call verifies a server ECDSA signature — no one can mint or transfer without the server's authorization.
- Each block ID can only be recorded once — replay attacks are impossible.
- Full ERC-721 compliance — tokens are visible on any block explorer.

---

## 💻 Getting Started (Local Development)

### Prerequisites
- **Python 3.9+**
- **Node.js & npm**
- **MongoDB Atlas** cluster URI (or local MongoDB)
- **MetaMask** configured for Sepolia Testnet
- **Google Cloud** OAuth 2.0 credentials
- **Infura or Alchemy** Sepolia RPC endpoint

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/vkrr170/authchain.git
   cd authchain
   ```

2. **Set up the Python environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Configure environment variables** (`.env`):
   ```env
   SECRET_KEY=your_flask_secret_key
   MONGO_URI=mongodb+srv://user:pass@cluster.mongodb.net/
   WEB3_PROVIDER_URI=https://sepolia.infura.io/v3/YOUR_KEY
   AUTHCHAIN_CONTRACT_ADDRESS=0xYourDeployedContract
   ETH_PRIVATE_KEY=0xYourServerWalletPrivateKey
   ETH_CHAIN_ID=11155111
   GOOGLE_CLIENT_ID=your_google_client_id.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=your_google_client_secret
   ```

4. **Deploy the smart contract (if needed):**
   ```bash
   npm install
   node scripts/deploy_contract.js
   ```

5. **Run the application:**
   ```bash
   python app.py
   ```

---

## 📁 Project Structure

```text
authchain/
├── app.py                      # Flask application — 45+ routes, all business logic
├── contracts/
│   └── AuthChainLedger.sol     # ERC-721 smart contract
├── scripts/
│   └── deploy_contract.js      # Contract deployment script
├── templates/                  # Jinja2 HTML templates
│   ├── dashboard.html          # Role-specific dashboard
│   ├── blueprints.html         # Blueprint management + CSV upload
│   ├── transfer_product.html   # Batch transfer interface
│   ├── verify.html             # 5-point verification results
│   └── ...                     
├── static/
│   ├── product_images/         # Product imagery
│   └── qrcodes/                # Auto-generated QR codes (ephemeral)
├── docs/execution_flow/        # 47 screenshots covering the full workflow
├── seed_products.py            # Seed product catalogue for testing
└── requirements.txt            # Python dependencies
```

---

## 🔑 Core Design Decisions

1. **Hybrid on-chain / off-chain architecture** — MongoDB handles fast application reads; Ethereum handles permanent ownership proof.
2. **Server-signed blockchain transactions** — The backend signs every transaction with ECDSA before the client submits it to MetaMask. Unauthorized minting is cryptographically impossible.
3. **BLAKE2b hash chain in MongoDB** — Off-chain audit records are chained like a mini-blockchain. Any insertion or modification breaks the chain instantly.
4. **Strict role-based transfers** — The flow (`M → D → R → C`) is enforced in code, not just UI. Intermediary spoofing is impossible.
5. **Verification cross-checks both layers** — The 5-point check queries the blockchain and MongoDB independently and flags any discrepancy.

---

## 👥 Target Users

- **Manufacturers** — Onboard product catalogues, mint NFTs, and initiate the chain of custody.
- **Distributors & Retailers** — Receive and forward products with blockchain-verified transfers.
- **Consumers** — Scan QR codes on any purchased product to verify authenticity instantly.
- **Compliance Teams** — Access the immutable audit log for regulatory investigations.
