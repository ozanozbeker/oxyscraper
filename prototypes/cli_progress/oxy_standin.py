"""PROTOTYPE, throwaway: a stand-in for oxyscraper as the map has decided it, so the CLI's progress output runs against the fake.

It extends the stand-in of [Prototype: the fake Oxylabs API](https://github.com/ozanozbeker/oxyscraper/issues/48) with Progress, the `oxyscraper` logger, a local destination, the run log and `check_storage`.
It sends no real request, and its pacing is simpler than the decided one.
"""

# ruff: noqa: ANN401, ASYNC240, C901, D101, D102, D103, D105, EM101, EM102, FBT001, INP001, PLR0913, PLR2004, S311, TRY003
# pyrefly: ignore-errors

from __future__ import annotations

import json
import logging
import random
import time
from collections import Counter, deque
from contextlib import AsyncExitStack, ExitStack
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, ClassVar, Literal, Self, get_args

import anyio
import httpx2
import testing
from anyio.from_thread import start_blocking_portal
from pydantic import BaseModel, ConfigDict, Field, model_validator

if TYPE_CHECKING:
    import os
    from collections.abc import Callable, Iterable, Iterator

    from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream

logger = logging.getLogger("oxyscraper")

DATA = "https://data.oxylabs.io/v1/queries"
REALTIME = "https://realtime.oxylabs.io/v1/queries"
InputKey = Literal[
    "query", "url", "product_id", "prompt", "video_id", "channel_handle", "category_id"
]
Render = Literal["html", "png"]
UserAgentType = Literal[
    "desktop",
    "mobile",
    "mobile_android",
    "mobile_ios",
    "tablet",
    "tablet_android",
    "tablet_ios",
]
StorageType = Literal["gcs", "s3", "tos", "s3_compatible"]
AmazonDomain = Literal[
    "ca", "co.jp", "co.uk", "com", "de", "es", "fr", "it", "nl", "pl"
]
State = Literal["unsubmitted", "pending", "done", "faulted", "rejected", "unfetched"]
INPUT_KEYS = get_args(InputKey)
STATES = get_args(State)
# A list under any other input key returns 400, so those payloads go one per request.
BATCH_KEYS = ("query", "url", "prompt")
NO_BATCH = "is not available with a batch request"
THROTTLE = "has been limited to 1 req/s"
RETRIED = (httpx2.TimeoutException, httpx2.NetworkError, httpx2.RemoteProtocolError)
# The request never reached the API, so it created no job.
UNSENT = (httpx2.ConnectError, httpx2.ConnectTimeout, httpx2.PoolTimeout)


class Payload(BaseModel):
    """One job's parameters, for any source."""

    model_config = ConfigDict(extra="allow")
    CONTEXT: ClassVar[frozenset[str]] = frozenset()

    source: str
    render: Render | None = Field(
        None, description="Render JavaScript, and return HTML or a screenshot."
    )
    parse: bool | None = Field(
        None, description="Return parsed JSON, for a source with a parser."
    )
    user_agent_type: UserAgentType | None = None
    geo_location: str | None = None
    locale: str | None = None
    domain: str | None = Field(
        None, description="The target's top-level domain, such as `de`."
    )
    start_page: Annotated[int, Field(ge=1)] | None = None
    pages: Annotated[int, Field(ge=1)] | None = Field(
        None, description="Pages per job. Each page bills."
    )
    storage_type: StorageType | None = Field(
        None, description="Upload each result to your bucket with Cloud Storage."
    )
    storage_url: str | None = Field(
        None, description="The bucket and path that Cloud Storage uploads to."
    )
    callback_url: str | None = None
    context: list[dict[str, Any]] | None = None

    @model_validator(mode="after")
    def _one_input(self) -> Self:
        body = self.to_api()
        keys = [key for key in INPUT_KEYS if key in body]
        if len(keys) != 1 or not body[keys[0]]:
            raise ValueError(
                f"set exactly one non-empty input key: {', '.join(INPUT_KEYS)}"
            )
        return self

    def to_api(self) -> dict[str, Any]:
        data = self.model_dump(exclude_none=True)
        extra = data.pop("extra", {})
        context = [
            {"key": key, "value": data.pop(key)}
            for key in sorted(self.CONTEXT)
            if key in data
        ]
        if context:
            data["context"] = [*data.get("context", []), *context]
        return {**data, **extra}


