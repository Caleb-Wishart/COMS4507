"""
The script that implements the algorithm to detect if a pair of transactions
form a frontrunning attack.
"""
import os.path
from utils.infura import *
from datetime import timedelta
import pandas as pd

# from https://etherscan.io/address/0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2
# used to check if the transaction has WETH has one of the swap tokens
WETH_contract_address = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"


class FrontrunPair:
    """
    The class the represents an identified fronrunning attack pair
    """

    def __init__(self, frontrun: dict, backrun: dict, gains: int, victim: dict = None,
                 victim_input_amount: int = None):
        """
            :param frontrun: The frontrunning transaction
            :param backrun: The backrunning transaction
            :param gains: The gains in wei (can be negative)
            :param victim: The victim transaction (if there exists one)
            :param victim_input_amount: the input amount of victim transaction (in wei)
        """
        assert frontrun["blockHash"] == backrun["blockHash"], \
            "Two transactions not belong to same block"
        if victim:
            assert backrun["blockHash"] == victim["blockHash"], \
                "Attacking transactions and victim transaction not located in the same block"
        self.frontrun = frontrun
        self.backrun = backrun
        self.victim = victim
        self.victim_input_amount = victim_input_amount
        self.gains = gains

    def __repr__(self):
        text = f'In block: {self.frontrun["blockHash"].hex()}\n' \
               f'gains: {self.gains}\n' \
               f'frontrunning transaction:\n' \
               f'tx_hash: {self.frontrun["_hash"].hex()}, from: {self.frontrun["_from"]}, ' \
               f'to: {self.frontrun["_to"]}\n' \
               f'backrunning transaction:\n' \
               f'tx_hash: {self.backrun["_hash"].hex()}, from: {self.backrun["_from"]},' \
               f' to: {self.backrun["_to"]}'
        if not self.victim:
            return text
        text += f"\nvictim transaction:\n" \
                f"tx_hash: {self.victim['_hash'].hex()}, from: {self.victim['_from']}, " \
                f"to: {self.victim['_to']},\n" \
                f"input amount = {self.victim_input_amount} wei"
        return text

    def save(self, file_name):
        """
        Save the 3 objects into 1 json file
        """
        if not file_name.endswith("json"):
            file_name = os.path.join(file_name, ".json")

        out = {"t1": self.backrun, "t2": self.frontrun, "net_gains": self.gains}
        if self.victim:
            out['tv'] = self.victim
            out["tv_input_amount"] = self.victim_input_amount

        with open(file_name, "w") as fp:
            fp.write(Infura.jsonify(out))


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
             (
                the amount of gains from the swap action,
                t1 gas cost,
                t2 gas cost
               ) tuple (in wei)
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
    t1_decoded_amounts = t1_swap_info["args"]
    # buy action in t1:
    # amount1In = amount sent for swap (ETH); amount0Out = amount received from swap
    t1_input, t1_output = \
        t1_decoded_amounts["amount1In"], t1_decoded_amounts["amount0Out"]

    t2_decoded_amounts = t2_swap_info["args"]
    # sell action in t2:
    # amount0In = amount sent for swap (== amount0Out of t1); amount1Out = amount received from swap (ETH)
    t2_input, t2_output = t2_decoded_amounts["amount0In"], t2_decoded_amounts["amount1Out"]

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


def get_token_transferred_or_deposited(transaction: dict) -> set:
    """
    Get the contract addresses appeared in the Deposit or Transfer events
    (ignore WETH's contract address)

    :param transaction: the transaction to check
    :return the set that includes the contract addresses other than WETH's
        that appeared in the Deposit or Transfer events
    """
    current_involved_contract_addresses = set()
    for decoded_info in transaction["transfer_deposit_events"]:
        contract_addr = decoded_info["address"]
        if contract_addr != WETH_contract_address:
            # ignore WETH contract address
            current_involved_contract_addresses.add(contract_addr)
    return current_involved_contract_addresses


