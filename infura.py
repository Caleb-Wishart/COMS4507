from __future__ import annotations
from io import TextIOWrapper
from sys import stderr
from typing import Dict, List, Union
from requests import JSONDecodeError, get
from time import sleep, time
from web3 import Web3
import json
from hexbytes import HexBytes
from web3.datastructures import AttributeDict
from web3.logs import DISCARD
# https://web3py.readthedocs.io/en/stable/web3.eth.html#web3.eth.Eth.get_block
# https://towardsdatascience.com/access-ethereum-data-using-web3-py-infura-and-the-graph-d6fb981c2dc9
# https://infura.io/dashboard/ethereum/b07f1f09ee5443c6b89fcfd1a4300fbc/settings


class Infura:
    # infrua API key
    INFURA_API_KEY = 'b07f1f09ee5443c6b89fcfd1a4300fbc'
    w3: Web3 = Web3(Web3.HTTPProvider(
        f'https://mainnet.infura.io/v3/{INFURA_API_KEY}'))
    ETHERSCAN_API_KEY = 'AMD3PDCXAPI6WKK8VJ6VGAZB5XJB2UHV1U'
    abi_endpoint = "https://api.etherscan.io/api?module=contract&action=getabi"
    ABI = {}
    _contract_times = [0] * 5

    @staticmethod
    def get_block(blockNum: Union[str, int] = 'latest', n: int = 1) -> Union[Block, List[Block]]:
        res = []
        # init
        block: Dict = {'parentHash': blockNum}
        # get n blocks and append
        for _ in range(n):
            block: AttributeDict = Infura.w3.eth.get_block(block['parentHash'])
            res.append(Block(block))
        return res if len(res) != 1 else res[0]

    @staticmethod
    def get_transaction(txnHash: str) -> Transaction:
        return Transaction(Infura.w3.eth.get_transaction(txnHash))

    @staticmethod
    def get_transaction_receipt(txnHash: str) -> Transaction:
        return TransactionReceipt(Infura.w3.eth.get_transaction_receipt(txnHash))

    @staticmethod
    def save_data(f: TextIOWrapper, data: List[Block]) -> None:
        f.write(Infura.jsonify([block.encode() for block in data]))

    @staticmethod
    def get_contract(contractAddr: HexBytes):
        if contractAddr not in Infura.ABI:
            # 5 calls/second API limit
            newTime = time()
            deltaTime = newTime - Infura._contract_times[4]
            Infura._contract_times = [newTime] + Infura._contract_times[:4]
            if deltaTime < 1 and Infura._contract_times[4] != 0:
                sleep(deltaTime)
                # SAFE MODE
                sleep(0.1)
            abi = get(f"{Infura.abi_endpoint}&address={contractAddr}&apikey={Infura.ETHERSCAN_API_KEY}").text
            if "Max rate limit reached" in abi:
                print("Etherscan API Limit reached",file=stderr)
                sleep(2)
            if "Contract source code not verified" in abi:
                return None
            Infura.ABI[contractAddr] = json.loads(abi)
        return Infura.w3.eth.contract(address=contractAddr, abi=Infura.ABI[contractAddr]["result"])

    @staticmethod
    def jsonify(data) -> str:
        # thanks voith
        # https://github.com/ethereum/web3.py/issues/782
        class HexJsonEncoder(json.JSONEncoder):
            def default(self, obj):
                if isinstance(obj, HexBytes):
                    return obj.hex()
                if isinstance(obj, AttributeDict):
                    return dict(obj)
                return super().default(obj)
        return json.dumps(data, cls=HexJsonEncoder, indent=4, sort_keys=True)

    @staticmethod
    def load_data(name: str = "data.json") -> List[Block]:
        with open(name, 'r') as f:
            try:
                return json.loads(f.read())
            except JSONDecodeError:
                raise Exception("File must contain json data")


