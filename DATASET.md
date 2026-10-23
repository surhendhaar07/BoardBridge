# BoardBridge Dataset

## Source

- **Project:** Zephyr RTOS
- **Repository:** https://github.com/zephyrproject-rtos/zephyr
- **Raw-file source:** https://raw.githubusercontent.com/zephyrproject-rtos/zephyr/main/
- **Collection script:** `scripts/collect_zephyr_files.py`
- **Target:** At least 50 source/documentation files under `data/raw/`

## Why this dataset?

BoardBridge helps firmware engineers locate Zephyr drivers, devicetree bindings, Kconfig options, board definitions, samples, and documentation. The collected subset focuses on examples related to sensors, PWM, CAN, GPIO, UART, SPI, Blinky, and board porting.

## File types

The collector selects relevant repository files such as:

- C source and header files: `.c`, `.h`
- Devicetree and overlays: `.dts`, `.dtsi`, `.overlay`
- Bindings and configuration: `.yaml`, `.yml`, `.conf`, `Kconfig`
- Documentation: `.rst`, `.txt`, `.md`

Text/code files are counted as **files**, not pages. `count_pages.py` counts source files and, if PDF files are added later, counts their physical pages when the optional `pypdf` package is installed.

## Collect the dataset

From the repository root, run:

```bash
python scripts/collect_zephyr_files.py --target 60
python scripts/count_pages.py data/raw
```

The collector uses GitHub's public repository tree API to discover relevant files and downloads them from the official Zephyr repository. An internet connection is required. If GitHub's API rate limit is reached, wait and run the collector again.

## Reproducibility and licence

The default source URL tracks the `main` branch, so the exact content can change over time. For reproducible experiments, record the commit SHA used for collection and pin the collector to that revision.

Zephyr is generally distributed under Apache-2.0, but individual files and third-party components may carry different notices or licences. Preserve source headers and verify the licence of files before redistributing them. This dataset is intended for research and development; consult the upstream repository's licence files and individual file headers.

## Dataset inventory

- Collection date: 2026-10-23
- Zephyr revision/commit: 2a9e8ac155a3f2fd85d4559753be86a47b44ccf0
- Files collected: 60
- PDF pages, if any: nil