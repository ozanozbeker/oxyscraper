import asyncio
import dataclasses
import gc
import json
import logging
import math
import random
import re
import signal
import threading
import weakref
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from functools import partial
from importlib.metadata import version
from pathlib import Path
from typing import Any, Literal

import anyio
import httpx2
import obstore
import pytest
from obstore.store import MemoryStore
from typing_extensions import override

import oxyscraper as oxy
from oxyscraper.testing import FakeOxylabs, Outcome, Rejected

pytestmark = pytest.mark.anyio

SANDBOX = "https://sandbox.oxylabs.io"
open_session = partial(oxy.Session, username="USERNAME", password="PASSWORD")  # noqa: S106
open_async_session = partial(
    oxy.AsyncSession,
    username="USERNAME",
    password="PASSWORD",  # noqa: S106
)
# The fake counts `created_at` from here.
START = datetime(2026, 1, 1, tzinfo=UTC)
PNG = b"\x89PNG\r\n\x1a\n"
# Tests that wait run on trio's mock clock only, so their waits take no real time.
on_mock_clock = pytest.mark.parametrize("anyio_backend", ["trio"], indirect=True)
# The mock clock jumps while a write waits on its worker thread, so tests that write run on real time.
on_real_time = pytest.mark.parametrize("anyio_backend", ["asyncio", "trio"])


def universal(path: str = "", **fields: Any) -> oxy.Payload:
    return oxy.Payload(source="universal", url=f"{SANDBOX}/{path}", **fields)


def walmart(product_id: str) -> oxy.Payload:
    """Return a payload that goes out alone, because `product_id` takes no batch."""
    return oxy.Payload(source="walmart_product", product_id=product_id)


def checks(fake: FakeOxylabs) -> int:
    return sum(request.url.path.endswith("/results") for request in fake.requests)


def submissions(fake: FakeOxylabs) -> int:
    return sum(request.method == "POST" for request in fake.requests)


def warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return sorted(
        record.getMessage()
        for record in caplog.records
        if record.name == "oxyscraper" and record.levelno == logging.WARNING
    )


async def incomplete(run: oxy.AsyncRun) -> oxy.IncompleteRunError:
    with pytest.raises(oxy.IncompleteRunError) as caught:
        await run.all()
    return caught.value


def cause(error: oxy.IncompleteRunError) -> oxy.OxylabsError:
    assert isinstance(error.__cause__, oxy.OxylabsError)
    return error.__cause__


class Slow(FakeOxylabs):
    """Answer each request after a second, and record the most requests at once."""

    def __init__(self) -> None:
        super().__init__(limit=150)
        self.active = 0
        self.most = 0

    @override
    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        self.active += 1
        self.most = max(self.most, self.active)
        await anyio.sleep(1)
        self.active -= 1
        return await super().handle_async_request(request)


class Garbled(FakeOxylabs):
    """Answer the first results download with `body`."""

    def __init__(self, body: str) -> None:
        super().__init__()
        self.body = body
        self.garbled = 0

    @override
    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        if request.url.path.endswith("/results") and not self.garbled:
            self.garbled += 1
            return httpx2.Response(200, text=self.body)
        return await super().handle_async_request(request)


class Recorded(FakeOxylabs):
    """Keep the body of each response that holds a job's results, by job ID."""

    def __init__(self, outcome: Outcome | Callable[[dict[str, Any]], Outcome]) -> None:
        super().__init__(outcome)
        self.bodies: dict[str, bytes] = {}

    @override
    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        response = await super().handle_async_request(request)
        if response.status_code == 200 and "results" in (body := response.json()):
            self.bodies[body["job"]["id"]] = response.content
        return response


def stored(store: MemoryStore) -> dict[str, bytes]:
    return {
        meta["path"]: bytes(obstore.get(store, meta["path"]).bytes())
        for chunk in obstore.list(store)
        for meta in chunk
    }


def test_session_runs_a_payload(fake: FakeOxylabs) -> None:
    """`Session.execute` returns the payload's job, and `get` returns it again without the payload."""
    payload = universal()
    with open_session() as session:
        job = session.execute(payload).one()
        again = session.get(job.id)
    [result] = job.results
    assert job.id == fake.jobs[0]["id"]
    assert (job.status, job.source, job.input) == ("done", "universal", payload.url)
    assert (job.created_at, job.finished_at) == (START, START)
    assert (job.payload, job.upload, job.data["status"]) == (payload, None, "done")
    assert (result.page, result.type, result.status_code) == (1, "raw", 200)
    assert (result.created_at, result.updated_at) == (START, START)
    assert result.data["job_id"] == job.id
    assert job.content == result.content == result.data["content"]
    assert again == dataclasses.replace(job, payload=None)


def test_session_iterates_jobs() -> None:
    """Iterating a `Session` run yields one job per payload."""
    payloads = [universal(str(page)) for page in range(3)]
    with open_session() as session:
        jobs = list(session.execute(payloads))
    assert sorted(job.input for job in jobs) == [payload.url for payload in payloads]


async def test_stream_yields_jobs(fake: FakeOxylabs) -> None:
    """`stream` yields one job per payload, with oxy's user agent on every request."""
    payloads = [universal(str(page)) for page in range(3)]
    async with open_async_session() as session:
        jobs = [job async for job in await session.stream(payloads)]
    assert sorted(job.input for job in jobs) == [payload.url for payload in payloads]
    assert {request.headers["user-agent"] for request in fake.requests} == {
        f"oxyscraper/{version('oxyscraper')}"
    }


@on_mock_clock
async def test_batch(fake: FakeOxylabs) -> None:
    """Payloads that share every parameter but the input go out as one batch, and each job keeps its own payload."""
    payloads = [universal(str(page), user_agent_type="mobile") for page in range(3)]
    async with open_async_session() as session:
        jobs = (await session.execute(payloads)).all()
    [submission] = [request for request in fake.requests if request.method == "POST"]
    assert submission.url.path == "/v1/queries/batch"
    assert json.loads(submission.content) == {
        "source": "universal",
        "url": [payload.url for payload in payloads],
        "user_agent_type": "mobile",
    }
    assert {job.input: job.payload for job in jobs} == {
        payload.url: payload for payload in payloads
    }


@on_mock_clock
async def test_batch_errors(caplog: pytest.LogCaptureFixture) -> None:
    """An entry in a batch's `errors` rejects the payload whose value has no job, with the batch's 202, and the rest run."""
    fake = FakeOxylabs(
        lambda payload: (
            Rejected("No.") if payload["query"] == "B0BAD00000" else Outcome()
        )
    )
    asins = ["B000000001", "B0BAD00000", "B000000002"]
    payloads = [oxy.AmazonProduct(query=asin) for asin in asins]
    async with open_async_session(transport=fake) as session:
        error = await incomplete(await session.stream(payloads))
    assert sorted((job.input, job.payload) for job in error.jobs) == [
        (payload.query, payload) for payload in (payloads[0], payloads[2])
    ]
    assert error.rejections == [
        oxy.Rejection(
            payload=payloads[1], status_code=202, message="No.", trace_id=None
        )
    ]
    assert warnings(caplog) == ["Rejected amazon_product B0BAD00000: 202 No."]


@on_mock_clock
async def test_amazon_url_batch_errors() -> None:
    """Each job and each error of an `amazon` URL batch pairs with the payload of its URL, although the API sets each job's `query` to its ASIN."""
    bad = "https://www.amazon.com/dp/B0BAD00000"
    fake = FakeOxylabs(
        lambda payload: Rejected("No.") if payload["url"] == bad else Outcome()
    )
    urls = [
        bad,
        "https://www.amazon.com/dp/B000000001",
        "https://www.amazon.com/dp/B000000002",
    ]
    payloads = [oxy.Amazon(url=url) for url in urls]
    async with open_async_session(transport=fake) as session:
        error = await incomplete(await session.stream(payloads))
    assert sorted((job.data["url"], job.payload) for job in error.jobs) == [
        (payload.url, payload) for payload in payloads[1:]
    ]
    assert error.rejections == [
        oxy.Rejection(
            payload=payloads[0], status_code=202, message="No.", trace_id=None
        )
    ]


class Normalized(FakeOxylabs):
    """Return each batch's jobs with a slash after each URL."""

    @override
    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        response = await super().handle_async_request(request)
        if not request.url.path.endswith("/batch"):
            return response
        answer = json.loads(response.content)
        for job in answer["queries"]:
            job["url"] += "/"
        return httpx2.Response(response.status_code, json=answer)


@on_mock_clock
async def test_batch_job_with_a_changed_input() -> None:
    """A batch job whose input differs from every value pairs with the payload in its place."""
    fake = Normalized()
    payloads = [universal("1"), universal("2")]
    async with open_async_session(transport=fake) as session:
        jobs = (await session.execute(payloads)).all()
    assert sorted((job.input, job.payload) for job in jobs) == [
        (payload.url, payload) for payload in payloads
    ]


@on_mock_clock
async def test_batch_error_before_a_changed_input() -> None:
    """A batch error pairs with the payload of its `url`, so a job with a changed input after it pairs with its own payload."""
    fake = Normalized(
        lambda payload: (
            Rejected("No.") if payload["url"].endswith("/bad") else Outcome()
        )
    )
    payloads = [universal("bad"), universal("1")]
    async with open_async_session(transport=fake) as session:
        error = await incomplete(await session.stream(payloads))
    assert [job.payload for job in error.jobs] == [payloads[1]]
    assert [rejection.payload for rejection in error.rejections] == [payloads[0]]


