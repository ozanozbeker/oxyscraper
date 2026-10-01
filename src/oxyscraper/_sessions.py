"""The sessions, which submit payloads and return their jobs, the types they return, and `dry_run`.

`Session` drives `AsyncSession` through an anyio blocking portal, so both share one code path.
Every request goes through `AsyncSession._request`, which holds the limit of 100 requests at once per host.
"""

from __future__ import annotations

import base64
import collections
import itertools
import math
from contextlib import AsyncExitStack, ExitStack
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial
from importlib.metadata import version
from typing import TYPE_CHECKING, Any, Literal, Self, cast

import anyio
import httpx2
from anyio.from_thread import start_blocking_portal

from oxyscraper._payloads import _INPUT_KEYS, Payload, _redacted
from oxyscraper.testing import _switched_on

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Mapping, Sequence

    from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream

_OutputType = Literal["raw", "parsed", "png", "markdown", "xhr"]
_Status = Literal["pending", "done", "faulted"]
_Content = str | bytes | dict[str, Any] | list[Any]

_DATA = "https://data.oxylabs.io/v1/queries"
_USER_AGENT = f"oxyscraper/{version('oxyscraper')}"
# httpx2 makes a request past a connection's 100 HTTP/2 streams wait with no timeout.
_MAX_REQUESTS = 100
_MAX_WAITING = 100


@dataclass(frozen=True, kw_only=True)
class Result:
    """One page of a job's results, in one output type.

    Attributes
    ----------
    page
        The page number.
    type
        The output type.
    status_code
        The target's status code, or 613 for a faulted job.
    content
        The content, with `png` decoded from Base64 to bytes.
    created_at
        When the job started, in UTC.
    updated_at
        When the result finished, in UTC.
    data
        The result entry as the API returned it.
    """

    page: int
    type: _OutputType
    status_code: int
    content: _Content = field(repr=False)
    created_at: datetime
    updated_at: datetime
    data: dict[str, Any] = field(repr=False)


@dataclass(frozen=True, kw_only=True)
class Upload:
    """A job's Cloud Storage upload.

    Attributes
    ----------
    storage_url
        The object's path, which the API resolved from the payload's `storage_url`.
    code
        The code of the first entry in the job's `statuses`, where 13000 means success, or `None` while no entry exists.
    message
        That entry's message.
    """

    storage_url: str
    code: int | None
    message: str | None


@dataclass(frozen=True, kw_only=True)
class Job:
    """One job and its results.

    Attributes
    ----------
    id
        The job's ID.
    status
        `pending` until the job finishes.
    source
        The job's source.
    input
        The value of the job's input key, such as its `url` or `query`.
    created_at
        When the API accepted the job, in UTC.
    finished_at
        When the job finished, in UTC, or `None` while it is pending.
        It comes from the results, because a Realtime job object keeps `updated_at` equal to `created_at`.
    payload
        The payload that created the job, or `None` for a job from `get`.
    results
        One entry per page and output type.
        A pending job has none, and so has a job from `get` whose results expired.
    data
        The job object as the API returned it, so a field that oxy does not type stays readable.
    upload
        The Cloud Storage upload, or `None` without `storage_type`.
    """

    id: str
    status: _Status
    source: str
    input: str
    created_at: datetime
    finished_at: datetime | None
    payload: Payload | None
    results: list[Result] = field(repr=False)
    data: dict[str, Any] = field(repr=False)
    upload: Upload | None

    @property
    def content(self) -> _Content:
        """The content of the job's only result.

        Raises
        ------
        ValueError
            If the job has more or fewer than one result.
        """
        if len(self.results) != 1:
            msg = f"job {self.id} has {len(self.results)} results, so read job.results"
            raise ValueError(msg)
        return self.results[0].content