class TransactionReceipt:
    def __init__(self, raw) -> None:
        raw = dict(raw)
        self.raw = raw
        self.blockHash: HexBytes = raw["blockHash"]
        self.blockNumber: int = raw["blockNumber"]
        self.contractAddress: HexBytes = raw["contractAddress"]
        self.cumulativeGasUsed: int = raw["cumulativeGasUsed"]
        self.effectiveGasPrice: int = raw["effectiveGasPrice"]
        self._from: HexBytes = raw["from"]
        self.gasUsed: HexBytes = raw["gasUsed"]
        self.logs: List = [dict(log) for log in raw["logs"]]
        for log in self.logs:
            contract = Infura.get_contract(log["address"])
            if contract == None:
                log["decoded"] = "No Valid contract"
                continue
            # Get event signature of log (first item in topics array)
            receipt_event_signature_hex = log["topics"][0]
            abi_events = [abi for abi in contract.abi if abi["type"] == "event"]
            # Determine which event in ABI matches the transaction log you are decoding
            for event in abi_events:
                # Get event signature components
                name = event["name"]
                inputs = [param["type"] for param in event["inputs"]]
                inputs = ",".join(inputs)
                # Hash event signature
                event_signature_text = f"{name}({inputs})"
                event_signature_hex = Infura.w3.keccak(text=event_signature_text)
                # Find match between log's event signature and ABI's event signature
                if event_signature_hex == receipt_event_signature_hex:
                    # Decode matching log
                    decoded = contract.events[event["name"]]().processReceipt(self.raw, errors=DISCARD)
                    log["decoded"] = decoded
        self.logsBloom: HexBytes = raw["logsBloom"]
        self.status: int = raw["status"]
        self._to: HexBytes = raw["to"]
        self.transactionHash: HexBytes = raw["transactionHash"]
        self.transactionIndex: int = raw["transactionIndex"]
        self._type: HexBytes = raw["type"]

    def __hash__(self) -> int:
        return self.transactionHash

    def __str__(self) -> str:
        return f"<Receipt {self.transactionHash}>"

    def encode(self) -> Dict:
        return {
            "blockHash": self.blockHash,
            "blockNumber": self.blockNumber,
            "contractAddress": self.contractAddress,
            "cumulativeGasUsed": self.cumulativeGasUsed,
            "effectiveGasPrice": self.effectiveGasPrice,
            "_from": self._from,
            "gasUsed": self.gasUsed,
            "logs": self.logs,
            "logsBloom": self.logsBloom,
            "status": self.status,
            "_to": self._to,
            "transactionHash": self.transactionHash,
            "transactionIndex": self.transactionIndex,
            "_type": self._type
        }


class Transaction:
    def __init__(self, raw) -> None:
        raw = dict(raw)
        self.blockHash: HexBytes = raw["blockHash"]
        self.blockNumber: int = raw["blockNumber"]
        self._from: HexBytes = raw["from"]
        self.gas: int = raw["gas"]
        self.gasPrice: int = raw["gasPrice"]
        self._hash: HexBytes = raw["hash"]
        self.input: HexBytes = raw["input"]
        self.nonce: int = raw["nonce"]
        self.r: HexBytes = raw["r"]
        self.s: HexBytes = raw["s"]
        self._to: HexBytes = raw["to"]
        self.index: int = raw["transactionIndex"]
        self.type: HexBytes = raw["type"]
        self.v: int = raw["v"]
        self.value: int = raw["value"]
        self.receipt: TransactionReceipt = Infura.get_transaction_receipt(
            self._hash)

    def __hash__(self) -> int:
        return self._hash

    def __str__(self) -> str:
        return f"<Transaction {self._hash}>"

    def encode(self) -> Dict:
        return {
            "blockHash": self.blockHash,
            "blockNumber": self.blockNumber,
            "_from": self._from,
            "gas": self.gas,
            "gasPrice": self.gasPrice,
            "_hash": self._hash,
            "input": self.input,
            "nonce": self.nonce,
            "r": self.r,
            "s": self.s,
            "_to": self._to,
            "index": self.index,
            "type": self.type,
            "v": self.v,
            "value": self.value,
            "receipt": self.receipt.encode()
        }