@on_mock_clock
async def test_batch_rejected_whole(fake: FakeOxylabs) -> None:
    """A 400 on a whole batch rejects every payload in it."""
    message = "Batch request must contain one array of `query` or `url`."
    fake.fail(400, on="submit", message=message)
    payloads = [universal("1"), universal("2")]
    async with open_async_session() as session:
        error = await incomplete(await session.stream(payloads))
    assert [
        (rejection.payload, rejection.status_code, rejection.message)
        for rejection in error.rejections
    ] == [(payload, 400, message) for payload in payloads]


def posts(fake: FakeOxylabs) -> list[str]:
    return [request.url.path for request in fake.requests if request.method == "POST"]


@on_mock_clock
async def test_source_without_batches(fake: FakeOxylabs) -> None:
    """A source that takes no batch gets its payloads one per request, for the rest of the session."""
    payloads = [oxy.Payload(source="walmart_search", query=query) for query in "ab"]
    async with open_async_session() as session:
        first = await session.execute(payloads)
        second = await session.execute(payloads)
    assert posts(fake) == ["/v1/queries/batch", *["/v1/queries"] * 4]
    assert [len(first.all()), len(second.all())] == [2, 2]


@on_mock_clock
async def test_input_key_without_batches(fake: FakeOxylabs) -> None:
    """Three `walmart_product` payloads go out one per request, because a batch takes only `query`, `url` or `prompt`."""
    async with open_async_session() as session:
        run = await session.execute([walmart(str(product)) for product in range(3)])
    assert posts(fake) == ["/v1/queries"] * 3
    assert len(run.all()) == 3


@on_mock_clock
@pytest.mark.parametrize(("limit", "render_limit"), [(50, 13), (100, 25)])
@pytest.mark.parametrize("realtime", [False, True])
async def test_pacing(limit: int, render_limit: int, realtime: bool) -> None:
    """A run of batches, single payloads, rendered payloads and pages gets no 429, on Starter's limits and on Business's, through either integration method."""
    fake = FakeOxylabs(limit=limit, render_limit=render_limit)
    payloads = [
        *(universal(str(page)) for page in range(300)),
        *(walmart(str(product)) for product in range(120)),
        *(universal(str(page), render="html") for page in range(40)),
        *(universal(str(page), pages=3) for page in range(30)),
    ]
    async with open_async_session(transport=fake) as session:
        run = await session.execute(payloads, realtime=realtime)
    assert (len(run.all()), run.progress.retries) == (len(payloads), 0)


@on_mock_clock
async def test_llm_pacing(fake: FakeOxylabs) -> None:
    """A run of LLM payloads gets no 429, because each counts against the rendered limit."""
    payloads = [
        oxy.Payload(source="chatgpt", prompt=f"Question {n}") for n in range(40)
    ]
    async with open_async_session() as session:
        run = await session.execute(payloads)
    assert (len(run.all()), run.progress.retries) == (40, 0)


@on_mock_clock
async def test_payload_above_a_limit(fake: FakeOxylabs) -> None:
    """A rendered payload with `pages: 14` ends as a Rejection without a retry, and the payloads beside it run."""
    large = universal("large", render="html", pages=14)
    async with open_async_session() as session:
        error = await incomplete(await session.stream([large, universal()]))
    [rejection] = error.rejections
    assert (rejection.payload, rejection.status_code) == (large, 429)
    assert rejection.message == (
        "The payload's 14 pages exceed the total-render-requests limit of 13, so the API returns 429 for it in every window"
    )
    assert rejection.trace_id
    assert (submissions(fake), len(error.jobs), error.__cause__) == (2, 1, None)


@on_mock_clock
async def test_smaller_plan() -> None:
    """A batch sized for Starter's limits goes out again in batches that fit the limits its 429 names."""
    fake = FakeOxylabs(limit=10, render_limit=3)
    payloads = [universal(str(page)) for page in range(30)]
    async with open_async_session(transport=fake) as session:
        run = await session.execute(payloads)
    assert (len(run.all()), run.progress.retries) == (30, 1)
    assert [
        len(json.loads(request.content)["url"])
        for request in fake.requests
        if request.method == "POST"
    ] == [30, 10, 10, 10]


@on_mock_clock
async def test_runs_share_budgets(fake: FakeOxylabs) -> None:
    """Two runs on one session share its budgets, so together they get no 429."""
    async with open_async_session() as session:
        first = await session.stream([walmart(str(product)) for product in range(60)])
        second = await session.stream(
            [walmart(str(product)) for product in range(60, 120)]
        )
        jobs = [*await first.all(), *await second.all()]
    assert len(jobs) == 120
    assert first.progress.retries + second.progress.retries == 0


@on_mock_clock
async def test_slow_loop_pauses_submissions(fake: FakeOxylabs) -> None:
    """While 100 finished jobs wait for the caller's loop, oxy sends at most the submissions it already paced."""
    payloads = [universal(str(page)) for page in range(500)]
    async with open_async_session() as session:
        run = await session.stream(payloads)
        await anyio.sleep(30)
        submitted = len(fake.jobs)
        jobs = await run.all()
    assert submitted <= 200
    assert len(jobs) == 500


@pytest.mark.parametrize("realtime", [False, True])
async def test_run_releases_taken_results(realtime: bool) -> None:
    """A run holds no results of a job that its loop has taken."""
    payloads = [universal(str(page)) for page in range(3)]
    async with open_async_session() as session:
        run = await session.stream(payloads, realtime=realtime)
        taken = [weakref.ref(job.results[0]) async for job in run]
        gc.collect()
        assert [result() for result in taken] == [None, None, None]
        assert run.progress.done == 3


def test_session_run_releases_taken_results() -> None:
    """A `Session` run holds no results of a job that its loop has taken."""
    payloads = [universal(str(page)) for page in range(3)]
    with open_session() as session:
        run = session.execute(payloads)
        taken = [weakref.ref(job.results[0]) for job in run]
        gc.collect()
        assert [result() for result in taken] == [None, None, None]
        assert run.progress.done == 3


@on_mock_clock
async def test_execute_returns_a_run() -> None:
    """`AsyncSession.execute` returns a run whose partitions hold every job."""
    payloads = [universal(str(page)) for page in range(5)]
    async with open_async_session() as session:
        run = await session.execute(payloads)
    assert [len(jobs) for jobs in run.partitions(2)] == [2, 2, 1]


@on_mock_clock
async def test_one_needs_one_job() -> None:
    """`one` raises for a run of two jobs."""
    async with open_async_session() as session:
        run = await session.execute([universal("1"), universal("2")])
    with pytest.raises(ValueError, match="2 jobs"):
        run.one()


@on_mock_clock
async def test_output_types() -> None:
    """`output_types` sends `type`, and a `png` result holds the decoded bytes."""
    fake = FakeOxylabs(Outcome(content=lambda _, kind: PNG if kind == "png" else ""))
    async with open_async_session(transport=fake) as session:
        run = await session.stream(universal(), output_types=["raw", "png"])
        job = await anext(run)
        markdown = await session.get(job.id, output_types=["markdown"])
    assert [(result.type, result.content) for result in job.results] == [
        ("raw", ""),
        ("png", PNG),
    ]
    assert [result.type for result in markdown.results] == ["markdown"]
    assert fake.requests[1].url.params["type"] == "raw,png"
    with pytest.raises(ValueError, match="2 results"):
        _ = job.content


@on_mock_clock
async def test_check_schedule() -> None:
    """oxy checks a job every second until it is 10 seconds old, then every 5 seconds."""
    fake = FakeOxylabs(Outcome(after=12))
    async with open_async_session(transport=fake) as session:
        started = anyio.current_time()
        job = (await session.execute(universal())).one()
        elapsed = anyio.current_time() - started
    assert checks(fake) == 11
    assert elapsed == 15
    assert job.finished_at == START + timedelta(seconds=12)


