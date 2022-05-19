"""
The script that runs an example frontrunning detection algorithm
"""
import sys

from utils.frontrun_algorithm import *
from argparse import ArgumentParser
import os

# temp/example_block.json generated with:
#    block = Infura.get_block("0xb720a918a1892b1ba1d5921c674a09c3f391cc3c078f08f49a69cad26f2690cd",deep=True)
#    block1 = Infura.get_block("0xc41cb10e1533c0443dba2c1bf8e5758cbc71b2f3431b9060041a86fbb44cb168",deep=True)
#    with open('temp/example_block.json', 'w') as f:
#        Infura.save_data(f, [block, block1])

if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("-input_blocks_file", type=str, default="./temp/example_block.json",
                        help="The file that has saved blocks that needed to be"
                             "analysed for attack detection")
    args = parser.parse_args()

    if not os.path.exists(args.input_blocks_file):
        print("Input blocks file does not exist", file=sys.stderr)
        exit(1)

    data = Infura.load_data(args.input_blocks_file)
    print(f"Total number of blocks to be analyzed = {len(data)}")

    block_count = 0
    transaction_count = 0
    start_time = time()
    for rawBlock in data:
        retrieve_time = time()
        current_block = Block(rawBlock, False, decode=True)
        block_number = current_block.number
        print(f"Building {block_number} finished in {timedelta(seconds=time() - retrieve_time)}, now starting to analyze block {block_number} for insertion attacks...")
        _, t_count1 = insertion_check_block_transactions(current_block=current_block)
        print(f"Insertion analysis finished, now starting to analyze block {block_number} for supression attacks...")
        _, t_count2 = supression_check_block_transactions(current_block=current_block, num_tran=3,min_eth=0.25)
        if t_count1 != t_count2:
            print(f"Unexpected error: Transaction counts are not the same -> insertion({t_count1}), supression({t_count2})")
        t_count =  t_count1
        block_count += 1
        transaction_count += t_count
        print(f"Supression analysis finished\n\n")

    end_time = time()
    print(f'Number of blocks analyzed = {block_count}, number of transactions scanned = {transaction_count}.\n'
          f'Insertion attack analysis finished, now exit.\nProgram elapsed time ='
          f' {timedelta(seconds=end_time - start_time)}')
