"""
The script that implements the algorithm to detect if a pair of transactions
form a frontrunning attack.
"""
import os.path
from infura import *
from datetime import timedelta
import pandas as pd

# from https://etherscan.io/address/0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2
# used to check if the transaction has WETH has one of the swap tokens
WETH_contract_address = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"


class FrontrunPair:
    """
    The class the represents an identified fronrunning attack pair
    """
    def __init__(self, frontrun: dict, backrun: dict, gains: int):
        """
            :param frontrun: The frontrunning transaction
            :param backrun: The backrunning transaction
            :param gains: The gains in wei (can be negative)
        """
        assert frontrun["blockHash"] == backrun["blockHash"], "Two transactions not belong to same block"
        self.frontrun = frontrun
        self.backrun = backrun
        self.gains = gains

    def __repr__(self):
        return f'In block: {self.frontrun["blockHash"].hex()}\n' \
               f'gains: {self.gains}\n' \
               f'frontrunning transaction:\n' \
               f'tx_hash: {self.frontrun["_hash"].hex()}, from: {self.frontrun["_from"]}, ' \
               f'to: {self.frontrun["_to"]}\n' \
               f'backrunning transaction:\n' \
               f'tx_hash: {self.backrun["_hash"].hex()}, from: {self.backrun["_from"]},' \
               f' to: {self.backrun["_to"]}'

    def save(self, file_name):
        """
        Save the 3 objects into 1 json file
        """
        if not file_name.endswith("json"):
            file_name = os.path.join(file_name, ".json")

        with open(file_name, "w") as fp:
            fp.write(Infura.jsonify({"t1": self.backrun, "t2": self.frontrun, "net_gains": self.gains}))


def get_swap_gains(t1: Union[Transaction, dict], t2: Union[Transaction, dict]):
    """
    This function checks if the transaction pair satisfies heuristics.
    If it does, then return the amount gained from the swap action (in wei),
    the transaction costs of the 2 transactions have been taken away and will
    be added to the transaction dict, if t1, t2 are dict objects.

    Assumptions:
        1. t1 is a transaction that swaps ETH with other tokens (i.e. t1 is a buy action)
        2. consider transaction that includes only ONE swap event in the
            transaction event
        3. gains between two transactions calculated in wei (1 ETH = 10**18 wei)
        4. all transactions passed to this function has and only has
            1 swap event in the transaction_receipt log
        5. victim transaction not required

    Heuristics:
        1. t1 and t2 belong to same block and index of t1 < index of t2
        2. t1 and t2 have different transaction hashes
        3. the amount swapped in t1 == amount swapped in t2

        :param t1: the suspected frontrunning transaction
        :param t2: the suspected backrunning transaction
        :return -inf if the two does not construct a frontrunning attack;
             (the amount of gains from the swap action, t1 gas cost, t2 gas cost) tuple (in wei)
    """
    if isinstance(t1, Transaction):
        t1 = t1.encode()
    if isinstance(t2, Transaction):
        t2 = t2.encode()

    # check same block, different transaction hashses and t1[idx] < t2[idx]
    if not (t1["blockNumber"] == t2["blockNumber"] and t1["_hash"] != t2["_hash"] and
            t1["index"] < t2["index"]):
        print("not in same block, identical transaction hashses or t1[idx] < t2[idx]", file=stderr)
        return -float("inf")

    # find Swap transaction of t1 and t2
    t1_swap_info, t2_swap_info = t1.get("swap_event"), t2.get('swap_event')
    assert t1_swap_info and t2_swap_info, "t1 or t2 do not have swap info shortcut"
    t1_last_decoded_amounts = t1_swap_info["args"]
    # buy action in t1:
    # amount1In = amount sent for swap (ETH); amount0Out = amount received from swap
    t1_input, t1_output = \
        t1_last_decoded_amounts["amount1In"], t1_last_decoded_amounts["amount0Out"]

    t2_last_decoded_amounts = t2_swap_info["args"]
    # sell action in t2:
    # amount0In = amount sent for swap (== amount0Out of t1); amount1Out = amount received from swap (ETH)
    t2_input, t2_output = t2_last_decoded_amounts["amount0In"], t2_last_decoded_amounts["amount1Out"]

    # for log in t1["receipt"]["logs"]:
    #     for decode_info in log["decoded"]:
    #         if decode_info["event"] == "Swap":
    #             # check if amount swapped in first transaction equals amount swap in second transaction
    #             t1_last_decoded_amounts = decode_info["args"]
    #             # ensure the swap has only 2 non-zero values
    #             assert np.count_nonzero(list(t1_last_decoded_amounts.values())) == 2, \
    #                 "t1 Swap amount incorrect"
    #             # buy action in t1:
    #             # amount1In = amount sent for swap (ETH); amount0Out = amount received from swap
    #             t1_input, t1_output = \
    #                 t1_last_decoded_amounts["amount1In"], t1_last_decoded_amounts["amount0Out"]
    if t1_input == 0:
        # first transaction not buy action
        # print("t1 is a sell action", file=stderr)
        return -float("inf")
    elif t2_input == 0:
        # second transaction not sell action
        # print("t2 is a buy action", file=stderr)
        return -float("inf")
    elif t1_output != t2_input:
        # todo: this may be modified to allow some deviation in the amount being swapped back
        # t1 output mismatched with t2 input
        # print("t1 output mismatched with t2 input", file=stderr)
        return -float("inf")
    else:
        # calculate the gains (in wei)
        # = t2_output - t1_input - transaction cost t1 - transaction cost of t2
        gross_gain = t2_output - t1_input
        # gas cost in wei = gas price * actual gas used
        t1_gas_cost = t1["receipt"]["effectiveGasPrice"] * t1["receipt"]["gasUsed"]
        t1["actual_transaction_cost"] = t1_gas_cost
        t2_gas_cost = t2["receipt"]["effectiveGasPrice"] * t2["receipt"]["gasUsed"]
        t2["actual_transaction_cost"] = t2_gas_cost
        net_gain = gross_gain - t1_gas_cost - t2_gas_cost
    return net_gain, t1_gas_cost, t2_gas_cost


