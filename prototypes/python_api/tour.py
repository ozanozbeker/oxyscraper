# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx2>=2.13.1", "pydantic>=2.11", "trio>=0.34"]
# ///
"""PROTOTYPE, throwaway: drive `oxy_prototype` against a fake Oxylabs API, one scenario per key.

Run it with `uv run prototypes/python_api/tour.py`.
The fake answers in the shapes that docs/research/live-api.md recorded, so nothing is billed.
"""

# ruff: noqa: ANN401, BLE001, D102, D103, PLR0911, PLR2004, S106, T201
# pyrefly: ignore-errors

from __future__ import annotations

import base64
import contextlib
import inspect
import io
import itertools
import json
import sys
import textwrap
import time
import zlib
from datetime import UTC, datetime, timedelta
from typing import Any

import anyio
import httpx2
import oxy_prototype as oxy
from pydantic import ValidationError

AUTH = "Basic " + base64.b64encode(b"USERNAME:PASSWORD").decode()
BATCH_SOURCES = {"universal", "amazon_product", "amazon_search", "google_search"}
BOLD, DIM, RESET = "\x1b[1m", "\x1b[2m", "\x1b[0m"


class FakeOxylabs:
    """Answer like the live API: a job finishes after a delay taken from its input, and one with FAULT in it faults."""

    def __init__(self) -> None:
        self.jobs: dict[str, dict[str, Any]] = {}
        self.log: list[str] = []
        self.start = time.monotonic()
        self.ids = itertools.count(7508980357849460000)
        self._create(
            {"source": "universal", "url": "https://sandbox.oxylabs.io/"},
            job_id="7508980357849459714",
        )

    async def __call__(self, request: httpx2.Request) -> httpx2.Response:
        response = await self._route(request)
        target = request.url.host.split(".")[0] + request.url.path
        if "type" in request.url.params:
            target += "?type=" + request.url.params["type"]
        note = ""
        if request.url.path.endswith("/batch"):
            payload = json.loads(request.content)
            note = f"  ({len(next(v for k, v in payload.items() if k in oxy.INPUT_KEYS))} values)"
        elif "x-oxylabs-job-status" in response.headers:
            note = "  " + response.headers["x-oxylabs-job-status"]
        self.log.append(
            f"{time.monotonic() - self.start:5.2f}s  {request.method:<4} {target}  {response.status_code}{note}"
        )
        return response

    async def _route(self, request: httpx2.Request) -> httpx2.Response:
        if request.headers.get("authorization") != AUTH:
            # An unknown username gets a 401 with an empty body.
            return httpx2.Response(401)
        types = request.url.params.get("type")
        if request.method == "POST":
            payload = json.loads(request.content)
            if request.url.host.startswith("realtime"):
                job = self._create(payload)
                await anyio.sleep(job["ready"] - time.monotonic())
                return httpx2.Response(200, json=self._body(job, types, realtime=True))
            if request.url.path.endswith("/batch"):
                return httpx2.Response(202, json=self._batch(payload))
            return httpx2.Response(202, json=self._object(self._create(payload)))
        job = self.jobs.get(request.url.path.split("/")[3])
        if job is None:
            return httpx2.Response(404, json={"message": "Query not found."})
        status = self._status(job)
        if not request.url.path.endswith("/results"):
            return httpx2.Response(200, json=self._object(job))
        if status == "pending":
            return httpx2.Response(204, headers={"x-oxylabs-job-status": status})
        return httpx2.Response(
            200, json=self._body(job, types), headers={"x-oxylabs-job-status": status}
        )

    def _create(
        self, payload: dict[str, Any], job_id: str | None = None
    ) -> dict[str, Any]:
        value = next(payload[key] for key in oxy.INPUT_KEYS if key in payload)
        seconds = 0.4 + zlib.crc32(value.encode()) % 16 / 10
        created = datetime.now(UTC)
        job = {
            "id": job_id or str(next(self.ids)),
            "payload": payload,
            "value": value,
            "created": created,
            "finished": created + timedelta(seconds=seconds),
            "ready": 0.0 if job_id else time.monotonic() + seconds,
            "faulted": "FAULT" in value.upper(),
        }
        self.jobs[job["id"]] = job
        return job

    def _status(self, job: dict[str, Any]) -> str:
        if time.monotonic() < job["ready"]:
            return "pending"
        return "faulted" if job["faulted"] else "done"

    def _batch(self, payload: dict[str, Any]) -> dict[str, Any]:
        key = next(key for key in oxy.INPUT_KEYS if key in payload)
        source = payload["source"]
        if source not in BATCH_SOURCES:
            error = {
                "message": f"Source `{source}` is not available with a batch request."
            }
            return {"queries": [], "errors": [error for _ in payload[key]]}
        queries, errors = [], []
        for value in payload[key]:
            if value:
                queries.append(self._object(self._create({**payload, key: value})))
            else:
                errors.append({"message": "Query parameter is empty."})
        return (
            {"queries": queries, "errors": errors} if errors else {"queries": queries}
        )

    def _object(self, job: dict[str, Any], *, realtime: bool = False) -> dict[str, Any]:
        status = "done" if realtime and not job["faulted"] else self._status(job)
        updated = job["created"] if status == "pending" or realtime else job["finished"]
        return {
            **job["payload"],
            "id": job["id"],
            "status": "faulted" if realtime and job["faulted"] else status,
            "query": job["payload"].get("query", ""),
            "created_at": f"{job['created']:%Y-%m-%d %H:%M:%S}",
            "updated_at": f"{updated:%Y-%m-%d %H:%M:%S}",
            "statuses": [],
        }

    def _body(
        self, job: dict[str, Any], types: str | None, *, realtime: bool = False
    ) -> dict[str, Any]:
        payload = job["payload"]
        default = next(
            (
                name
                for name, on in [
                    ("parsed", payload.get("parse")),
                    ("markdown", payload.get("markdown")),
                    ("xhr", payload.get("xhr")),
                    ("png", payload.get("render") == "png"),
                ]
                if on
            ),
            "raw",
        )
        first = payload.get("start_page", 1)
        pages = range(first, first + payload.get("pages", 1))
        if job["faulted"]:
            results = [self._entry(job, first, default, 613)]
        else:
            results = [
                self._entry(job, page, kind, 200)
                for page in pages
                for kind in (types.split(",") if types else [default])
            ]
        return {"job": self._object(job, realtime=realtime), "results": results}

    def _entry(
        self, job: dict[str, Any], page: int, kind: str, status_code: int
    ) -> dict[str, Any]:
        value = job["value"]
        content: Any = {
            "raw": f"<!doctype html><html>{value}, page {page}</html>",
            "parsed": {
                "title": f"Product {value}",
                "price": 9.99,
                "page": page,
                "parse_status_code": 12000,
            },
            "markdown": f"# {value}\n\nPage {page}.",
            "png": base64.b64encode(b"\x89PNG\r\n\x1a\n" + value.encode()).decode(),
            "xhr": [],
        }[kind]
        return {
            "content": "" if status_code == 613 else content,
            "created_at": f"{job['created']:%Y-%m-%d %H:%M:%S}",
            "updated_at": f"{job['finished']:%Y-%m-%d %H:%M:%S}",
            "page": page,
            "url": job["payload"].get("url") or f"https://www.example.com/{value}",
            "job_id": job["id"],
            "is_render_forced": False,
            "status_code": status_code,
            "type": kind,
        }


