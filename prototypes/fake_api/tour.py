# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx2>=2.13.1", "anyio>=4.15", "pydantic>=2.11", "trio>=0.34"]
# ///
"""PROTOTYPE, throwaway: run tests that drive `FakeOxylabs`, one scenario per key, and show what the fake received.

Run `uv run prototypes/fake_api/tour.py` to pick scenarios, or pass their keys, such as `tour.py 2 5` or `tour.py all`.
An async scenario runs under trio's `MockClock`, and a sync one runs on real time, as [How is oxy tested, with and without spending credits?](https://github.com/ozanozbeker/oxyscraper/issues/23) decided.
"""

# ruff: noqa: ANN401, BLE001, D103, PLR2004, PLW0603, S101, S106, SLF001, T201
# pyrefly: ignore-errors

from __future__ import annotations

import contextlib
import inspect
import io
import json
import math
import sys
import textwrap
import time
import traceback
from contextlib import ExitStack
from typing import Any

import anyio
import httpx2
import oxy_standin as oxy
from testing import FakeOxylabs, Outcome, Rejected
from trio.testing import MockClock

BOLD, DIM, RESET = "\x1b[1m", "\x1b[2m", "\x1b[0m"
SANDBOX = "https://sandbox.oxylabs.io"
THROTTLE = (
    "Access to www.amazon.com has been limited to 1 req/s due to a low success rate."
)
started = 0.0


def clock() -> float:
    """Return the seconds since the scenario started, on the clock the scenario runs on."""
    try:
        return anyio.current_time() - started
    except anyio.NoEventLoopError:
        return time.monotonic() - started


def zero_config() -> FakeOxylabs:
    fake = FakeOxylabs()
    payloads = [
        oxy.AmazonProduct(query="B07FZ8S74R", parse=True),
        oxy.Payload(source="amazon_search", query="usb c cable", pages=2),
        oxy.Universal(url=f"{SANDBOX}/", render="png"),
    ]
    with oxy.Session(
        username="USERNAME", password="PASSWORD", transport=fake
    ) as session:
        for job in session.execute(payloads):
            for result in job.results:
                print(
                    job.source,
                    job.status,
                    result.page,
                    result.type,
                    repr(result.content)[:45],
                )
        job = session.execute(payloads[0], output_types=["raw", "parsed"]).one()
        print([result.type for result in job.results])

    assert [job["source"] for job in fake.jobs][:3] == [
        "amazon_product",
        "amazon_search",
        "universal",
    ]
    assert fake.requests[0].url.path == "/v1/queries/batch"
    return fake


async def outcomes() -> FakeOxylabs:
    fixture = {"title": "Anker USB C Cable", "price": 9.99}

    def outcome(payload: dict[str, Any]) -> Outcome:
        match payload["query"]:
            case "B0FAULT001":
                return Outcome(status="faulted", after=17)
            case "B0SLOW0001":
                return Outcome(after=120)
            case "B0GONE0001":
                return Outcome(status_code=404, content="<html>Not found</html>")
        return Outcome(after=3, content=fixture)

    fake = FakeOxylabs(outcome)
    asins = ["B07FZ8S74R", "B0FAULT001", "B0SLOW0001", "B0GONE0001"]
    async with oxy.AsyncSession(
        username="USERNAME", password="PASSWORD", transport=fake
    ) as session:
        run = await session.stream(
            [oxy.AmazonProduct(query=asin, parse=True) for asin in asins]
        )
        async for job in run:
            result = job.results[0]
            print(
                f"{clock():5.0f} s",
                job.input,
                job.status,
                result.status_code,
                result.content,
            )
    return fake


async def rejections() -> FakeOxylabs:
    def outcome(payload: dict[str, Any]) -> Outcome | Rejected:
        # The fake does not copy Amazon's location check, so the test rejects the payload itself.
        if payload.get("geo_location") == "United States":
            return Rejected(
                "Parameter `geo_location` with value `United States` is not valid."
            )
        return Outcome()

    fake = FakeOxylabs(outcome)
    payloads = [
        oxy.AmazonProduct(query="B07FZ8S74R"),
        oxy.AmazonProduct(query="B08N5WRWNW", geo_location="United States"),
        oxy.Payload(source="amazon_reviews", query="B07FZ8S74R"),
        oxy.Universal(url=f"{SANDBOX}/products"),
        oxy.Universal(url="https://sandbox.oxylabs.test/"),
        oxy.Universal(url="not a url"),
    ]
    async with oxy.AsyncSession(
        username="USERNAME", password="PASSWORD", transport=fake
    ) as session:
        try:
            async for job in await session.stream(payloads):
                print(job.source, repr(job.input), job.status)
        except oxy.IncompleteRunError as error:
            print(error)
            for rejection in error.rejections:
                print(
                    rejection.status_code, rejection.payload.source, rejection.message
                )
    assert len(fake.jobs) == 2
    return fake