class Run:
    """The jobs of one run, each as it finishes.

    Iteration yields each job once, so `all`, `one` and `partitions` return only the jobs it has not yet yielded.
    """

    def __init__(self, jobs: Iterator[Job]) -> None:
        self._jobs = jobs

    def __iter__(self) -> Iterator[Job]:
        """Yield each job as it finishes."""
        return self._jobs

    def all(self) -> list[Job]:
        """Wait for every job, and return them in the order they finished."""
        return list(self._jobs)

    def one(self) -> Job:
        """Wait for the run's only job, and return it.

        Raises
        ------
        ValueError
            If the run holds more or fewer than one job.
        """
        jobs = self.all()
        if len(jobs) != 1:
            msg = f"the run holds {len(jobs)} jobs, not one"
            raise ValueError(msg)
        return jobs[0]

    def partitions(self, size: int) -> Iterator[list[Job]]:
        """Yield the jobs in lists of `size` as they finish, with a shorter last list."""
        while jobs := list(itertools.islice(self._jobs, size)):
            yield jobs


class AsyncRun:
    """The jobs of one `AsyncSession.stream` call, each as it finishes."""

    def __init__(
        self, jobs: MemoryObjectReceiveStream[Job], waiting: anyio.Semaphore
    ) -> None:
        self._jobs = jobs
        self._waiting = waiting

    def __aiter__(self) -> Self:
        """Yield each job as it finishes."""
        return self

    async def __anext__(self) -> Job:
        """Wait for the next job to finish, and return it."""
        try:
            job = await self._jobs.receive()
        except anyio.EndOfStream:
            raise StopAsyncIteration from None
        self._waiting.release()
        return job

    async def all(self) -> list[Job]:
        """Wait for every job, and return them in the order they finished."""
        return [job async for job in self]


