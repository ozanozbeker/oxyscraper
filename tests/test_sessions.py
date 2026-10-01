import dataclasses
import math
from datetime import UTC, datetime, timedelta
from functools import partial
from importlib.metadata import version
from typing import Any

import anyio
import httpx2
import pytest
from typing_extensions import override

import oxyscraper as oxy
from oxyscraper.testing import FakeOxylabs, Outcome

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
