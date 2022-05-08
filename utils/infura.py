from __future__ import annotations
from io import TextIOWrapper
from sys import stderr
from typing import Dict, List, Union
from requests import JSONDecodeError, get
from time import sleep, time
from web3 import Web3
import json
# import logging
from hexbytes import HexBytes
from web3.datastructures import AttributeDict
from web3.logs import DISCARD


class Infura:
    # infrua API key
    # jason's Infura key: "ee4c35b8c3114586a74eda3b8b634228"
    # jason's etherscan key: "2JPX8EJNBE2USI1VDBHJPTCGG994ERQ6QZ"
    INFURA_API_KEY = 'b07f1f09ee5443c6b89fcfd1a4300fbc'
    w3: Web3 = Web3(Web3.HTTPProvider(
        f'https://mainnet.infura.io/v3/{INFURA_API_KEY}'))
    # Etherscan API key
    ETHERSCAN_API_KEY = 'AMD3PDCXAPI6WKK8VJ6VGAZB5XJB2UHV1U'
    abi_endpoint = "https://api.etherscan.io/api?module=contract&action=getabi"
    ABI = {}
    _contract_times = [0] * 5

    @staticmethod
    def get_block(blockNum: Union[str, int] = 'latest', n: int = 1, deep=True) -> Union[Block, List[Block]]:
        """
        Get a block from the block chain

        :param blockNum: can either by a block hash (hex num) or the latest, defaults to 'latest'
        :param n: how many blocks to get (parents), defaults to 1
        :param deep: search lower values as well
        :return: Either a single or a list of block objects
        """
        res = []
        # init
        block: Dict = {'parentHash': blockNum}
        # get n blocks and append
        for _ in range(n):
            # logging.info(f"Requesting Block '{block['parentHash']}' from Infura API")
            block: AttributeDict = Infura.w3.eth.get_block(block['parentHash'])
            res.append(Block(block, deep))
        return res if len(res) != 1 else res[0]

    @staticmethod
    def get_transaction(txnHash: str, deep=True) -> Transaction:
        """
        Get a transaction from the block chain

        :param txnHash: the transaction hash
        :return: a transaction object
        """
        # logging.info(f"Requesting Transaction '{txnHash}' from Infura API")
        return Transaction(Infura.w3.eth.get_transaction(txnHash),deep)

    @staticmethod
    def get_transaction_receipt(txnHash: str, deep=True) -> Transaction:
        """
        Get a transaction receipt from the block chain

        :param txnHash: the transaction hash
        :return: a transaction receipt object
        """
        # logging.info(f"Requesting Transaction Receipt '{txnHash}' from Infura API")
        return TransactionReceipt(Infura.w3.eth.get_transaction_receipt(txnHash),deep)

    @staticmethod
    def save_data(f: TextIOWrapper, data) -> None:
        """
        Save a List of blocks to a file in JSON format

        :param f: file descriptor
        :param data: temp to save
        """
        if isinstance(data, list):
            f.write(Infura.jsonify([item.encode() for item in data]))
        else:
            f.write(Infura.jsonify(data.encode()))

    @staticmethod
    def get_contract(contractAddr: HexBytes):
        """
        Gets the ethereum Solidity contract information and adds it to the ABI
        class variable

        :param contractAddr: addr of the contract
        :return: Eth contract
        """
        if contractAddr not in Infura.ABI:
            # 5 calls/second API limit
            # ensure we don't hit it
            newTime = time()
            deltaTime = newTime - Infura._contract_times[4]
            Infura._contract_times = [newTime] + Infura._contract_times[:4]
            if deltaTime < 1 and Infura._contract_times[4] != 0:
                sleep(deltaTime)
                # SAFE MODE
                sleep(0.1)
            # logging.info(f"Requesting abi info from contract '{contractAddr}' from Etherscan API")
            abi = get(f"{Infura.abi_endpoint}&address={contractAddr}&apikey={Infura.ETHERSCAN_API_KEY}").text
            if "Max rate limit reached" in abi:
                print("Etherscan API Limit reached",file=stderr)
                sleep(2)
            if "Contract source code not verified" in abi:
                return None
            try:
                Infura.ABI[contractAddr] = json.loads(abi)
            except json.decoder.JSONDecodeError:
                # problem decoding
                return None
        # logging.info(f"Requesting Contract '{contractAddr}' from Infura API")
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
    def load_data(name: str = "temp.json") -> List[Block]:
        with open(name, 'r') as f:
            try:
                return json.loads(f.read())
            except JSONDecodeError:
                raise Exception("File must contain json temp")


class TransactionReceipt:
    """
    A copy class for a transaction receipt, useful for type hinting

    """
    def __init__(self, raw, deep) -> None:
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
        if deep:
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
                        try:
                            decoded = contract.events[event["name"]]().processReceipt(self.raw, errors=DISCARD)
                        except ValueError:
                            # No matching events found or Multiple events found
                            continue
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
    """
    A copy class for a transaction, useful for type hinting

    """
    def __init__(self, raw, deep) -> None:
        raw = dict(raw)
        self.blockHash: HexBytes = raw["blockHash"]
        self.blockNumber: int = raw["blockNumber"]
        self._from: HexBytes = raw["from"]
        self.gas: int = raw["gas"]  # value in wei
        self.gasPrice: int = raw["gasPrice"]  # value in wei
        self._hash: HexBytes = raw["hash"]
        self.input: HexBytes = raw["input"]
        self.nonce: int = raw["nonce"]
        self.r: HexBytes = raw["r"]
        self.s: HexBytes = raw["s"]
        self._to: HexBytes = raw["to"]
        self.index: int = raw["transactionIndex"]
        self.type: HexBytes = raw["type"]
        self.v: int = raw["v"]
        self.value: int = raw["value"]  # note: value here is in wei, convert to eth, do eth = value / 10**18
        self.receipt: TransactionReceipt = Infura.get_transaction_receipt(
            self._hash.hex(), deep=deep) if deep else ""

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
            "receipt": self.receipt.encode() if self.receipt != "" else ""
        }


class Block:
    """
    A copy class for a block, useful for type hinting

    If deep is True, the transactions will be a list of Transaction objects.

    """
    def __init__(self, raw, deep) -> None:
        raw = dict(raw)
        self.raw = raw
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
            Infura.get_transaction(txn.hex()) for txn in self.transactionHashes] if deep else ""
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
            "transactions": [transaction.encode() for transaction in self.transactions if transaction != ""],
            "transactionsRoot": self.transactionsRoot,
            "uncles": self.uncles
        }


if __name__ == "__main__":
    # logging.basicConfig(filename="process.log",level=logging.INFO)
    block = Infura.get_block('0x4cb6e139755c24f5c295be2d1010aaeccab8f3003cf0d1944dd8642116e97a24',deep=False)
    with open('results/example_block.json', 'w') as f:
        Infura.save_data(f, [block])
