"""
The script that runs the frontrunning detection algorithm
"""
import sys
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
    df = None
    for block_number in input_blocks["block_number"]:
        if block_number < args.start_from:
            # to start from a particular block number
            continue
        print(f"Now starting to analyze block {block_number}")
        print(f"Pulling block {block_number}...")
        current_block = Infura.get_block(blockNum=block_number, deep=True)
        print(f"Pulling finished, now starting to analyze block {block_number}...")
        df = check_block_transactions(current_block=current_block, save=True, data_frame=df)
        df.to_csv(out_path, index=False)
        print(f"Checkpoint to block {block_number} saved.\n")
    print('Frontrunning analysis finished, now exit.')
