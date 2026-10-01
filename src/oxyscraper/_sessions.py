"""The sessions, which submit payloads and return their jobs, the types they return, and `dry_run`.

`Session` drives `AsyncSession` through an anyio blocking portal, so both share one code path.
Every request goes through `AsyncSession._request`, which holds the limit of 100 requests at once per host and the retry policy.
"""

from __future__ import annotations

import base64
import collections
import itertools
import logging
import math
import random
import re
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

    from anyio.abc import TaskGroup
    from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream

_OutputType = Literal["raw", "parsed", "png", "markdown", "xhr"]
_Status = Literal["pending", "done", "faulted"]
_Content = str | bytes | dict[str, Any] | list[Any]

_DATA = "https://data.oxylabs.io/v1/queries"
_USER_AGENT = f"oxyscraper/{version('oxyscraper')}"
# httpx2 makes a request past a connection's 100 HTTP/2 streams wait with no timeout.
_MAX_REQUESTS = 100
_MAX_WAITING = 100
_MAX_WAIT = 30.0
_RETRIED = (httpx2.TimeoutException, httpx2.NetworkError, httpx2.RemoteProtocolError)
# These fail before the request leaves, so the API created no job.
_UNSENT = (httpx2.ConnectError, httpx2.ConnectTimeout, httpx2.PoolTimeout)
# httpx2 renamed 422's constant after the floor version, and warns on the old name.
_REJECTED = frozenset({400, 422})
_UNAUTHORIZED = frozenset({401, 403})
_THROTTLE = re.compile(r"Access to \S+ has been limited to 1 req/s")
# The API's 500 page names its trace ID only in its text.
_TRACE_ID = re.compile(r"trace_id: ([\w-]+)")

_logger = logging.getLogger("oxyscraper")


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


class OxylabsError(Exception):
    """One error response from the API, or a network failure that lasted past the retry limit.

    It chains the httpx2 exception.

    Attributes
    ----------
    status_code
        The response's status code, or `None` for a network failure.
    message
        The body's `message`, or its `errors` joined when it has none, or else the reason phrase.
    trace_id
        The ID that Oxylabs support asks for, or `None` when the response names none.
    """

    def __init__(
        self, *, status_code: int | None, message: str, trace_id: str | None = None
    ) -> None:
        super().__init__(message if status_code is None else f"{status_code} {message}")
        self.status_code = status_code
        self.message = message
        self.trace_id = trace_id


@dataclass(frozen=True, kw_only=True)
class Rejection:
    """The error that the API returned for a payload instead of a job, so nothing billed.

    Attributes
    ----------
    payload
        The rejected payload.
    status_code
        The response's status code.
    message
        The response's message, as `OxylabsError.message` reads it.
    trace_id
        The response's trace ID.
    """

    payload: Payload
    status_code: int
    message: str
    trace_id: str | None


class IncompleteRunError(Exception):
    """The error a run raises after its last job, when a payload ended with no done or faulted job.

    Its `__cause__` is the `OxylabsError` that stopped the run, if one did.

    Attributes
    ----------
    rejections
        One rejection per rejected payload.
    unsubmitted
        The payloads that a stop left unsent.
    unfetched
        The jobs that oxy stopped checking, each pending and with no results.
        `get` fetches one later.
    unuploaded
        The jobs whose Cloud Storage upload failed.
    jobs
        The jobs that `all` collected before it raised, and empty for any other call.
    """

    def __init__(
        self,
        *,
        rejections: list[Rejection],
        unsubmitted: list[Payload],
        unfetched: list[Job],
        unuploaded: list[Job],
    ) -> None:
        counts = {
            "rejected": len(rejections),
            "unsubmitted": len(unsubmitted),
            "unfetched": len(unfetched),
            "unuploaded": len(unuploaded),
        }
        super().__init__(
            ", ".join(f"{count} {state}" for state, count in counts.items() if count)
        )
        self.rejections = rejections
        self.unsubmitted = unsubmitted
        self.unfetched = unfetched
        self.unuploaded = unuploaded
        self.jobs: list[Job] = []