class AmazonProduct(Payload):
    model_config = ConfigDict(extra="forbid")
    CONTEXT: ClassVar[frozenset[str]] = frozenset({"currency", "autoselect_variant"})

    source: Literal["amazon_product"] = "amazon_product"
    query: Annotated[str, Field(pattern=r"^[0-9A-Z]{10}$", description="An ASIN.")]
    domain: AmazonDomain | None = None
    currency: str | None = None
    autoselect_variant: bool | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class AmazonSearch(Payload):
    model_config = ConfigDict(extra="forbid")
    CONTEXT: ClassVar[frozenset[str]] = frozenset(
        {"sort_by", "currency", "min_price", "max_price"}
    )

    source: Literal["amazon_search"] = "amazon_search"
    query: Annotated[str, Field(min_length=1)]
    domain: AmazonDomain | None = None
    sort_by: (
        Literal[
            "most_recent",
            "price_low_to_high",
            "price_high_to_low",
            "featured",
            "average_review",
            "bestsellers",
        ]
        | None
    ) = None
    currency: str | None = None
    min_price: int | None = None
    max_price: int | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class Universal(Payload):
    model_config = ConfigDict(extra="forbid")

    source: Literal["universal"] = "universal"
    url: str
    extra: dict[str, Any] = Field(default_factory=dict)


SOURCES = (AmazonProduct, AmazonSearch, Universal)


@dataclass(frozen=True, kw_only=True)
class Result:
    page: int
    type: str
    status_code: int
    content: Any = field(repr=False)
    data: dict[str, Any] = field(repr=False)


@dataclass(frozen=True, kw_only=True)
class Upload:
    storage_url: str
    code: int | None
    message: str | None


@dataclass(frozen=True, kw_only=True)
class Job:
    id: str
    status: Literal["pending", "done", "faulted"]
    source: str
    input: str
    payload: Payload | None = field(repr=False)
    results: list[Result] = field(repr=False)
    data: dict[str, Any] = field(repr=False)
    upload: Upload | None = None


@dataclass(frozen=True, kw_only=True)
class Rejection:
    payload: Payload
    status_code: int
    message: str


class OxylabsError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(f"{status_code} {message}".strip() if status_code else message)
        self.status_code = status_code
        self.message = message


class IncompleteRunError(Exception):
    def __init__(
        self,
        *,
        rejections: list[Rejection],
        unsubmitted: list[Payload],
        unfetched: list[Job],
        unuploaded: list[Job],
    ) -> None:
        self.rejections = rejections
        self.unsubmitted = unsubmitted
        self.unfetched = unfetched
        self.unuploaded = unuploaded
        self.jobs: list[Job] = []
        counts = (len(rejections), len(unsubmitted), len(unfetched), len(unuploaded))
        super().__init__(
            "{} rejected, {} unsubmitted, {} unfetched and {} unuploaded".format(
                *counts
            )
        )


@dataclass(frozen=True, kw_only=True)
class Progress:
    """The number of a run's payloads in each state, at one moment.

    The six states sum to `payloads`, and the last snapshot is the run's summary.
    """

    payloads: int
    unsubmitted: int = 0
    pending: int = 0
    done: int = 0
    faulted: int = 0
    rejected: int = 0
    unfetched: int = 0
    written: int = 0
    uploaded: int = 0
    unuploaded: int = 0
    retries: int = 0
    elapsed: timedelta = timedelta()

    def __str__(self) -> str:
        return ", ".join(
            [
                f"{self.done:,}/{self.payloads:,} done",
                *self.others(),
                elapsed(self.elapsed),
            ]
        )

    def others(self) -> list[str]:
        """Name each count besides `done` that is not zero."""
        counts = [
            f"{getattr(self, state):,} {state}"
            for state in ("faulted", "rejected", "unfetched", "pending", "unsubmitted")
            if getattr(self, state)
        ]
        if self.uploaded:
            counts.append(f"{self.uploaded:,} uploaded")
        if self.unuploaded:
            counts.append(plural(self.unuploaded, "failed upload"))
        if self.retries:
            counts.append(plural(self.retries, "retry", "retries"))
        return counts


@dataclass(frozen=True, kw_only=True)
class DryRun:
    jobs: list[dict[str, Any]]
    max_results: int

    @property
    def job_count(self) -> int:
        return len(self.jobs)


def dry_run(payloads: Payload | Iterable[Payload]) -> DryRun:
    jobs = [payload.to_api() for payload in _listed(payloads)]
    return DryRun(jobs=jobs, max_results=sum(job.get("pages", 1) for job in jobs))


class Run:
    def __init__(self, jobs: Iterator[Job], progress: Callable[[], Progress]) -> None:
        self._jobs = jobs
        self._progress = progress

    def __iter__(self) -> Iterator[Job]:
        return self._jobs

    @property
    def progress(self) -> Progress:
        return self._progress()


