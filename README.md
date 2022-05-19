<img src="./static/sandwich_attack_banned.png" width="200">

# COMS4507-Project: Insertion and Suppression Attacks Detection Tool
 This repo contains the code segment for COMS4507 Project *Frontrunning and Sandwich attacks in Ethereum*.

The implemented component can be split into 3 parts:
1. random block sampling tool [sample_blocks](./sample_blocks.py).
2. frontrunnig attack detection tool [frontrun_runner](./frontrun_runner.py)
3. quick testing / example tool [quick_test](./quick_test.py)


# Block sampling
[sample_blocks](./sample_blocks.py) provides functionality to sample blocks from a full block info dataset.
Usage:

```shell
python3 sample_blocks.py -seed 1 -days_tp_monitor 7 -sample_size 10 \
-first_start_timestamp 2022-04-29 00:00:00 \
-first_end_timestamp 2022-04-29 23:59:59 \
-all_blocks_csv ./data/blocks_0429_0505.csv \
-sample_file_name ./temp/sample_blocks.csv
```
Example full blocks info for 1-week time frame between Apr 29, 2022 and May 5, 2022 is available in [blocks_0429_0505.csv](./data/blocks_0429_0505.csv).


# Insertion Attack Detection
[frontrun_runner](./frontrun_runner.py) is the runner of the sandwich attack detection tool.
Algorithm can be found in [here](./utils/frontrun_algorithm.py).

Heuristics for insertion attack detection (adpated from [Züst, 2021](https://pub.tik.ee.ethz.ch/students/2021-FS/BA-2021-07.pdf)):
```
t1: frontrunning transaction
t2: backrunning transaction
tv: victim transaction
```

- t1 is a transaction that swaps ETH with other tokens (i.e. t1 is a buy action)
- consider transaction that includes only ONE swap event in the transaction event
- each t2 is mapped to exactly ONE t1
- victim transaction not required
- swap event in the transaction log is formulated in standard form `Swap(index_topic_1 address sender, uint256 amount0In, uint256 amount1In,
         uint256 amount0Out, uint256 amount1Out, index_topic_2 address to)`.

Usage:

```shell
python3 frontrun_runner.py \
-input_blocks_file ./temp/sample_blocks.csv \
-output_dir ./temp/insertion_attack/
```
# Suppression Attack Detection
[frontrun_runner](./frontrun_runner.py) is also the runner of the suppression attack detection tool.
Algorithm can be found in [here](./utils/frontrun_algorithm.py).

Heuristics for an Supression attack detection (adpated from [Torres, Camino, State, 2021](https://www.usenix.org/system/files/sec21-torres.pdf)).
```
We 'cluster' together the transactions done by particular users in the block
```
- The number of transactions in the cluster must be larger than 5.
- all transactions in the cluster have consumed more than 21,000 gas units each.
- The ratio between gas used and gas limit must be larger than 99.9% for all transactions in the cluster.
- We do not require the use of any particular technique to include potential new commers to the scene
- We do not require the precense of a victim transaction

### Backtesting
- Insertion attack detection log of example can be found in [insertion_attack_records.csv](temp/insertion_attack/insertion_attack_records.csv).
Full transaction object of detected insertion attack instances are named as *block_blocknum* and can be found in [here](temp/insertion_attack/).

- Some stats and result visualization are prepared in [insertion_attack_record_analysis.ipynb](./insertion_attack_record_analysis.ipynb).

# Quick Testing
[quick_test](./quick_test.py) provides functionality to quickly show an example result of running the program.

This file uses a given json file with saved block data instead of querying the Etherscan API for data.

Usage:

```shell
python3 ./quick_test.py -input_blocks_file="./temp/example_block.json"
```

An an example saved block file is available in [example_block.json](./temp/example_block.json).

This contains the data for 4 different blocks that had different identified attacks.
The example should contain 6 attacks, 3 suppression and 3 insertion.