SETUP = """transport = httpx2.MockTransport(FakeOxylabs())
with oxy.Session(username="USERNAME", password="PASSWORD", transport=transport) as session:
    ...  # each scenario runs here"""
fake = FakeOxylabs()
transport = httpx2.MockTransport(fake)
session: oxy.Session


def one_job() -> None:
    payload = oxy.AmazonProduct(query="B07FZ8S74R", parse=True, geo_location="90210")
    job = session.execute(payload).one()
    print(job)
    print(job.content)


def typos_raise() -> None:
    attempts = {
        "misspelt parameter": lambda: oxy.AmazonProduct(
            query="B07FZ8S74R", geo_loaction="90210"
        ),
        "not an ASIN": lambda: oxy.AmazonProduct(query="B07FZ8S74"),
        "unknown marketplace": lambda: oxy.AmazonSearch(
            query="usb c cable", domain="com.uk"
        ),
        "empty query": lambda: oxy.AmazonSearch(query=""),
        "no model, bad render": lambda: oxy.Payload(
            source="walmart_product", product_id="436012154", render="pdf"
        ),
        "no model, two inputs": lambda: oxy.Payload(
            source="walmart_product", product_id="1", url="https://x.com"
        ),
    }
    for name, attempt in attempts.items():
        try:
            attempt()
        except ValidationError as error:
            print(f"{name}: {error.errors()[0]['msg'][:70]}")


def many_jobs() -> None:
    pairs = [
        ("B07FZ8S74R", "com"),
        ("B0FAULT001", "com"),
        ("B08N5WRWNW", "de"),
        ("B09B8V1LZ3", "de"),
    ]
    start = time.monotonic()
    run = session.execute(
        [oxy.AmazonProduct(query=asin, domain=domain) for asin, domain in pairs]
    )
    time.sleep(
        1.5
    )  # The caller is busy, and the session keeps polling in the background.
    for job in run:
        print(
            f"+{time.monotonic() - start:.1f}s",
            job.input,
            job.data["domain"],
            job.status,
        )


def many_jobs_realtime() -> None:
    payloads = [
        oxy.AmazonProduct(query=asin)
        for asin in ["B07FZ8S74R", "B0FAULT001", "B08N5WRWNW", "B09B8V1LZ3"]
    ]
    start = time.monotonic()
    for job in session.execute(payloads, realtime=True):
        print(f"+{time.monotonic() - start:.1f}s", job.input, job.status)


def no_model_yet() -> None:
    payloads = [
        oxy.Payload(source="walmart_product", product_id=pid, store_id="1234")
        for pid in ["436012154", "5073186532"]
    ]
    for job in session.execute(payloads):
        print(job.input, job.status, job.data["store_id"])
    print(
        "sources with a model:",
        [model.model_fields["source"].default for model in oxy.SOURCES],
    )