def legit_check(transaction: dict) -> tuple:
    """
    1. Count how many events exist in transaction receipt logs,
    add shortcut of the decoded Swap event to transaction dict, if possible
    2. ensure the one of the token is in WETH (only cares about swap of WETH)

    :param transaction: The transaction to be processed
    :return
        (the dict that contains the count of each Event, whether the transaction contains at least a WETH related event)
    """
    WETH_in_swap = False
    logs = transaction["receipt"]["logs"]
    res = {}
    for log in logs:
        if log == [] or log.get("decoded") in [None, "No Valid contract"]:
            continue
        for decode_info in log["decoded"]:
            event = decode_info.get('event')
            if not event:
                continue
            if decode_info['address'] == WETH_contract_address:
                WETH_in_swap = True

            if not res.get(event):
                res[event] = 1
            else:
                res[event] += 1
            if event == "Swap":
                # add decoded dict shortcut to transaction
                transaction["swap_event"] = decode_info
    return res, WETH_in_swap


def print_and_write_stat(text: Union[str, FrontrunPair], end="\n", fp=None):
    """
    Print the text to stdout and save to fp, if applicable

    :param text: the text to be outputted
    :param end: The ending of the text
    :param fp: if this is filled, the same text will also be outputted to fp
    """
    print(text, end=end)
    if fp:
        print(text, end=end, file=fp)


