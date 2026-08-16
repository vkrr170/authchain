# AuthChain Execution Flow

This document provides a comprehensive, step-by-step visual walkthrough of the AuthChain system in action. It covers the entire lifecycle of a product from registration to consumer verification.

---

## Phase 0: Landing & Authentication

### 1. Landing Page
The application features a modern, responsive landing page with support for both light and dark modes. It highlights the core features: Tamper-Proof Records, QR Code Verification, and Multi-Role Access.

![Landing Page 1](docs/execution_flow/1.png)
![Landing Page 2](docs/execution_flow/2.png)

### 2. Registration & OAuth
Users can register using traditional email/password or use the seamless Google OAuth integration for quick access.

![Registration](docs/execution_flow/3.png)
![Google OAuth](docs/execution_flow/4.png)

### 3. Profile Completion
After signing in with Google, users must complete their profile by selecting their **Role** (Manufacturer, Distributor, Retailer, or Customer). This role dictates their permissions throughout the system.

![Profile Setup](docs/execution_flow/5.png)

### 4. Manufacturer Dashboard
Upon completing setup, the Manufacturer is greeted by the dashboard showing system statistics and their position in the Supply Chain Flow.

![Manufacturer Dashboard](docs/execution_flow/6.png)

---

## Phase 1: MetaMask Integration

To interact with the blockchain, users must connect their MetaMask wallet. Each role uses a dedicated wallet address to sign transactions.

![Connect MetaMask](docs/execution_flow/7.png)
![MetaMask Popup](docs/execution_flow/8.png)
![Wallet Selection](docs/execution_flow/9.png)
![Edit Accounts](docs/execution_flow/10.png)
![Connecting Wallet](docs/execution_flow/11.png)
![Wallet Connected](docs/execution_flow/12.png)

---

## Phase 2: Blueprints (Product Onboarding)

Manufacturers can define product "Blueprints". While they can be created manually, the system supports bulk onboarding via CSV uploads.

### 1. Blueprints Page
![Blueprints Empty](docs/execution_flow/13.png)
![Create Blueprint Modal](docs/execution_flow/14.png)

### 2. Bulk CSV Upload
Manufacturers can upload a CSV containing product details (Name, Brand, Category, Price, Shelf Life). The system previews the data before committing.

![Upload CSV Highlight](docs/execution_flow/15.png)
![Upload Flow](docs/execution_flow/16.png)
![CSV Preview](docs/execution_flow/17.png)

### 3. Saved Blueprints
Once uploaded, the blueprints are saved to the library, ready for manufacturing.

![Blueprints Library](docs/execution_flow/18.png)

---

## Phase 3: Manufacturing (Minting NFTs)

The Manufacturer initiates the creation of physical units by minting them as ERC-721 tokens on the Sepolia testnet.

### 1. Setting Quantity
The manufacturer selects a blueprint (e.g., Smart LED Bulb 9W) and specifies the batch quantity (50 units).

![Set Quantity](docs/execution_flow/19.png)

### 2. Blockchain Transaction
A MetaMask transaction (`mintBatch`) is requested. This mints 50 unique NFTs in a single, cost-effective transaction.

![Mint Transaction](docs/execution_flow/20.png)
![Success Confirmation](docs/execution_flow/21.png)

### 3. Inventory & Product Details
The newly minted units appear in the Inventory. Each unit is assigned a unique Serial ID (SUID) and a scannable QR Code that maps to its on-chain Token ID.

![Inventory Page](docs/execution_flow/22.png)
![Batch View](docs/execution_flow/23.png)
![Individual Unit QR](docs/execution_flow/24.png)

### 4. Audit Log
The Audit Log records the event. Each unit generates a "MANUFACTURED" record with a unique BLAKE2b hash and a shared on-chain Transaction hash.

![Audit Log](docs/execution_flow/25.png)

---

## Phase 4: Distributor Operations

The Distributor logs in and connects their MetaMask wallet to receive the products.

![Distributor Dashboard](docs/execution_flow/26.png)
![Distributor MetaMask](docs/execution_flow/27.png)
![Distributor Connected](docs/execution_flow/28.png)

---

## Phase 5: Transfer 1 (Manufacturer → Distributor)

The Manufacturer transfers a portion of the batch (30 units) to the Distributor.

### 1. Initiating Transfer
The Manufacturer selects the recipient and the quantity to transfer.

![Transfer Selection](docs/execution_flow/29.png)

### 2. Blockchain Transfer
The transfer is signed via MetaMask, executing a `transferBatch` on the smart contract.

![Transfer Transaction](docs/execution_flow/30.png)

### 3. Records Updated
The Audit Log reflects the "TRANSFERRED" status, and the Distributor's inventory is updated with the received 30 units.

![Manufacturer Audit Log](docs/execution_flow/31.png)
![Distributor Inventory](docs/execution_flow/32.png)

---

## Phase 6: Transfer 2 (Distributor → Retailer)

The process repeats down the supply chain. The Retailer logs in and connects their wallet.

![Retailer Dashboard](docs/execution_flow/33.png)
![Retailer MetaMask 1](docs/execution_flow/34.png)
![Retailer MetaMask 2](docs/execution_flow/35.png)

The Distributor transfers 20 units to the Retailer.

![Distributor Transfer Page](docs/execution_flow/36.png)
![Distributor Transfer Tx](docs/execution_flow/37.png)
![Distributor Audit Log](docs/execution_flow/38.png)
![Retailer Inventory](docs/execution_flow/39.png)

---

## Phase 7: Transfer 3 (Retailer → Customer)

Finally, the Customer logs in and connects their wallet. Note that customers cannot manufacture or transfer products; they can only receive and verify them.

![Customer Dashboard](docs/execution_flow/40.png)
![Customer MetaMask 1](docs/execution_flow/41.png)
![Customer MetaMask 2](docs/execution_flow/42.png)

The Retailer transfers 10 units to the Customer.

![Retailer Transfer Page](docs/execution_flow/43.png)
![Retailer Transfer Tx](docs/execution_flow/44.png)
![Retailer Audit Log](docs/execution_flow/45.png)

---

## Phase 8: Verification Scenarios

Customers verify product authenticity using the **Scan & Verify** feature, which performs a 5-point check against the blockchain and off-chain hash chain.

### Scenario A: Genuine Product
The customer scans a unit they successfully received. All checks pass, proving the product is genuine and the supply chain is complete.

![Verify Input](docs/execution_flow/46.png)
![Genuine Result](docs/execution_flow/47.png)

### Scenario B: Supply Chain Incomplete
The customer scans a genuine product that was *not* transferred to them (e.g., it is still held by a distributor). The system flags that the supply chain flow is broken.

![Verify Input Incomplete](docs/execution_flow/48.png)
![Incomplete Result](docs/execution_flow/49.png)

### Scenario C: Possible Counterfeit (PUID Mismatch)
The customer scans a QR code where the Serial ID (SUID) is valid, but it has been relabeled with a different Product ID (PUID). The mismatch immediately flags the item as a counterfeit.

![Verify Input Counterfeit](docs/execution_flow/50.png)
![Counterfeit Result](docs/execution_flow/51.png)

### Scenario D: Product Not Found
The customer scans a completely fabricated QR code. The system fails to find the product entirely.

![Verify Input Not Found](docs/execution_flow/52.png)
![Not Found Result](docs/execution_flow/53.png)