@on_mock_clock
async def test_delayed_check_sends_no_burst(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A check delayed past later checks in the schedule skips them, and sends the next one on time."""

    def uniform(low: float, high: float) -> float:
        return high

    monkeypatch.setattr(random, "uniform", uniform)
    fake = FakeOxylabs(Outcome(after=30))
    # The first check fails 4 times and waits 1, 2, 4 and 8 seconds, so it ends 16 seconds after the submission.
    fake.fail(503, on="results", times=4)
    async with open_async_session(transport=fake) as session:
        started = anyio.current_time()
        job = (await session.execute(universal())).one()
        elapsed = anyio.current_time() - started
    # 5 requests at 1 to 16 seconds, then one check each at 20, 25 and 30.
    assert checks(fake) == 8
    assert (job.status, elapsed) == ("done", 30)


@on_mock_clock
async def test_slow_loop_pauses_checks() -> None:
    """At most 100 finished jobs wait for the caller's loop, and oxy checks no more until one leaves."""
    fake = FakeOxylabs(limit=150)
    payloads = [universal(str(page)) for page in range(150)]
    async with open_async_session(transport=fake) as session:
        run = await session.stream(payloads)
        await anyio.sleep(30)
        waiting = checks(fake)
        await anext(run)
        await anyio.sleep(1)
        assert (waiting, checks(fake)) == (100, 101)


@on_mock_clock
async def test_requests_at_once() -> None:
    """oxy sends at most 100 requests at once."""
    fake = Slow()
    payloads = [universal(str(page)) for page in range(150)]
    async with open_async_session(transport=fake) as session:
        await session.execute(payloads)
    assert fake.most == 100


@on_mock_clock
async def test_get_pending() -> None:
    """`get` returns a pending job at once, with no results, and leaving the block stops the run."""
    fake = FakeOxylabs(Outcome(after=math.inf))
    async with open_async_session(transport=fake) as session:
        await session.stream(universal())
        await anyio.sleep(1)
        job = await session.get(fake.jobs[0]["id"])
    assert (job.status, job.results, job.finished_at) == ("pending", [], None)
    assert (job.payload, job.data["status"]) == (None, "pending")


@on_mock_clock
async def test_get_expired() -> None:
    """`get` returns a finished job whose results expired with its final status and no results."""
    fake = FakeOxylabs(Outcome(after=2, expires_after=5))
    async with open_async_session(transport=fake) as session:
        done = (await session.execute(universal())).one()
        await anyio.sleep(10)
        expired = await session.get(done.id)
    assert (expired.status, expired.results) == ("done", [])
    assert expired.finished_at == done.finished_at == START + timedelta(seconds=2)


def stored_universal(path: str = "", **fields: Any) -> oxy.Payload:
    return universal(path, storage_type="gcs", storage_url="gs://bucket/path", **fields)


@on_mock_clock
async def test_upload(fake: FakeOxylabs) -> None:
    """A job with `storage_type` is checked on the status endpoint alone, and the run yields it with its upload and no results."""
    async with open_async_session() as session:
        run = await session.stream(stored_universal())
        [job] = await run.all()
    assert job.upload == oxy.Upload(
        storage_url=f"gs://bucket/path/{job.id}.json",
        code=13000,
        message="Upload Successful",
    )
    assert (job.status, job.results) == ("done", [])
    assert checks(fake) == 0
    assert (run.progress.uploaded, run.progress.unuploaded) == (1, 0)


@on_mock_clock
@pytest.mark.parametrize(
    ("status", "code", "message"),
    [
        ("done", 10001, "Unexpected Exception"),
        ("done", 13001, "Upload Failed"),
        ("done", 13102, "No such path"),
        ("faulted", 13103, "Access Denied"),
    ],
)
async def test_failed_upload(
    caplog: pytest.LogCaptureFixture,
    status: Literal["done", "faulted"],
    code: int,
    message: str,
) -> None:
    """Any code but 13000 moves the job into `unuploaded`, and the run yields it and raises."""
    fake = FakeOxylabs(Outcome(status=status, upload=code))
    payload = stored_universal()
    async with open_async_session(transport=fake) as session:
        run = await session.stream(payload)
        error = await incomplete(run)
    [job] = error.jobs
    assert error.unuploaded == [job]
    assert (job.status, job.upload and job.upload.code) == (status, code)
    assert (run.progress.uploaded, run.progress.unuploaded) == (0, 1)
    assert (
        f"The upload of job {job.id} failed with {code} {message}: universal {payload.url}"
        in warnings(caplog)
    )


@on_mock_clock
async def test_late_upload() -> None:
    """A finished job stays pending until its `statuses` entry appears."""
    fake = FakeOxylabs(Outcome(upload_after=18))
    async with open_async_session(transport=fake) as session:
        run = await session.stream(stored_universal())
        await anyio.sleep(17)
        middle = run.progress
        [job] = await run.all()
    assert (middle.pending, middle.done) == (1, 0)
    assert job.upload
    assert job.upload.code == 13000
    assert run.progress.elapsed == timedelta(seconds=20)


@on_mock_clock
async def test_upload_without_entry(caplog: pytest.LogCaptureFixture) -> None:
    """A finished job with no `statuses` entry at the pending limit counts as a failed upload."""
    fake = FakeOxylabs(Outcome(upload=None))
    payload = stored_universal()
    async with open_async_session(transport=fake, pending_limit=30) as session:
        run = await session.stream(payload)
        error = await incomplete(run)
    [job] = error.unuploaded
    assert error.jobs == [job]
    assert (job.status, job.upload and job.upload.code) == ("done", None)
    assert run.progress == dataclasses.replace(
        progress(done=1, unuploaded=1), elapsed=timedelta(seconds=30)
    )
    assert warnings(caplog) == [
        f"Cloud Storage recorded no upload for job {job.id} within 30.00s: universal {payload.url}"
    ]


@on_mock_clock
async def test_unchecked_upload(caplog: pytest.LogCaptureFixture) -> None:
    """A job object without `statuses` leaves its upload unchecked, with one warning per `storage_url`."""
    payloads = [
        oxy.Payload(
            source="walmart_product",
            product_id=product_id,
            storage_type="gcs",
            storage_url="gs://bucket/path",
        )
        for product_id in ("1", "2")
    ]
    async with open_async_session() as session:
        run = await session.stream(payloads)
        jobs = await run.all()
    assert {job.upload and job.upload.code for job in jobs} == {None}
    assert run.progress == dataclasses.replace(
        progress(done=2), elapsed=run.progress.elapsed
    )
    assert warnings(caplog) == [
        "Cannot check the uploads to gs://bucket/path, because the job object of walmart_product has no statuses"
    ]


def created(fake: FakeOxylabs) -> list[float]:
    """Return the second each job was created, counted from the fake's start."""
    return [
        (datetime.fromisoformat(job["created_at"]).replace(tzinfo=UTC) - START).seconds
        for job in fake.jobs
    ]


@on_mock_clock
async def test_check_storage(caplog: pytest.LogCaptureFixture) -> None:
    """`check_storage` submits the first payload of a `storage_url` alone, and the rest once its upload succeeds."""
    caplog.set_level(logging.INFO, "oxyscraper")
    fake = FakeOxylabs(Outcome(upload_after=5))
    payloads = [stored_universal(str(page)) for page in range(3)]
    async with open_async_session(transport=fake) as session:
        await session.execute([*payloads, universal("other")])
    assert created(fake) == [0, 0, 5, 5]
    assert lines(caplog, logging.INFO)[1:3] == [
        "Checking the upload to gs://bucket/path with one job before submitting 2 more payloads",
        "Uploaded the first job to gs://bucket/path in 5.00s",
    ]


@on_mock_clock
async def test_without_check_storage(fake: FakeOxylabs) -> None:
    """`check_storage=False` submits every payload at once, and still checks each upload."""
    payloads = [stored_universal(str(page)) for page in range(3)]
    async with open_async_session() as session:
        run = await session.stream(payloads, check_storage=False)
        await run.all()
    assert submissions(fake) == 1
    assert run.progress.uploaded == 3


@on_mock_clock
@pytest.mark.parametrize(
    ("outcome", "reason"),
    [
        (Outcome(upload=13103), "the first upload failed"),
        (Outcome(after=math.inf), "oxy stopped checking the first job"),
    ],
)
async def test_first_upload_fails(
    caplog: pytest.LogCaptureFixture, outcome: Outcome, reason: str
) -> None:
    """When the first upload of a `storage_url` fails, the rest of its payloads stay unsubmitted."""
    fake = FakeOxylabs(outcome)
    payloads = [stored_universal(str(page)) for page in range(3)]
    async with open_async_session(transport=fake, pending_limit=20) as session:
        error = await incomplete(await session.stream(payloads))
    assert error.unsubmitted == payloads[1:]
    assert len(fake.jobs) == 1
    assert f"Held back 2 payloads for gs://bucket/path, because {reason}" in warnings(
        caplog
    )


@on_mock_clock
async def test_check_storage_after_a_rejection(fake: FakeOxylabs) -> None:
    """A rejected first payload passes the check to the next payload of its `storage_url`."""
    rejected = oxy.Payload(
        source="universal",
        url="https://10.0.0.1/",
        storage_type="gcs",
        storage_url="gs://bucket/path",
    )
    payloads = [rejected, stored_universal("1"), stored_universal("2")]
    async with open_async_session() as session:
        error = await incomplete(await session.stream(payloads))
    assert [rejection.payload for rejection in error.rejections] == [rejected]
    assert [job.input for job in error.jobs] == [f"{SANDBOX}/1", f"{SANDBOX}/2"]
    assert submissions(fake) == 3


def unlinked(job: oxy.Job) -> oxy.Job:
    """Return the job without its ID, the IDs in its results and its `_links`."""
    results = [
        dataclasses.replace(result, data=result.data | {"job_id": None})
        for result in job.results
    ]
    data = {
        key: value for key, value in job.data.items() if key not in {"id", "_links"}
    }
    return dataclasses.replace(job, id="", results=results, data=data)


@on_mock_clock
async def test_realtime_matches_push_pull(fake: FakeOxylabs) -> None:
    """A Realtime run yields the same job as a Push-Pull run, apart from `_links`."""
    payload = oxy.AmazonProduct(query="B000000001", parse=True)
    async with open_async_session() as session:
        realtime = (await session.execute(payload, realtime=True)).one()
        push_pull = (await session.execute(payload)).one()
    assert [request.url.host for request in fake.requests] == [
        "realtime.oxylabs.io",
        "data.oxylabs.io",
        "data.oxylabs.io",
    ]
    assert realtime.id == fake.jobs[0]["id"]
    assert "_links" not in realtime.data
    assert unlinked(realtime) == unlinked(push_pull)


def test_session_realtime(fake: FakeOxylabs) -> None:
    """`Session.execute` takes `realtime=True`."""
    with open_session() as session:
        job = session.execute(universal(), realtime=True).one()
    assert (job.status, fake.requests[0].url.host) == ("done", "realtime.oxylabs.io")


@on_mock_clock
async def test_realtime_job() -> None:
    """A Realtime job finishes when its response returns, with `finished_at` from its results and a read timeout of 300 seconds."""
    fake = FakeOxylabs(Outcome(after=12))
    async with open_async_session(transport=fake) as session:
        started = anyio.current_time()
        job = (
            await session.execute(universal(), realtime=True, output_types=["raw"])
        ).one()
        elapsed = anyio.current_time() - started
    [request] = fake.requests
    assert request.url.params["type"] == "raw"
    assert request.extensions["timeout"]["read"] == 300
    assert elapsed == 12
    assert (job.created_at, job.finished_at) == (START, START + timedelta(seconds=12))
    assert job.data["updated_at"] == job.data["created_at"]


@on_mock_clock
async def test_realtime_rejections(caplog: pytest.LogCaptureFixture) -> None:
    """A 408, an LLM source's 422 and a 400 each reject their payload once, and the run carries on."""
    caplog.set_level(logging.INFO, "oxyscraper")
    fake = FakeOxylabs(
        lambda payload: Outcome(after=150 if payload.get("url") == SLOW else 0)
    )
    slow = universal("slow")
    llm = oxy.Payload(source="chatgpt", prompt="Name a color.")
    ip = oxy.Payload(source="universal", url="https://10.0.0.1/")
    async with open_async_session(transport=fake) as session:
        error = await incomplete(
            await session.stream([slow, llm, ip, universal()], realtime=True)
        )
    [job] = error.jobs
    assert job.status == "done"
    assert [
        (rejection.payload, rejection.status_code, rejection.message)
        for rejection in error.rejections
    ] == [
        (
            slow,
            408,
            "Timed out. Realtime returns 408 for a job that runs 150 seconds or longer, so run this payload with Push-Pull",
        ),
        (
            llm,
            422,
            "Realtime integration is not supported for LLM sources. Please use Push-Pull.",
        ),
        (ip, 400, "The hostname cannot be an ip address."),
    ]
    assert (submissions(fake), error.__cause__) == (4, None)
    info = lines(caplog, logging.INFO)
    assert (info[0], info[1], info[-1]) == (
        "Running 4 payloads with Realtime",
        "1/4 done, 2 rejected, 1 pending, 10.00s",
        "Finished 4 payloads in 2m 40s: 1 done, 3 rejected",
    )


SLOW = f"{SANDBOX}/slow"


@pytest.mark.parametrize(
    "arguments", [{"realtime": True}, {"destination": MemoryStore()}]
)
async def test_storage_type_conflicts(
    fake: FakeOxylabs, arguments: dict[str, Any]
) -> None:
    """`realtime=True` or `destination=` with a payload that sets `storage_type` raises before any request."""
    payloads = [universal(), universal(storage_type="gcs", storage_url="gs://bucket")]
    async with open_async_session() as session:
        with pytest.raises(ValueError, match="storage_type"):
            await session.stream(payloads, **arguments)
    assert fake.requests == []


@on_mock_clock
async def test_realtime_payload_above_a_limit(fake: FakeOxylabs) -> None:
    """A Realtime payload with `pages: 14` and `render` ends as a Rejection without a retry."""
    large = universal(render="html", pages=14)
    async with open_async_session() as session:
        error = await incomplete(await session.stream(large, realtime=True))
    [rejection] = error.rejections
    assert (rejection.payload, rejection.status_code) == (large, 429)
    assert "exceed the total-render-requests limit of 13" in rejection.message
    assert submissions(fake) == 1


@on_mock_clock
async def test_realtime_retries(
    fake: FakeOxylabs, caplog: pytest.LogCaptureFixture
) -> None:
    """A Realtime submission retries a 503 under the same policy, with a WARNING line."""
    fake.fail(503, on="submit")
    payload = universal()
    async with open_async_session() as session:
        job = (await session.execute(payload, realtime=True)).one()
    assert (job.status, submissions(fake)) == ("done", 2)
    assert warnings(caplog) == [
        f"Retrying a submission of universal {payload.url} after 503 Service Unavailable; the API may have created its job, and a duplicate bills"
    ]


@on_mock_clock
async def test_realtime_slow_loop() -> None:
    """At most 100 Realtime jobs wait for the caller's loop or for their response, and oxy submits no more until one leaves."""
    fake = FakeOxylabs(limit=150)
    payloads = [universal(str(page)) for page in range(150)]
    async with open_async_session(transport=fake) as session:
        run = await session.stream(payloads, realtime=True)
        await anyio.sleep(30)
        waiting = submissions(fake)
        await anext(run)
        await anyio.sleep(1)
        assert (waiting, submissions(fake)) == (100, 101)


@on_mock_clock
async def test_realtime_stop(
    fake: FakeOxylabs, caplog: pytest.LogCaptureFixture
) -> None:
    """A 401 on one Realtime submission stops the run, and a submission that waits to retry stays unsubmitted."""
    fake.fail(503, on="submit")
    fake.fail(401, on="submit", times=None)
    payloads = [universal("1"), universal("2")]
    async with open_async_session() as session:
        run = await session.stream(payloads, realtime=True)
        error = await incomplete(run)
    assert sorted(error.unsubmitted, key=repr) == sorted(payloads, key=repr)
    assert (error.unfetched, cause(error).status_code) == ([], 401)
    assert run.progress.unsubmitted == 2
    assert warnings(caplog)[-1] == (
        "Stopped submitting, because the API returned 401 Unauthorized; 2 payloads stay unsubmitted"
    )


@on_real_time
async def test_destination() -> None:
    """Each done job's body goes unchanged to `<job_id>.json` before the run yields the job, on Push-Pull and Realtime."""
    fake = Recorded(
        lambda payload: Outcome(
            status="faulted" if "FAULT" in payload["url"] else "done"
        )
    )
    store = MemoryStore()
    written: dict[str, bool] = {}
    async with open_async_session(transport=fake) as session:
        for realtime in (False, True):
            run = await session.stream(
                [universal(), universal("FAULT")], realtime=realtime, destination=store
            )
            async for job in run:
                written[job.id] = f"{job.id}.json" in stored(store)
            assert run.progress.written == 1
    done = [job_id for job_id, found in written.items() if found]
    assert len(done) == 2
    assert stored(store) == {f"{job_id}.json": fake.bodies[job_id] for job_id in done}


def test_destination_folder(tmp_path: Path) -> None:
    """A path or a string without `://` names a local folder that oxy creates and appends to, and a string with `://` names a store."""
    folder = tmp_path / "results" / "2026"
    with open_session() as session:
        first = session.execute(universal("1"), realtime=True, destination=folder).one()
        second = session.execute(
            universal("2"), realtime=True, destination=str(folder)
        ).one()
        run = session.execute(universal("3"), realtime=True, destination="memory:///")
        run.one()
    assert sorted(path.name for path in folder.iterdir()) == [
        f"{first.id}.json",
        f"{second.id}.json",
    ]
    assert json.loads((folder / f"{second.id}.json").read_bytes()) == {
        "job": second.data,
        "results": [result.data for result in second.results],
    }
    assert run.progress.written == 1


async def test_unreachable_destination(fake: FakeOxylabs) -> None:
    """A destination that oxy cannot list raises before any request."""
    async with open_async_session() as session:
        with pytest.raises(obstore.exceptions.BaseError):
            await session.stream(universal(), destination="nowhere://bucket")
    assert fake.requests == []


@on_real_time
async def test_failed_write(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """A failed write stops submission, and the run yields the jobs it already submitted unwritten before it raises."""
    # The first job's path is a folder, so its write fails.
    (tmp_path / "7500000000000000001.json").mkdir()
    fake = FakeOxylabs(
        lambda payload: Outcome(after=0.5 if "slow" in payload["url"] else 0)
    )
    # The first payload takes the whole render budget, so the last two wait for the next window.
    full = universal(render="html", pages=13)
    held = [universal("1", render="html"), universal("2", render="html")]
    store = MemoryStore()
    async with open_async_session(transport=fake) as session:
        run = await session.stream(
            [full, universal("slow"), *held],
            realtime=True,
            destination=tmp_path,
            run_log=store,
        )
        error = await incomplete(run)
    assert sorted(job.id for job in error.jobs) == [job["id"] for job in fake.jobs]
    assert error.unsubmitted == held
    assert isinstance(error.__cause__, obstore.exceptions.BaseError)
    assert [path.name for path in tmp_path.iterdir()] == ["7500000000000000001.json"]  # noqa: ASYNC240
    assert run.progress.written == 0
    stopped, failed = warnings(caplog)
    assert failed.startswith(
        "Writing job 7500000000000000001 to the destination failed, so oxy writes nothing more: "
    )
    assert stopped == (
        "Stopped submitting, because a write to the destination failed; 2 payloads stay unsubmitted"
    )
    *_, first, second = logged(store)
    assert first["error"] == second["error"]
    assert first["error"]["status_code"] is None
    assert first["error"]["message"].startswith(f"{type(error.__cause__).__name__}: ")


@on_real_time
async def test_failed_last_write(tmp_path: Path) -> None:
    """A failed write raises after the last job even when every payload has a job."""
    (tmp_path / "7500000000000000001.json").mkdir()
    async with open_async_session() as session:
        error = await incomplete(
            await session.stream(universal(), realtime=True, destination=tmp_path)
        )
    assert [job.status for job in error.jobs] == ["done"]
    assert isinstance(error.__cause__, obstore.exceptions.BaseError)
    assert str(error) == "the run stopped"


def trace(number: int) -> str:
    """Return the fake's trace ID for its `number`th error response."""
    return f"{number:08x}-{'0' * 24}"


def logged(store: MemoryStore) -> list[dict[str, Any]]:
    """Return the lines of the store's only run log."""
    [log] = stored(store).values()
    return [json.loads(line) for line in log.splitlines()]


def record(
    state: str,
    payload: dict[str, Any],
    job_id: str | None = None,
    error: dict[str, Any] | None = None,
    upload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "state": state,
        "id": job_id,
        "payload": payload,
        "error": error,
        "upload": upload,
    }


@on_mock_clock
async def test_run_log() -> None:
    """The run log holds one line per payload in input order, with `storage_url` credentials redacted."""
    fake = FakeOxylabs(
        lambda payload: Outcome(
            status="faulted" if "FAULT" in payload["url"] else "done",
            after=math.inf if "STUCK" in payload["url"] else 0,
        )
    )
    rejected = oxy.Payload(
        source="universal",
        url="https://10.0.0.1/",
        storage_type="s3_compatible",
        storage_url="https://key-id:s3cr3t@storage.example.com/bucket",
    )
    payloads = [universal("1"), rejected, universal("FAULT"), universal("STUCK")]
    store = MemoryStore()
    async with open_async_session(transport=fake, pending_limit=5) as session:
        error = await incomplete(await session.stream(payloads, run_log=store))
    done, faulted = sorted(error.jobs, key=lambda job: job.status)
    [rejection] = error.rejections
    [stuck] = error.unfetched
    assert logged(store) == [
        record("done", {"source": "universal", "url": f"{SANDBOX}/1"}, done.id),
        record(
            "rejected",
            {
                "source": "universal",
                "url": "https://10.0.0.1/",
                "storage_type": "s3_compatible",
                "storage_url": "https://redacted:redacted@storage.example.com/bucket",
            },
            error={
                "status_code": 400,
                "message": "The hostname cannot be an ip address.",
                "trace_id": rejection.trace_id,
            },
        ),
        record(
            "faulted", {"source": "universal", "url": f"{SANDBOX}/FAULT"}, faulted.id
        ),
        record(
            "unfetched", {"source": "universal", "url": f"{SANDBOX}/STUCK"}, stuck.id
        ),
    ]


@on_mock_clock
async def test_run_log_upload() -> None:
    """A line's `upload` holds the code and message of its job's `statuses` entry."""
    fake = FakeOxylabs(
        lambda payload: Outcome(upload=None if "NONE" in payload["url"] else 13102)
    )
    store = MemoryStore()
    payloads = [stored_universal("1"), stored_universal("NONE")]
    async with open_async_session(transport=fake, pending_limit=20) as session:
        run = await session.stream(payloads, run_log=store, check_storage=False)
        error = await incomplete(run)
    failed, missing = error.unuploaded
    assert [line["upload"] for line in logged(store)] == [
        {"code": 13102, "message": "No such path"},
        {"code": None, "message": None},
    ]
    assert [line["id"] for line in logged(store)] == [failed.id, missing.id]


def test_empty_run_log() -> None:
    """oxy writes an empty run log before the first submission, on Realtime too."""
    store = MemoryStore()
    seen: list[dict[str, bytes]] = []

    def outcome(payload: dict[str, Any]) -> Outcome:
        seen.append(stored(store))
        return Outcome()

    with FakeOxylabs(outcome), open_session() as session:
        job = session.execute(universal(), realtime=True, run_log=store).one()
    assert [list(contents.values()) for contents in seen] == [[b""]]
    assert logged(store) == [
        record("done", {"source": "universal", "url": f"{SANDBOX}/"}, job.id)
    ]


@on_mock_clock
@pytest.mark.parametrize("taken", [True, False])
async def test_run_log_after_a_stop(
    caplog: pytest.LogCaptureFixture, taken: bool
) -> None:
    """Leaving the `with` block, after a `break` or without taking the done job, writes the pending job as unfetched."""
    fake = FakeOxylabs(
        lambda payload: Outcome(after=math.inf if "STUCK" in payload["url"] else 0)
    )
    store = MemoryStore()
    async with open_async_session(transport=fake) as session:
        run = await session.stream([universal("1"), universal("STUCK")], run_log=store)
        if taken:
            async for _ in run:
                break
        else:
            await anyio.sleep(1.5)
    done, stuck = (job["id"] for job in fake.jobs)
    assert logged(store) == [
        record("done", {"source": "universal", "url": f"{SANDBOX}/1"}, done),
        record("unfetched", {"source": "universal", "url": f"{SANDBOX}/STUCK"}, stuck),
    ]
    assert (run.progress.pending, run.progress.unfetched) == (0, 1)
    [name] = stored(store)
    assert warnings(caplog) == [
        f"Stopped with 1 job pending, which may still bill; the run log at {name} lists their IDs"
    ]


@on_mock_clock
async def test_stop_cancels_retries(fake: FakeOxylabs) -> None:
    """Leaving the `with` block cancels a submission's retries, and its payload stays unsubmitted."""
    fake.fail(503, on="submit", times=None)
    async with open_async_session() as session:
        started = anyio.current_time()
        run = await session.stream(universal())
        await anyio.sleep(5)
    assert anyio.current_time() - started == 5
    assert run.progress.unsubmitted == 1


class Delayed(FakeOxylabs):
    """Answer each submission after `delay` seconds, and set `sent` when one arrives."""

    def __init__(self, delay: float) -> None:
        super().__init__()
        self.delay = delay
        self.sent = threading.Event()

    @override
    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        if request.method == "POST":
            self.sent.set()
            await anyio.sleep(self.delay)
        return await super().handle_async_request(request)


def ctrl_c(fake: Delayed, store: MemoryStore, *, twice: bool = False) -> None:
    """Send Ctrl+C once the fake receives a batch, and again half a second later if `twice`."""
    with open_session(transport=fake) as session:
        session.execute([universal("1"), universal("2")], run_log=store)
        fake.sent.wait()
        if twice:
            main = threading.main_thread().ident
            threading.Timer(0.5, signal.pthread_kill, [main, signal.SIGINT]).start()
        signal.raise_signal(signal.SIGINT)


def test_ctrl_c_keeps_a_sent_batch() -> None:
    """Ctrl+C while a batch's response is delayed raises `KeyboardInterrupt` itself, and the run log lists the batch's jobs."""
    fake = Delayed(1)
    store = MemoryStore()
    with pytest.raises(KeyboardInterrupt):
        ctrl_c(fake, store)
    first, second = (job["id"] for job in fake.jobs)
    assert logged(store) == [
        record("unfetched", {"source": "universal", "url": f"{SANDBOX}/1"}, first),
        record("unfetched", {"source": "universal", "url": f"{SANDBOX}/2"}, second),
    ]


@pytest.mark.skipif(
    not hasattr(signal, "pthread_kill"), reason="Windows has no pthread_kill"
)
def test_second_ctrl_c() -> None:
    """A second Ctrl+C while the session closes stops the sent batch at once, and leaves the run log empty."""
    fake = Delayed(5)
    store = MemoryStore()
    with pytest.raises(KeyboardInterrupt):
        ctrl_c(fake, store, twice=True)
    assert fake.jobs == []
    assert list(stored(store).values()) == [b""]


async def cancel_twice(fake: Delayed, store: MemoryStore) -> None:
    """Leave the block once the fake receives a batch, and cancel the task half a second later, as `asyncio.run` does after a second Ctrl+C."""
    task = asyncio.current_task()
    assert task is not None
    async with open_async_session(transport=fake) as session:
        await session.stream([universal("1"), universal("2")], run_log=store)
        await anyio.to_thread.run_sync(fake.sent.wait)
        asyncio.get_running_loop().call_later(0.5, task.cancel)


@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_second_stop_on_asyncio() -> None:
    """The cancellation that `asyncio.run` sends after a second Ctrl+C stops the sent batch at once, and leaves the run log empty."""
    fake = Delayed(5)
    store = MemoryStore()
    with pytest.raises(asyncio.CancelledError):
        await cancel_twice(fake, store)
    task = asyncio.current_task()
    assert task is not None
    task.uncancel()
    assert fake.jobs == []
    assert list(stored(store).values()) == [b""]


def test_run_log_folder(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """A run writes `<run_log>/<run start>.jsonl`, with the start in UTC to the millisecond, and names it in an INFO line."""
    caplog.set_level(logging.INFO, "oxyscraper")
    folder = tmp_path / "logs"
    before = datetime.now(UTC)
    with open_session() as session:
        session.execute(universal(), realtime=True, run_log=str(folder)).one()
        session.execute(universal(), realtime=True, run_log="memory:///").one()
    after = datetime.now(UTC)
    [log] = folder.iterdir()
    assert re.fullmatch(r"\d{8}T\d{6}\.\d{3}Z\.jsonl", log.name)
    started = datetime.strptime(log.name, "%Y%m%dT%H%M%S.%fZ.jsonl").replace(tzinfo=UTC)
    assert before - timedelta(milliseconds=1) <= started <= after
    first, second = (
        message for message in lines(caplog, logging.INFO) if "run log" in message
    )
    assert first == f"Wrote the run log to {log}"
    assert re.fullmatch(r"Wrote the run log to memory:///\d{8}T[\d.]+Z\.jsonl", second)


@on_real_time
async def test_failed_run_log(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """A failed final write of the run log raises after the last job."""
    async with open_async_session() as session:
        run = await session.stream(universal(), realtime=True, run_log=tmp_path)
        # The run's first checkpoint comes after this, so the final write finds a folder.
        [log] = tmp_path.iterdir()  # noqa: ASYNC240
        log.unlink()
        log.mkdir()
        error = await incomplete(run)
    assert [job.status for job in error.jobs] == ["done"]
    assert isinstance(error.__cause__, obstore.exceptions.BaseError)
    [failed] = warnings(caplog)
    assert failed.startswith(f"Writing the run log to {log} failed: ")


@on_mock_clock
async def test_run_log_errors() -> None:
    """An unsubmitted or unfetched payload's line holds the error behind it."""

    def outcome(payload: dict[str, Any]) -> Outcome:
        fake.fail(403, on="submit", times=None)
        return Outcome(after=math.inf)

    fake = FakeOxylabs(outcome)
    fake.fail(404, on="results")
    store = MemoryStore()
    async with open_async_session(transport=fake) as session:
        error = await incomplete(
            await session.stream([walmart("1"), walmart("2")], run_log=store)
        )
    [unfetched] = error.unfetched
    assert logged(store) == [
        record(
            "unfetched",
            {"source": "walmart_product", "product_id": "1"},
            unfetched.id,
            {"status_code": 404, "message": "Not Found", "trace_id": trace(2)},
        ),
        record(
            "unsubmitted",
            {"source": "walmart_product", "product_id": "2"},
            error={"status_code": 403, "message": "Forbidden", "trace_id": trace(1)},
        ),
    ]


@on_mock_clock
async def test_run_log_after_leaving_at_once(fake: FakeOxylabs) -> None:
    """Leaving the `with` block before the first submission writes every payload as unsubmitted."""
    store = MemoryStore()
    async with open_async_session() as session:
        await session.stream([universal("1"), universal("2")], run_log=store)
    assert fake.requests == []
    assert logged(store) == [
        record("unsubmitted", {"source": "universal", "url": f"{SANDBOX}/1"}),
        record("unsubmitted", {"source": "universal", "url": f"{SANDBOX}/2"}),
    ]


@pytest.mark.parametrize(
    ("session", "username", "password"),
    [(oxy.Session, "", "PASSWORD"), (oxy.AsyncSession, "USERNAME", "")],
)
def test_empty_credentials(
    session: type[oxy.Session | oxy.AsyncSession], username: str, password: str
) -> None:
    """An empty username or password raises before any request."""
    with pytest.raises(ValueError, match="must not be empty"):
        session(username=username, password=password)


@on_mock_clock
async def test_innermost_fake(fake: FakeOxylabs) -> None:
    """A session built inside a `with FakeOxylabs()` block uses that fake."""
    with FakeOxylabs() as inner:
        async with open_async_session() as session:
            await session.execute(universal())
    assert (len(inner.jobs), len(fake.jobs)) == (1, 0)


@on_mock_clock
async def test_transport_wins(fake: FakeOxylabs) -> None:
    """`transport=` wins over an open `with FakeOxylabs()` block."""
    given = FakeOxylabs()
    async with open_async_session(transport=given) as session:
        await session.execute(universal())
    assert (len(given.jobs), len(fake.jobs)) == (1, 0)


THROTTLE = "Access to sandbox.oxylabs.io has been limited to 1 req/s due to a low success rate. If you are using custom headers or cookies, ensure they are correct, then try again. The normal request limit will be restored automatically when the success rate improves."


@on_mock_clock
@pytest.mark.parametrize(
    "error",
    [
        429,
        503,
        httpx2.ReadTimeout("no answer"),
        httpx2.ConnectError("refused"),
        httpx2.RemoteProtocolError("closed"),
        httpx2.DecodingError("bad gzip"),
    ],
)
@pytest.mark.parametrize("on", ["submit", "results"])
async def test_retries(
    fake: FakeOxylabs, error: int | Exception, on: Literal["submit", "results"]
) -> None:
    """oxy retries a 429, a 5xx, a network error and a body that does not decode on a submission and on a check."""
    fake.fail(error, on=on, times=3)
    async with open_async_session() as session:
        job = (await session.execute(universal())).one()
    assert job.status == "done"
    assert len(fake.requests) == 5


@on_mock_clock
@pytest.mark.parametrize(
    "body",
    [
        "<html>",
        "{}",
        '{"job": {"status": "done"}, "results": [{"page": 1, "type": "png", "status_code": 200, "content": "a"}]}',
    ],
    ids=["not JSON", "no job", "bad Base64"],
)
async def test_retries_a_body_that_does_not_parse(body: str) -> None:
    """A 2xx whose body oxy cannot read retries."""
    fake = Garbled(body)
    async with open_async_session(transport=fake) as session:
        job = (await session.execute(universal())).one()
    assert (job.status, fake.garbled) == ("done", 1)


@on_mock_clock
@pytest.mark.parametrize(
    ("error", "shown"),
    [
        (503, "503 Service Unavailable"),
        (httpx2.ReadTimeout("no answer"), "ReadTimeout: no answer"),
        (httpx2.DecodingError("bad gzip"), "DecodingError: bad gzip"),
        (httpx2.ConnectError("refused"), None),
        (429, None),
    ],
)
async def test_unknown_outcome(
    fake: FakeOxylabs,
    caplog: pytest.LogCaptureFixture,
    error: int | Exception,
    shown: str | None,
) -> None:
    """A submission retried after a 5xx or a read error writes a WARNING line, and one that never reached a job writes none."""
    fake.fail(error, on="submit")
    payload = universal()
    async with open_async_session() as session:
        await session.execute(payload)
    line = f"Retrying a submission of universal {payload.url} after {shown}; the API may have created its job, and a duplicate bills"
    assert warnings(caplog) == ([line] if shown else [])


@on_mock_clock
async def test_unknown_outcome_of_a_batch(
    fake: FakeOxylabs, caplog: pytest.LogCaptureFixture
) -> None:
    """A batch retried after a 5xx writes one WARNING line that names its size."""
    fake.fail(503, on="submit")
    async with open_async_session() as session:
        await session.execute([universal("1"), universal("2")])
    assert warnings(caplog) == [
        "Retrying a batch of 2 universal payloads after 503 Service Unavailable; the API may have created their jobs, and each duplicate bills"
    ]


@on_mock_clock
async def test_retry_limit(fake: FakeOxylabs) -> None:
    """A submission stops retrying `retry_limit` seconds after its first failure, and stops the run."""
    fake.fail(503, on="submit", times=None)
    payload = universal()
    async with open_async_session(retry_limit=5) as session:
        started = anyio.current_time()
        error = await incomplete(await session.stream(payload))
        elapsed = anyio.current_time() - started
    assert elapsed == pytest.approx(5)
    assert (error.unsubmitted, error.rejections, error.unfetched) == ([payload], [], [])
    assert (cause(error).status_code, cause(error).message) == (
        503,
        "Service Unavailable",
    )
    assert re.fullmatch(r"[0-9a-f]{8}-0{24}", cause(error).trace_id or "")
    assert isinstance(cause(error).__cause__, httpx2.HTTPStatusError)
    assert str(error) == "1 unsubmitted"


@on_mock_clock
async def test_backoff_bounds(
    fake: FakeOxylabs, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each retry waits up to a ceiling that doubles from 1 second to 30, and never past `retry_limit`."""
    bounds: list[tuple[float, float]] = []

    def uniform(low: float, high: float) -> float:
        bounds.append((low, high))
        return high

    monkeypatch.setattr(random, "uniform", uniform)
    fake.fail(503, on="submit", times=None)
    async with open_async_session(retry_limit=100) as session:
        started = anyio.current_time()
        await incomplete(await session.stream(universal()))
        elapsed = anyio.current_time() - started
    assert bounds == [
        (0, 1),
        (0, 2),
        (0, 4),
        (0, 8),
        (0, 16),
        (0, 30),
        (0, 30),
        (0, 30),
    ]
    # 1 + 2 + 4 + 8 + 16 + 30 + 30 is 91, so the last wait stops at the limit after 9 seconds.
    assert elapsed == 100


@on_mock_clock
@pytest.mark.parametrize(
    ("error", "retry_limit"),
    [(httpx2.ReadTimeout("no answer"), 0), (httpx2.ProxyError("refused"), 600)],
)
async def test_network_failure(
    fake: FakeOxylabs,
    caplog: pytest.LogCaptureFixture,
    error: Exception,
    retry_limit: float,
) -> None:
    """A network error past the retry limit, or one that oxy never retries, stops the run with no status code."""
    fake.fail(error, on="submit", times=None)
    async with open_async_session(retry_limit=retry_limit) as session:
        stopped = await incomplete(await session.stream(universal()))
    shown = f"{type(error).__name__}: {error}"
    assert submissions(fake) == 1
    assert cause(stopped).__cause__ is error
    assert (cause(stopped).status_code, cause(stopped).trace_id) == (None, None)
    assert cause(stopped).message == str(cause(stopped)) == shown
    assert warnings(caplog) == [
        f"Stopped submitting, because httpx2 raised {shown}; 1 payloads stay unsubmitted"
    ]


@on_mock_clock
async def test_rejections(caplog: pytest.LogCaptureFixture) -> None:
    """A 400 or a 422 rejects its payload, and the run finishes the rest before it raises."""
    fake = FakeOxylabs(
        lambda payload: (
            Rejected("Nope.", status_code=422)
            if payload["url"].endswith("422")
            else Outcome()
        )
    )
    # Each payload differs from the others in a parameter, so each goes out alone.
    ip = oxy.Payload(
        source="universal", url="https://10.0.0.1/", user_agent_type="mobile"
    )
    llm = universal("422", user_agent_type="tablet")
    async with open_async_session(transport=fake) as session:
        error = await incomplete(await session.stream([ip, llm, universal()]))
    [job] = error.jobs
    assert job.status == "done"
    assert [
        (rejection.payload, rejection.status_code, rejection.message)
        for rejection in error.rejections
    ] == [(ip, 400, "The hostname cannot be an ip address."), (llm, 422, "Nope.")]
    assert all(rejection.trace_id for rejection in error.rejections)
    assert (error.unsubmitted, error.unfetched, error.__cause__) == ([], [], None)
    assert warnings(caplog) == [
        "Rejected universal https://10.0.0.1/: 400 The hostname cannot be an ip address.",
        f"Rejected universal {llm.url}: 422 Nope.",
    ]


@on_mock_clock
async def test_rejection_lists_errors() -> None:
    """A rejection whose body has no `message` joins its `errors`."""
    payload = oxy.Payload(source="walmart_product", query="436012154")
    async with open_async_session() as session:
        error = await incomplete(await session.stream(payload))
    [rejection] = error.rejections
    assert rejection.message == (
        "[product_id]: This field is missing. [query]: This field was not expected."
    )


@on_mock_clock
async def test_stop_yields_accepted_jobs(caplog: pytest.LogCaptureFixture) -> None:
    """A 403 on a submission stops submission, and the run still yields the job the API accepted."""

    def outcome(payload: dict[str, Any]) -> Outcome:
        fake.fail(403, on="submit", times=None)
        return Outcome(after=5)

    fake = FakeOxylabs(outcome)
    payloads = [walmart(str(product)) for product in range(3)]
    async with open_async_session(transport=fake) as session:
        error = await incomplete(await session.stream(payloads))
    [job] = error.jobs
    assert (job.status, job.id) == ("done", fake.jobs[0]["id"])
    assert sorted([job.payload, *error.unsubmitted], key=repr) == sorted(
        payloads, key=repr
    )
    assert cause(error).status_code == 403
    assert warnings(caplog) == [
        "Stopped submitting, because the API returned 403 Forbidden; 2 payloads stay unsubmitted"
    ]


@on_mock_clock
async def test_domain_throttle(fake: FakeOxylabs) -> None:
    """The domain throttle's 429 stops submission without a retry."""
    fake.fail(429, on="submit", times=None, message=THROTTLE)
    payload = universal()
    async with open_async_session() as session:
        error = await incomplete(await session.stream(payload))
    assert (submissions(fake), error.unsubmitted) == (1, [payload])
    assert (cause(error).status_code, cause(error).message) == (429, THROTTLE)


@on_mock_clock
@pytest.mark.parametrize(
    ("status", "phrase", "trace_id"),
    [(401, "Unauthorized", None), (403, "Forbidden", trace(1))],
)
async def test_unauthorized_check(
    caplog: pytest.LogCaptureFixture, status: int, phrase: str, trace_id: str | None
) -> None:
    """A 401 or 403 on a check stops the run at once, with every pending job unfetched because of it."""

    def outcome(payload: dict[str, Any]) -> Outcome:
        fake.fail(status, on="results", times=None)
        return Outcome(after=30)

    fake = FakeOxylabs(outcome)
    store = MemoryStore()
    async with open_async_session(transport=fake) as session:
        started = anyio.current_time()
        error = await incomplete(
            await session.stream([universal("1"), universal("2")], run_log=store)
        )
        elapsed = anyio.current_time() - started
    assert elapsed == 1
    assert sorted(job.id for job in error.unfetched) == [job["id"] for job in fake.jobs]
    assert {job.status for job in error.unfetched} == {"pending"}
    assert cause(error).status_code == status
    assert [record["error"] for record in logged(store)] == 2 * [
        {"status_code": status, "message": phrase, "trace_id": trace_id}
    ]
    [name] = stored(store)
    assert warnings(caplog) == [
        f"Stopped checking 2 jobs, because the API returned {status} {phrase}; each may still bill",
        f"Stopped with 2 jobs pending, which may still bill; the run log at {name} lists their IDs",
    ]


@on_mock_clock
async def test_unauthorized_check_yields_fetched_jobs() -> None:
    """A 401 on a check still yields the job that an earlier check fetched and the caller has not taken."""
    fake = FakeOxylabs(
        lambda payload: Outcome(after=1 if payload["url"].endswith("/1") else 30)
    )
    async with open_async_session(transport=fake) as session:
        run = await session.stream([universal("1"), universal("2")])
        await anyio.sleep(1.5)
        fake.fail(401, on="results", times=None)
        error = await incomplete(run)
    [job] = error.jobs
    [unfetched] = error.unfetched
    assert (job.input, job.status) == (f"{SANDBOX}/1", "done")
    assert (unfetched.input, unfetched.status) == (f"{SANDBOX}/2", "pending")
    assert cause(error).status_code == 401


@on_mock_clock
async def test_failed_read(fake: FakeOxylabs, caplog: pytest.LogCaptureFixture) -> None:
    """A read that returns an error moves only its own job into `unfetched`."""
    fake.fail(404, on="results")
    async with open_async_session() as session:
        error = await incomplete(await session.stream([universal("1"), universal("2")]))
    [job] = error.jobs
    [unfetched] = error.unfetched
    assert (job.status, unfetched.status, unfetched.results) == ("done", "pending", [])
    assert error.__cause__ is None
    assert warnings(caplog) == [
        f"Stopped checking job {unfetched.id}, because the API returned 404 Not Found: universal {unfetched.input}"
    ]


@on_mock_clock
async def test_read_out_of_retries(fake: FakeOxylabs) -> None:
    """A check out of retries moves its job into `unfetched`, and stops nothing else."""
    fake.fail(503, on="results", times=None)
    async with open_async_session(retry_limit=5) as session:
        error = await incomplete(await session.stream(universal()))
    assert [job.id for job in error.unfetched] == [fake.jobs[0]["id"]]
    assert (error.unsubmitted, error.__cause__) == ([], None)


@on_mock_clock
@pytest.mark.parametrize(
    ("limit", "shown"),
    [(0.5, "500ms"), (20, "20.00s"), (90, "1m 30s"), (3700, "1h 01m 40s")],
)
async def test_pending_limit(
    caplog: pytest.LogCaptureFixture, limit: float, shown: str
) -> None:
    """A check that shows a job pending at or past the pending limit moves it into `unfetched`."""
    fake = FakeOxylabs(Outcome(after=math.inf))
    payload = universal()
    async with open_async_session(transport=fake, pending_limit=limit) as session:
        started = anyio.current_time()
        error = await incomplete(await session.stream(payload))
        elapsed = anyio.current_time() - started
    [job] = error.unfetched
    assert elapsed == max(limit, 1)
    assert warnings(caplog) == [
        f"Stopped checking job {job.id}, because it is still pending after {shown}: universal {payload.url}"
    ]


@on_mock_clock
async def test_no_pending_limit() -> None:
    """`pending_limit=None` checks a job until it finishes."""
    fake = FakeOxylabs(Outcome(after=700))
    async with open_async_session(transport=fake, pending_limit=None) as session:
        job = (await session.execute(universal())).one()
    assert job.status == "done"


@on_mock_clock
async def test_faulted(caplog: pytest.LogCaptureFixture) -> None:
    """A run whose only problem is a faulted job yields it and raises nothing."""
    fake = FakeOxylabs(Outcome(status="faulted"))
    payload = universal()
    async with open_async_session(transport=fake) as session:
        job = (await session.execute(payload)).one()
    assert job.status == "faulted"
    assert warnings(caplog) == [f"Job {job.id} faulted: universal {payload.url}"]


@on_mock_clock
async def test_faulted_without_results() -> None:
    """A run yields a faulted job whose results endpoint returns 204, with no results."""
    fake = FakeOxylabs(Outcome(status="faulted", after=3, expires_after=0))
    payload = universal()
    async with open_async_session(transport=fake) as session:
        job = (await session.execute(payload)).one()
    assert (job.status, job.results, job.payload) == ("faulted", [], payload)
    assert job.finished_at == START + timedelta(seconds=3)


def test_all_keeps_collected_jobs() -> None:
    """`Run.all` stores the jobs it collected in the error it raises, and a second call raises again."""
    ip = oxy.Payload(source="universal", url="https://10.0.0.1/")
    with open_session() as session:
        run = session.execute([ip, universal()])
        with pytest.raises(oxy.IncompleteRunError) as caught:
            run.all()
        with pytest.raises(oxy.IncompleteRunError) as again:
            run.all()
    [job] = caught.value.jobs
    assert job.status == "done"
    assert again.value.jobs == []


@on_mock_clock
async def test_async_all_raises_again() -> None:
    """A second `AsyncRun.all` raises again, as `Run.all` does."""
    ip = oxy.Payload(source="universal", url="https://10.0.0.1/")
    async with open_async_session() as session:
        run = await session.stream([ip, universal()])
        await incomplete(run)
        assert (await incomplete(run)).jobs == []


def test_partitions_yield_the_partial_list() -> None:
    """`Run.partitions` yields its partial list before it raises."""
    ip = oxy.Payload(source="universal", url="https://10.0.0.1/")
    with open_session() as session:
        partitions = session.execute([ip, universal()]).partitions(5)
        [job] = next(partitions)
        with pytest.raises(oxy.IncompleteRunError) as caught:
            next(partitions)
    assert job.status == "done"
    assert caught.value.jobs == []


@on_mock_clock
async def test_get_raises(fake: FakeOxylabs) -> None:
    """`get` raises `OxylabsError` with the status code, message and trace ID."""
    async with open_async_session(retry_limit=0) as session:
        with pytest.raises(oxy.OxylabsError) as missing:
            await session.get("7000000000000000001")
        fake.fail(401, on="results")
        with pytest.raises(oxy.OxylabsError) as unauthorized:
            await session.get("7000000000000000001")
        fake.fail(500, on="results")
        with pytest.raises(oxy.OxylabsError) as server:
            await session.get("7000000000000000001")
    assert (missing.value.status_code, missing.value.message) == (
        404,
        "Query not found.",
    )
    assert missing.value.trace_id == f"{1:08x}-{'0' * 24}"
    assert str(missing.value) == "404 Query not found."
    assert isinstance(missing.value.__cause__, httpx2.HTTPStatusError)
    assert (unauthorized.value.message, unauthorized.value.trace_id) == (
        "Unauthorized",
        None,
    )
    assert (server.value.message, server.value.trace_id) == (
        "Internal Server Error",
        f"{2:08x}-{'0' * 24}",
    )


def progress(**counts: Any) -> oxy.Progress:
    states = ("unsubmitted", "pending", "done", "faulted", "rejected", "unfetched")
    totals = dict.fromkeys((*states, "written", "uploaded", "unuploaded", "retries"), 0)
    totals |= counts
    return oxy.Progress(
        payloads=sum(totals[state] for state in states), **totals, elapsed=timedelta()
    )


@pytest.mark.parametrize(
    ("counts", "elapsed", "shown"),
    [
        (
            {
                "done": 412,
                "faulted": 3,
                "pending": 1250,
                "unsubmitted": 6935,
                "retries": 12,
            },
            timedelta(seconds=45.21),
            "412/8,600 done, 3 faulted, 1,250 pending, 6,935 unsubmitted, 12 retries, 45.21s",
        ),
        (
            {"unsubmitted": 1, "retries": 1},
            timedelta(milliseconds=312),
            "0/1 done, 1 unsubmitted, 1 retry, 312ms",
        ),
        (
            {"done": 2, "rejected": 1, "unfetched": 1},
            timedelta(seconds=4.02),
            "2/4 done, 1 rejected, 1 unfetched, 4.02s",
        ),
        (
            {"done": 2, "written": 2, "uploaded": 1, "unuploaded": 1},
            timedelta(seconds=65),
            "2/2 done, 2 written, 1 uploaded, 1 unuploaded, 1m 05s",
        ),
        (
            {"done": 1},
            timedelta(hours=2, minutes=24, seconds=5.9),
            "1/1 done, 2h 24m 05s",
        ),
    ],
)
def test_progress_str(counts: dict[str, int], elapsed: timedelta, shown: str) -> None:
    """`str(Progress)` leaves out zero counts and formats the elapsed time as uv does."""
    assert str(dataclasses.replace(progress(**counts), elapsed=elapsed)) == shown


SIX = ("unsubmitted", "pending", "done", "faulted", "rejected", "unfetched")


@on_mock_clock
async def test_progress_sums_to_payloads() -> None:
    """Every snapshot's six states sum to `payloads`, and the last one matches the error's lists."""

    def outcome(payload: dict[str, Any]) -> Outcome:
        page = int(payload["url"].rsplit("/", 1)[1])
        return Outcome(status="faulted" if page % 4 == 0 else "done", after=page)

    fake = FakeOxylabs(outcome)
    payloads = [universal(str(page)) for page in range(1, 9)]
    payloads.append(oxy.Payload(source="universal", url="https://10.0.0.1/"))
    async with open_async_session(transport=fake, pending_limit=6) as session:
        run = await session.stream(payloads)
        snapshots = [run.progress]
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(incomplete, run)
            for _ in range(20):
                await anyio.sleep(0.5)
                snapshots.append(run.progress)
        error = await incomplete(run)
    last = run.progress
    assert {
        sum(getattr(snapshot, state) for state in SIX) for snapshot in snapshots
    } == {9}
    assert snapshots[0] == dataclasses.replace(
        progress(unsubmitted=9), elapsed=timedelta()
    )
    assert snapshots[3] == dataclasses.replace(
        progress(pending=7, done=1, rejected=1), elapsed=timedelta(seconds=1.5)
    )
    assert last == dataclasses.replace(
        progress(done=5, faulted=1, rejected=1, unfetched=2),
        elapsed=timedelta(seconds=6),
    )
    assert (last.rejected, last.unsubmitted, last.unfetched) == (
        len(error.rejections),
        len(error.unsubmitted),
        len(error.unfetched),
    )


def lines(caplog: pytest.LogCaptureFixture, level: int) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.name == "oxyscraper" and record.levelno == level
    ]


@on_mock_clock
@pytest.mark.parametrize(
    ("interval", "periodic"),
    [
        (10, ["0/2 done, 2 pending, 10.00s", "0/2 done, 2 pending, 20.00s"]),
        (None, []),
    ],
)
async def test_info_lines(
    caplog: pytest.LogCaptureFixture, interval: float | None, periodic: list[str]
) -> None:
    """A run writes its start, a progress line every `progress_interval` seconds while a payload is pending, and its end."""
    caplog.set_level(logging.INFO, "oxyscraper")
    fake = FakeOxylabs(Outcome(after=25))
    async with open_async_session(
        transport=fake, progress_interval=interval
    ) as session:
        await session.execute([universal("1"), universal("2")])
        await anyio.sleep(30)
    assert lines(caplog, logging.INFO) == [
        "Running 2 payloads with Push-Pull",
        *periodic,
        "Finished 2 payloads in 25.00s: 2 done",
    ]


@on_mock_clock
async def test_stopped_line(caplog: pytest.LogCaptureFixture) -> None:
    """A run that a failure stops ends with a line that names each state and the retries."""
    caplog.set_level(logging.INFO, "oxyscraper")

    def outcome(payload: dict[str, Any]) -> Outcome:
        fake.fail(401, on="submit", times=None)
        return Outcome(after=math.inf)

    fake = FakeOxylabs(outcome)
    fake.fail(503, on="submit")
    async with open_async_session(transport=fake, pending_limit=None) as session:
        run = await session.stream([walmart("1"), walmart("2"), walmart("3")])
        await anyio.sleep(2.5)
        fake.fail(401, on="results", times=None)
        await incomplete(run)
    assert lines(caplog, logging.INFO)[-1] == (
        "Stopped 3 payloads after 3.00s: 0 done, 1 unfetched, 2 unsubmitted, 1 retry"
    )


@on_mock_clock
async def test_debug_lines(
    fake: FakeOxylabs, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run writes each change of state and each retry at DEBUG, with `storage_url` credentials redacted."""

    def uniform(low: float, high: float) -> float:
        return high / 2

    monkeypatch.setattr(random, "uniform", uniform)
    caplog.set_level(logging.DEBUG, "oxyscraper")
    fake.fail(503, on="status", times=2)
    payload = universal(
        storage_type="s3_compatible",
        storage_url="https://key-id:s3cr3t@storage.example.com/bucket/folder",
    )
    async with open_async_session() as session:
        run = await session.stream(payload)
        [job] = await run.all()
    status = f"https://data.oxylabs.io/v1/queries/{job.id}"
    assert lines(caplog, logging.DEBUG) == [
        f"Job {job.id} is pending: {payload!r}",
        f"Retrying GET {status} in 500ms after 503 Service Unavailable",
        f"Retrying GET {status} in 1.00s after 503 Service Unavailable",
        f"Job {job.id} is done: {payload!r}",
    ]
    assert "redacted:redacted" in repr(payload)
    assert not any("s3cr3t" in record.getMessage() for record in caplog.records)
    assert run.progress.retries == 2


def test_session_progress() -> None:
    """A `Session` run's progress reads mid-run from the caller's thread, and stops changing after the run ends."""
    payloads = [universal(str(page)) for page in range(3)]
    with open_session() as session:
        run = session.execute(payloads)
        started = run.progress
        jobs = iter(run)
        next(jobs)
        middle = run.progress
        list(jobs)
        ended = run.progress
    assert started.unsubmitted + started.pending == 3
    assert middle.done >= 1
    assert sum(getattr(middle, state) for state in SIX) == 3
    assert (ended.done, ended.elapsed >= timedelta(seconds=1)) == (3, True)
    assert run.progress == ended