async def stays_pending() -> FakeOxylabs:
    fake = FakeOxylabs(Outcome(after=math.inf))
    async with oxy.AsyncSession(
        username="USERNAME", password="PASSWORD", transport=fake
    ) as session:
        try:
            await session.execute(oxy.Universal(url=f"{SANDBOX}/"))
        except oxy.IncompleteRunError as error:
            [job] = error.unfetched
            print(f"{clock():.0f} s", error)
        job = await session.get(job.id)
        print(f"{clock():.0f} s", "get returns", job.status, job.results)
    return fake


async def http_failures() -> list[FakeOxylabs]:
    payloads = [oxy.Universal(url=f"{SANDBOX}/products/{n}") for n in (1, 2)]

    fake = FakeOxylabs(Outcome(after=2))
    fake.fail(429, on="submit", times=2)
    fake.fail(503, on="results")
    fake.fail(httpx2.ReadTimeout("no answer"), on="results")
    async with oxy.AsyncSession(
        username="USERNAME", password="PASSWORD", transport=fake
    ) as session:
        jobs = (await session.execute(payloads)).all()
        print(
            f"{clock():.0f} s", [job.status for job in jobs], session.retries, "retries"
        )

    outage = FakeOxylabs()
    outage.fail(503, times=None)
    async with oxy.AsyncSession(
        username="USERNAME", password="PASSWORD", transport=outage
    ) as session:
        try:
            await session.execute(payloads)
        except oxy.IncompleteRunError as error:
            print(f"{clock():.0f} s", error, "from", repr(error.__cause__)[:40])

    throttle = FakeOxylabs()
    throttle.fail(429, on="submit", message=THROTTLE)
    async with oxy.AsyncSession(
        username="USERNAME", password="PASSWORD", transport=throttle
    ) as session:
        try:
            await session.execute(payloads)
        except oxy.IncompleteRunError as error:
            print(f"{clock():.0f} s", error, "from", repr(error.__cause__)[:60])
    assert throttle.jobs == []
    return [fake, outage, throttle]


async def rate_limits() -> FakeOxylabs:
    fake = FakeOxylabs(limit=5, render_limit=2)
    urls = [f"{SANDBOX}/products/{n}" for n in range(1, 13)]
    async with oxy.AsyncSession(
        username="USERNAME", password="PASSWORD", transport=fake
    ) as session:
        jobs = (await session.execute([oxy.Universal(url=url) for url in urls])).all()
        print(f"{clock():.1f} s", len(jobs), "jobs")
        rendered = [oxy.Universal(url=url, render="html") for url in urls[:4]]
        jobs = (await session.execute(rendered)).all()
        print(f"{clock():.1f} s", len(jobs), "rendered jobs")

    batches = [
        request for request in fake.requests if request.url.path.endswith("/batch")
    ]
    print(
        [len(json.loads(request.content)["url"]) for request in batches],
        "values a batch",
    )
    return fake


async def no_batch() -> FakeOxylabs:
    fake = FakeOxylabs()
    queries = ["usb hub", "hdmi cable", "usb c cable"]
    async with oxy.AsyncSession(
        username="USERNAME", password="PASSWORD", transport=fake
    ) as session:
        for _ in range(2):
            payloads = [
                oxy.Payload(source="walmart_search", query=query) for query in queries
            ]
            print([job.input for job in await session.execute(payloads)])

    posts = [request.url.path for request in fake.requests if request.method == "POST"]
    assert posts == ["/v1/queries/batch", *["/v1/queries"] * 6]
    return fake


async def cloud_storage() -> FakeOxylabs:
    def outcome(payload: dict[str, Any]) -> Outcome:
        match payload["url"].removeprefix(f"{SANDBOX}/"):
            case "late":
                return Outcome(after=2, upload_after=20)
            case "never":
                return Outcome(after=2, upload=None)
            case "name-exists":
                return Outcome(after=2, upload=10001, upload_after=20)
            case "no-bucket":
                return Outcome(after=2, upload=13102)
            case "faulted":
                return Outcome(status="faulted", after=15)
        return Outcome(after=2)

    fake = FakeOxylabs(outcome)
    names = ["at-once", "late", "never", "name-exists", "no-bucket", "faulted"]
    payloads = [
        oxy.Universal(
            url=f"{SANDBOX}/{name}", storage_type="gcs", storage_url="bucket/run"
        )
        for name in names
    ]
    async with oxy.AsyncSession(
        username="USERNAME", password="PASSWORD", transport=fake
    ) as session:
        try:
            async for job in await session.stream(payloads):
                upload = job.upload
                print(
                    f"{clock():5.0f} s",
                    job.input[27:],
                    job.status,
                    upload.code,
                    upload.storage_url,
                )
        except oxy.IncompleteRunError as error:
            print(error)
            print([(job.input[27:], job.upload.message) for job in error.unuploaded])
    return fake


