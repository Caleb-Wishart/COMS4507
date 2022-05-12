<img src="./static/sandwich_attack_banned.png" width="200">

# COMS4507-Project: Frontrunning and Insertion Attacks Detection Tool
 This repo contains the code segment for COMS4507 Project *Frontrunning and Sandwich attacks in Ethereum*.
 
The implemented component can be split into 3 parts:
1. random block sampling tool [sample_blocks](./sample_blocks.py).
2. frontrunning attack detection tool [frontrun_runner](./frontrun_runner.py)
3. insertion attack detection tool ... #todo



# Block sampling
This [script](./sample_blocks.py) provides functionality to sample blocks from a full block info dataset.
Usage:

```shell
python3 sample_blocks.py -seed 1 -days_tp_monitor 7 -sample_size 10 \
-first_start_timestamp 2022-04-29 00:00:00 \
-first_end_timestamp 2022-04-29 23:59:59 \
-all_blocks_csv ./data/blocks_0429_0505.csv \
-sample_file_name ./temp/sample_blocks.csv
```
Example full blocks info between Apr 29 and May 5 is available in [blocks_0429_0505.csv](./data/blocks_0429_0505.csv).



# Frontrunning detection
This [script](./frontrun_runner.py) is the runner of the sandwich attack detection tool.
Algorithm can be found in [here](./utils/frontrun_algorithm.py).


Heuristics for sandwich attack detection (adpated from [Züst, 2021](https://pub.tik.ee.ethz.ch/students/2021-FS/BA-2021-07.pdf)):
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
-output_dir ./temp/frontrun/
```

### Backtesting
- Frontrunning detection log of example can be found in [frontrun_records.csv](./temp/frontrun/frontrun_records.csv).
Full transaction object of detected frontrunning instances are named as *block_blocknum* and can be found in [here](./temp/frontrun/).

- Some stats and result visualization are prepared in [frontrun_record_analysis.ipynb](./frontrun_record_analysis.ipynb).