@dataclass(eq=False)
class _Line:
    """What happened to one payload of a run."""

    payload: Payload
    state: Literal[
        "unsubmitted", "pending", "done", "faulted", "rejected", "unfetched"
    ] = "unsubmitted"
    job: Job | None = None
    rejection: Rejection | None = None


@dataclass(eq=False)
class _RunState:
    """What the tasks of one run share with its `AsyncRun`."""

    lines: list[_Line]
    send: MemoryObjectSendStream[Job]
    waiting: anyio.Semaphore
    output_types: Sequence[_OutputType]
    # Cancelling `submitting` stops submission, and cancelling `running` stops the checks too.
    submitting: anyio.CancelScope = field(default_factory=anyio.CancelScope)
    running: anyio.CancelScope = field(default_factory=anyio.CancelScope)
    cause: OxylabsError | None = None

    def stop(self, error: OxylabsError, scope: anyio.CancelScope) -> None:
        self.cause = self.cause or error
        scope.cancel()

    def end(self) -> None:
        """Count the jobs that a stop left pending as unfetched, and log the stop."""
        halted = [line for line in self.lines if line.state == "pending"]
        for line in halted:
            line.state = "unfetched"
        if self.cause is None:
            return
        because = _because(self.cause)
        if unsubmitted := sum(line.state == "unsubmitted" for line in self.lines):
            _logger.warning(
                "Stopped submitting, because %s; %s payloads stay unsubmitted",
                because,
                unsubmitted,
            )
        if halted:
            _logger.warning(
                "Stopped checking %s jobs, because %s; each may still bill",
                len(halted),
                because,
            )

    def error(self) -> IncompleteRunError | None:
        rejections = [line.rejection for line in self.lines if line.rejection]
        unsubmitted = [
            line.payload for line in self.lines if line.state == "unsubmitted"
        ]
        unfetched = [
            line.job for line in self.lines if line.state == "unfetched" and line.job
        ]
        if not (rejections or unsubmitted or unfetched):
            return None
        return IncompleteRunError(
            rejections=rejections,
            unsubmitted=unsubmitted,
            unfetched=unfetched,
            unuploaded=[],
        )


class Run:
    """The jobs of one run, each as it finishes.

    Iteration yields each job once, so `all`, `one` and `partitions` return only the jobs it has not yet yielded.
    After the last job, it raises `IncompleteRunError` if a payload ended with no done or faulted job.
    """

    def __init__(self, jobs: Iterator[Job]) -> None:
        self._jobs = jobs

    def __iter__(self) -> Iterator[Job]:
        """Yield each job as it finishes."""
        return self._jobs

    def all(self) -> list[Job]:
        """Wait for every job, and return them in the order they finished.

        Raises
        ------
        IncompleteRunError
            If a payload ended with no done or faulted job, with the jobs collected so far in its `jobs`.
        """
        jobs: list[Job] = []
        try:
            jobs.extend(self._jobs)
        except IncompleteRunError as error:
            error.jobs = jobs
            raise
        return jobs

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
        """Yield the jobs in lists of `size` as they finish, with a shorter last list.

        When the run raises, the partial list comes first, so a bulk write keeps every job.
        """
        while True:
            jobs: list[Job] = []
            try:
                jobs.extend(itertools.islice(self._jobs, size))
            except IncompleteRunError:
                if jobs:
                    yield jobs
                raise
            if not jobs:
                return
            yield jobs


