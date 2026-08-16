# Blockchain Setup for Render Deployment

Use a public Ethereum testnet for the deployed Render app. Ganache only works on your local machine because Render cannot reach `127.0.0.1:7545` on your laptop.

## Recommended Network

Use Sepolia:

```text
ETH_CHAIN_ID=11155111
ETH_NETWORK_NAME=Sepolia
METAMASK_CHAIN_ID_HEX=0xaa36a7
```

## 1. Create an RPC URL

Create a Sepolia RPC endpoint with a provider such as Infura, Alchemy, or QuickNode.

Example:

```text
WEB3_PROVIDER_URI=https://sepolia.infura.io/v3/YOUR_PROJECT_ID
```

## 2. Create a Server Wallet

Create or import a wallet that the Flask server will use to write product lifecycle blocks to the smart contract.

Fund it with Sepolia test ETH from a faucet.

Render must receive the private key as an environment variable:

```text
ETH_PRIVATE_KEY=your_server_wallet_private_key
```

Do not commit this key to GitHub.

## 3. Deploy the Contract to Sepolia

On your local machine:

```bash
npm install
```

Create a local `.env` file:

```text
WEB3_PROVIDER_URI=https://sepolia.infura.io/v3/YOUR_PROJECT_ID
ETH_CHAIN_ID=11155111
ETH_NETWORK_NAME=Sepolia
METAMASK_CHAIN_ID_HEX=0xaa36a7
ETH_PRIVATE_KEY=your_server_wallet_private_key
```

Deploy:

```bash
npm run deploy:sepolia
```

Copy the printed contract address:

```text
AUTHCHAIN_CONTRACT_ADDRESS=0x...
```

## 4. Set Render Environment Variables

In Render dashboard, set:

```text
WEB3_PROVIDER_URI=https://sepolia.infura.io/v3/YOUR_PROJECT_ID
ETH_CHAIN_ID=11155111
ETH_NETWORK_NAME=Sepolia
METAMASK_CHAIN_ID_HEX=0xaa36a7
AUTHCHAIN_CONTRACT_ADDRESS=0x...
ETH_PRIVATE_KEY=your_server_wallet_private_key
```

Also keep your existing:

```text
MONGO_URI=...
SECRET_KEY=...
ADMIN_USERNAME=...
ADMIN_PASSWORD=...
```

## 5. Push to GitHub and Redeploy Render

Commit and push these files:

```text
app.py
requirements.txt
render.yaml
templates/base.html
templates/ledger.html
contracts/AuthChainLedger.sol
scripts/deploy_contract.js
package.json
.env.example
BLOCKCHAIN_RENDER_SETUP.md
```

Render will redeploy from GitHub.

## 6. Connect MetaMask

In MetaMask, switch to Sepolia and connect from the app top bar.

The app uses MetaMask for browser wallet identity, while the Flask server writes verified supply-chain events to Sepolia through `ETH_PRIVATE_KEY`.

## Optional Local Ganache Demo

For local testing only:

```text
WEB3_PROVIDER_URI=http://127.0.0.1:7545
ETH_CHAIN_ID=1337
ETH_NETWORK_NAME=Ganache Local
METAMASK_CHAIN_ID_HEX=0x539
```

Then run:

```bash
npm run deploy:ganache
python app.py
```
