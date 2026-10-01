import dataclasses
import logging
import math
import random
import re
from datetime import UTC, datetime, timedelta
from functools import partial
from importlib.metadata import version
from typing import Any, Literal

import anyio
import httpx2
import pytest
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


def universal(path: str = "", **fields: Any) -> oxy.Payload:
    return oxy.Payload(source="universal", url=f"{SANDBOX}/{path}", **fields)


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
    """Answer the first results download with a body that is not JSON."""

    def __init__(self) -> None:
        super().__init__()
        self.garbled = 0

    @override
    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        if request.url.path.endswith("/results") and not self.garbled:
            self.garbled += 1
            return httpx2.Response(200, text="<html>")
        return await super().handle_async_request(request)


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
    """`stream` submits one job per payload and yields each job, with oxy's user agent on every request."""
    payloads = [universal(str(page)) for page in range(3)]
    async with open_async_session() as session:
        jobs = [job async for job in await session.stream(payloads)]
    submissions = [request for request in fake.requests if request.method == "POST"]
    assert sorted(job.input for job in jobs) == [payload.url for payload in payloads]
    assert len(submissions) == 3
    assert {request.headers["user-agent"] for request in fake.requests} == {
        f"oxyscraper/{version('oxyscraper')}"
    }


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


@on_mock_clock
async def test_upload() -> None:
    """A job with `storage_type` carries its upload's path, code and message."""
    payload = universal(storage_type="gcs", storage_url="gs://bucket/path")
    async with open_async_session() as session:
        job = (await session.execute(payload)).one()
    assert job.upload == oxy.Upload(
        storage_url=f"gs://bucket/path/{job.id}.json",
        code=13000,
        message="Upload Successful",
    )


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
    ],
)
@pytest.mark.parametrize("on", ["submit", "results"])
async def test_retries(
    fake: FakeOxylabs, error: int | Exception, on: Literal["submit", "results"]
) -> None:
    """oxy retries a 429, a 5xx and a network error on a submission and on a check."""
    fake.fail(error, on=on, times=3)
    async with open_async_session() as session:
        job = (await session.execute(universal())).one()
    assert job.status == "done"
    assert len(fake.requests) == 5


@on_mock_clock
async def test_retries_a_body_that_is_not_json() -> None:
    """A 2xx whose body does not parse retries."""
    fake = Garbled()
    async with open_async_session(transport=fake) as session:
        job = (await session.execute(universal())).one()
    assert (job.status, fake.garbled) == ("done", 1)


@on_mock_clock
@pytest.mark.parametrize(
    ("error", "shown"),
    [
        (503, "503 Service Unavailable"),
        (httpx2.ReadTimeout("no answer"), "ReadTimeout: no answer"),
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
    ip = oxy.Payload(source="universal", url="https://10.0.0.1/")
    llm = universal("422")
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
    payloads = [universal(str(page)) for page in range(3)]
    async with open_async_session(transport=fake) as session:
        error = await incomplete(await session.stream(payloads))
    [job] = error.jobs
    assert (job.status, job.id) == ("done", fake.jobs[0]["id"])
    assert sorted(
        [job.input, *(str(payload.url) for payload in error.unsubmitted)]
    ) == [str(payload.url) for payload in payloads]
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
    ("status", "phrase"), [(401, "Unauthorized"), (403, "Forbidden")]
)
async def test_unauthorized_check(
    caplog: pytest.LogCaptureFixture, status: int, phrase: str
) -> None:
    """A 401 or 403 on a check stops the run at once, with every pending job unfetched."""

    def outcome(payload: dict[str, Any]) -> Outcome:
        fake.fail(status, on="results", times=None)
        return Outcome(after=30)

    fake = FakeOxylabs(outcome)
    async with open_async_session(transport=fake) as session:
        started = anyio.current_time()
        error = await incomplete(await session.stream([universal("1"), universal("2")]))
        elapsed = anyio.current_time() - started
    assert elapsed == 1
    assert sorted(job.id for job in error.unfetched) == [job["id"] for job in fake.jobs]
    assert {job.status for job in error.unfetched} == {"pending"}
    assert cause(error).status_code == status
    assert warnings(caplog) == [
        f"Stopped checking 2 jobs, because the API returned {status} {phrase}; each may still bill"
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
