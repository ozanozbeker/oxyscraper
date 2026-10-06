"""The sessions, which submit payloads and return their jobs, the types they return, and `dry_run`.

`Session` drives `AsyncSession` through an anyio blocking portal, so both share one code path.
Every request goes through `AsyncSession._request`, which holds the limit of 100 requests at once per host and the retry policy.
"""

from __future__ import annotations

import base64
import collections
import itertools
import json
import logging
import math
import os
import posixpath
import random
import re
from contextlib import AsyncExitStack, ExitStack, contextmanager, nullcontext
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from functools import partial
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Self, TypeVar, cast

import anyio
import httpx2
import obstore
from anyio.from_thread import start_blocking_portal
from obstore.store import LocalStore, from_url

from oxyscraper._payloads import _INPUT_KEYS, Payload, _integer, _redacted
from oxyscraper.testing import _switched_on

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence

    from anyio.abc import TaskGroup, TaskStatus
    from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
    from obstore.store import ObjectStore

_OutputType = Literal["raw", "parsed", "png", "markdown", "xhr"]
_Status = Literal["pending", "done", "faulted"]
_Content = str | bytes | dict[str, Any] | list[Any]
_T = TypeVar("_T")
_Limit = Literal["total-requests", "total-render-requests"]

_DATA = "https://data.oxylabs.io/v1/queries"
_BATCH = f"{_DATA}/batch"
_REALTIME = "https://realtime.oxylabs.io/v1/queries"
# The API returns 408 after about 160 seconds, and a read timeout of 300 seconds waits for it.
_REALTIME_TIMEOUTS = httpx2.Timeout(5.0, read=300.0)
_TIMED_OUT = "Realtime returns 408 for a job that runs 150 seconds or longer, so run this payload with Push-Pull"
_BATCH_KEYS = ("query", "url", "prompt")
_MAX_BATCH = 5000
_USER_AGENT = f"oxyscraper/{version('oxyscraper')}"
# httpx2 makes a request past a connection's 100 HTTP/2 streams wait with no timeout.
_MAX_REQUESTS = 100
_MAX_WAITING = 100
_MAX_WAIT = 30.0
_RETRIED = (
    httpx2.TimeoutException,
    httpx2.NetworkError,
    httpx2.RemoteProtocolError,
    httpx2.DecodingError,
)
# These fail before the request leaves, so the API created no job.
_UNSENT = (httpx2.ConnectError, httpx2.ConnectTimeout, httpx2.PoolTimeout)
_REJECTED = frozenset({httpx2.codes.BAD_REQUEST, httpx2.codes.UNPROCESSABLE_CONTENT})
_UNAUTHORIZED = frozenset({httpx2.codes.UNAUTHORIZED, httpx2.codes.FORBIDDEN})
_THROTTLE = re.compile(r"Access to \S+ has been limited to 1 req/s")
# The API's 500 page names its trace ID only in its text.
_TRACE_ID = re.compile(r"trace_id: ([\w-]+)")
# Each name carries the account's UUID and client ID, which stay the same for an account.
_RATE_LIMIT = re.compile(
    r"x-ratelimit-(?P<name>total_requests|total_render_requests)_[\w-]+-(?P<kind>limit|remaining)"
)
# The API counts every payload of these sources against the rendered limit, without `render` (docs/research/live-api.md).
_RENDERED_SOURCES = frozenset({"chatgpt", "gemini", "perplexity"})
# Starter's limits, which oxy assumes until a response carries the account's own.
_STARTER: dict[_Limit, int] = {"total-requests": 50, "total-render-requests": 13}

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
        The target's status code.
        A faulted job's entry holds 613 or 400, and a faulted job can have no entry.
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
        The code of the first entry in the job's `statuses`, where 13000 means success.
        `None` means no entry appeared before the pending limit, or the job object has no `statuses`, which holds for the sources whose job object is the payload alone.
        oxy cannot check those uploads, so it counts them neither as uploaded nor as unuploaded.
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
    """The error a run raises after its last job, when a payload ended with no done or faulted job, an upload failed, or a failure stopped the run.

    Its `__cause__` is the `OxylabsError` or the failed write that stopped the run, if one did.

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
            or "the run stopped"
        )
        self.rejections = rejections
        self.unsubmitted = unsubmitted
        self.unfetched = unfetched
        self.unuploaded = unuploaded
        self.jobs: list[Job] = []


@dataclass(frozen=True, kw_only=True)
class Progress:
    """The number of a run's payloads in each state, at one moment.

    The six states from `unsubmitted` to `unfetched` sum to `payloads`.
    After the run's last job, the snapshot stops changing and is the run's summary.

    Attributes
    ----------
    payloads
        The run's payloads.
    unsubmitted
        The payloads not yet sent, including those that oxy holds back.
    pending
        The payloads whose job is pending.
    done
        The payloads whose job is done.
    faulted
        The payloads whose job faulted.
    rejected
        The payloads that the API rejected, so no job exists.
    unfetched
        The payloads whose job oxy stopped checking.
    written
        The done jobs that oxy wrote to the destination.
    uploaded
        The jobs whose Cloud Storage upload succeeded.
    unuploaded
        The jobs whose Cloud Storage upload failed.
    retries
        The requests that the run sent again.
    elapsed
        The time since the run started, or the run's length once it ends.
    """

    payloads: int
    unsubmitted: int
    pending: int
    done: int
    faulted: int
    rejected: int
    unfetched: int
    written: int
    uploaded: int
    unuploaded: int
    retries: int
    elapsed: timedelta

    def __str__(self) -> str:
        """Return the done count, every other count that is not zero, and the elapsed time."""
        shown = [f"{self.done:,}/{self.payloads:,} done", *_counts(self)]
        return ", ".join([*shown, _duration(self.elapsed.total_seconds())])


_State = Literal["unsubmitted", "pending", "done", "faulted", "rejected", "unfetched"]
_ENDED = frozenset({"done", "faulted", "rejected", "unfetched"})


class _Shields:
    """The cancel scopes that keep a step running through a stop by the caller, until a second Ctrl+C drops them."""

    def __init__(self) -> None:
        self._scopes: set[anyio.CancelScope] = set()
        self._dropped = False

    @contextmanager
    def scope(self) -> Iterator[None]:
        with anyio.CancelScope(shield=not self._dropped) as scope:
            self._scopes.add(scope)
            try:
                yield
            finally:
                self._scopes.discard(scope)

    def drop(self) -> None:
        """Let the stop cancel every shielded step, open now or later."""
        self._dropped = True
        for scope in self._scopes:
            scope.shield = False


@dataclass(eq=False)
class _Line:
    """What happened to one payload of a run."""

    payload: Payload
    state: _State = "unsubmitted"
    job: Job | None = None
    rejection: Rejection | None = None
    # The error that left the payload unsubmitted or unfetched.
    error: Exception | None = None
    ended: anyio.Event = field(default_factory=anyio.Event, repr=False)

    def __post_init__(self) -> None:
        self.body = self.payload.model_dump()


class _ShownPath(str):
    """A path or URL as a log line shows it, so the CLI's handler can print it in cyan."""

    __slots__ = ()


