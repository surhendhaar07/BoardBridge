#!/usr/bin/env python3
"""Collect a focused subset of Zephyr RTOS files into data/raw/.

Example:
    python scripts/collect_zephyr_files.py --target 60
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

API_TREE = "https://api.github.com/repos/zephyrproject-rtos/zephyr/git/trees/{ref}?recursive=1"
RAW_BASE = "https://raw.githubusercontent.com/zephyrproject-rtos/zephyr/{ref}/"

# Prefer files that support the project's 10 evaluation questions.
PREFERRED_PATHS = (
    "samples/sensor/bme280/",
    "drivers/sensor/bosch/bme280/",
    "dts/bindings/sensor/",
    "samples/drivers/pwm/",
    "dts/bindings/pwm/",
    "drivers/can/",
    "samples/drivers/can/",
    "samples/basic/button/",
    "samples/basic/blinky/",
    "drivers/console/",
    "subsys/console/",
    "dts/bindings/spi/",
    "doc/hardware/porting/",
    "boards/nordic/nrf52840dk/",
    "boards/",
)

ALLOWED_NAMES = {"Kconfig", "prj.conf", "CMakeLists.txt"}
ALLOWED_SUFFIXES = {
    ".c", ".h", ".yaml", ".yml", ".dts", ".dtsi", ".overlay",
    ".rst", ".md", ".txt", ".conf",
}


def request_json(url: str) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "BoardBridge-dataset-collector",
        },
    )
    with urllib.request.urlopen(req, timeout=45) as response:
        return json.loads(response.read().decode("utf-8"))


def download_text(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "BoardBridge-dataset-collector"})
    with urllib.request.urlopen(req, timeout=45) as response:
        return response.read()


def is_candidate(path: str) -> bool:
    name = Path(path).name
    return name in ALLOWED_NAMES or Path(path).suffix.lower() in ALLOWED_SUFFIXES


def priority(path: str) -> tuple[int, int, str]:
    for index, prefix in enumerate(PREFERRED_PATHS):
        if path.startswith(prefix):
            return (0, index, path)
    return (1, 999, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=int, default=60, help="number of files to collect (default: 60)")
    parser.add_argument("--ref", default="main", help="Git branch, tag, or commit SHA (default: main)")
    parser.add_argument("--out", default="data/raw", help="output directory (default: data/raw)")
    args = parser.parse_args()

    if args.target < 50:
        print("Warning: the task requires 50+ files; consider --target 60 or higher.", file=sys.stderr)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    api_url = API_TREE.format(ref=args.ref)
    print(f"Reading repository tree: {api_url}")
    try:
        tree_data = request_json(api_url)
    except urllib.error.HTTPError as exc:
        print(f"GitHub API error: {exc}. Try again later or use a pinned commit SHA.", file=sys.stderr)
        return 1
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"Network error: {exc}", file=sys.stderr)
        return 1

    tree = tree_data.get("tree", [])
    candidates = [
        item["path"] for item in tree
        if item.get("type") == "blob" and is_candidate(item.get("path", ""))
    ]
    candidates.sort(key=priority)

    downloaded = 0
    failures: list[tuple[str, str]] = []
    for path in candidates:
        if downloaded >= args.target:
            break
        destination = out_dir / path
        if destination.exists() and destination.stat().st_size > 0:
            downloaded += 1
            continue

        destination.parent.mkdir(parents=True, exist_ok=True)
        url = RAW_BASE.format(ref=args.ref) + path
        try:
            content = download_text(url)
            # Avoid saving obvious Git LFS pointer stubs as if they were real source files.
            if content.startswith(b"version https://git-lfs.github.com/spec/v1"):
                failures.append((path, "Git LFS pointer; skipped"))
                continue
            destination.write_bytes(content)
            downloaded += 1
            print(f"[{downloaded}/{args.target}] {path}")
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            failures.append((path, str(exc)))
            if isinstance(exc, urllib.error.HTTPError) and exc.code == 404:
                continue
            time.sleep(0.2)

    print(f"\nCollected/reused {downloaded} files in {out_dir}")
    if failures:
        print(f"{len(failures)} file(s) could not be downloaded:")
        for path, reason in failures[:15]:
            print(f"  - {path}: {reason}")

    if downloaded < 50:
        print("Target not met: fewer than 50 files are present. Re-run with internet access or a different --ref.", file=sys.stderr)
        return 2

    print("Target met: at least 50 files collected/reused.")
    print("Next: python scripts/count_pages.py data/raw")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
