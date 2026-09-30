# /// script
# requires-python = ">=3.11"
# dependencies = ["typer>=0.27", "rich>=15", "pydantic>=2.11", "httpx2>=2.13.1", "anyio>=4.15"]
# ///
"""PROTOTYPE, throwaway: run each scenario of the CLI's progress output, on the terminal and then into a file.

Run `uv run prototypes/cli_progress/tour.py` in a terminal for every scenario, or pass their numbers, such as `tour.py 1 4`.
`--terminal` or `--file` runs one of the two.
Each command runs in a scratch folder against the fake in `testing.py`, so nothing bills.
"""

# ruff: noqa: D101, D103, S603, T201
# pyrefly: ignore-errors

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
# `cli.py` keeps the fake's jobs here too, so a wipe starts each scenario with an empty fake.
STATE = Path(tempfile.gettempdir()) / "oxy-cli-progress-prototype"
BOLD, DIM, RESET = "\x1b[1m", "\x1b[2m", "\x1b[0m"
SANDBOX = "https://sandbox.oxylabs.io/products"
FIRST_LOG = "$(ls logs/*.jsonl | head -1)"
SIGNAL_AFTER = 4.0


@dataclass
class Command:
    text: str
    env: dict[str, str] = field(default_factory=dict)
    signal: signal.Signals | None = None


def urls(count: int, *words: str) -> str:
    return "".join(f"{SANDBOX}/{i}\n" for i in range(1, count + 1)) + "".join(
        f"{SANDBOX}/{word}\n" for word in words
    )


def mixed() -> str:
    payloads = [
        *({"source": "universal", "url": f"{SANDBOX}/{i}"} for i in range(1, 19)),
        {"source": "universal", "url": f"{SANDBOX}/FAULT-1"},
        {"source": "universal", "url": f"{SANDBOX}/FAULT-2"},
        {"source": "universal", "url": "https://10.0.0.1/"},
        {"source": "universal", "url": "https://shop.invalid/"},
        {"source": "amazon_prodcut", "query": "B07FZ8S74R"},
        *(
            {
                "source": "universal",
                "url": f"{SANDBOX}/{i}",
                "storage_type": "gcs",
                "storage_url": "wrong-bucket/demo",
            }
            for i in range(100, 103)
        ),
    ]
    return "".join(json.dumps(payload) + "\n" for payload in payloads)