class AsyncRun:
    """The jobs of one `AsyncSession.stream` call, each as it finishes."""

    def __init__(self, jobs: MemoryObjectReceiveStream[Job], state: _RunState) -> None:
        self._jobs = jobs
        self._state = state

    def __aiter__(self) -> Self:
        """Yield each job as it finishes."""
        return self

    async def __anext__(self) -> Job:
        """Wait for the next job to finish, and return it."""
        try:
            job = await self._jobs.receive()
        except anyio.EndOfStream:
            if error := self._state.error():
                raise error from self._state.cause
            raise StopAsyncIteration from None
        self._state.waiting.release()
        return job

    async def all(self) -> list[Job]:
        """Wait for every job, and return them in the order they finished.

        It raises as `Run.all` does.
        """
        jobs: list[Job] = []
        try:
            # A comprehension drops the jobs it collected when the run raises.
            async for job in self:
                jobs.append(job)  # noqa: PERF401
        except IncompleteRunError as error:
            error.jobs = jobs
            raise
        return jobs


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
        send, receive = anyio.create_memory_object_stream[Job](math.inf)
        self._streams.callback(receive.close)
        state = _RunState(
            lines=[_Line(payload) for payload in _listed(payloads)],
            send=send,
            # A finished job holds a slot until the caller's loop takes it, so at most 100 wait in memory.
            waiting=anyio.Semaphore(_MAX_WAITING),
            output_types=output_types,
        )
        self._tasks.start_soon(self._run, state)
        return AsyncRun(receive, state)

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

        Raises
        ------
        OxylabsError
            If the API returns an error, or a network failure lasts past the retry limit.
        """
        response, body = await self._results(job_id, output_types)
        if body is None:
            _, data = await self._request("GET", f"{_DATA}/{job_id}")
            status = response.headers["x-oxylabs-job-status"]
            return _job(data, [], status=status)
        return _job(body["job"], body["results"])

    async def _run(self, state: _RunState) -> None:
        async with state.send:
            with state.running:
                async with anyio.create_task_group() as checks:
                    with state.submitting:
                        async with anyio.create_task_group() as submissions:
                            for line in state.lines:
                                submissions.start_soon(self._push, state, line, checks)
            state.end()

    async def _push(self, state: _RunState, line: _Line, checks: TaskGroup) -> None:
        """Submit one payload, and start the checks of its job."""
        body = line.payload.model_dump()
        try:
            _, data = await self._request("POST", _DATA, json=body)
        except OxylabsError as error:
            if error.status_code not in _REJECTED:
                state.stop(error, state.submitting)
                return
            line.state = "rejected"
            line.rejection = Rejection(
                payload=line.payload,
                status_code=error.status_code,
                message=error.message,
                trace_id=error.trace_id,
            )
            _logger.warning("Rejected %s %s: %s", *_named(body), error)
            return
        line.state = "pending"
        line.job = _job(data, [], payload=line.payload)
        checks.start_soon(self._check, state, line, line.job)

    async def _check(self, state: _RunState, line: _Line, pending: Job) -> None:
        """Check a job until it finishes, or until oxy stops checking it."""
        accepted = anyio.current_time()
        for age in itertools.chain(range(1, 10), itertools.count(10, 5)):
            await anyio.sleep_until(accepted + age)
            await state.waiting.acquire()
            try:
                _, body = await self._results(pending.id, state.output_types)
            except OxylabsError as error:
                state.waiting.release()
                if error.status_code in _UNAUTHORIZED:
                    state.stop(error, state.running)
                    return
                line.state = "unfetched"
                _logger.warning(
                    "Stopped checking job %s, because %s: %s %s",
                    pending.id,
                    _because(error),
                    pending.source,
                    pending.input,
                )
                return
            if body is not None:
                job = _job(body["job"], body["results"], payload=line.payload)
                line.state, line.job = job.status, job
                if job.status == "faulted":
                    _logger.warning(
                        "Job %s faulted: %s %s", job.id, job.source, job.input
                    )
                # `send` checks for cancellation first, so a stop would lose the fetched job.
                state.send.send_nowait(job)
                return
            state.waiting.release()
            limit = self._pending_limit
            if limit is not None and anyio.current_time() >= accepted + limit:
                line.state = "unfetched"
                _logger.warning(
                    "Stopped checking job %s, because it is still pending after %s: %s %s",
                    pending.id,
                    _duration(limit),
                    pending.source,
                    pending.input,
                )
                return

    async def _results(
        self, job_id: str, output_types: Sequence[_OutputType]
    ) -> tuple[httpx2.Response, Any]:
        """Fetch a job's results, which returns 204 and no body while the job is pending."""
        params = {"type": ",".join(output_types)} if output_types else None
        return await self._request("GET", f"{_DATA}/{job_id}/results", params=params)

    async def _request(
        self,
        method: str,
        url: str,
        *,
        json: dict[str, Any] | None = None,
        params: Mapping[str, str] | None = None,
    ) -> tuple[httpx2.Response, Any]:
        """Send a request under the retry policy, and return the response and its parsed body.

        Raises
        ------
        OxylabsError
            If the response is an error that oxy does not retry, or the retries outlast `retry_limit`.
        """
        deadline: float | None = None
        ceiling = 1.0
        while True:
            try:
                return await self._attempt(method, url, json=json, params=params)
            except OxylabsError as error:
                now = anyio.current_time()
                deadline = now + self._retry_limit if deadline is None else deadline
                if not _retried(error) or now >= deadline:
                    raise
                if json is not None and _unknown(error):
                    _logger.warning(
                        "Retrying a submission of %s %s after %s; the API may have created its job, and a duplicate bills",
                        *_named(json),
                        error,
                    )
            await anyio.sleep(min(random.uniform(0, ceiling), deadline - now))  # noqa: S311
            ceiling = min(ceiling * 2, _MAX_WAIT)

    async def _attempt(
        self,
        method: str,
        url: str,
        *,
        json: dict[str, Any] | None,
        params: Mapping[str, str] | None,
    ) -> tuple[httpx2.Response, Any]:
        try:
            async with self._hosts[httpx2.URL(url).host]:
                # The API may create a job once a submission is sent, so a stop lets the attempt finish and keeps the job's ID.
                with anyio.CancelScope(shield=method == "POST"):
                    response = await self._http.request(
                        method, url, json=json, params=params
                    )
            response.raise_for_status()
            if response.status_code == httpx2.codes.NO_CONTENT:
                return response, None
            try:
                return response, response.json()
            except ValueError as error:
                msg = f"the API returned {response.status_code} with a body that is not JSON"
                raise httpx2.RemoteProtocolError(msg) from error
        except httpx2.HTTPStatusError as error:
            raise _error(error.response) from error
        except httpx2.TransportError as error:
            message = f"{type(error).__name__}: {error}".removesuffix(": ")
            raise OxylabsError(status_code=None, message=message) from error


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


