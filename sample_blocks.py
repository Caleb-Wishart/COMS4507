"""
The script that samples the blocks from a block dataset

Example data: use data from Apr 29 to May 5
"""
import os.path
import sys

from utils.infura import *
import pandas as pd
import random
from argparse import ArgumentParser


def get_time_intervals(days: int, first_start: str, first_end: str) -> list:
    """
    Generate a list of pd.TimeStamp pairs of the starting timestamp and ending timestamp

    :param days: the number of days to be generated (including first start and end stamps)
    :param first_start: the first starting timestamp
    :param first_end: the first ending timestamp
    :return the list that contains all starting and ending stamp
    """
    if days <= 0:
        return []
    start_stamp, end_stamp = pd.Timestamp(first_start), pd.Timestamp(first_end)
    intervals = [(start_stamp, end_stamp)]
    # increment by 1 day
    inc = pd.Timedelta(1, "d")
    for _ in range(days - 1):
        last_start, last_end = intervals[-1]
        intervals.append((last_start + inc, last_end + inc))
    return intervals


def draw_random_blocks(n: int, all_blocks: pd.DataFrame,
                       intervals: list, sort_blocks: bool = True,
                       extra_blocks: dict = None) -> pd.DataFrame:
    """
    Randomly draw n samples from all_blocks for each interval

    :param extra_blocks: in form of start_timestamp: set of blocks to be added manually for that
                            specific time period
    :param n: the number of samples for each time period
    :param all_blocks: the df that contains all candidate blocks
    :param intervals: the list of all intervals to get sample on
    :param sort_blocks: whether the return block numbers are sorted
    :return the new df that contains all sampled block numbers
    """
    blocks = []
    for start_inv, end_inv in intervals:
        if extra_blocks:
            extra = list(extra_blocks[start_inv])
        else:
            extra = []
        sample_num = n - len(extra)
        if sample_num <= 0:
            # extra ones already exceeds n limit
            blocks += extra[:n]
            continue
        current_df = all_blocks[(all_blocks["time"] >= start_inv) & (all_blocks["time"] <= end_inv)]
        # find complement of extra
        current_df = current_df[~current_df.isin(extra)]
        if len(current_df) < sample_num:
            # no enough search space to sample, add all
            extra += list(current_df["id"])
        else:
            samples = current_df["id"].sample(n=sample_num, random_state=seed)
            extra += [int(_) for _ in samples]
        blocks += extra
    df = pd.DataFrame.from_dict(data={"block_number": blocks})
    if sort_blocks:
        df = df.sort_values(ascending=True, by="block_number")
    return df


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("-seed", type=int, default=1, help="The random seed")
    parser.add_argument("-days_to_monitor", type=int, default=7,
                        help="The number of days to be monitor")
    parser.add_argument("-sample_size", default=100, type=int,
                        help="The number of samples generated for each time period.")
    parser.add_argument("-first_start_timestamp", type=str,
                        default="2022-04-29 00:00:00",
                        help="The starting timestamp to be evaluated."
                             " In form of YYYY-MM-DD HH-MM-SS")
    parser.add_argument("-first_end_timestamp", type=str,
                        default="2022-04-29 23:59:59",
                        help="The starting timestamp to be evaluated."
                             " In form of YYYY-MM-DD HH-MM-SS")
    parser.add_argument("-all_blocks_csv", type=str,
                        default="./data/blocks_0429_0505.csv",
                        help="The file where all blocks data are stored.")
    parser.add_argument('-sample_file_name', type=str,
                        default="./temp/sample_blocks.csv",
                        help="The name of the sampled df to be stored.")
    args = parser.parse_args()

    if not os.path.exists(args.all_blocks_csv):
        print(f"Please ensure csv file with all blocks are located in {args.all_blocks_csv}", file=sys.stderr)
        exit(1)

    # sample size
    sample_size = args.sample_size

    # random seed
    seed = args.seed
    random.seed(seed)

    # number of days to be
    total_days = args.days_to_monitor
    # get all time intervals
    time_intervals = get_time_intervals(days=total_days,
                                        first_start=args.first_start_timestamp,
                                        first_end=args.first_end_timestamp)

    block_log_file = args.all_blocks_csv
    block_df = pd.read_csv(block_log_file)
    block_df["time"] = pd.to_datetime(block_df.time, format="%Y-%m-%d %H:%M:%S")

    # now generate samples and save
    out = draw_random_blocks(n=sample_size, all_blocks=block_df,
                             intervals=time_intervals)
    prev_save_path = args.sample_file_name.rsplit('/', 1)[0]
    if not os.path.exists(prev_save_path):
        os.mkdir(prev_save_path)

    out.to_csv(args.sample_file_name, index=False)
    print(f"Sampled file with size of {len(out)} generated and stored in {args.sample_file_name}.")