class AsyncSession:
    """Submit payloads and fetch their jobs inside an `async with` block, on asyncio or trio.

    The block holds the task group that submits and checks while the caller's loop body runs.
    Leaving it stops every unfinished run.

    Parameters
    ----------
    username
        The API user's username.
    password
        The API user's password.
    transport
        The transport of every request, such as a `FakeOxylabs`.
        `None` uses the fake of the innermost open `with FakeOxylabs()` block, or else Oxylabs over HTTP/2.
    retry_limit
        The seconds after a request's first failure until it stops retrying.
    pending_limit
        The seconds after a job's acceptance until oxy stops checking it.
        `None` waits without limit.
    progress_interval
        The seconds between progress lines.
        `None` turns the lines off.

    Raises
    ------
    ValueError
        If `username` or `password` is empty.
    """

    def __init__(  # noqa: PLR0913
        self,
        *,
        username: str,
        password: str,
        transport: httpx2.AsyncBaseTransport | None = None,
        retry_limit: float = 600.0,
        pending_limit: float | None = 600.0,
        progress_interval: float | None = 10.0,
    ) -> None:
        if not username or not password:
            msg = "username and password must not be empty"
            raise ValueError(msg)
        # A given transport turns off httpx2's `http2`, `limits`, `verify` and proxy variables, so oxy passes none in production.
        self._http = httpx2.AsyncClient(
            auth=(username, password),
            transport=transport or _switched_on(),
            http2=True,
            headers={"User-Agent": _USER_AGENT},
        )
        self._retry_limit = retry_limit
        self._pending_limit = pending_limit
        self._progress_interval = progress_interval
        self._hosts: collections.defaultdict[str, anyio.Semaphore] = (
            collections.defaultdict(lambda: anyio.Semaphore(_MAX_REQUESTS))
        )
        self._stack = AsyncExitStack()

    async def __aenter__(self) -> Self:
        """Open the client and the task group that runs the runs."""
        await self._stack.enter_async_context(self._http)
        # The streams close after the task group exits, so no task sends into a closed stream.
        self._streams = self._stack.enter_context(ExitStack())
        self._tasks = await self._stack.enter_async_context(anyio.create_task_group())
        self._stack.callback(self._tasks.cancel_scope.cancel)
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        """Stop every unfinished run, and close the client."""
        await self._stack.aclose()

    async def execute(
        self,
        payloads: Payload | Iterable[Payload],
        *,
        output_types: Sequence[_OutputType] = (),
    ) -> Run:
        """Run the payloads, and return the run once its last job finishes.

        It takes the arguments of `stream`.
        """
        run = await self.stream(payloads, output_types=output_types)
        return Run(iter(await run.all()))

    async def stream(
        self,
        payloads: Payload | Iterable[Payload],
        *,
        output_types: Sequence[_OutputType] = (),
    ) -> AsyncRun:
        """Start a run, and return its jobs as they finish.

        Parameters
        ----------
        payloads
            One payload or several, each submitted as one job.
        output_types
            The output types of each result, sent as the API's `type` parameter.
            Empty returns the default type of each job.
        """
        listed = _listed(payloads)
        send, receive = anyio.create_memory_object_stream[Job](math.inf)
        self._streams.callback(receive.close)
        # A finished job holds a slot until the caller's loop takes it, so at most 100 wait in memory.
        waiting = anyio.Semaphore(_MAX_WAITING)
        self._tasks.start_soon(self._run, listed, send, waiting, output_types)
        return AsyncRun(receive, waiting)

    async def get(
        self, job_id: str, *, output_types: Sequence[_OutputType] = ()
    ) -> Job:
        """Return a job as it stands, at once.

        A pending job has empty `results`, and so has a finished job whose results expired.

        Parameters
        ----------
        job_id
            The job's ID.
        output_types
            The output types of each result, as in `stream`.
        """
        response = await self._results(job_id, output_types)
        if response.status_code == httpx2.codes.NO_CONTENT:
            data = (await self._request("GET", f"{_DATA}/{job_id}")).json()
            status = response.headers["x-oxylabs-job-status"]
            return _job(data, [], status=status)
        body = response.json()
        return _job(body["job"], body["results"])

    async def _run(
        self,
        payloads: list[Payload],
        send: MemoryObjectSendStream[Job],
        waiting: anyio.Semaphore,
        output_types: Sequence[_OutputType],
    ) -> None:
        async with send, anyio.create_task_group() as tasks:
            for payload in payloads:
                tasks.start_soon(self._push, payload, send, waiting, output_types)

    async def _push(
        self,
        payload: Payload,
        send: MemoryObjectSendStream[Job],
        waiting: anyio.Semaphore,
        output_types: Sequence[_OutputType],
    ) -> None:
        """Submit one payload, and check its job until it finishes."""
        response = await self._request("POST", _DATA, json=payload.model_dump())
        job_id = response.json()["id"]
        accepted = anyio.current_time()
        for age in itertools.chain(range(1, 10), itertools.count(10, 5)):
            await anyio.sleep_until(accepted + age)
            await waiting.acquire()
            response = await self._results(job_id, output_types)
            if response.status_code == httpx2.codes.NO_CONTENT:
                waiting.release()
                continue
            body = response.json()
            await send.send(_job(body["job"], body["results"], payload=payload))
            return

    async def _results(
        self, job_id: str, output_types: Sequence[_OutputType]
    ) -> httpx2.Response:
        """Fetch a job's results, which returns 204 while the job is pending."""
        params = {"type": ",".join(output_types)} if output_types else None
        return await self._request("GET", f"{_DATA}/{job_id}/results", params=params)

    async def _request(
        self,
        method: str,
        url: str,
        *,
        json: dict[str, Any] | None = None,
        params: Mapping[str, str] | None = None,
    ) -> httpx2.Response:
        async with self._hosts[httpx2.URL(url).host]:
            response = await self._http.request(method, url, json=json, params=params)
        return response.raise_for_status()