class Block:
    def __init__(self, raw) -> None:
        raw = dict(raw)
        self.raw = raw
        self.baseFeePerGas: int = raw["baseFeePerGas"]
        self.difficulty: int = raw["difficulty"]
        self.extraData: HexBytes = raw["extraData"]
        self.gasLimit: int = raw["gasLimit"]
        self.gasUsed: int = raw["gasUsed"]
        self._hash: HexBytes = raw["hash"]
        self.logsBloom: HexBytes = raw["logsBloom"]
        self.miner: HexBytes = raw["miner"]
        self.mixHash: HexBytes = raw["mixHash"]
        self.nonce: HexBytes = raw["nonce"]
        self.number: int = raw["number"]
        self.parentHash: HexBytes = raw["parentHash"]
        self.receiptsRoot: HexBytes = raw["receiptsRoot"]
        self.sha3Uncles: HexBytes = raw["sha3Uncles"]
        self.size: int = raw["size"]
        self.stateRoot: HexBytes = raw["stateRoot"]
        self.timestamp: int = raw["timestamp"]
        self.totalDifficulty: int = raw["totalDifficulty"]
        self.transactionHashes: List[HexBytes] = raw["transactions"]
        self.transactions: List[Transaction] = [
            Infura.get_transaction(txn) for txn in self.transactionHashes]
        self.transactionsRoot: HexBytes = raw["transactionsRoot"]
        self.uncles: List[HexBytes] = raw["uncles"]

    def __hash__(self) -> int:
        return self._hash

    def __len__(self) -> int:
        return len(self.transactionHashes)

    def __contains__(self, other) -> bool:
        return other in self.transactionHashes

    def __str__(self) -> str:
        return f"<Block {self._hash}>"

    def encode(self) -> Dict:
        return {
            "raw": self.raw,
            "baseFeePerGas": self.baseFeePerGas,
            "difficulty": self.difficulty,
            "extraData": self.extraData,
            "gasLimit": self.gasLimit,
            "gasUsed": self.gasUsed,
            "_hash": self._hash,
            "logsBloom": self.logsBloom,
            "miner": self.miner,
            "mixHash": self.mixHash,
            "nonce": self.nonce,
            "number": self.number,
            "parentHash": self.parentHash,
            "receiptsRoot": self.receiptsRoot,
            "sha3Uncles": self.sha3Uncles,
            "size": self.size,
            "stateRoot": self.stateRoot,
            "timestamp": self.timestamp,
            "totalDifficulty": self.totalDifficulty,
            "transactionHashes": self.transactionHashes,
            "transactions": [transaction.encode() for transaction in self.transactions],
            "transactionsRoot": self.transactionsRoot,
            "uncles": self.uncle
        }


# with open('known_bad.json','w') as f:
#     save_data(f,get_n_blocks(w3,11876244,n=1))
# txn = Infura.get_transaction_receipt(
#     0x87b5d812c93001ec0d9f95c1922efed54b78b30e91805c09f86b1048e17c66d6)
# txn2 = Infura.get_transaction_receipt(
#     0xea1f0d4b4e427671350db3c2c24d48bf06460eb08f901bc1b02e43221d1c7a1c)
# txn3 = Infura.get_transaction_receipt(
#     0xf493d8254568a7c89f4e2ad9e9fb5a7243374d3cd873dea3657e9b7d83be4054)
# a = [txn, txn2, txn3]
txn = Infura.get_transaction(
    0x87b5d812c93001ec0d9f95c1922efed54b78b30e91805c09f86b1048e17c66d6)
with open('test123.json', 'w') as f:
    Infura.save_data(f, [txn])