def dry_run() -> None:
    payloads = [
        oxy.AmazonSearch(
            query="usb c cable", pages=2, sort_by="price_low_to_high", currency="EUR"
        ),
        oxy.AmazonProduct(query="B07FZ8S74R", extra={"new_param": True}),
        oxy.Payload(source="walmart_search", query="usb hub"),
    ]
    report = oxy.dry_run(payloads)
    print(report.job_count, "jobs,", report.max_results, "billed results at most")
    for job in report.jobs:
        print(job)


def output_types() -> None:
    payload = oxy.AmazonProduct(query="B07FZ8S74R", parse=True, render="png")
    job = session.execute(payload, output_types=["parsed", "raw", "png"]).one()
    for result in job.results:
        print(
            result.page,
            result.type,
            type(result.content).__name__,
            str(result.content)[:40],
        )


def async_backends() -> None:
    async def main(backend: str) -> None:
        async with oxy.AsyncSession(
            username="USERNAME", password="PASSWORD", transport=transport
        ) as session:
            job = (await session.execute(oxy.AmazonSearch(query="usb c cable"))).one()
            print(backend, "execute:", job.input, job.status)
            async for job in await session.stream(
                [oxy.AmazonSearch(query=q) for q in ["hdmi cable", "usb hub"]]
            ):
                print(backend, "stream:", job.input, job.status)

    for backend in ("asyncio", "trio"):
        anyio.run(main, backend, backend=backend)


def rejected_value() -> None:
    payloads = [
        oxy.Payload(source="amazon_search", query=query)
        for query in ["usb c cable", "", "hdmi cable"]
    ]
    for job in session.execute(payloads):
        print(job.input, job.status)


def get_and_errors() -> None:
    job = session.get("7508980357849459714")
    print(job.id, job.status, job.input)
    with oxy.Session(
        username="USERNAME", password="wrong", transport=transport
    ) as other:
        try:
            other.execute(oxy.AmazonProduct(query="B07FZ8S74R")).one()
        except oxy.OxylabsError as error:
            print("wrong password:", repr(error))
    session.get("7000000000000000001")


SCENARIOS = {
    "1": ("One typed job", one_job),
    "2": ("Typos raise before billing", typos_raise),
    "3": ("Per-job parameters, started at once", many_jobs),
    "4": ("Many jobs, Realtime", many_jobs_realtime),
    "5": ("A source with no model yet", no_model_yet),
    "6": ("Dry run: context and extra", dry_run),
    "7": ("Several output types", output_types),
    "8": ("Async, under asyncio and trio", async_backends),
    "9": ("A value the API rejects", rejected_value),
    "0": ("Get by ID, and errors that raise", get_and_errors),
}


def run(fn: Any) -> tuple[str, str, float]:
    fake.log.clear()
    fake.start = started = time.monotonic()
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        try:
            fn()
        except Exception as error:
            print(f"{type(error).__name__}: {error}")
    lines = (
        fake.log
        if len(fake.log) <= 12
        else [*fake.log[:8], f"  ... {len(fake.log) - 11} more", *fake.log[-3:]]
    )
    return output.getvalue().rstrip(), "\n".join(lines), time.monotonic() - started


def render(frame: tuple[str, Any, str, str, float] | None) -> None:
    if sys.stdout.isatty():
        print("\x1b[2J\x1b[H", end="")
    print(
        f"{BOLD}oxy prototype{RESET}  {DIM}against a fake Oxylabs API, so nothing is billed{RESET}"
    )
    print(DIM + SETUP + RESET + "\n")
    keys = list(SCENARIOS)
    for left, right in zip(keys[:5], keys[5:], strict=True):
        print(
            f"{BOLD}[{left}]{RESET} {SCENARIOS[left][0]:<40}{BOLD}[{right}]{RESET} {SCENARIOS[right][0]}"
        )
    if frame:
        title, fn, output, log, seconds = frame
        body = textwrap.dedent("".join(inspect.getsourcelines(fn)[0][1:]))
        print(f"\n{BOLD}{title}{RESET}  {DIM}{seconds:.1f} s{RESET}\n{body}")
        print(
            f"{BOLD}output{RESET}\n{output}\n\n{BOLD}requests{RESET}\n{DIM}{log}{RESET}"
        )
    print(
        f"\n{BOLD}[0-9]{RESET} {DIM}run a scenario{RESET}  {BOLD}[q]{RESET} {DIM}quit{RESET}"
    )


def main() -> None:
    global session
    with oxy.Session(
        username="USERNAME", password="PASSWORD", transport=transport
    ) as session:
        frame = None
        while True:
            render(frame)
            try:
                key = input("> ").strip().lower()
            except EOFError:
                return
            if key == "q":
                return
            if key in SCENARIOS:
                title, fn = SCENARIOS[key]
                frame = (title, fn, *run(fn))


if __name__ == "__main__":
    main()