class AsyncRun:
    def __init__(
        self,
        receive: MemoryObjectReceiveStream[Job | Exception],
        progress: Callable[[], Progress],
    ) -> None:
        self._receive = receive
        self._progress = progress

    def __aiter__(self) -> Self:
        return self

    async def __anext__(self) -> Job:
        try:
            item = await self._receive.receive()
        except anyio.EndOfStream:
            raise StopAsyncIteration from None
        if isinstance(item, Exception):
            raise item
        return item

    @property
    def progress(self) -> Progress:
        return self._progress()


@dataclass
class _Line:
    """One payload of a run, as its run log line records it."""

    payload: Payload
    state: State = "unsubmitted"
    id: str | None = None
    error: dict[str, Any] | None = None
    upload: dict[str, Any] | None = None


@dataclass
class _Group:
    """The payloads that share every parameter but the input, which go out as batches."""

    key: str
    shared: dict[str, Any]
    items: deque[tuple[str, int]] = field(default_factory=deque)


@dataclass
class _Pending:
    index: int
    data: dict[str, Any]
    accepted: float
    next_check: float


@dataclass
class _State:
    lines: list[_Line]
    started: float
    retries_at_start: int
    destination: Path | None
    run_log: Path | None
    submitting: bool = True
    stop: OxylabsError | None = None
    ended: Progress | None = None
    pending: dict[str, _Pending] = field(default_factory=dict)
    checking: set[str] = field(default_factory=set)
    rejections: list[Rejection] = field(default_factory=list)
    unfetched: list[Job] = field(default_factory=list)
    unuploaded: list[Job] = field(default_factory=list)
    written: int = 0
    uploaded: int = 0
    # `check_storage`: the index of each storage URL's first payload, and whether its upload worked.
    first_of: dict[int, str] = field(default_factory=dict)
    first_events: dict[str, anyio.Event] = field(default_factory=dict)
    first_ok: dict[str, bool] = field(default_factory=dict)
    counts: Counter[str] = field(init=False)
    snapshot: Progress = field(init=False)

    def __post_init__(self) -> None:
        self.counts = Counter({"unsubmitted": len(self.lines)})
        self.snapshot = Progress(payloads=len(self.lines), unsubmitted=len(self.lines))

    def move(self, index: int, state: State, **fields: Any) -> None:
        """Move one payload to a state, and replace the snapshot in one step."""
        line = self.lines[index]
        self.counts[line.state] -= 1
        self.counts[state] += 1
        line.state = state
        for name, value in fields.items():
            setattr(line, name, value)
        self.snapshot = Progress(
            payloads=len(self.lines),
            **{name: self.counts[name] for name in STATES},
            written=self.written,
            uploaded=self.uploaded,
            unuploaded=len(self.unuploaded),
        )
        if index in self.first_of and state != "pending":
            url = self.first_of[index]
            self.first_ok[url] = bool(line.upload) and line.upload["code"] == 13000
            self.first_events[url].set()

    def error(self) -> IncompleteRunError | None:
        unsubmitted = [
            line.payload for line in self.lines if line.state == "unsubmitted"
        ]
        if self.stop is None and not (
            self.rejections or unsubmitted or self.unfetched or self.unuploaded
        ):
            return None
        error = IncompleteRunError(
            rejections=self.rejections,
            unsubmitted=unsubmitted,
            unfetched=self.unfetched,
            unuploaded=self.unuploaded,
        )
        error.__cause__ = self.stop
        return error