def check_block_transactions(current_block: Union[Block, dict], save: bool = False, save_dir: str = "./temp/"):
    """
    Check all transactions in a block to find out suspected fronrunning
    attack pairs.

    Assumptions: we only check the transaction that has and only has ONE
    swap event

    :param current_block: The block to be checked
    :param save: whether the found frontrunning pairs are saved
    :param save_dir: the directory to be saved
    """
    start_time = time()

    if isinstance(current_block, Block):
        current_block = current_block.encode()
    transactions = current_block["transactions"]
    # keep track of original transaction numbers in the block
    current_block["origin_transaction_number"] = original_number = len(transactions)

    out_log = None
    name = None
    if save:
        # save dir named after current block number
        name = f'block_{current_block["number"]}'
        save_dir = os.path.join(save_dir, name)
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
        out_log = open(os.path.join(save_dir, name + "_" + "stats.log"), "w")

    # heuristics:
    # each transaction has and only has one swap event, eliminate those
    # with number of swap event != 1
    transaction_idx = 0
    while transaction_idx < len(transactions):
        transaction = transactions[transaction_idx]
        traanction_hash = transaction["_hash"].hex()
        transaction_receipt = transaction["receipt"]
        # if swap event available, transaction["swap_event"] shortcut added here
        event_counts, weth_in_swap = legit_check(transaction=transaction)
        swap_count = event_counts.get("Swap")

        if not weth_in_swap:
            # transaction not involving WETH as one of the swap tokens
            del transactions[transaction_idx]
        elif not swap_count or swap_count != 1:
            # number of swap event != 1
            del transactions[transaction_idx]
        else:
            transaction_idx += 1
            # add event counts to each transaction receipt in case it is useful later
            transaction_receipt['event_counts'] = event_counts

    # the list that records the set of identified (t1, t2)
    frontrunning_pairs: [FrontrunPair] = []
    t1_hashes, t2_hashes, transaction_gains = [], [], []
    t1_gases, t2_gases = [], []
    attack_count = 0

    for t1_idx in range(len(transactions)):
        t1 = transactions[t1_idx]
        t1_hash = t1["_hash"].hex().lower()
        if t1_hash in t1_hashes or t1_hash in t2_hashes:
            # each t1 is mapped to exactly 1 t2
            continue
        for t2_idx in range(t1_idx + 1, len(transactions)):
            t2 = transactions[t2_idx]
            t2_hash = t2["_hash"].hex().lower()
            if t2_hash in t1_hashes or t2_hash in t2_hashes:
                # each t1 is mapped to exactly 1 t2
                continue

            gains = get_swap_gains(t1, t2)
            if gains == -float("inf"):
                # the 2 cannot form frontrunning attack pair
                continue
            gains, t1_gas_cost, t2_gas_cost = gains

            # suspected frontrunning pair, output text
            pair = FrontrunPair(frontrun=t1, backrun=t2, gains=gains)
            frontrunning_pairs.append(pair)
            t1_hashes.append(t1_hash)
            t2_hashes.append(t2_hash)
            t1_gases.append(t1_gas_cost)
            t2_gases.append(t2_gas_cost)
            transaction_gains.append(gains)
            print_and_write_stat("*" * 80, fp=out_log)
            print_and_write_stat(f"Found frontrunning attack", fp=out_log)
            print_and_write_stat(pair, fp=out_log)
            print_and_write_stat("*" * 80, fp=out_log, end="\n\n")

            attack_count += 1

            # save the pair to folder, named with attack_count
            if save:
                pair.save(file_name=os.path.join(save_dir, f"{attack_count}.json"))
    end_time = time()

    if attack_count == 0:
        # no sandwich attack found
        text = f'Block {current_block["number"]} analyzed, \n' \
                f'total number of transactions in the block = {original_number},' \
                f' attacks found = {attack_count}.\n' \
                f'Time elapsed = {timedelta(seconds=(end_time - start_time))}\n\n'
        print_and_write_stat(text, fp=out_log)
        if out_log:
            out_log.close()

    if save:
        # save csv file
        df = pd.DataFrame(data={"t1": t1_hashes, "t1_gas_cost_wei": t1_gases, "t2": t2_hashes,
                                "t2_gas_cost_wei": t2_gases, "net_gains_wei": transaction_gains})
        df.to_csv(os.path.join(save_dir, name + "_" + "stats.csv"), index=False)

    text = f'Block {current_block["number"]} analyzed, \n' \
           f'total number of transactions in the block = {original_number},' \
           f' attacks found = {attack_count}, percentage = {(attack_count / original_number) * 100 :4f}%\n'
    text += f"max gain: {max(transaction_gains)} from Attack#{transaction_gains.index(max(transaction_gains)) + 1}\n"
    text += f"min gain: {min(transaction_gains)} from Attack#{transaction_gains.index(min(transaction_gains)) + 1}\n"
    text += f'Time elapsed = {timedelta(seconds=(end_time - start_time))}\n\n'
    text += f"t1's: {t1_hashes}\nt2's: {t2_hashes}\ngains: {transaction_gains}"
    print_and_write_stat(text, fp=out_log)
    if out_log:
        out_log.close()