@dataclass(frozen=True)
class _RunLog:
    """Where a run writes its run log."""

    store: ObjectStore
    path: str
    # The path as the caller named it, for the log lines.
    shown: _ShownPath


@dataclass(eq=False)
class _RunState:
    """What the tasks of one run share with its `AsyncRun`."""

    lines: list[_Line]
    send: MemoryObjectSendStream[Job]
    waiting: anyio.Semaphore
    realtime: bool
    check_storage: bool
    output_types: Sequence[_OutputType]
    destination: ObjectStore | None
    log: _RunLog | None
    shields: _Shields
    # Cancelling `submitting` stops submission, and cancelling `running` stops the checks too.
    submitting: anyio.CancelScope = field(default_factory=anyio.CancelScope)
    running: anyio.CancelScope = field(default_factory=anyio.CancelScope)
    cause: Exception | None = None
    started: float = field(default_factory=anyio.current_time)
    ended: float | None = None
    retries: int = 0
    # The `storage_url` values whose uploads oxy warned it cannot check.
    unchecked: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.snapshot = Progress(
            payloads=len(self.lines),
            unsubmitted=len(self.lines),
            pending=0,
            done=0,
            faulted=0,
            rejected=0,
            unfetched=0,
            written=0,
            uploaded=0,
            unuploaded=0,
            retries=0,
            elapsed=timedelta(),
        )

    def move(self, line: _Line, state: _State) -> None:
        """Change a line's state, and replace the snapshot in one step.

        A reader in another thread then sees the six states sum to `payloads`.
        """
        old, new = getattr(self.snapshot, line.state), getattr(self.snapshot, state)
        changes = {line.state: old - 1, state: new + 1}
        line.state = state
        self.snapshot = replace(self.snapshot, **changes)
        if state in _ENDED:
            line.ended.set()
        if line.job:
            _logger.debug("Job %s is %s: %r", line.job.id, state, line.payload)

    async def finish(self, line: _Line, job: Job, body: bytes | None) -> None:
        """Record a finished job, write a done one's `body` to the destination, and send it to the caller's loop, for which it holds a `waiting` slot."""
        line.job = job
        self.move(line, job.status)
        if job.status == "faulted":
            _logger.warning("Job %s faulted: %s %s", job.id, job.source, job.input)
        elif self.destination is not None and body is not None:
            await self.write(self.destination, job.id, body)
        if job.upload is not None:
            self.count(line, job, job.upload)
        # `send` checks for cancellation first, so a stop would lose the fetched job.
        self.send.send_nowait(job)
        # The run reads no results after this, and keeping them holds the whole run in memory.
        line.job = replace(job, results=[])

    def count(self, line: _Line, job: Job, upload: Upload) -> None:
        """Count a finished job's upload as uploaded or unuploaded, unless its job object cannot show the upload's outcome."""
        if "statuses" not in job.data:
            storage_url = line.body["storage_url"]
            if storage_url not in self.unchecked:
                self.unchecked.add(storage_url)
                _logger.warning(
                    "Cannot check the uploads to %s, because the job object of %s has no statuses",
                    _redacted(line.body)["storage_url"],
                    job.source,
                )
            return
        if not _upload_failed(job):
            self.snapshot = replace(self.snapshot, uploaded=self.snapshot.uploaded + 1)
            return
        self.snapshot = replace(self.snapshot, unuploaded=self.snapshot.unuploaded + 1)
        if upload.code is not None:
            _logger.warning(
                "The upload of job %s failed with %s %s: %s %s",
                job.id,
                upload.code,
                upload.message,
                job.source,
                job.input,
            )

    async def write(self, store: ObjectStore, job_id: str, body: bytes) -> None:
        """Write a job's body, or stop submission and every later write if the write fails."""
        # A stop waits for the write, so the job still reaches the caller's loop.
        with self.shields.scope():
            try:
                await anyio.to_thread.run_sync(
                    obstore.put,
                    store,
                    f"{job_id}.json",
                    body,
                    abandon_on_cancel=True,
                )
            # obstore raises its own errors, and a store's credential provider may raise anything.
            except Exception as error:  # noqa: BLE001
                self.destination = None
                _logger.warning(
                    "Writing job %s to the destination failed, so oxy writes nothing more: %s",
                    job_id,
                    error,
                )
                self.stop(error, self.submitting)
                return
        self.snapshot = replace(self.snapshot, written=self.snapshot.written + 1)

    def progress(self) -> Progress:
        end = anyio.current_time() if self.ended is None else self.ended
        return replace(
            self.snapshot,
            retries=self.retries,
            elapsed=timedelta(seconds=end - self.started),
        )

    def stop(self, error: Exception, scope: anyio.CancelScope) -> None:
        self.cause = self.cause or error
        scope.cancel()

    def end(self, *, stopped: bool) -> int:
        """Count the jobs that a stop left pending as unfetched, set the run's end, log it, and return the number of those jobs.

        A Realtime submission that a stop cancelled has no job, so its payload counts as unsubmitted.
        """
        halted = [line for line in self.lines if line.state == "pending" and line.job]
        for line in self.lines:
            if line.state == "pending":
                self.move(line, "unfetched" if line.job else "unsubmitted")
                line.error = self.cause
            elif line.state == "unsubmitted":
                line.error = self.cause
        self.ended = anyio.current_time()
        if self.cause is not None:
            because = _because(self.cause)
            if unsubmitted := self.snapshot.unsubmitted:
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
        summary = self.progress()
        _logger.info(
            "Finished %s in %s: %s"
            if self.cause is None and not stopped
            else "Stopped %s after %s: %s",
            _counted(summary.payloads, "payload"),
            _duration(summary.elapsed.total_seconds()),
            ", ".join([f"{summary.done:,} done", *_counts(summary)]),
        )
        return len(halted)

    async def save(self, log: _RunLog, halted: int) -> None:
        """Replace the run log with one line per payload, or make the run raise if the write fails."""
        records = b"".join(
            json.dumps(_record(line)).encode() + b"\n" for line in self.lines
        )
        try:
            await anyio.to_thread.run_sync(
                obstore.put, log.store, log.path, records, abandon_on_cancel=True
            )
        # obstore raises its own errors, and a store's credential provider may raise anything.
        except Exception as error:  # noqa: BLE001
            self.cause = self.cause or error
            _logger.warning("Writing the run log to %s failed: %s", log.shown, error)
            return
        _logger.info("Wrote the run log to %s", log.shown)
        if halted:
            _logger.warning(
                "Stopped with %s pending, which may still bill; the run log at %s lists their IDs",
                _counted(halted, "job"),
                log.shown,
            )

    def error(self) -> IncompleteRunError | None:
        rejections = [line.rejection for line in self.lines if line.rejection]
        unsubmitted = [
            line.payload for line in self.lines if line.state == "unsubmitted"
        ]
        unfetched = [
            line.job for line in self.lines if line.state == "unfetched" and line.job
        ]
        unuploaded = [
            line.job for line in self.lines if line.job and _upload_failed(line.job)
        ]
        if (
            not (rejections or unsubmitted or unfetched or unuploaded)
            and self.cause is None
        ):
            return None
        return IncompleteRunError(
            rejections=rejections,
            unsubmitted=unsubmitted,
            unfetched=unfetched,
            unuploaded=unuploaded,
        )


