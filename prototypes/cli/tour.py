# /// script
# requires-python = ">=3.11"
# dependencies = ["typer>=0.27", "pydantic>=2.11"]
# ///
"""PROTOTYPE, throwaway: run each scenario of the CLI prototype, and show what it prints and writes.

Run `uv run prototypes/cli/tour.py` for every scenario, or pass their numbers, such as `tour.py 5 6`.
Each command runs in a scratch folder, against the simulated API in `fake_oxy`, so nothing bills.
"""

# ruff: noqa: D103, S602, T201
# pyrefly: ignore-errors

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import fake_oxy

HERE = Path(__file__).resolve().parent
BOLD, DIM, RESET = "\x1b[1m", "\x1b[2m", "\x1b[0m"
LINES, WIDTH = 12, 140
URLS = "printf 'https://sandbox.oxylabs.io/products/1\\nhttps://sandbox.oxylabs.io/products/2\\nhttps://sandbox.oxylabs.io/FAULT\\nhttps://sandbox.oxylabs.io/SLOW\\nhttps://sandbox.oxylabs.io/products/3\\n'"
SCENARIOS = [
    ("Help", ["oxy --help", "oxy run --help"]),
    (
        "One job, printed to stdout",
        ["oxy run amazon_product B07FZ8S74R --parse --domain de"],
    ),
    (
        "Mistakes raise before anything bills",
        [
            "oxy run amazon_search 'usb c cable' -p sort_bu=price_low_to_high",
            "oxy run amazon_product B07FZ8S74 --parse",
            "oxy run amazon_product B07FZ8S74R --render pdf",
        ],
    ),
    (
        "A dry run prints payloads to stdout and totals to stderr",
        [
            "printf 'B07FZ8S74R\\nB0BSHF7WHW\\n' | oxy run amazon_product --parse --pages 2 --dry-run"
        ],
    ),
    (
        "Inputs from stdin, into a destination",
        [f"{URLS} | oxy run universal -d results", "find results -type f | sort"],
    ),
    (
        "The same command again resumes the run",
        [f"{URLS} | oxy run universal -d results", "find results -type f | sort"],
    ),
    (
        "A third run, to retry the faulted job, submits every payload again",
        [f"{URLS} | oxy run universal -d results", "find results -type f | sort"],
    ),
    (
        "Payloads as JSON lines, such as a dry run's output",
        [
            "printf 'usb c cable\\nhdmi cable\\n' | oxy run amazon_search -p sort_by=price_low_to_high --dry-run > payloads.jsonl",
            "cat payloads.jsonl",
            "oxy run --parse < payloads.jsonl",
        ],
    ),
    (
        "Cloud Storage, with a working bucket and a wrong one",
        [
            "oxy run amazon_product B07FZ8S74R B0BSHF7WHW --storage-type gcs --storage-url my-bucket/amazon",
            "oxy run amazon_product B07FZ8S74R B0BSHF7WHW B0CHX1W1XY --storage-type gcs --storage-url wrong-bucket/amazon",
        ],
    ),
    (
        "A source the API rejects, and a wrong password",
        [
            "oxy run amazon_prodcut B07FZ8S74R",
            "OXY_WSA_PASSWORD=wrong oxy run amazon_product B07FZ8S74R",
        ],
    ),
    (
        "A job by ID, and a Realtime run",
        [
            "oxy get $(basename $(ls results/*.json | head -1) .json)",
            "oxy run universal https://sandbox.oxylabs.io/products/9 --realtime",
        ],
    ),
]


def main() -> None:
    chosen = [int(arg) for arg in sys.argv[1:]] or range(1, len(SCENARIOS) + 1)
    scratch = fake_oxy.STATE / "tour"
    if 1 in chosen or not sys.argv[1:]:
        shutil.rmtree(fake_oxy.STATE, ignore_errors=True)
    scratch.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "OXY_WSA_USERNAME": "USERNAME", "OXY_WSA_PASSWORD": "PASSWORD"}
    oxy = f'oxy() {{ "{sys.executable}" "{HERE / "cli.py"}" "$@"; }}; '
    print(f"{DIM}Scratch folder: {scratch}{RESET}")
    for number in chosen:
        title, commands = SCENARIOS[number - 1]
        print(f"\n{BOLD}{number}. {title}{RESET}")
        for command in commands:
            print(f"\n{BOLD}${RESET} {command}")
            done = subprocess.run(
                oxy + command,
                shell=True,
                cwd=scratch,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            limit = 100 if "--help" in command else LINES
            for stream, style in ((done.stdout, ""), (done.stderr, DIM)):
                lines = stream.splitlines()
                for line in lines[:limit]:
                    print(
                        f"{style}  {line[:WIDTH]}{'...' if len(line) > WIDTH else ''}{RESET}"
                    )
                if len(lines) > limit:
                    print(f"{style}  ... {len(lines) - limit} more lines{RESET}")
            print(f"{DIM}  exit {done.returncode}{RESET}")


if __name__ == "__main__":
    main()
