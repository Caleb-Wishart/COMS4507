"""
The script that runs the sandwich detection algorithm
"""
import datetime
import sys
import traceback
import pandas as pd
import requests.exceptions
from utils.frontrun_algorithm import *
from argparse import ArgumentParser
import os


def switch_keys():
    """
    The functon that toggles the keys for Infura and Etherscan
    """
    if Infura.INFURA_API_KEY == jason_infura_key:
        print("Currently using Jason's key, now try Caleb's")
        Infura.INFURA_API_KEY = caleb_infura_key
        Infura.ETHERSCAN_API_KEY = caleb_etherscan_key
    else:
        print("Currently using Caleb's key, now try Jason's")
        Infura.INFURA_API_KEY = jason_infura_key
        Infura.ETHERSCAN_API_KEY = jason_etherscan_key
    Infura.w3 = Web3(Web3.HTTPProvider(
        f'https://mainnet.infura.io/v3/{Infura.INFURA_API_KEY}'))


if __name__ == "__main__":
    # error handling config
    # error count == 2 then exceeds quota
    error_count = 0
    error_time = None
    jason_infura_key = "ee4c35b8c3114586a74eda3b8b634228"
    jason_etherscan_key = "2JPX8EJNBE2USI1VDBHJPTCGG994ERQ6QZ"
    caleb_infura_key = 'b07f1f09ee5443c6b89fcfd1a4300fbc'
    caleb_etherscan_key = 'AMD3PDCXAPI6WKK8VJ6VGAZB5XJB2UHV1U'

    parser = ArgumentParser()
    parser.add_argument("-input_blocks_file", type=str, default="./temp/sample_blocks.csv",
                        help="The file that records all the blocks that needed to undertake"
                             "insertion attack detection")
    parser.add_argument("-output_dir", type=str, default="./temp/insertion_attack/",
                        help="The directory where the output files will be stored")
    parser.add_argument("-supp_output_dir", type=str, default="./temp/supression_attack/",
                        help="The directory where the supression attack output files will be stored")
    parser.add_argument("-start_from", type=int, default=-1,
                        help="The block number to start from")

    args = parser.parse_args()

    if not os.path.exists(args.input_blocks_file):
        print("Input blocks file does not exist", file=sys.stderr)
        exit(1)
    if not os.path.exists(args.output_dir):
        os.mkdir(args.output_dir)

    input_blocks = pd.read_csv(args.input_blocks_file)
    print(f"Total number of blocks to be analyzed = {len(input_blocks)}")

    out_path = os.path.join(args.output_dir, "insertion_attack_records.csv")
    if os.path.exists(out_path) and args.start_from != -1:
        # resume previous work
        print("Found previous dataset, now try to load and resume.")
        df = pd.read_csv(out_path)
        assert max(df["block_num"]) < args.start_from, \
            f"latest record in {out_path} is block later than current starting block {args.start_from}."
    else:
        # start up new df
        df = None
    sup_out_path = os.path.join(args.supp_output_dir, "supression_attack_records.csv")
    if os.path.exists(sup_out_path) and args.start_from != -1:
        # resume previous work
        print("Found previous dataset, now try to load and resume.")
        df_sup = pd.read_csv(sup_out_path)
        assert max(df_sup["block_num"]) < args.start_from, \
            f"latest record in {sup_out_path} is block later than current starting block {args.start_from}."
    else:
        # start up new df
        df_sup = None

    block_count = 0
    transaction_count = 0
    start_time = time()
    for block_number in input_blocks["block_number"]:
        if block_number < args.start_from:
            # to start from a particular block number
            continue
        print(f"Now starting to analyze block {block_number}")
        print(f"Pulling block {block_number}...")
        retrieve_time = time()

        current_block = None
        try:
            current_block = Infura.get_block(blockNum=block_number, deep=True)
        except requests.exceptions.HTTPError as e:
            traceback.print_exc()
            if error_count == 0:
                switch_keys()

                error_count += 1
                error_time = datetime.datetime.utcnow()
                current_block = Infura.get_block(blockNum=block_number, deep=True)
            elif error_time and error_time.day != datetime.datetime.utcnow().day:
                # since last error not in the same day
                error_count = 0
                error_time = None

                switch_keys()
                current_block = Infura.get_block(blockNum=block_number, deep=True)
            else:
                # error twice with interval less than one day
                print("error occurred more than once", file=sys.stderr)
                exit(1)
        print(f"Pulling finished in {timedelta(seconds=time() - retrieve_time)}, now starting to analyze block {block_number} for insertion attacks...")
        df, t_count1 = insertion_check_block_transactions(current_block=current_block, save=True,
                                               data_frame=df, save_dir=args.output_dir)
        print(f"Insertion analysis finished, now starting to analyze block {block_number} for supression attacks...")
        df_sup, t_count2 = supression_check_block_transactions(current_block=current_block, save=True,
                                               data_frame=df_sup, save_dir=args.supp_output_dir)
        if t_count1 != t_count2:
            print(f"Unexpected error: Transaction counts are not the same -> insertion({t_count1}), supression({t_count2})")
        t_count =  t_count1
        block_count += 1
        transaction_count += t_count
        if df is not None:
            df.to_csv(out_path, index=False)
            print(f"Checkpoint to block {block_number} saved for insertion attack.\n")
        if df_sup is not None:
            df_sup.to_csv(sup_out_path, index=False)
            print(f"Checkpoint to block {block_number} saved for supression attack.\n")
    end_time = time()
    print(f'Number of blocks analyzed = {block_count}, number of transactions scanned = {transaction_count}.\n'
          f'Insertion attack analysis finished, now exit.\nProgram elapsed time ='
          f' {timedelta(seconds=end_time - start_time)}')