class _Budgets:
    """The rate limits of one session, and what is left of each in the current window.

    Oxylabs opens a window at the first submission it receives after the last window closed, and no response carries a reset time.
    So oxy ends a window 1 second after its first response, by when the API's window has closed.
    """

    def __init__(self) -> None:
        self.limits = dict(_STARTER)
        self._left = dict(_STARTER)
        self._opened: float | None = None
        self._lock = anyio.Lock()
        self._settled = anyio.Event()

    def fits(self, cost: Mapping[_Limit, int]) -> bool:
        return all(count <= self.limits[name] for name, count in cost.items())

    async def take(self, cost: Mapping[_Limit, int]) -> None:
        """Wait until `cost` fits every budget, and take it from each.

        A cost above a limit counts as the whole limit, so it goes out alone once that budget is full.
        """
        async with self._lock:
            while True:
                capped = {
                    name: min(count, self.limits[name]) for name, count in cost.items()
                }
                if all(self._left[name] >= count for name, count in capped.items()):
                    for name, count in capped.items():
                        self._left[name] -= count
                    return
                if self._opened is None:
                    await self._settled.wait()
                else:
                    await anyio.sleep_until(self._opened + 1)
                    self._left = dict(self.limits)
                    self._opened = None

    def settle(self, headers: httpx2.Headers) -> None:
        """Open the window if this submission ended first in it, and read the limits from its response's headers.

        A submission that ended without a response opens the window too, so no `take` waits for a response that never comes.
        """
        if self._opened is None:
            self._opened = anyio.current_time()
        for header, value in headers.items():
            if (match := _RATE_LIMIT.fullmatch(header)) and value.isdigit():
                name = cast("_Limit", match["name"].replace("_", "-"))
                if match["kind"] == "limit":
                    self.limits[name] = int(value)
                else:
                    self._left[name] = min(self._left[name], int(value))
        self._settled.set()
        self._settled = anyio.Event()