def try_get_victim_transaction(current_block: dict, t1: dict, t2: dict,
                               involved_contract_addresses: set):
    """
    Call this when get_swap_gains(t1, t2) != - float("inf"),
    iterate through all transactions between the 2 transactions and try to find
    the victim transaction

    :param current_block: block that is analyzed
    :param t1: the suspected frontrunning transaction
    :param t2: the suspected backrunning transaction
    :param involved_contract_addresses: the set that records the contract addresses
        other than WETH address that was involved in Deposit and Transfer events of t1 and t2
    :return None if no suspected transaction found, otherwise the dict of victim_transaction
    """
    # suspected input amount in wei
    suspected, suspected_input_amount = None, None
    transactions = current_block["transactions"]

    for transaction in transactions:
        if transaction["index"] <= t1["index"]:
            continue
        elif transaction["index"] >= t2["index"]:
            break
        swap_info = transaction.get("swap_event")
        if swap_info:
            decoded_amounts = swap_info["args"]
            # buy action in victim transaction:
            # amount1In = amount sent for swap (ETH); amount0Out = amount received from swap
            input_amount, output_amount = \
                decoded_amounts["amount1In"], decoded_amounts["amount0Out"]
            if input_amount == 0:
                # this is not a buying action
                continue
            elif transaction["_from"] in [t1["_from"], t2["_from"]] or \
                    transaction["_to"] in [t1["_to"], t2["_to"]]:
                # same from/to address with attacking transactions
                continue

            current_involved_contract_addresses = get_token_transferred_or_deposited(transaction)
            if len(current_involved_contract_addresses & involved_contract_addresses) == 0:
                # no intersect between the involved contract addresses between the 3 transactions
                # (exclude WETH's contract address)
                continue

            # get greater amount as possible
            if not suspected or suspected_input_amount < input_amount:
                suspected = transaction
                suspected_input_amount = input_amount
    return suspected, suspected_input_amount


def legit_check(transaction: dict) -> tuple:
    """
    1. Count how many events exist in transaction receipt logs,
    add shortcut of the decoded Swap event to transaction dict, if possible
    2. ensure the one of the token is in WETH (only cares about swap of WETH)
    3. added transfer or deposit logs to transaction so later record the
        contract addresses and use that to determine what tokens are swapped exactly
    4. for each swap event, check it is formulated in standard form
        Swap (index_topic_1 address sender, uint256 amount0In, uint256 amount1In,
         uint256 amount0Out, uint256 amount1Out, index_topic_2 address to)

    :param transaction: The transaction to be processed
    :return
        (
        the dict that contains the count of each Event,
        whether the transaction contains at least a WETH related event,
        whether the Swap event is formulated in the standard form
         )
    """
    # add all transfer or deposit events here so we can add check contract addresses
    # to find out what tokens are swapped later
    transaction["transfer_deposit_events"] = []

    WETH_in_swap = False
    swap_format_correct = True

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

                if set(decode_info["args"].keys()) != {'sender', 'to', 'amount0In', 'amount1In',
                                                       'amount0Out', 'amount1Out'}:
                    # swap function not standardized
                    swap_format_correct = False
            elif event in ["Deposit", "Transfer"]:
                transaction["transfer_deposit_events"].append(decode_info)
    return res, WETH_in_swap, swap_format_correct


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


