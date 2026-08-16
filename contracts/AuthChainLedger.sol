// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import "@openzeppelin/contracts/utils/cryptography/MessageHashUtils.sol";

contract AuthChainLedger is ERC721 {
    using ECDSA for bytes32;
    using MessageHashUtils for bytes32;

    struct ProductEvent {
        string puid;
        string suid;
        string action;
        string fromUser;
        string toUser;
        bytes32 blockHash;
        string previousHash;
        uint256 timestamp;
        bool exists;
    }

    address public serverSigner;
    mapping(string => ProductEvent) private eventsByBlockId;
    string[] private blockIds;
    
    mapping(string => uint256) public suidToTokenId;

    event ProductEventRecorded(
        string indexed blockId,
        uint256 indexed tokenId,
        string puid,
        string suid,
        string action,
        bytes32 blockHash
    );

    constructor() ERC721("AuthChain Product", "ACP") {
        serverSigner = msg.sender;
    }

    function setServerSigner(address _signer) external {
        require(msg.sender == serverSigner, "Only current signer can change");
        serverSigner = _signer;
    }

    function _verifySignature(bytes32 blockHash, bytes memory signature) internal view returns (bool) {
        bytes32 ethSignedMessageHash = blockHash.toEthSignedMessageHash();
        return ethSignedMessageHash.recover(signature) == serverSigner;
    }

    struct BlockData {
        string blockId;
        string puid;
        string suid;
        string action;
        string fromUser;
        string toUser;
        bytes32 blockHash;
        string previousHash;
        bytes signature;
    }

    function mintProduct(
        address to,
        uint256 tokenId,
        BlockData calldata data
    ) external {
        require(_verifySignature(data.blockHash, data.signature), "Unauthorized: Invalid server signature");
        require(bytes(data.blockId).length > 0, "block id required");
        require(!eventsByBlockId[data.blockId].exists, "block already exists");

        _safeMint(to, tokenId);
        suidToTokenId[data.suid] = tokenId;

        eventsByBlockId[data.blockId] = ProductEvent({
            puid: data.puid,
            suid: data.suid,
            action: data.action,
            fromUser: data.fromUser,
            toUser: data.toUser,
            blockHash: data.blockHash,
            previousHash: data.previousHash,
            timestamp: block.timestamp,
            exists: true
        });
        blockIds.push(data.blockId);

        emit ProductEventRecorded(data.blockId, tokenId, data.puid, data.suid, data.action, data.blockHash);
    }

    function mintProductBatch(
        address to,
        uint256[] calldata tokenIds,
        BlockData[] calldata dataArray
    ) external {
        require(tokenIds.length == dataArray.length, "Mismatched arrays");
        
        for (uint256 i = 0; i < dataArray.length; i++) {
            BlockData calldata data = dataArray[i];
            uint256 tokenId = tokenIds[i];

            require(_verifySignature(data.blockHash, data.signature), "Unauthorized: Invalid server signature");
            require(bytes(data.blockId).length > 0, "block id required");
            require(!eventsByBlockId[data.blockId].exists, "block already exists");

            _safeMint(to, tokenId);
            suidToTokenId[data.suid] = tokenId;

            eventsByBlockId[data.blockId] = ProductEvent({
                puid: data.puid,
                suid: data.suid,
                action: data.action,
                fromUser: data.fromUser,
                toUser: data.toUser,
                blockHash: data.blockHash,
                previousHash: data.previousHash,
                timestamp: block.timestamp,
                exists: true
            });
            blockIds.push(data.blockId);

            emit ProductEventRecorded(data.blockId, tokenId, data.puid, data.suid, data.action, data.blockHash);
        }
    }

    function transferProduct(
        address to,
        uint256 tokenId,
        BlockData calldata data
    ) external {
        require(_verifySignature(data.blockHash, data.signature), "Unauthorized: Invalid server signature");
        require(bytes(data.blockId).length > 0, "block id required");
        require(!eventsByBlockId[data.blockId].exists, "block already exists");
        
        safeTransferFrom(msg.sender, to, tokenId);

        eventsByBlockId[data.blockId] = ProductEvent({
            puid: data.puid,
            suid: data.suid,
            action: data.action,
            fromUser: data.fromUser,
            toUser: data.toUser,
            blockHash: data.blockHash,
            previousHash: data.previousHash,
            timestamp: block.timestamp,
            exists: true
        });
        blockIds.push(data.blockId);

        emit ProductEventRecorded(data.blockId, tokenId, data.puid, data.suid, data.action, data.blockHash);
    }

    function transferProductBatch(
        address to,
        uint256[] calldata tokenIds,
        BlockData[] calldata dataArray
    ) external {
        require(tokenIds.length == dataArray.length, "Mismatched arrays");
        
        for (uint256 i = 0; i < dataArray.length; i++) {
            BlockData calldata data = dataArray[i];
            uint256 tokenId = tokenIds[i];

            require(_verifySignature(data.blockHash, data.signature), "Unauthorized: Invalid server signature");
            require(bytes(data.blockId).length > 0, "block id required");
            require(!eventsByBlockId[data.blockId].exists, "block already exists");
            
            safeTransferFrom(msg.sender, to, tokenId);

            eventsByBlockId[data.blockId] = ProductEvent({
                puid: data.puid,
                suid: data.suid,
                action: data.action,
                fromUser: data.fromUser,
                toUser: data.toUser,
                blockHash: data.blockHash,
                previousHash: data.previousHash,
                timestamp: block.timestamp,
                exists: true
            });
            blockIds.push(data.blockId);

            emit ProductEventRecorded(data.blockId, tokenId, data.puid, data.suid, data.action, data.blockHash);
        }
    }

    function getEvent(string calldata blockId)
        external
        view
        returns (
            string memory puid,
            string memory suid,
            string memory action,
            string memory fromUser,
            string memory toUser,
            bytes32 blockHash,
            string memory previousHash,
            uint256 timestamp,
            bool exists
        )
    {
        ProductEvent storage productEvent = eventsByBlockId[blockId];
        return (
            productEvent.puid,
            productEvent.suid,
            productEvent.action,
            productEvent.fromUser,
            productEvent.toUser,
            productEvent.blockHash,
            productEvent.previousHash,
            productEvent.timestamp,
            productEvent.exists
        );
    }

    function totalEvents() external view returns (uint256) {
        return blockIds.length;
    }
}