async def two_sessions() -> FakeOxylabs:
    def outcome(payload: dict[str, Any]) -> Outcome:
        return (
            Outcome(after=900)
            if "slow" in payload["url"]
            else Outcome(expires_after=3600)
        )

    fake = FakeOxylabs(outcome)
    payloads = [oxy.Universal(url=f"{SANDBOX}/{name}") for name in ("fast", "slow")]
    async with oxy.AsyncSession(
        username="USERNAME", password="PASSWORD", transport=fake
    ) as first:
        try:
            await first.execute(payloads)
        except oxy.IncompleteRunError as error:
            print(f"{clock():5.0f} s", "first session:", error)
            ids = [job.id for job in error.jobs + error.unfetched]

    for wait in (300, 3600):
        await anyio.sleep(wait)
        async with oxy.AsyncSession(
            username="USERNAME", password="PASSWORD", transport=fake
        ) as second:
            for job_id in ids:
                job = await second.get(job_id)
                print(
                    f"{clock():5.0f} s",
                    "second session:",
                    job.input,
                    job.status,
                    len(job.results),
                    "results",
                )
    return fake


def the_switch() -> list[FakeOxylabs]:
    def scrape(url: str) -> str:
        """Build a session inside the code under test, as a Dagster resource or the CLI does."""
        with oxy.Session(username="USERNAME", password="PASSWORD") as session:
            return session.execute(oxy.Universal(url=url)).one().content

    with FakeOxylabs(Outcome(content="<html>fixture</html>")) as fake:
        assert scrape(f"{SANDBOX}/") == "<html>fixture</html>"
    assert [job["url"] for job in fake.jobs] == [f"{SANDBOX}/"]

    # After the block, a session builds its own transport again. The stand-in raises where oxy would reach Oxylabs.
    try:
        scrape(f"{SANDBOX}/")
    except RuntimeError as error:
        print(error)

    # No `with` block spans the cells of a docs page, so its hidden setup cell enters the fake through `ExitStack`.
    page = ExitStack()
    docs = page.enter_context(FakeOxylabs())
    print(scrape(f"{SANDBOX}/products/1"))
    page.close()
    return [fake, docs]


async def realtime() -> FakeOxylabs:
    def outcome(payload: dict[str, Any]) -> Outcome:
        match payload["url"].removeprefix(f"{SANDBOX}/"):
            case "faulted":
                return Outcome(status="faulted", after=24)
            case "past-the-ttl":
                return Outcome(after=200)
        return Outcome(after=3)

    fake = FakeOxylabs(outcome)
    payloads = [
        *[
            oxy.Universal(url=f"{SANDBOX}/{name}")
            for name in ("done", "faulted", "past-the-ttl")
        ],
        oxy.Payload(
            source="perplexity", prompt="what is the tallest mountain in europe"
        ),
    ]
    async with oxy.AsyncSession(
        username="USERNAME", password="PASSWORD", transport=fake
    ) as session:
        try:
            async for job in await session.stream(payloads, realtime=True):
                print(
                    f"{clock():5.0f} s",
                    job.input[27:],
                    job.status,
                    job.results[0].status_code,
                )
        except oxy.IncompleteRunError as error:
            for rejection in error.rejections:
                print(f"{clock():5.0f} s", rejection.status_code, rejection.message)
        try:
            await session.get(fake.jobs[0]["id"])
        except oxy.OxylabsError as error:
            print("get:", error)
    return fake


SCENARIOS = {
    "1": ("No setup: every job finishes at once", zero_config),
    "2": ("A function sets each job's outcome", outcomes),
    "3": ("Rejections: the API's checks, and the test's own", rejections),
    "4": ("A job that stays pending", stays_pending),
    "5": ("A 429, a 5xx and a network error", http_failures),
    "6": ("The test sets both rate limits", rate_limits),
    "7": ("A source that takes no batch", no_batch),
    "8": ("Cloud Storage: late, missing and failed uploads", cloud_storage),
    "9": ("A second session fetches the first one's jobs", two_sessions),
    "0": ("The switch, for code that builds its own session", the_switch),
    "a": ("Realtime", realtime),
}