def check_block_transactions(current_block: Union[Block, dict], save: bool = False, data_frame=None,
                             save_dir: str = "./temp/frontrun/"):
    """
    Check all transactions in a block to find out suspected fronrunning
    attack pairs.

    Assumptions: we only check the transaction that has and only has ONE
    swap event

    :param current_block: The block to be checked
    :param save: whether the found frontrunning pairs are saved
    :param save_dir: the directory to be saved
    :param data_frame: the dataframe the records all detection info
    :return (data_frame, number of transactions scanned)
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
        transaction_hash = transaction["_hash"].hex()
        transaction_receipt = transaction["receipt"]
        # if swap event available, transaction["swap_event"] shortcut added here
        event_counts, weth_in_swap, swap_format_correct = legit_check(transaction=transaction)
        swap_count = event_counts.get("Swap")

        if not weth_in_swap:
            # transaction not involving WETH as one of the swap tokens
            del transactions[transaction_idx]
        elif not swap_count or swap_count != 1:
            # number of swap event != 1
            del transactions[transaction_idx]
        elif not swap_format_correct:
            # swap function not standardized
            del transactions[transaction_idx]
        else:
            transaction_idx += 1
            # add event counts to each transaction receipt in case it is useful later
            transaction_receipt['event_counts'] = event_counts

    # the list that records the set of identified (t1, t2)
    frontrunning_pairs: [FrontrunPair] = []
    # lists that record hashes of t1, t2, victim transaction as well as transaction gains of each attack
    t1_hashes, t2_hashes, transaction_gains = [], [], []
    victim_hashes, victim_input_amounts = [], []
    # lists that record gas fees of the frontrunning and backrunning transactions
    t1_gases, t2_gases = [], []
    # lists that record the to and from address of the frontrunning and backrunning transactions
    t1_to_lists, t1_from_lists = [], []
    t2_to_lists, t2_from_lists = [], []

    attack_count = 0

    for t1_idx in range(len(transactions)):
        t1 = transactions[t1_idx]
        t1_hash = t1["_hash"].hex()

        if t1_hash in t1_hashes or t1_hash in t2_hashes or t1_hash in victim_hashes:
            # each t1 is mapped to exactly 1 t2
            continue

        t1_token_addresses = get_token_transferred_or_deposited(t1)

        for t2_idx in range(t1_idx + 1, len(transactions)):
            t2 = transactions[t2_idx]
            t2_hash = t2["_hash"].hex()
            if t2_hash in t1_hashes or t2_hash in t2_hashes or t2_hash in victim_hashes:
                # each t1 is mapped to exactly 1 t2
                continue

            t2_token_addresses = get_token_transferred_or_deposited(t2)

            involved_addresses = t1_token_addresses & t2_token_addresses
            if len(involved_addresses) == 0:
                # tokens no intersect, not possible to be a pair
                continue

            res = get_swap_gains(t1, t2)
            if res == -float("inf"):
                # the 2 cannot form frontrunning attack pair
                continue
            gains, t1_gas_cost, t2_gas_cost = res

            tv, tv_input_amount = try_get_victim_transaction(current_block=current_block, t1=t1, t2=t2,
                                                             involved_contract_addresses=involved_addresses)

            # suspected frontrunning pair, output text
            pair = FrontrunPair(frontrun=t1, backrun=t2, gains=gains, victim=tv, victim_input_amount=tv_input_amount)

            # update the lists above
            frontrunning_pairs.append(pair)
            t1_hashes.append(t1_hash)
            t2_hashes.append(t2_hash)
            t1_gases.append(t1_gas_cost)
            t2_gases.append(t2_gas_cost)
            transaction_gains.append(gains)
            t1_to_lists.append(t1["_to"])
            t2_to_lists.append(t2['_to'])
            t1_from_lists.append(t1["_from"])
            t2_from_lists.append(t2["_from"])
            victim_hashes.append(tv['_hash'].hex() if tv else "")
            victim_input_amounts.append(tv_input_amount if tv_input_amount else "")

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
        # no sandwich attack found, return early in case encounter error when
        # doing min(), max() call on empty arrays
        text = f'Block {current_block["number"]} analyzed, \n' \
               f'total number of transactions in the block = {original_number},' \
               f' attacks found = {attack_count}.\n' \
               f'Time elapsed = {timedelta(seconds=(end_time - start_time))}\n\n'
        print_and_write_stat(text, fp=out_log)
        if out_log:
            out_log.close()
        return data_frame, original_number

    if save:
        # save csv file
        df = pd.DataFrame(data={"block_num": [current_block["number"]] * len(t1_hashes),
                                "t1": t1_hashes, "t1_from": t1_from_lists,
                                "t1_to": t1_to_lists, "t1_gas_cost_wei": t1_gases,
                                "t2": t2_hashes, "t2_from": t2_from_lists, "t2_to": t2_to_lists,
                                "t2_gas_cost_wei": t2_gases, "net_gains_wei": transaction_gains,
                                "tv": victim_hashes, "tv_input_amount_wei": victim_input_amounts})
        df.to_csv(os.path.join(save_dir, name + "_" + "stats.csv"), index=False)

        if data_frame is not None:
            # if dataframe exists, then concat it
            assert list(data_frame.columns) == list(df.columns), \
                f"DataFrame's columns: {data_frame.columns}\n" \
                f"df's columns: {df.columns}"
            data_frame = pd.concat([data_frame, df])
        else:
            data_frame = df

    tv_count = len([_ for _ in victim_hashes if _ != ""])
    max_tv_input = max([_ for _ in victim_input_amounts if _ != ""], default=0)

    text = f'Block {current_block["number"]} analyzed, \n' \
           f'total number of transactions in the block = {original_number},' \
           f' attacks found = {attack_count}, percentage = {(attack_count / original_number) * 100 :4f}%.\n'
    text += f"max gain: {max(transaction_gains)} from Attack#{transaction_gains.index(max(transaction_gains)) + 1};\n"
    text += f"min gain: {min(transaction_gains)} from Attack#{transaction_gains.index(min(transaction_gains)) + 1}.\n"
    text += f"most frequent t1 to address: {max(t1_from_lists, key=t1_from_lists.count)};\n" \
            f"most frequent t1 from address: {max(t1_to_lists, key=t1_to_lists.count)}.\n"
    text += f"most frequent t2 to address: {max(t2_from_lists, key=t2_from_lists.count)};\n" \
            f"most frequent t2 from address: {max(t2_to_lists, key=t2_to_lists.count)}.\n"
    text += f"Number of victim transactions = {tv_count}, max victim transaction input = {max_tv_input}.\n"
    text += f'Time elapsed = {timedelta(seconds=(end_time - start_time))}.\n\n'
    text += f"t1's: {t1_hashes}\nt2's: {t2_hashes}\ngains: {transaction_gains}"
    print_and_write_stat(text, fp=out_log)
    if out_log:
        out_log.close()
    return data_frame, original_number