def _error(response: httpx2.Response) -> OxylabsError:
    """Read an error response, whose body is JSON, the 500 page or empty."""
    try:
        body = response.json()
    except ValueError:
        body = None
    body = body if isinstance(body, dict) else {}
    errors = body.get("errors")
    joined = " ".join(map(str, errors)) if isinstance(errors, list) else None
    page = _TRACE_ID.search(response.text)
    return OxylabsError(
        status_code=response.status_code,
        message=body.get("message") or joined or response.reason_phrase,
        trace_id=body.get("trace_id") or (page[1] if page else None),
    )


def _retried(error: OxylabsError) -> bool:
    if error.status_code is None:
        return isinstance(error.__cause__, _RETRIED)
    if error.status_code == httpx2.codes.TOO_MANY_REQUESTS:
        return not _THROTTLE.match(error.message)
    return error.status_code >= httpx2.codes.INTERNAL_SERVER_ERROR


def _unknown(error: OxylabsError) -> bool:
    """Return whether the API may have created a job for a submission that failed with `error`."""
    if error.status_code is None:
        return not isinstance(error.__cause__, _UNSENT)
    return error.status_code >= httpx2.codes.INTERNAL_SERVER_ERROR


def _because(error: OxylabsError) -> str:
    if error.status_code is None:
        return f"httpx2 raised {error}"
    return f"the API returned {error}"


def _named(data: Mapping[str, Any]) -> tuple[str, str]:
    """Return the source and the input of a body or a job object."""
    return data["source"], next((data[key] for key in _INPUT_KEYS if data.get(key)), "")


def _duration(seconds: float) -> str:
    """Format a duration as uv does."""
    whole = int(seconds)
    if whole >= 3600:  # noqa: PLR2004
        return f"{whole // 3600}h {whole % 3600 // 60:02}m {whole % 60:02}s"
    if whole >= 60:  # noqa: PLR2004
        return f"{whole // 60}m {whole % 60:02}s"
    if whole:
        return f"{int(seconds * 100) / 100:.2f}s"
    return f"{int(seconds * 1000)}ms"


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
        input=_named(data)[1],
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