def state(fake: FakeOxylabs) -> str:
    """Describe the fake as it stood at its last request."""
    limits = ", ".join(f"{name} {limit}" for name, limit in fake._limits.items())
    lines = [
        f"{len(fake.requests)} requests, {len(fake.jobs)} jobs, limits: {limit_names(limits)}"
    ]
    lines += [
        f"  still fails: {failure.error!r} on {failure.on or 'any request'}, "
        f"{'every time' if failure.times is None else f'{failure.times} more'}"
        for failure in fake._failures
    ]
    for record in list(fake._records.values())[:8]:
        outcome = record.outcome
        status = "pending" if fake._last < record.finished else outcome.status
        after = "never" if math.isinf(outcome.after) else f"after {outcome.after:g} s"
        parts = [f"{outcome.status} {after}", f"now {status}"]
        if record.realtime:
            parts.append("Realtime")
        if record.storage_url:
            code = "none" if outcome.upload is None else outcome.upload
            parts.append(f"upload {code} after {outcome.upload_after:g} s")
        value = next(
            str(record.payload[key]) for key in oxy.INPUT_KEYS if key in record.payload
        )
        lines.append(
            f"  {record.id[-3:]}  {record.payload['source']:<15} {value[:38]:<38} {', '.join(parts)}"
        )
    if len(fake._records) > 8:
        lines.append(f"  ... {len(fake._records) - 8} more jobs")
    return "\n".join(lines)


def limit_names(limits: str) -> str:
    return limits.replace("total-requests", "total").replace(
        "total-render-requests", "rendered"
    )


def run(fn: Any) -> tuple[str, list[FakeOxylabs], float, float | None]:
    """Run a scenario, and return its output, its fakes, the real seconds and the mock clock's seconds."""
    global started
    output = io.StringIO()
    fakes: Any = []
    ticked = None
    wall = time.perf_counter()

    async def timed() -> tuple[Any, float]:
        global started
        started = anyio.current_time()
        return await fn(), anyio.current_time() - started

    with contextlib.redirect_stdout(output):
        try:
            if inspect.iscoroutinefunction(fn):
                options = {"clock": MockClock(autojump_threshold=0)}
                fakes, ticked = anyio.run(
                    timed, backend="trio", backend_options=options
                )
            else:
                started = time.monotonic()
                fakes = fn()
        except Exception:
            print(traceback.format_exc(limit=-3))
    fakes = fakes if isinstance(fakes, list) else [fakes]
    return output.getvalue().rstrip(), fakes, time.perf_counter() - wall, ticked


def render(key: str | None) -> None:
    print(
        f"{BOLD}FakeOxylabs prototype{RESET}  {DIM}no request leaves the process, so nothing bills{RESET}\n"
    )
    keys = list(SCENARIOS)
    half = math.ceil(len(keys) / 2)
    for index in range(half):
        left = keys[index]
        right = keys[index + half] if index + half < len(keys) else None
        line = f"{BOLD}[{left}]{RESET} {SCENARIOS[left][0]:<52}"
        if right:
            line += f"{BOLD}[{right}]{RESET} {SCENARIOS[right][0]}"
        print(line)
    if key:
        title, fn = SCENARIOS[key]
        output, fakes, wall, ticked = run(fn)
        source = textwrap.dedent("".join(inspect.getsourcelines(fn)[0][1:]))
        source = "\n".join(
            line
            for line in source.splitlines()
            if not line.strip().startswith("return [fake")
            and line.strip() != "return fake"
        )
        took = (
            f"{wall:.2f} s on real time, in a sync session"
            if ticked is None
            else f"{ticked:,.0f} s on the mock clock, {wall:.2f} s on real time"
        )
        print(f"\n{BOLD}[{key}] {title}{RESET}  {DIM}{took}{RESET}\n{source.rstrip()}")
        print(f"\n{BOLD}output{RESET}\n{output}")
        for number, fake in enumerate(fakes, start=1):
            name = "the fake" if len(fakes) == 1 else f"fake {number}"
            log = fake._log
            if len(log) > 16:
                log = [*log[:10], f"  ... {len(log) - 14} more requests", *log[-4:]]
            print(f"\n{BOLD}{name} received{RESET}\n{DIM}" + "\n".join(log) + RESET)
            print(f"{BOLD}{name} holds{RESET}\n{state(fake)}")
    print(
        f"\n{BOLD}[key]{RESET} {DIM}run a scenario{RESET}  {BOLD}[q]{RESET} {DIM}quit{RESET}"
    )


def main() -> None:
    keys = list(SCENARIOS) if sys.argv[1:] == ["all"] else sys.argv[1:]
    if keys:
        for key in keys:
            render(key)
        return
    key = None
    while True:
        if sys.stdout.isatty():
            print("\x1b[2J\x1b[H", end="")
        render(key)
        try:
            pressed = input("> ").strip().lower()
        except EOFError:
            return
        if pressed == "q":
            return
        key = pressed if pressed in SCENARIOS else None


if __name__ == "__main__":
    main()
