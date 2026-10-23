# BoardBridge Day 3 dataset starter

1. Copy `DATASET.md` to your repository root.
2. Copy `scripts/collect_zephyr_files.py` and `scripts/count_pages.py` into your repo's `scripts/` folder.
3. Run from the repository root:
   `python scripts/collect_zephyr_files.py --target 60`
4. Count the files:
   `python scripts/count_pages.py data/raw`
5. Commit the scripts and `DATASET.md`. Commit `data/raw/` only if your project policy allows it and you have reviewed the upstream licences.

The data collection step needs internet access and downloads files from the official Zephyr GitHub repository. The starter package does not pretend that 50 files have already been collected.
