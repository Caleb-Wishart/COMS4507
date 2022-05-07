"""
The script that runs the frontrunning detection algorithm
"""
import sys
import pandas as pd
from utils.frontrun_algorithm import *
from argparse import ArgumentParser
import os


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("-input_blocks_file", type=str, default="./temp/sample_blocks.csv",
                        help="The file that records all the blocks that needed to undertake"
                             "frontrunning attack detection")
    parser.add_argument("-output_dir", type=str, default="./temp/frontrun/",
                        help="The directory where the output files will be stored")
    parser.add_argument("-start_from", type=int, default=-1,
                        help="The block number to start from")

    args = parser.parse_args()

    if not os.path.exists(args.input_blocks_file):
        print("Input blocks file does not exist", file=sys.stderr)
        exit(1)

    input_blocks = pd.read_csv(args.input_blocks_file)
    print(f"Total number of blocks to be analyzed = {len(input_blocks)}")

    out_path = os.path.join(args.output_dir, "frontrun_records.csv")
    if os.path.exists(out_path) and args.start_from != -1:
        # resume previous work
        print("Found previous dataset, now try to load and resume.")
        df = pd.read_csv(out_path)
        assert max(df["block_num"]) < args.start_from, \
            f"latest record in {out_path} is block later than current starting block {args.start_from}."
    else:
        # start up new df
        df = None

    block_count = 0
    transaction_count = 0
    start_time = time()
    for block_number in input_blocks["block_number"]:
        if block_number < args.start_from:
            # to start from a particular block number
            continue
        print(f"Now starting to analyze block {block_number}")
        print(f"Pulling block {block_number}...")
        current_block = Infura.get_block(blockNum=block_number, deep=True)
        print(f"Pulling finished, now starting to analyze block {block_number}...")
        df, t_count = check_block_transactions(current_block=current_block, save=True, data_frame=df)
        block_count += 1
        transaction_count += t_count
        if df is not None:
            df.to_csv(out_path, index=False)
            print(f"Checkpoint to block {block_number} saved.\n")
        else:
            print(f"No detected transactions after analyzed {block_number}")
    end_time = time()
    print(f'Number of blocks analyzed = {block_count}, number of transactions scanned = {transaction_count}.\n'
          f'Frontrunning analysis finished, now exit.\nProgram elapsed time ='
          f' {timedelta(seconds=end_time - start_time)}')