class AsyncSession:
    def __init__(
        self,
        *,
        username: str,
        password: str,
        transport: httpx2.AsyncBaseTransport | None = None,
        retry_limit: float = 600.0,
        pending_limit: float = 600.0,
        progress_interval: float | None = 10.0,
    ) -> None:
        if not username or not password:
            raise ValueError("username and password must not be empty")
        # The switch: a session with no `transport=` uses the fake that a `with` block switched on.
        if transport is None:
            transport = testing.switched_on()
        if transport is None:
            raise RuntimeError(
                "PROTOTYPE: no fake is switched on, and the stand-in sends no real request"
            )
        self._http = httpx2.AsyncClient(
            auth=(username, password),
            transport=transport,
            timeout=httpx2.Timeout(5, read=300),
        )
        self._retry_limit = retry_limit
        self._pending_limit = pending_limit
        self._progress_interval = progress_interval
        self._requests = anyio.CapacityLimiter(100)
        self._no_batch: set[str] = set()
        # Starter's limits, until the first response names the real ones.
        self._limits = {"total-requests": 50, "total-render-requests": 13}
        self._budgets = dict(self._limits)
        self._window: float | None = None
        # PROTOTYPE: one count per session, and each run reads its own share.
        self.retries = 0
        self._stack = AsyncExitStack()
        self._tasks: anyio.abc.TaskGroup | None = None

    async def __aenter__(self) -> Self:
        await self._stack.enter_async_context(self._http)
        self._tasks = await self._stack.enter_async_context(anyio.create_task_group())
        self._stack.callback(self._tasks.cancel_scope.cancel)
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self._stack.__aexit__(*exc_info)

    async def stream(
        self,
        payloads: Payload | Iterable[Payload],
        *,
        realtime: bool = False,
        destination: str | os.PathLike[str] | None = None,
        run_log: str | os.PathLike[str] | None = None,
        check_storage: bool = True,
    ) -> AsyncRun:
        if self._tasks is None:
            raise RuntimeError(
                "open the session with `async with oxy.AsyncSession(...)`"
            )
        payloads = _listed(payloads)
        storage = any(payload.storage_type for payload in payloads)
        if storage and destination is not None:
            raise ValueError(
                "destination= cannot take a payload that sets storage_type, because Cloud Storage uploads it"
            )
        if realtime and storage:
            raise ValueError("storage_type needs Push-Pull")
        # The setup checks run before the first submission, so a bad folder bills nothing.
        folder = None
        if destination is not None:
            folder = Path(destination)
            folder.mkdir(parents=True, exist_ok=True)
        log = None
        if run_log is not None:
            Path(run_log).mkdir(parents=True, exist_ok=True)
            now = datetime.now(UTC)
            log = (
                Path(run_log)
                / f"{now:%Y%m%dT%H%M%S}.{now.microsecond // 1000:03d}Z.jsonl"
            )
            log.write_text("")
        state = _State(
            lines=[_Line(payload) for payload in payloads],
            started=time.monotonic(),
            retries_at_start=self.retries,
            destination=folder,
            run_log=log,
        )
        send, receive = anyio.create_memory_object_stream[Job | Exception](100)
        self._tasks.start_soon(self._run, state, send, realtime, check_storage)
        return AsyncRun(receive, partial(self._progress, state))

    async def get(self, job_id: str) -> Job:
        url = f"{DATA}/{job_id}"
        response = await self._send("GET", f"{url}/results")
        if response.status_code == 204:
            # A 204 covers a pending job and expired results, and the job object tells them apart.
            response = await self._send("GET", url)
        if response.is_error:
            raise _error(response)
        body = response.json()
        return _job(body.get("job", body), body.get("results", []), None)

    def _progress(self, state: _State) -> Progress:
        """Return the run's snapshot, with the retries and elapsed time at this read."""
        if state.ended is not None:
            return state.ended
        return replace(
            state.snapshot,
            retries=self.retries - state.retries_at_start,
            elapsed=timedelta(seconds=time.monotonic() - state.started),
        )

    async def _run(
        self,
        state: _State,
        send: MemoryObjectSendStream[Job | Exception],
        realtime: bool,
        check_storage: bool,
    ) -> None:
        stopped = False
        async with send:
            try:
                try:
                    logger.info(
                        "Running %s with %s",
                        plural(len(state.lines), "payload"),
                        "Realtime" if realtime else "Push-Pull",
                    )
                    async with anyio.create_task_group() as outer:
                        if self._progress_interval is not None:
                            outer.start_soon(self._report, state)
                        async with anyio.create_task_group() as tg:
                            if realtime:
                                state.submitting = False
                                for index in range(len(state.lines)):
                                    tg.start_soon(self._realtime, state, index, send)
                            else:
                                tg.start_soon(self._submit_all, state, check_storage)
                                tg.start_soon(self._poll_all, state, send)
                        outer.cancel_scope.cancel()
                except anyio.get_cancelled_exc_class():
                    stopped = True
                    raise
                finally:
                    self._finish(state, stopped=stopped)
                if error := state.error():
                    await send.send(error)
            except anyio.BrokenResourceError:
                pass

    def _finish(self, state: _State, *, stopped: bool) -> None:
        """Log the end, and write the run log, however the run ended."""
        left = list(state.pending.values())
        for pending in left:
            payload = state.lines[pending.index].payload
            state.unfetched.append(_job(pending.data, [], payload))
            state.move(pending.index, "unfetched")
        state.pending.clear()
        if stopped and left and state.run_log:
            logger.warning(
                "Stopped with %s pending, which may still bill; the run log at %s lists their IDs",
                plural(len(left), "job"),
                state.run_log,
            )
        elif stopped and left:
            logger.warning(
                "Stopped with %s pending, which may still bill",
                plural(len(left), "job"),
            )
        state.ended = self._progress(state)
        if state.run_log is not None:
            state.run_log.write_text(
                "".join(
                    json.dumps(
                        {
                            "state": line.state,
                            "id": line.id,
                            "payload": line.payload.to_api(),
                            "error": line.error,
                            "upload": line.upload,
                        }
                    )
                    + "\n"
                    for line in state.lines
                )
            )
        logger.info(
            "Stopped %s after %s: %s" if stopped else "Finished %s in %s: %s",
            plural(state.ended.payloads, "payload"),
            elapsed(state.ended.elapsed),
            ", ".join([f"{state.ended.done:,} done", *state.ended.others()]),
        )
        if state.run_log is not None:
            logger.info("Wrote the run log to %s", state.run_log)

    async def _report(self, state: _State) -> None:
        while True:
            await anyio.sleep(self._progress_interval)
            logger.info("%s", self._progress(state))

    async def _submit_all(self, state: _State, check_storage: bool) -> None:
        try:
            everything = range(len(state.lines))
            firsts: dict[str, int] = {}
            if check_storage:
                for index in everything:
                    url = state.lines[index].payload.storage_url
                    if url and url not in firsts:
                        firsts[url] = index
            held = {
                url: [
                    index
                    for index in everything
                    if index != first and state.lines[index].payload.storage_url == url
                ]
                for url, first in firsts.items()
            }
            held = {url: indexes for url, indexes in held.items() if indexes}
            for url, indexes in held.items():
                state.first_of[firsts[url]] = url
                state.first_events[url] = anyio.Event()
                logger.info(
                    "Checking the upload to %s with one job before submitting %s",
                    url,
                    plural(len(indexes), "more payload"),
                )
            waiting = {index for indexes in held.values() for index in indexes}
            await self._submit(state, [i for i in everything if i not in waiting])
            async with anyio.create_task_group() as tg:
                for url, indexes in held.items():
                    tg.start_soon(self._after_first_upload, state, url, indexes)
        finally:
            state.submitting = False

    async def _after_first_upload(
        self, state: _State, url: str, indexes: list[int]
    ) -> None:
        started = anyio.current_time()
        await state.first_events[url].wait()
        if state.stop is not None:
            return
        if not state.first_ok[url]:
            logger.warning(
                "Held back %s for %s, because the first upload failed",
                plural(len(indexes), "payload"),
                url,
            )
            return
        logger.info(
            "Uploaded the first job to %s in %s",
            url,
            elapsed(timedelta(seconds=anyio.current_time() - started)),
        )
        await self._submit(state, indexes)

    async def _submit(self, state: _State, indexes: list[int]) -> None:
        groups: dict[str, _Group] = {}
        for index in indexes:
            body = state.lines[index].payload.to_api()
            key = next((key for key in INPUT_KEYS if key in body), "query")
            shared = {name: value for name, value in body.items() if name != key}
            name = json.dumps(shared, sort_keys=True)
            groups.setdefault(name, _Group(key, shared)).items.append(
                (body.get(key, ""), index)
            )
        for group in groups.values():
            if state.stop is not None:
                return
            try:
                await self._submit_group(state, group)
            except OxylabsError as error:
                self._stop(state, error)

    async def _submit_group(self, state: _State, group: _Group) -> None:
        source, pages = group.shared["source"], group.shared.get("pages", 1)
        names = _limit_names(group.shared)
        first_429: float | None = None
        while group.items and state.stop is None:
            batch = group.key in BATCH_KEYS and source not in self._no_batch
            fit = max(1, min(self._limits[name] for name in names) // pages)
            chunk = list(group.items)[: fit if batch else 1]
            await self._pace(len(chunk) * pages, names)
            values = [value for value, _ in chunk]
            response = await self._send(
                "POST",
                f"{DATA}/batch" if batch else DATA,
                json={**group.shared, group.key: values if batch else values[0]},
                submission=plural(len(chunk), f"{source} payload"),
            )
            self._learn(response)
            if response.status_code == 429:
                now = anyio.current_time()
                first_429 = now if first_429 is None else first_429
                # The domain throttle stops submission, and any other 429 goes again.
                if (
                    THROTTLE in _message(response)
                    or now - first_429 >= self._retry_limit
                ):
                    raise _error(response)
                self.retries += 1
                logger.debug(
                    "Retrying a submission of %s after 429, in 1s",
                    plural(len(chunk), f"{source} payload"),
                )
                # PROTOTYPE: the decided wait ends 1 second after the window's first response.
                await anyio.sleep(1)
                self._budgets, self._window = dict(self._limits), None
                continue
            first_429 = None
            if response.status_code not in {202, 400, 422}:
                raise _error(response)
            body = response.json()
            errors = body.get("errors", []) if batch else []
            if errors and not body["queries"] and NO_BATCH in errors[0]["message"]:
                self._no_batch.add(source)
                continue
            for _ in chunk:
                group.items.popleft()
            if response.status_code != 202:
                for _, index in chunk:
                    self._reject(state, index, response.status_code, _message(response))
                continue
            now = anyio.current_time()
            for job in body["queries"] if batch else [body]:
                # A batch's error does not repeat an empty value, so the accepted values show which ones it rejected.
                position = values.index(job.get(group.key))
                values.pop(position)
                index = chunk.pop(position)[1]
                state.pending[job["id"]] = _Pending(index, job, now, now + 1)
                state.move(index, "pending", id=job["id"])
                logger.debug(
                    "Job %s is pending: %s",
                    job["id"],
                    describe(state.lines[index].payload),
                )
            for (_, index), error in zip(chunk, errors, strict=False):
                self._reject(state, index, 400, error["message"])

    def _reject(
        self, state: _State, index: int, status_code: int, message: str
    ) -> None:
        payload = state.lines[index].payload
        state.rejections.append(
            Rejection(payload=payload, status_code=status_code, message=message)
        )
        state.move(
            index, "rejected", error={"status_code": status_code, "message": message}
        )
        logger.warning(
            "Rejected %s: %s", describe(payload), f"{status_code} {message.rstrip('.')}"
        )

    def _stop(self, state: _State, error: OxylabsError) -> None:
        if state.stop is not None:
            return
        state.stop = error
        count = state.counts["unsubmitted"]
        reason = (
            f"the API returned {error.status_code}" if error.status_code else str(error)
        )
        if error.status_code and error.message:
            reason += f": {error.message.rstrip('.')}"
        logger.warning(
            "Stopped submitting, because %s; %s unsubmitted",
            reason,
            f"{plural(count, 'payload')} {'stays' if count == 1 else 'stay'}",
        )

    async def _poll_all(
        self, state: _State, send: MemoryObjectSendStream[Job | Exception]
    ) -> None:
        async with anyio.create_task_group() as tg:
            while state.submitting or state.pending:
                now = anyio.current_time()
                for job_id, pending in list(state.pending.items()):
                    if job_id not in state.checking and pending.next_check <= now:
                        state.checking.add(job_id)
                        tg.start_soon(self._check, state, job_id, pending, send)
                await anyio.sleep(0.1)

    async def _check(
        self,
        state: _State,
        job_id: str,
        pending: _Pending,
        send: MemoryObjectSendStream[Job | Exception],
    ) -> None:
        try:
            try:
                job = await self._fetch(job_id, pending, state)
            except OxylabsError as error:
                if error.status_code in {401, 403}:
                    # Every check fails the same way, so the run stops polling at once.
                    self._stop(state, error)
                    for other_id, other in list(state.pending.items()):
                        self._unfetch(
                            state, other_id, other, f"the API returned {error}"
                        )
                elif job_id in state.pending:
                    self._unfetch(state, job_id, pending, f"the API returned {error}")
                return
            if job_id not in state.pending:
                return
            now = anyio.current_time()
            age = now - pending.accepted
            waiting = job.status == "pending" or (
                job.upload is not None and job.upload.code is None
            )
            if waiting and age < self._pending_limit:
                # The decided schedule: every second until the job is 10 seconds old, then every 5.
                pending.next_check = now + (1 if age < 10 else 5)
                return
            if job.status == "pending":
                self._unfetch(
                    state,
                    job_id,
                    pending,
                    f"it is still pending after {duration(self._pending_limit)}",
                )
                return
            del state.pending[job_id]
            await self._finished(state, pending.index, job, send)
        finally:
            state.checking.discard(job_id)

    def _unfetch(
        self, state: _State, job_id: str, pending: _Pending, reason: str
    ) -> None:
        del state.pending[job_id]
        payload = state.lines[pending.index].payload
        state.unfetched.append(_job(pending.data, [], payload))
        state.move(pending.index, "unfetched", error={"message": reason})
        logger.warning(
            "Stopped checking job %s, because %s: %s", job_id, reason, describe(payload)
        )

    async def _finished(
        self,
        state: _State,
        index: int,
        job: Job,
        send: MemoryObjectSendStream[Job | Exception],
    ) -> None:
        payload = state.lines[index].payload
        upload = None
        if job.upload is not None:
            upload = {"code": job.upload.code, "message": job.upload.message}
            if job.upload.code == 13000:
                state.uploaded += 1
            else:
                state.unuploaded.append(job)
                if job.upload.code is None:
                    logger.warning(
                        "Cloud Storage recorded no upload for job %s within %s: %s",
                        job.id,
                        duration(self._pending_limit),
                        describe(payload),
                    )
                else:
                    logger.warning(
                        "The upload of job %s failed with %s: %s",
                        job.id,
                        f"{job.upload.code} {job.upload.message}",
                        describe(payload),
                    )
        if job.status == "faulted":
            logger.warning("Job %s faulted: %s", job.id, describe(payload))
        elif state.destination is not None and job.upload is None:
            body = {"results": [result.data for result in job.results], "job": job.data}
            (state.destination / f"{job.id}.json").write_text(
                json.dumps(body, separators=(",", ":")) + "\n"
            )
            state.written += 1
        logger.debug("Job %s is %s: %s", job.id, job.status, describe(payload))
        state.move(index, job.status, upload=upload)
        await send.send(job)

    async def _fetch(self, job_id: str, pending: _Pending, state: _State) -> Job:
        url = f"{DATA}/{job_id}"
        payload = state.lines[pending.index].payload
        if payload.storage_type:
            # Cloud Storage uploads the results, so oxy reads the job object alone.
            response = await self._send("GET", url)
            if response.is_error:
                raise _error(response)
            return _job(response.json(), [], payload)
        response = await self._send("GET", f"{url}/results")
        if response.status_code == 204:
            return _job(pending.data, [], payload)
        if response.is_error:
            raise _error(response)
        body = response.json()
        return _job(body["job"], body["results"], payload)

    async def _realtime(
        self,
        state: _State,
        index: int,
        send: MemoryObjectSendStream[Job | Exception],
    ) -> None:
        # PROTOTYPE: the payload stays unsubmitted until its answer returns.
        payload = state.lines[index].payload
        body = payload.to_api()
        await self._pace(body.get("pages", 1), _limit_names(body))
        try:
            response = await self._send("POST", REALTIME, json=body)
        except OxylabsError as error:
            self._stop(state, error)
            return
        self._learn(response)
        if response.status_code in {400, 408, 422}:
            self._reject(state, index, response.status_code, _message(response))
        elif response.is_error:
            self._stop(state, _error(response))
        else:
            answer = response.json()
            job = _job(answer["job"], answer["results"], payload)
            state.lines[index].id = job.id
            await self._finished(state, index, job, send)

    async def _pace(self, cost: int, names: list[str]) -> None:
        """Wait until a submission of this cost fits every budget, then take it."""
        if any(self._budgets[name] < cost for name in names):
            opened = anyio.current_time() if self._window is None else self._window
            await anyio.sleep(max(opened + 1 - anyio.current_time(), 0))
            self._budgets, self._window = dict(self._limits), None
        for name in names:
            self._budgets[name] -= cost

    def _learn(self, response: httpx2.Response) -> None:
        """Read each limit, and what is left of it, from the headers of a submission's response."""
        for header, value in response.headers.items():
            for name in self._limits:
                if not header.startswith(f"x-ratelimit-{name}-"):
                    continue
                if header.endswith("-limit"):
                    self._limits[name] = int(value)
                elif header.endswith("-remaining"):
                    self._budgets[name] = min(self._budgets[name], int(value))
                if self._window is None:
                    self._window = anyio.current_time()

    async def _send(
        self,
        method: str,
        url: str,
        *,
        json: dict[str, Any] | None = None,
        submission: str | None = None,
    ) -> httpx2.Response:
        """Send a request, and retry a 5xx, a network error, and a 429 on anything but a Push-Pull submission.

        `submission` names what a Push-Pull submission holds, for its warning.
        """
        ceiling, first = 1.0, None
        while True:
            response = failure = None
            try:
                async with self._requests:
                    response = await self._http.request(method, url, json=json)
            except RETRIED as error:
                failure = error
            if response is not None and not (
                response.status_code >= 500
                or (response.status_code == 429 and submission is None)
            ):
                return response
            now = anyio.current_time()
            first = now if first is None else first
            if now - first >= self._retry_limit:
                if response is not None:
                    raise _error(response)
                raise OxylabsError(f"{type(failure).__name__}: {failure}") from failure
            self.retries += 1
            cause = (
                str(response.status_code)
                if response is not None
                else type(failure).__name__
            )
            wait = random.uniform(0, ceiling)
            if submission and not isinstance(failure, UNSENT):
                logger.warning(
                    "Retrying a submission of %s after %s; the API may have created their jobs, and each duplicate bills",
                    submission,
                    cause,
                )
            else:
                logger.debug(
                    "Retrying %s %s after %s, in %s", method, url, cause, f"{wait:.2f}s"
                )
            await anyio.sleep(wait)
            ceiling = min(ceiling * 2, 30.0)


class Session:
    """Run `AsyncSession` from sync code, through a blocking portal that lives as long as the `with` block."""

    def __init__(
        self,
        *,
        username: str,
        password: str,
        transport: httpx2.AsyncBaseTransport | None = None,
        retry_limit: float = 600.0,
        pending_limit: float = 600.0,
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
        self._portal: Any = None

    def __enter__(self) -> Self:
        self._portal = self._stack.enter_context(start_blocking_portal())
        self._stack.enter_context(
            self._portal.wrap_async_context_manager(self._session)
        )
        return self

    def __exit__(self, *exc_info: object) -> None:
        # The caller's exception stays out of the event loop, where a task group would wrap it in an ExceptionGroup.
        self._stack.__exit__(None, None, None)

    def execute(
        self,
        payloads: Payload | Iterable[Payload],
        *,
        realtime: bool = False,
        destination: str | os.PathLike[str] | None = None,
        run_log: str | os.PathLike[str] | None = None,
        check_storage: bool = True,
    ) -> Run:
        if self._portal is None:
            raise RuntimeError("open the session with `with oxy.Session(...)`")
        run = self._portal.call(
            partial(
                self._session.stream,
                payloads,
                realtime=realtime,
                destination=destination,
                run_log=run_log,
                check_storage=check_storage,
            )
        )
        return Run(self._pull(run), lambda: run.progress)

    def get(self, job_id: str) -> Job:
        return self._portal.call(self._session.get, job_id)

    def _pull(self, run: AsyncRun) -> Iterator[Job]:
        while True:
            try:
                yield self._portal.call(anext, run)
            except StopAsyncIteration:
                return


def describe(payload: Payload) -> str:
    """Name a payload by its source and input, as a log line does."""
    body = payload.to_api()
    return f"{body['source']} " + next(
        str(body[key]) for key in INPUT_KEYS if key in body
    )


def plural(count: int, noun: str, nouns: str | None = None) -> str:
    return f"{count:,} {noun if count == 1 else nouns or noun + 's'}"


def duration(seconds: float) -> str:
    return f"{seconds / 60:g}m" if seconds >= 60 else f"{seconds:g}s"


def elapsed(delta: timedelta) -> str:
    """Format a duration as uv does, such as `312ms`, `4.02s` or `1m 05s`."""
    seconds = delta.total_seconds()
    whole = int(seconds)
    if whole >= 3600:
        return f"{whole // 3600}h {whole % 3600 // 60:02}m {whole % 60:02}s"
    if whole >= 60:
        return f"{whole // 60}m {whole % 60:02}s"
    if whole:
        return f"{seconds:.2f}s"
    return f"{seconds * 1000:.0f}ms"


def _listed(payloads: Payload | Iterable[Payload]) -> list[Payload]:
    return [payloads] if isinstance(payloads, Payload) else list(payloads)


def _limit_names(body: dict[str, Any]) -> list[str]:
    rendered = bool(body.get("render")) or body.get("xhr") is True
    return ["total-requests", *(["total-render-requests"] if rendered else [])]


def _message(response: httpx2.Response) -> str:
    json_body = response.headers.get("content-type", "").startswith("application/json")
    return response.json().get("message", "") if json_body and response.content else ""


def _error(response: httpx2.Response) -> OxylabsError:
    return OxylabsError(_message(response), response.status_code)


def _job(
    data: dict[str, Any], results: list[dict[str, Any]], payload: Payload | None
) -> Job:
    upload = None
    if data.get("storage_type"):
        entry = next(iter(data.get("statuses") or []), {})
        upload = Upload(
            storage_url=data["storage_url"],
            code=entry.get("code"),
            message=entry.get("message"),
        )
    return Job(
        id=data["id"],
        status=data["status"],
        source=data["source"],
        input=next((str(data[key]) for key in INPUT_KEYS if data.get(key)), ""),
        payload=payload,
        results=[
            Result(
                page=result["page"],
                type=result["type"],
                status_code=result["status_code"],
                content=result["content"],
                data=result,
            )
            for result in results
        ],
        data=data,
        upload=upload,
    )
