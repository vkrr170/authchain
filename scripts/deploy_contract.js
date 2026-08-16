const fs = require('fs');
const path = require('path');
const solc = require('solc');
const { Web3 } = require('web3');
require('dotenv').config();

async function main() {
  const providerUrl = process.env.WEB3_PROVIDER_URI;
  const privateKey = process.env.ETH_PRIVATE_KEY;
  const chainId = process.env.ETH_CHAIN_ID || '11155111';
  const networkName = process.env.ETH_NETWORK_NAME || 'Sepolia';

  if (!providerUrl) {
    throw new Error('Set WEB3_PROVIDER_URI before deploying.');
  }
  if (!privateKey) {
    throw new Error('Set ETH_PRIVATE_KEY before deploying.');
  }

  const contractPath = path.join(__dirname, '..', 'contracts', 'AuthChainLedger.sol');
  const source = fs.readFileSync(contractPath, 'utf8');
  const input = {
    language: 'Solidity',
    sources: {
      'AuthChainLedger.sol': { content: source }
    },
    settings: {
      optimizer: {
        enabled: true,
        runs: 200
      },
      viaIR: true,
      outputSelection: {
        '*': {
          '*': ['abi', 'evm.bytecode']
        }
      }
    }
  };

  console.log("Compiling contract...");
  const output = JSON.parse(solc.compile(JSON.stringify(input), {
    import: function(dependency) {
      if (dependency.startsWith('@openzeppelin/')) {
        const depPath = path.resolve(__dirname, '..', 'node_modules', dependency);
        try {
          return { contents: fs.readFileSync(depPath, 'utf8') };
        } catch (e) {
          return { error: 'File not found' };
        }
      }
      return { error: 'File not found' };
    }
  }));
  if (output.errors) {
    const fatal = output.errors.filter((err) => err.severity === 'error');
    output.errors.forEach((err) => console.log(err.formattedMessage));
    if (fatal.length) process.exit(1);
  }

  const compiled = output.contracts['AuthChainLedger.sol'].AuthChainLedger;
  const web3 = new Web3(providerUrl);
  const account = web3.eth.accounts.privateKeyToAccount(privateKey);
  web3.eth.accounts.wallet.add(account);

  console.log("Estimating gas...");
  const contract = new web3.eth.Contract(compiled.abi);
  const gasPrice = await web3.eth.getGasPrice();
  const deployTx = contract.deploy({ data: compiled.evm.bytecode.object });
  const estimatedGas = await deployTx.estimateGas({ from: account.address });
  
  // Add a 10% buffer to estimated gas just to be safe
  const gasLimit = Math.floor(Number(estimatedGas) * 1.1);
  
  console.log("Deploying contract...", "gasLimit:", gasLimit);
  const deployed = await deployTx.send({ 
      from: account.address, 
      gas: gasLimit.toString(), 
      gasPrice 
  });
  console.log("Deployment confirmed!");

  console.log('Network: ' + networkName);
  console.log('Deployer: ' + account.address);
  console.log('AUTHCHAIN_CONTRACT_ADDRESS=' + deployed.options.address);
  console.log('WEB3_PROVIDER_URI=' + providerUrl);
  console.log('ETH_CHAIN_ID=' + chainId);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