class Run:
    """The jobs of one run, each as it finishes.

    Iteration yields each job once, so `all`, `one` and `partitions` return only the jobs it has not yet yielded.
    After the last job, it raises `IncompleteRunError` if a payload ended with no done or faulted job or an upload failed, and raises it again on each later call.
    """

    def __init__(self, jobs: Iterator[Job], progress: Callable[[], Progress]) -> None:
        self._jobs = jobs
        self._progress = progress

    @property
    def progress(self) -> Progress:
        """The number of the run's payloads in each state, now."""
        return self._progress()

    def __iter__(self) -> Iterator[Job]:
        """Yield each job as it finishes."""
        return self._jobs

    def all(self) -> list[Job]:
        """Wait for every job, and return them in the order they finished.

        Raises
        ------
        IncompleteRunError
            If a payload ended with no done or faulted job or an upload failed, with the jobs collected so far in its `jobs`.
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

    @property
    def progress(self) -> Progress:
        """The number of the run's payloads in each state, now."""
        return self._state.progress()

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
        # The sources whose batch returned `not available with a batch request`, so their payloads go out one per request.
        self._unbatched: set[str] = set()
        self._shields = _Shields()
        self._runs = 0
        self._stack = AsyncExitStack()

    async def __aenter__(self) -> Self:
        """Open the client and the task group that runs the runs."""
        await self._stack.enter_async_context(self._http)
        self._budgets = _Budgets()
        # The streams close after the task group exits, so no task sends into a closed stream.
        self._streams = self._stack.enter_context(ExitStack())
        self._tasks = await self._stack.enter_async_context(anyio.create_task_group())
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        """Stop every unfinished run, and close the client.

        A second Ctrl+C while the runs stop makes them stop at once, without their run logs.
        """
        self._tasks.cancel_scope.cancel()
        try:
            # Only a second Ctrl+C gets through: trio raises `KeyboardInterrupt` here, and `asyncio.run` cancels every task.
            with anyio.CancelScope(shield=True):
                if self._runs:
                    await self._idle.wait()
        except BaseException:
            self._shields.drop()
            raise
        finally:
            await self._stack.aclose()

    async def execute(  # noqa: PLR0913
        self,
        payloads: Payload | Iterable[Payload],
        *,
        realtime: bool = False,
        destination: str | os.PathLike[str] | ObjectStore | None = None,
        run_log: str | os.PathLike[str] | ObjectStore | None = None,
        check_storage: bool = True,
        output_types: Sequence[_OutputType] = (),
    ) -> Run:
        """Run the payloads, and return the run once its last job finishes.

        It takes the arguments of `stream`.
        """
        run = await self.stream(
            payloads,
            realtime=realtime,
            destination=destination,
            run_log=run_log,
            check_storage=check_storage,
            output_types=output_types,
        )
        return Run(iter(await run.all()), lambda: run.progress)

    async def stream(  # noqa: PLR0913
        self,
        payloads: Payload | Iterable[Payload],
        *,
        realtime: bool = False,
        destination: str | os.PathLike[str] | ObjectStore | None = None,
        run_log: str | os.PathLike[str] | ObjectStore | None = None,
        check_storage: bool = True,
        output_types: Sequence[_OutputType] = (),
    ) -> AsyncRun:
        """Start a run, and return its jobs as they finish.

        Parameters
        ----------
        payloads
            One payload or several, each submitted as one job.
        realtime
            Submit each payload through Realtime, one request per payload, instead of Push-Pull.
            oxy never falls back from one integration method to the other.
        destination
            The folder that oxy writes each done job's body to, unchanged, as `<job_id>.json`, before the run yields the job.
            oxy passes a string with `://` to `obstore.store.from_url`, which reads credentials from the environment as Polars does.
            Any other string or path names a local folder, which oxy creates.
            Pass a store for explicit credentials or settings.
            A failed write stops submission and every later write.
        run_log
            The folder that oxy writes the run log to, as `<run start>.jsonl`, with one JSON line per payload in input order.
            It takes the same types as `destination`.
            oxy writes an empty file before the first submission, and replaces it when the run ends or stops.
            So an empty file means a second Ctrl+C or a killed process, and jobs may have billed without a record.
        check_storage
            Submit the first payload of each `storage_url` alone, and hold the rest of that `storage_url` until the first upload succeeds, so a wrong bucket bills one job.
            If that upload fails, the held payloads stay unsubmitted.
            A job object without `statuses` cannot show the upload, so the rest go out once the first job finishes.
            `False` submits every payload at once, and oxy still checks each upload.
        output_types
            The output types of each result, sent as the API's `type` parameter.
            Empty returns the default type of each job.

        Raises
        ------
        ValueError
            If `realtime` or `destination` is set and a payload sets `storage_type`.
        obstore.exceptions.BaseError
            If oxy cannot list `destination` or `run_log`, or cannot write the empty run log.
        """
        lines = [_Line(payload) for payload in _listed(payloads)]
        uploads = any("storage_type" in line.body for line in lines)
        if realtime and uploads:
            msg = "a payload that sets storage_type runs only through Push-Pull, so call without realtime=True"
            raise ValueError(msg)
        if destination is not None and uploads:
            msg = "oxy fetches no results for a payload that sets storage_type, so call without destination="
            raise ValueError(msg)
        store = (
            None
            if destination is None
            else await anyio.to_thread.run_sync(_store, destination)
        )
        log = None
        if run_log is not None:
            # Windows forbids colons in file names, so the start takes ISO 8601's basic form.
            path = f"{datetime.now(UTC):%Y%m%dT%H%M%S.%f}"[:-3] + "Z.jsonl"
            folder = await anyio.to_thread.run_sync(_store, run_log)
            # An unwritable run log raises here, before any request bills.
            await anyio.to_thread.run_sync(obstore.put, folder, path, b"")
            log = _RunLog(folder, path, _shown(run_log, path))
        send, receive = anyio.create_memory_object_stream[Job](math.inf)
        self._streams.callback(receive.close)
        state = _RunState(
            lines=lines,
            send=send,
            # A finished job holds a slot until the caller's loop takes it, so at most 100 wait in memory.
            waiting=anyio.Semaphore(_MAX_WAITING),
            realtime=realtime,
            check_storage=check_storage,
            output_types=output_types,
            destination=store,
            log=log,
            shields=self._shields,
        )
        if not self._runs:
            self._idle = anyio.Event()
        self._runs += 1
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
        fetched = await self._results(job_id, output_types)
        if isinstance(fetched, str):
            return await self._status(job_id, fetched)
        return fetched[0]

    async def _run(self, state: _RunState) -> None:
        _logger.info(
            "Running %s with %s",
            _counted(len(state.lines), "payload"),
            "Realtime" if state.realtime else "Push-Pull",
        )
        stopped = True
        try:
            async with state.send:
                try:
                    async with anyio.create_task_group() as reports:
                        if self._progress_interval is not None:
                            reports.start_soon(
                                self._report, state, self._progress_interval
                            )
                        with state.running:
                            async with anyio.create_task_group() as checks:
                                with state.submitting:
                                    async with anyio.create_task_group() as submissions:
                                        await self._submit(state, checks, submissions)
                        reports.cancel_scope.cancel()
                    stopped = False
                finally:
                    # A stop by the caller ends the run too, so the run log records the jobs it left pending.
                    with self._shields.scope():
                        halted = state.end(stopped=stopped)
                        if state.log is not None:
                            await state.save(state.log, halted)
        finally:
            self._runs -= 1
            if not self._runs:
                self._idle.set()

    async def _report(self, state: _RunState, interval: float) -> None:
        while True:
            await anyio.sleep(interval)
            _logger.info("%s", state.progress())

    async def _submit(
        self, state: _RunState, checks: TaskGroup, submissions: TaskGroup
    ) -> None:
        if state.realtime:
            for line in state.lines:
                await submissions.start(self._call, state, line)
            return
        lines = state.lines
        if state.check_storage:
            shared: collections.defaultdict[str, list[_Line]] = collections.defaultdict(
                list
            )
            for line in lines:
                if "storage_url" in line.body:
                    shared[line.body["storage_url"]].append(line)
            checked = [group for group in shared.values() if len(group) > 1]
            held = {line for group in checked for line in group}
            lines = [line for line in lines if line not in held]
            for group in checked:
                submissions.start_soon(self._probe, state, group, checks, submissions)
        for group in _groups(lines):
            await self._dispatch(state, group, checks, submissions)

    async def _probe(
        self,
        state: _RunState,
        lines: Sequence[_Line],
        checks: TaskGroup,
        submissions: TaskGroup,
    ) -> None:
        """Submit the first payload of a `storage_url` alone, and the rest once its upload succeeds.

        A rejected payload has no upload, so the next payload takes its place.
        """
        shown = _ShownPath(_redacted(lines[0].body)["storage_url"])
        _logger.info(
            "Checking the upload to %s with one job before submitting %s",
            shown,
            _counted(len(lines) - 1, "more payload"),
        )
        started = anyio.current_time()
        rest = collections.deque(lines)
        while rest:
            first = rest.popleft()
            await self._dispatch(state, [first], checks, submissions)
            await first.ended.wait()
            if first.state != "rejected":
                break
        if first.state == "unfetched":
            reason = "oxy stopped checking the first job"
        elif first.job and _upload_failed(first.job):
            reason = "the first upload failed"
        else:
            if first.job and "statuses" in first.job.data:
                _logger.info(
                    "Uploaded the first job to %s in %s",
                    shown,
                    _duration(anyio.current_time() - started),
                )
            for group in _groups(rest):
                await self._dispatch(state, group, checks, submissions)
            return
        _logger.warning(
            "Held back %s for %s, because %s",
            _counted(len(rest), "payload"),
            shown,
            reason,
        )

    async def _dispatch(
        self,
        state: _RunState,
        lines: Sequence[_Line],
        checks: TaskGroup,
        submissions: TaskGroup,
    ) -> None:
        """Submit lines that share every parameter but the input, in batches as large as the limits allow."""
        start = 0
        while start < len(lines):
            # Submissions pause while 100 finished jobs wait for the caller's loop.
            await state.waiting.acquire()
            state.waiting.release()
            size = self._size(lines[start].body)
            await submissions.start(
                self._push, state, lines[start : start + size], checks, submissions
            )
            start += size

    def _size(self, body: dict[str, Any]) -> int:
        """Return the most payloads like `body` that one submission holds."""
        if _input_key(body) not in _BATCH_KEYS or body["source"] in self._unbatched:
            return 1
        limits = self._budgets.limits
        size = min(limits[name] // pages for name, pages in _cost(body).items())
        return max(1, min(size, _MAX_BATCH))

    async def _push(
        self,
        state: _RunState,
        lines: Sequence[_Line],
        checks: TaskGroup,
        submissions: TaskGroup,
        *,
        task_status: TaskStatus[None] = anyio.TASK_STATUS_IGNORED,
    ) -> None:
        """Submit one payload or a batch, and start the checks of each job."""
        cost = _cost(lines[0].body, len(lines))
        await self._budgets.take(cost)
        task_status.started()
        key = _input_key(lines[0].body)
        single = len(lines) == 1

        def read(
            response: httpx2.Response,
        ) -> tuple[list[Job], list[dict[str, Any]]]:
            answer = response.json()
            if single:
                return [_job(answer, [])], []
            jobs = [_job(data, []) for data in answer["queries"]]
            return jobs, answer.get("errors", [])

        values = [line.body[key] for line in lines]
        try:
            jobs, errors = await self._request(
                "POST",
                _DATA if single else _BATCH,
                read,
                json=lines[0].body if single else lines[0].body | {key: values},
                state=state,
                cost=cost,
            )
        except OxylabsError as error:
            if _too_many(error) and not self._budgets.fits(cost):
                await self._resize(state, lines, error, checks, submissions)
                return
            if error.status_code not in _REJECTED:
                state.stop(error, state.submitting)
                return
            for line in lines:
                _reject(state, line, error.status_code, error.message, error.trace_id)
            return
        source = lines[0].body["source"]
        unavailable = f"Source `{source}` is not available with a batch request."
        if any(entry["message"] == unavailable for entry in errors):
            self._unbatched.add(source)
            await self._dispatch(state, lines, checks, submissions)
            return
        self._match(state, lines, jobs, errors, checks)

    async def _call(
        self,
        state: _RunState,
        line: _Line,
        *,
        task_status: TaskStatus[None] = anyio.TASK_STATUS_IGNORED,
    ) -> None:
        """Submit one payload through Realtime, whose response holds the finished job."""
        cost = _cost(line.body)
        # The response holds the finished job, so the submission takes the job's slot.
        await state.waiting.acquire()
        await self._budgets.take(cost)
        task_status.started()
        state.move(line, "pending")

        def read(response: httpx2.Response) -> tuple[Job, bytes]:
            body = response.json()
            job = _job(body["job"], body["results"], payload=line.payload)
            return job, response.content

        try:
            job, body = await self._request(
                "POST",
                _REALTIME,
                read,
                json=line.body,
                params=_params(state.output_types),
                state=state,
                cost=cost,
                timeouts=_REALTIME_TIMEOUTS,
            )
        except OxylabsError as error:
            state.waiting.release()
            status, trace_id = error.status_code, error.trace_id
            if _too_many(error) and (
                message := _oversized(line.body, self._budgets.limits)
            ):
                _reject(state, line, httpx2.codes.TOO_MANY_REQUESTS, message, trace_id)
            elif status == httpx2.codes.REQUEST_TIMEOUT:
                _reject(state, line, status, f"{error.message} {_TIMED_OUT}", trace_id)
            elif status in _REJECTED:
                _reject(state, line, status, error.message, trace_id)
            else:
                state.move(line, "unsubmitted")
                state.stop(error, state.submitting)
            return
        await state.finish(line, job, body)

    def _match(
        self,
        state: _RunState,
        lines: Sequence[_Line],
        jobs: list[Job],
        errors: list[dict[str, Any]],
        checks: TaskGroup,
    ) -> None:
        """Pair each job and each error with the payload of its input value, and the rest by order."""
        key = _input_key(lines[0].body)
        pools: collections.defaultdict[str, collections.deque[_Line]] = (
            collections.defaultdict(collections.deque)
        )
        for line in lines:
            pools[line.body[key]].append(line)
        unmatched: list[Job] = []
        for job in jobs:
            # `job.input` reads `query` first, and the API sets an `amazon` product URL's `query` to its ASIN.
            if pool := pools.get(job.data.get(key, "")):
                self._accept(state, pool.popleft(), job, checks)
            else:
                unmatched.append(job)
        messages: list[str] = []
        for entry in errors:
            message = str(entry["message"])
            # A URL batch's error holds its `url` (docs/research/live-api.md#a-batch-with-invalid-values).
            if pool := pools.get(entry.get(key, "")):
                _reject(state, pool.popleft(), httpx2.codes.ACCEPTED, message, None)
            else:
                messages.append(message)
        # The API returns jobs and errors in the order of the values, so the rest pair by order.
        rest = [line for line in lines if line.job is None and line.rejection is None]
        for line, job in zip(rest, unmatched, strict=False):
            self._accept(state, line, job, checks)
        remaining = iter(messages)
        for line in rest[len(unmatched) :]:
            message = next(remaining, "The batch returned neither a job nor an error")
            _reject(state, line, httpx2.codes.ACCEPTED, message, None)

    async def _resize(
        self,
        state: _RunState,
        lines: Sequence[_Line],
        error: OxylabsError,
        checks: TaskGroup,
        submissions: TaskGroup,
    ) -> None:
        """Reject payloads whose pages exceed a limit, or submit them again in batches that fit the limits."""
        if message := _oversized(lines[0].body, self._budgets.limits):
            for line in lines:
                _reject(
                    state,
                    line,
                    httpx2.codes.TOO_MANY_REQUESTS,
                    message,
                    error.trace_id,
                )
            return
        state.retries += 1
        await self._dispatch(state, lines, checks, submissions)

    def _accept(
        self, state: _RunState, line: _Line, job: Job, checks: TaskGroup
    ) -> None:
        line.job = replace(job, payload=line.payload)
        state.move(line, "pending")
        checks.start_soon(self._check, state, line, line.job)

    async def _check(self, state: _RunState, line: _Line, pending: Job) -> None:
        """Check a job until it finishes, or until oxy stops checking it."""
        accepted = anyio.current_time()
        for age in itertools.chain(range(1, 10), itertools.count(10, 5)):
            # A check delayed by retries or a slow loop skips the checks it overran, instead of sending them at once.
            if accepted + age <= anyio.current_time():
                continue
            await anyio.sleep_until(accepted + age)
            await state.waiting.acquire()
            try:
                fetched = await self._fetch(state, line, pending.id)
            except OxylabsError as error:
                state.waiting.release()
                if error.status_code in _UNAUTHORIZED:
                    state.stop(error, state.running)
                    return
                line.error = error
                state.move(line, "unfetched")
                _logger.warning(
                    "Stopped checking job %s, because %s: %s %s",
                    pending.id,
                    _because(error),
                    pending.source,
                    pending.input,
                )
                return
            limit = self._pending_limit
            expired = limit is not None and anyio.current_time() >= accepted + limit
            if isinstance(fetched, tuple):
                await state.finish(line, *fetched)
                return
            if fetched is not None and limit is not None and expired:
                _logger.warning(
                    "Cloud Storage recorded no upload for job %s within %s: %s %s",
                    pending.id,
                    _duration(limit),
                    pending.source,
                    pending.input,
                )
                await state.finish(line, fetched, None)
                return
            state.waiting.release()
            if limit is not None and expired:
                state.move(line, "unfetched")
                _logger.warning(
                    "Stopped checking job %s, because it is still pending after %s: %s %s",
                    pending.id,
                    _duration(limit),
                    pending.source,
                    pending.input,
                )
                return

    async def _fetch(
        self, state: _RunState, line: _Line, job_id: str
    ) -> tuple[Job, bytes | None] | Job | None:
        """Return a finished job with the body that holds its results, a finished job alone while its upload has no `statuses` entry, or `None` while it is pending.

        A job with `storage_type` has no body, so oxy reads the status endpoint instead of downloading results twice.
        """
        if "storage_type" in line.body:
            job = await self._status(job_id, None, line.payload, state)
            if job.status == "pending":
                return None
            # The entry appears seconds after the final status.
            return job if job.data.get("statuses") == [] else (job, None)
        fetched = await self._results(job_id, state.output_types, line.payload, state)
        if fetched == "pending":
            return None
        # A faulted job can have no results, so its 204 names its status alone.
        if isinstance(fetched, str):
            return await self._status(job_id, fetched, line.payload, state), None
        return fetched

    async def _results(
        self,
        job_id: str,
        output_types: Sequence[_OutputType],
        payload: Payload | None = None,
        state: _RunState | None = None,
    ) -> tuple[Job, bytes] | str:
        """Fetch a job with its results and the body that holds them, or the status that a 204 names for a job with none."""

        def read(response: httpx2.Response) -> tuple[Job, bytes] | str:
            if response.status_code == httpx2.codes.NO_CONTENT:
                return response.headers["x-oxylabs-job-status"]
            body = response.json()
            return _job(body["job"], body["results"], payload=payload), response.content

        return await self._request(
            "GET",
            f"{_DATA}/{job_id}/results",
            read,
            params=_params(output_types),
            state=state,
        )

    async def _status(
        self,
        job_id: str,
        status: str | None,
        payload: Payload | None = None,
        state: _RunState | None = None,
    ) -> Job:
        """Fetch a job with no results from the status endpoint, with the status that its 204 named, if one did."""
        return await self._request(
            "GET",
            f"{_DATA}/{job_id}",
            lambda response: _job(response.json(), [], status=status, payload=payload),
            state=state,
        )

    async def _request(  # noqa: PLR0913
        self,
        method: str,
        url: str,
        read: Callable[[httpx2.Response], _T],
        *,
        json: dict[str, Any] | None = None,
        params: Mapping[str, str] | None = None,
        state: _RunState | None = None,
        cost: Mapping[_Limit, int] | None = None,
        timeouts: httpx2.Timeout | None = None,
    ) -> _T:
        """Send a request under the retry policy, and return what `read` returns for the response.

        Each retry counts toward the retries of `state`, the run that sent the request.
        A submission passes its `cost`, which paces each retry, while the caller paces the first attempt.
        A 429 that leaves the cost above a limit raises, so the caller can resize the submission.
        `timeouts` replaces the client's timeouts.

        Raises
        ------
        OxylabsError
            If the response is an error that oxy does not retry, or the retries outlast `retry_limit`.
        """
        deadline: float | None = None
        ceiling = 1.0
        while True:
            try:
                return await self._attempt(
                    method,
                    url,
                    read,
                    json=json,
                    params=params,
                    paced=cost is not None,
                    timeouts=timeouts,
                )
            except OxylabsError as error:
                now = anyio.current_time()
                deadline = now + self._retry_limit if deadline is None else deadline
                resize = (
                    cost is not None
                    and _too_many(error)
                    and not self._budgets.fits(cost)
                )
                if not _retried(error) or now >= deadline or resize:
                    raise
                wait = min(random.uniform(0, ceiling), deadline - now)  # noqa: S311
                if state:
                    state.retries += 1
                if json is not None and _unknown(error):
                    values = json[_input_key(json)]
                    if isinstance(values, list):
                        _logger.warning(
                            "Retrying a batch of %s %s payloads after %s; the API may have created their jobs, and each duplicate bills",
                            len(values),
                            json["source"],
                            error,
                        )
                    else:
                        _logger.warning(
                            "Retrying a submission of %s %s after %s; the API may have created its job, and a duplicate bills",
                            *_named(json),
                            error,
                        )
                else:
                    _logger.debug(
                        "Retrying %s %s in %s after %s",
                        method,
                        url,
                        _duration(wait),
                        error,
                    )
            await anyio.sleep(wait)
            ceiling = min(ceiling * 2, _MAX_WAIT)
            if cost is not None:
                await self._budgets.take(cost)

    async def _attempt(  # noqa: PLR0913
        self,
        method: str,
        url: str,
        read: Callable[[httpx2.Response], _T],
        *,
        json: dict[str, Any] | None,
        params: Mapping[str, str] | None,
        paced: bool,
        timeouts: httpx2.Timeout | None,
    ) -> _T:
        try:
            try:
                async with self._hosts[httpx2.URL(url).host]:
                    # The API may create a job once a submission is sent, so a stop lets the attempt finish and keeps the job's ID.
                    with self._shields.scope() if method == "POST" else nullcontext():
                        response = await self._http.request(
                            method,
                            url,
                            json=json,
                            params=params,
                            timeout=timeouts or self._http.timeout,
                        )
            except BaseException:
                if paced:
                    self._budgets.settle(httpx2.Headers())
                raise
            if paced:
                self._budgets.settle(response.headers)
            response.raise_for_status()
            try:
                return read(response)
            # A body of an unexpected shape counts as one that does not parse.
            except (ValueError, LookupError, TypeError) as error:
                msg = f"the API returned {response.status_code} with a body that oxy cannot read"
                raise httpx2.RemoteProtocolError(msg) from error
        except httpx2.HTTPStatusError as error:
            raise _error(error.response) from error
        except httpx2.RequestError as error:
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
        # It runs after the session closes and before the portal waits for its thread.
        self._stack.push(self._interrupted)
        self._stack.enter_context(
            self._portal.wrap_async_context_manager(self._session)
        )
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Stop every unfinished run, and close the portal."""
        self._stack.close()

    def execute(  # noqa: PLR0913
        self,
        payloads: Payload | Iterable[Payload],
        *,
        realtime: bool = False,
        destination: str | os.PathLike[str] | ObjectStore | None = None,
        run_log: str | os.PathLike[str] | ObjectStore | None = None,
        check_storage: bool = True,
        output_types: Sequence[_OutputType] = (),
    ) -> Run:
        """Start a run, and return its jobs as they finish.

        It takes the arguments of `AsyncSession.stream`.
        """
        run = self._portal.call(
            partial(
                self._session.stream,
                payloads,
                realtime=realtime,
                destination=destination,
                run_log=run_log,
                check_storage=check_storage,
                output_types=output_types,
            )
        )
        # A generator ends once it raises, and `iter` with a sentinel calls again, so a second `all` raises too.
        return Run(
            iter(partial(self._next_job, run), None), partial(self._progress, run)
        )

    def get(self, job_id: str, *, output_types: Sequence[_OutputType] = ()) -> Job:
        """Return a job as it stands, at once.

        It takes the arguments of `AsyncSession.get`.
        """
        return self._portal.call(
            partial(self._session.get, job_id, output_types=output_types)
        )

    def _interrupted(self, kind: type[BaseException] | None, *_: object) -> None:
        """Stop at once if an exception, such as a second Ctrl+C, interrupted the wait for the session to close."""
        if kind is not None:
            self._portal.call(self._session._shields.drop)  # noqa: SLF001

    def _progress(self, run: AsyncRun) -> Progress:
        """Read the run's progress in the event loop's thread, which reads the loop's clock."""
        try:
            return self._portal.call(lambda: run.progress)
        except RuntimeError:
            # The portal stops after the run ends, and an ended run reads no clock.
            return run.progress

    def _next_job(self, run: AsyncRun) -> Job | None:
        try:
            return self._portal.call(run.__anext__)
        except StopAsyncIteration:
            return None


@dataclass(frozen=True, kw_only=True)
class DryRun:
    """The jobs a run would submit.

    Attributes
    ----------
    jobs
        Each job's body, with the credentials in `storage_url` replaced by `redacted:redacted`.
    max_results
        The most results the jobs can bill: the sum of their `pages`, read as the API reads them, with 1 for a job without a positive one.
        Rejected and faulted jobs bill nothing, and a source that ignores `pages` bills 1, so a run can bill less.
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
    return DryRun(
        jobs=jobs,
        max_results=sum(_pages(job) for job in jobs),
    )


def _store(destination: str | os.PathLike[str] | ObjectStore) -> ObjectStore:
    """Return the store that `destination` names, after listing one page of it."""
    if isinstance(destination, str) and "://" in destination:
        store = from_url(destination)
    elif isinstance(destination, str | os.PathLike):  # pyrefly: ignore[implicit-any-type-argument]
        store = LocalStore(Path(destination), mkdir=True)
    else:
        store = destination
    # A store that oxy cannot reach raises here, before any request bills.
    next(iter(obstore.list(store, chunk_size=1)), None)
    return store


def _shown(folder: str | os.PathLike[str] | ObjectStore, name: str) -> _ShownPath:
    """Return the path of the file `name` in `folder`, or `name` alone in a store the caller built."""
    if isinstance(folder, str) and "://" in folder:
        return _ShownPath(posixpath.join(folder, name))
    if isinstance(folder, str | os.PathLike):  # pyrefly: ignore[implicit-any-type-argument]
        return _ShownPath(Path(folder) / name)
    return _ShownPath(name)


def _listed(payloads: Payload | Iterable[Payload]) -> list[Payload]:
    return [payloads] if isinstance(payloads, Payload) else list(payloads)


def _groups(lines: Iterable[_Line]) -> list[list[_Line]]:
    """Group the lines whose bodies share every parameter but the input, in the order of their first line."""
    groups: dict[str, list[_Line]] = {}
    for line in lines:
        key = _input_key(line.body)
        rest = {name: value for name, value in line.body.items() if name != key}
        groups.setdefault(json.dumps([key, rest], sort_keys=True), []).append(line)
    return list(groups.values())


def _input_key(body: Mapping[str, Any]) -> str:
    return next(key for key in _INPUT_KEYS if key in body)


def _pages(body: Mapping[str, Any]) -> int:
    """Return the `pages` that the API counts, with 1 for a body without a positive one."""
    return max(_integer(body.get("pages")) or 1, 1)


def _cost(body: Mapping[str, Any], values: int = 1) -> dict[_Limit, int]:
    """Return what a submission of `values` payloads like `body` takes from each limit it counts against."""
    rendered = (
        bool(body.get("render"))
        or body.get("xhr") is True
        or body["source"] in _RENDERED_SOURCES
    )
    names: list[_Limit] = ["total-requests", "total-render-requests"]
    return dict.fromkeys(names[: 1 + rendered], values * _pages(body))


def _params(output_types: Sequence[_OutputType]) -> dict[str, str] | None:
    return {"type": ",".join(output_types)} if output_types else None


def _oversized(body: Mapping[str, Any], limits: Mapping[_Limit, int]) -> str | None:
    """Return why the API returns 429 for a payload like `body` in every window, if it does."""
    for name, pages in _cost(body).items():
        if pages > limits[name]:
            return f"The payload's {pages} pages exceed the {name} limit of {limits[name]}, so the API returns 429 for it in every window"
    return None


def _reject(
    state: _RunState,
    line: _Line,
    status_code: int,
    message: str,
    trace_id: str | None,
) -> None:
    line.rejection = Rejection(
        payload=line.payload,
        status_code=status_code,
        message=message,
        trace_id=trace_id,
    )
    state.move(line, "rejected")
    _logger.warning("Rejected %s %s: %s %s", *_named(line.body), status_code, message)


def _record(line: _Line) -> dict[str, Any]:
    """Return a payload's line of the run log."""
    error = line.rejection or line.error
    if isinstance(error, Rejection | OxylabsError):
        reported = {
            "status_code": error.status_code,
            "message": error.message,
            "trace_id": error.trace_id,
        }
    else:
        reported = error and {
            "status_code": None,
            "message": f"{type(error).__name__}: {error}",
            "trace_id": None,
        }
    upload = line.job.upload if line.job else None
    return {
        "state": line.state,
        "id": line.job and line.job.id,
        "payload": _redacted(line.body),
        "error": reported,
        "upload": upload and {"code": upload.code, "message": upload.message},
    }


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


def _too_many(error: OxylabsError) -> bool:
    return error.status_code == httpx2.codes.TOO_MANY_REQUESTS


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


def _because(error: Exception) -> str:
    if not isinstance(error, OxylabsError):
        return "a write to the destination failed"
    if error.status_code is None:
        return f"httpx2 raised {error}"
    return f"the API returned {error}"


def _named(data: Mapping[str, Any]) -> tuple[str, str]:
    """Return the source and the input of a body or a job object."""
    return data["source"], next((data[key] for key in _INPUT_KEYS if data.get(key)), "")


def _duration(seconds: float) -> str:
    """Format a duration as uv does, which truncates."""
    # Integer microseconds, because `4.02 * 100` truncates to 401.
    whole, micros = divmod(round(seconds * 1_000_000), 1_000_000)
    if whole >= 3600:  # noqa: PLR2004
        return f"{whole // 3600}h {whole % 3600 // 60:02}m {whole % 60:02}s"
    if whole >= 60:  # noqa: PLR2004
        return f"{whole // 60}m {whole % 60:02}s"
    if whole:
        return f"{whole}.{micros // 10_000:02}s"
    return f"{micros // 1000}ms"


def _counts(progress: Progress) -> list[str]:
    """Name each count of `progress` after `done` that is not zero."""
    names = ("faulted", "rejected", "unfetched", "pending", "unsubmitted")
    names += ("written", "uploaded", "unuploaded")
    counts = [
        f"{getattr(progress, name):,} {name}"
        for name in names
        if getattr(progress, name)
    ]
    if progress.retries:
        counts.append(_counted(progress.retries, "retry", "retries"))
    return counts


def _counted(count: int, noun: str, nouns: str | None = None) -> str:
    return f"{count:,} {noun if count == 1 else nouns or noun + 's'}"


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


def _upload_failed(job: Job) -> bool:
    """Return whether a finished job's upload failed, which a job object without `statuses` never shows."""
    return (
        job.status != "pending"
        and job.upload is not None
        and "statuses" in job.data
        and job.upload.code != 13000  # noqa: PLR2004
    )


def _time(value: str) -> datetime:
    # The API writes UTC with no offset.
    return datetime.fromisoformat(value).replace(tzinfo=UTC)