RUN = "oxy run universal -d results --run-log logs < urls.txt"
SCENARIOS = [
    (
        "A clean run of 300 payloads, where 1 job in 20 takes 10 to 40 seconds",
        {"urls.txt": urls(300)},
        [Command(RUN, {"OXY_DEMO_TAIL": "1"})],
    ),
    (
        "A retry through the run log: resubmit the faulted payloads, then fetch the unfetched jobs",
        {
            "urls.txt": urls(
                32,
                "FAULT-1",
                "FAULT-2",
                "FLAKY-1",
                "FLAKY-2",
                "FLAKY-3",
                "SLOW-1",
                "SLOW-2",
                "STUCK-1",
            )
        },
        [
            Command(RUN, {"OXY_DEMO_PENDING_LIMIT": "5"}),
            Command(
                f"jq -c 'select(.state == \"faulted\") | .payload' {FIRST_LOG} | oxy run -d results --run-log logs"
            ),
            Command(
                f"jq -r 'select(.state == \"unfetched\") | .id' {FIRST_LOG} | oxy get -d results"
            ),
        ],
    ),
    (
        "Faulted jobs, rejections and a failed upload, then a wrong password",
        {"payloads.jsonl": mixed()},
        [
            Command("oxy run < payloads.jsonl > results.ndjson"),
            Command(f"oxy run universal {SANDBOX}/1", {"OXY_WSA_PASSWORD": "wrong"}),
        ],
    ),
    (
        f"Ctrl+C, then SIGTERM, {SIGNAL_AFTER:g} seconds into a run",
        {"urls.txt": urls(300)},
        [
            Command(RUN, signal=signal.SIGINT),
            Command(RUN, signal=signal.SIGTERM),
            Command("jq -r .state logs/*.jsonl | sort | uniq -c"),
        ],
    ),
    (
        "An outage from 3 to 23 s, a throttle from 2 to 12 s, and the domain throttle from 2 s",
        {
            "urls.txt": urls(300),
            "asins.txt": "".join(f"B0{i:08d}\n" for i in range(1, 301)),
        },
        [
            Command(
                "oxy run universal -d results < urls.txt", {"OXY_DEMO_FAIL": "outage"}
            ),
            Command(
                "oxy run universal -d results < urls.txt", {"OXY_DEMO_FAIL": "throttle"}
            ),
            Command(
                "oxy run amazon_product -d results < asins.txt",
                {"OXY_DEMO_FAIL": "domain-throttle"},
            ),
        ],
    ),
    (
        "A check_storage wait before 99 of 100 payloads",
        {"urls.txt": urls(100)},
        [
            Command(
                "oxy run universal --storage-type gcs --storage-url bucket/demo < urls.txt"
            )
        ],
    ),
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("numbers", nargs="*", type=int)
    where = parser.add_mutually_exclusive_group()
    where.add_argument("--terminal", action="store_true")
    where.add_argument("--file", action="store_true")
    args = parser.parse_args()
    # The commands write to the same stdout, so the tour's own lines must not wait in a buffer.
    sys.stdout.reconfigure(line_buffering=True)
    modes = (
        ["terminal"]
        if args.terminal
        else ["file"]
        if args.file
        else ["terminal", "file"]
    )
    if "terminal" in modes and not sys.stderr.isatty():
        sys.exit("Run the tour in a terminal, or pass --file.")
    env = {
        **os.environ,
        "OXY_WSA_USERNAME": "USERNAME",
        "OXY_WSA_PASSWORD": "PASSWORD",
    }
    prelude = f'oxy() {{ exec "{sys.executable}" "{HERE / "cli.py"}" "$@"; }}; '
    for number in args.numbers or range(1, len(SCENARIOS) + 1):
        title, files, commands = SCENARIOS[number - 1]
        for mode in modes:
            shutil.rmtree(STATE, ignore_errors=True)
            scratch = STATE / "tour"
            scratch.mkdir(parents=True)
            for name, text in files.items():
                (scratch / name).write_text(text)
            print(
                f"\n{BOLD}{number}. {title}{RESET} {DIM}(stderr {'on the terminal' if mode == 'terminal' else 'into a file'}){RESET}"
            )
            for command in commands:
                shown = " ".join(f"{key}={value}" for key, value in command.env.items())
                sent = (
                    f"  # {command.signal.name} after {SIGNAL_AFTER:g} s"
                    if command.signal
                    else ""
                )
                print(
                    f"\n{BOLD}${RESET} {DIM}{shown}{RESET}{' ' if shown else ''}{command.text}{DIM}{sent}{RESET}"
                )
                log = scratch / "stderr.log"
                with log.open("w") as stderr:
                    code = _run(
                        prelude + command.text,
                        scratch,
                        env | command.env,
                        None if mode == "terminal" else stderr,
                        command.signal,
                    )
                for line in log.read_text().splitlines():
                    print(f"{DIM}  {line}{RESET}")
                print(f"{DIM}  exit {code}{RESET}")


def _run(
    text: str,
    cwd: Path,
    env: dict[str, str],
    stderr: object,
    sent: signal.Signals | None,
) -> int:
    # A handler, unlike SIG_IGN, resets at exec, so Ctrl+C reaches the command and the tour carries on.
    previous = signal.signal(signal.SIGINT, lambda *_: None)
    try:
        process = subprocess.Popen(
            ["/bin/sh", "-c", text], cwd=cwd, env=env, stderr=stderr
        )
        if sent:
            try:
                process.wait(SIGNAL_AFTER)
            except subprocess.TimeoutExpired:
                process.send_signal(sent)
        return process.wait()
    finally:
        signal.signal(signal.SIGINT, previous)


if __name__ == "__main__":
    main()