class Session:
    """Submit payloads and fetch their jobs from sync code, inside a `with` block.

    It takes the arguments of `AsyncSession`, and runs one through an anyio blocking portal.
    The portal's thread stays open only inside the block, because an open portal blocks the interpreter's exit.
    """

    def __init__(  # noqa: PLR0913
        self,
        *,
        username: str,
        password: str,
        transport: httpx2.AsyncBaseTransport | None = None,
        retry_limit: float = 600.0,
        pending_limit: float | None = 600.0,
        progress_interval: float | None = 10.0,
    ) -> None:
        self._session = AsyncSession(
            username=username,
            password=password,
            transport=transport,
            retry_limit=retry_limit,
            pending_limit=pending_limit,
            progress_interval=progress_interval,
        )
        self._stack = ExitStack()

    def __enter__(self) -> Self:
        """Start the portal, and open the session inside it."""
        self._portal = self._stack.enter_context(start_blocking_portal())
        self._stack.enter_context(
            self._portal.wrap_async_context_manager(self._session)
        )
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Stop every unfinished run, and close the portal."""
        self._stack.close()

    def execute(
        self,
        payloads: Payload | Iterable[Payload],
        *,
        output_types: Sequence[_OutputType] = (),
    ) -> Run:
        """Start a run, and return its jobs as they finish.

        It takes the arguments of `AsyncSession.stream`.
        """
        run = self._portal.call(
            partial(self._session.stream, payloads, output_types=output_types)
        )
        return Run(self._jobs(run))

    def get(self, job_id: str, *, output_types: Sequence[_OutputType] = ()) -> Job:
        """Return a job as it stands, at once.

        It takes the arguments of `AsyncSession.get`.
        """
        return self._portal.call(
            partial(self._session.get, job_id, output_types=output_types)
        )

    def _jobs(self, run: AsyncRun) -> Iterator[Job]:
        while True:
            try:
                yield self._portal.call(run.__anext__)
            except StopAsyncIteration:
                return


@dataclass(frozen=True, kw_only=True)
class DryRun:
    """The jobs a run would submit.

    Attributes
    ----------
    jobs
        Each job's body, with the credentials in `storage_url` replaced by `redacted:redacted`.
    max_results
        The most results the jobs can bill: the sum of their `pages`, with 1 for a job without it.
        Faulted jobs bill nothing, and a source that ignores `pages` bills 1, so a run can bill less.
    """

    jobs: list[dict[str, Any]]
    max_results: int

    @property
    def job_count(self) -> int:
        """The number of jobs."""
        return len(self.jobs)


def dry_run(payloads: Payload | Iterable[Payload]) -> DryRun:
    """List the jobs that a run of `payloads` would submit, and the most results they can bill.

    It sends no request and needs no credentials.
    oxy never reads the account's remaining results, so a caller who wants a spending limit compares `max_results` with their own.

    Examples
    --------
    ```python
    import oxyscraper as oxy

    report = oxy.dry_run(
        oxy.Payload(source="universal", url="https://example.com", pages=2)
    )
    print(report.job_count, report.max_results)  # 1 2
    ```
    """
    jobs = [_redacted(payload.model_dump()) for payload in _listed(payloads)]
    return DryRun(jobs=jobs, max_results=sum(job.get("pages", 1) for job in jobs))


def _listed(payloads: Payload | Iterable[Payload]) -> list[Payload]:
    return [payloads] if isinstance(payloads, Payload) else list(payloads)


def _job(
    data: dict[str, Any],
    results: list[dict[str, Any]],
    *,
    status: str | None = None,
    payload: Payload | None = None,
) -> Job:
    """Build a job from its job object, with `status` in place of the object's own."""
    final = cast("_Status", status or data["status"])
    entries = [_result(entry) for entry in results]
    finished = max(
        (entry.updated_at for entry in entries), default=_time(data["updated_at"])
    )
    return Job(
        id=data["id"],
        status=final,
        source=data["source"],
        input=next((data[key] for key in _INPUT_KEYS if data.get(key)), ""),
        created_at=_time(data["created_at"]),
        finished_at=None if final == "pending" else finished,
        payload=payload,
        results=entries,
        data=data,
        upload=_upload(data) if data.get("storage_type") else None,
    )


def _result(data: dict[str, Any]) -> Result:
    content = data["content"]
    return Result(
        page=data["page"],
        type=data["type"],
        status_code=data["status_code"],
        content=base64.b64decode(content) if data["type"] == "png" else content,
        created_at=_time(data["created_at"]),
        updated_at=_time(data["updated_at"]),
        data=data,
    )


def _upload(data: dict[str, Any]) -> Upload:
    entry = (data.get("statuses") or [{}])[0]
    return Upload(
        storage_url=data["storage_url"],
        code=entry.get("code"),
        message=entry.get("message"),
    )


def _time(value: str) -> datetime:
    # The API writes UTC with no offset.
    return datetime.fromisoformat(value).replace(tzinfo=UTC)
