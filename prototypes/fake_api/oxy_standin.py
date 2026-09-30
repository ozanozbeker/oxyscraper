"""PROTOTYPE, throwaway: a stand-in for oxyscraper as the map has decided it, so `tour.py` can run test code.

It sends no real request: a session with no fake raises.
Its pacing and retries are simpler than the decided ones, and it has no destination, run log, `check_storage` or Progress.
"""

# ruff: noqa: D101, D102, D105, EM101, EM102, FBT001, INP001, PLR2004, TRY003
# pyrefly: ignore-errors

from __future__ import annotations

import base64
import json
from collections import deque
from contextlib import AsyncExitStack, ExitStack
from dataclasses import dataclass, field
from functools import partial
from typing import TYPE_CHECKING, Annotated, Any, ClassVar, Literal, Self

import anyio
import httpx2
import testing
from anyio.from_thread import start_blocking_portal
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence

    from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream

DATA = "https://data.oxylabs.io/v1/queries"
REALTIME = "https://realtime.oxylabs.io/v1/queries"
INPUT_KEYS = (
    "query",
    "url",
    "product_id",
    "prompt",
    "video_id",
    "channel_handle",
    "category_id",
)
# A list under any other input key returns 400, so those payloads go one per request.
BATCH_KEYS = ("query", "url", "prompt")
NO_BATCH = "is not available with a batch request"
THROTTLE = "has been limited to 1 req/s"
RETRIED = (httpx2.TimeoutException, httpx2.NetworkError, httpx2.RemoteProtocolError)

OutputType = Literal["raw", "parsed", "png", "markdown", "xhr"]
Content = str | bytes | dict[str, Any] | list[Any]


class Payload(BaseModel):
    """One job's parameters, for any source."""

    model_config = ConfigDict(extra="allow")
    CONTEXT: ClassVar[frozenset[str]] = frozenset()

    source: str
    render: Literal["html", "png"] | None = None
    parse: bool | None = None
    start_page: Annotated[int, Field(ge=1)] | None = None
    pages: Annotated[int, Field(ge=1)] | None = None
    storage_type: Literal["gcs", "s3", "tos", "s3_compatible"] | None = None
    storage_url: str | None = None

    def to_api(self) -> dict[str, Any]:
        data = self.model_dump(exclude_none=True)
        context = [
            {"key": key, "value": data.pop(key)}
            for key in sorted(self.CONTEXT)
            if key in data
        ]
        return data | ({"context": context} if context else {})


class AmazonProduct(Payload):
    model_config = ConfigDict(extra="forbid")
    CONTEXT: ClassVar[frozenset[str]] = frozenset({"currency", "autoselect_variant"})

    source: Literal["amazon_product"] = "amazon_product"
    query: Annotated[str, Field(pattern=r"^[0-9A-Z]{10}$", description="An ASIN.")]
    domain: str | None = None
    geo_location: str | None = None
    currency: str | None = None
    autoselect_variant: bool | None = None


class Universal(Payload):
    model_config = ConfigDict(extra="forbid")

    source: Literal["universal"] = "universal"
    url: str
    xhr: bool | None = None
    markdown: bool | None = None


@dataclass(frozen=True, kw_only=True)
class Result:
    page: int
    type: OutputType
    status_code: int
    content: Content = field(repr=False)
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

    @property
    def content(self) -> Content:
        if len(self.results) != 1:
            raise ValueError(
                f"job {self.id} has {len(self.results)} results, so read job.results"
            )
        return self.results[0].content


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


class Run:
    def __init__(self, jobs: Iterator[Job]) -> None:
        self._jobs = jobs

    def __iter__(self) -> Iterator[Job]:
        return self._jobs

    def all(self) -> list[Job]:
        jobs: list[Job] = []
        try:
            jobs.extend(self._jobs)
        except IncompleteRunError as error:
            error.jobs = jobs
            raise
        return jobs

    def one(self) -> Job:
        jobs = self.all()
        if len(jobs) != 1:
            raise ValueError(f"expected one job, got {len(jobs)}")
        return jobs[0]


class AsyncRun:
    def __init__(self, receive: MemoryObjectReceiveStream[Job | Exception]) -> None:
        self._receive = receive

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

    async def all(self) -> list[Job]:
        jobs: list[Job] = []
        try:
            async for job in self:
                jobs.append(job)  # noqa: PERF401
        except IncompleteRunError as error:
            error.jobs = jobs
            raise
        return jobs


@dataclass
class _Group:
    """The payloads that share every parameter but the input, which go out as batches."""

    key: str
    shared: dict[str, Any]
    items: deque[tuple[str, Payload]] = field(default_factory=deque)


@dataclass
class _Pending:
    payload: Payload
    data: dict[str, Any]
    accepted: float
    next_check: float


@dataclass
class _State:
    submitting: bool = True
    stop: OxylabsError | None = None
    pending: dict[str, _Pending] = field(default_factory=dict)
    rejections: list[Rejection] = field(default_factory=list)
    unsubmitted: list[Payload] = field(default_factory=list)
    unfetched: list[Job] = field(default_factory=list)
    unuploaded: list[Job] = field(default_factory=list)

    def error(self) -> IncompleteRunError | None:
        lists = (self.rejections, self.unsubmitted, self.unfetched, self.unuploaded)
        if self.stop is None and not any(lists):
            return None
        error = IncompleteRunError(
            rejections=self.rejections,
            unsubmitted=self.unsubmitted,
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
        self._requests = anyio.CapacityLimiter(100)
        self._no_batch: set[str] = set()
        # Starter's limits, until the first response names the real ones.
        self._limits = {"total-requests": 50, "total-render-requests": 13}
        self._budgets = dict(self._limits)
        self._window: float | None = None
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

    async def execute(
        self,
        payloads: Payload | Iterable[Payload],
        *,
        realtime: bool = False,
        output_types: Sequence[OutputType] = (),
    ) -> Run:
        run = await self.stream(payloads, realtime=realtime, output_types=output_types)
        return Run(iter(await run.all()))

    async def stream(
        self,
        payloads: Payload | Iterable[Payload],
        *,
        realtime: bool = False,
        output_types: Sequence[OutputType] = (),
    ) -> AsyncRun:
        if self._tasks is None:
            raise RuntimeError(
                "open the session with `async with oxy.AsyncSession(...)`"
            )
        payloads = [payloads] if isinstance(payloads, Payload) else list(payloads)
        if realtime and any(payload.storage_type for payload in payloads):
            raise ValueError("storage_type needs Push-Pull")
        send, receive = anyio.create_memory_object_stream[Job | Exception](100)
        self._tasks.start_soon(self._run, payloads, send, realtime, output_types)
        return AsyncRun(receive)

    async def get(self, job_id: str, *, output_types: Sequence[OutputType] = ()) -> Job:
        url = f"{DATA}/{job_id}"
        response = await self._send(
            "GET", f"{url}/results", params=_types(output_types)
        )
        if response.status_code == 204:
            # A 204 covers a pending job and expired results, and the job object tells them apart.
            response = await self._send("GET", url)
        if response.is_error:
            raise _error(response)
        body = response.json()
        return _job(body.get("job", body), body.get("results", []), None)

    async def _run(
        self,
        payloads: list[Payload],
        send: MemoryObjectSendStream[Job | Exception],
        realtime: bool,
        output_types: Sequence[OutputType],
    ) -> None:
        state = _State()
        async with send:
            try:
                async with anyio.create_task_group() as tg:
                    if realtime:
                        for payload in payloads:
                            tg.start_soon(
                                self._realtime, state, payload, send, output_types
                            )
                    else:
                        tg.start_soon(self._submit_all, state, payloads)
                        tg.start_soon(self._poll_all, state, send, output_types)
                if error := state.error():
                    await send.send(error)
            except anyio.BrokenResourceError:
                pass

    async def _submit_all(self, state: _State, payloads: list[Payload]) -> None:
        groups: dict[str, _Group] = {}
        for payload in payloads:
            body = payload.to_api()
            key = next((key for key in INPUT_KEYS if key in body), "query")
            shared = {name: value for name, value in body.items() if name != key}
            name = json.dumps(shared, sort_keys=True)
            groups.setdefault(name, _Group(key, shared)).items.append(
                (body.get(key, ""), payload)
            )
        for group in groups.values():
            if state.stop is None:
                try:
                    await self._submit_group(state, group)
                except OxylabsError as error:
                    state.stop = error
            # A run-level failure leaves the rest unsubmitted.
            state.unsubmitted += [payload for _, payload in group.items]
        state.submitting = False

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
                submission=True,
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
                state.rejections += [
                    _rejection(payload, response) for _, payload in chunk
                ]
                continue
            now = anyio.current_time()
            for job in body["queries"] if batch else [body]:
                # A batch's error does not repeat an empty value, so the accepted values show which ones it rejected.
                index = values.index(job.get(group.key))
                values.pop(index)
                payload = chunk.pop(index)[1]
                state.pending[job["id"]] = _Pending(payload, job, now, now + 1)
            state.rejections += [
                Rejection(payload=payload, status_code=400, message=error["message"])
                for (_, payload), error in zip(chunk, errors, strict=False)
            ]

    async def _poll_all(
        self,
        state: _State,
        send: MemoryObjectSendStream[Job | Exception],
        output_types: Sequence[OutputType],
    ) -> None:
        while state.submitting or state.pending:
            for job_id, pending in list(state.pending.items()):
                if (
                    job_id in state.pending
                    and pending.next_check <= anyio.current_time()
                ):
                    await self._check(state, job_id, pending, send, output_types)
            await anyio.sleep(0.1)

    async def _check(
        self,
        state: _State,
        job_id: str,
        pending: _Pending,
        send: MemoryObjectSendStream[Job | Exception],
        output_types: Sequence[OutputType],
    ) -> None:
        try:
            job = await self._fetch(job_id, pending, output_types)
        except OxylabsError as error:
            if error.status_code in {401, 403}:
                # Every check fails the same way, so the run stops polling at once.
                state.stop = state.stop or error
                state.unfetched += [
                    _job(other.data, [], other.payload)
                    for other in state.pending.values()
                ]
                state.pending.clear()
            else:
                del state.pending[job_id]
                state.unfetched.append(_job(pending.data, [], pending.payload))
            return
        now = anyio.current_time()
        age = now - pending.accepted
        waiting = job.status == "pending" or (job.upload and job.upload.code is None)
        if waiting and age < self._pending_limit:
            # The decided schedule: every second until the job is 10 seconds old, then every 5.
            pending.next_check = now + (1 if age < 10 else 5)
            return
        del state.pending[job_id]
        if job.status == "pending":
            state.unfetched.append(job)
            return
        if job.upload and job.upload.code != 13000:
            state.unuploaded.append(job)
        await send.send(job)

    async def _fetch(
        self, job_id: str, pending: _Pending, output_types: Sequence[OutputType]
    ) -> Job:
        url = f"{DATA}/{job_id}"
        if pending.payload.storage_type:
            # Cloud Storage uploads the results, so oxy reads the job object alone.
            response = await self._send("GET", url)
            if response.is_error:
                raise _error(response)
            return _job(response.json(), [], pending.payload)
        response = await self._send(
            "GET", f"{url}/results", params=_types(output_types)
        )
        if response.status_code == 204:
            return _job(pending.data, [], pending.payload)
        if response.is_error:
            raise _error(response)
        body = response.json()
        return _job(body["job"], body["results"], pending.payload)

    async def _realtime(
        self,
        state: _State,
        payload: Payload,
        send: MemoryObjectSendStream[Job | Exception],
        output_types: Sequence[OutputType],
    ) -> None:
        body = payload.to_api()
        await self._pace(body.get("pages", 1), _limit_names(body))
        try:
            response = await self._send(
                "POST", REALTIME, json=body, params=_types(output_types)
            )
        except OxylabsError as error:
            state.stop = state.stop or error
            state.unsubmitted.append(payload)
            return
        self._learn(response)
        if response.status_code in {400, 408, 422}:
            state.rejections.append(_rejection(payload, response))
        elif response.is_error:
            state.stop = state.stop or _error(response)
            state.unsubmitted.append(payload)
        else:
            answer = response.json()
            await send.send(_job(answer["job"], answer["results"], payload))

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
        params: dict[str, str] | None = None,
        submission: bool = False,
    ) -> httpx2.Response:
        """Send a request, and retry a 5xx, a network error, and a 429 on anything but a Push-Pull submission."""
        ceiling, first = 1.0, None
        while True:
            response = failure = None
            try:
                async with self._requests:
                    response = await self._http.request(
                        method, url, json=json, params=params
                    )
            except RETRIED as error:
                failure = error
            if response is not None and not (
                response.status_code >= 500
                or (response.status_code == 429 and not submission)
            ):
                return response
            now = anyio.current_time()
            first = now if first is None else first
            if now - first >= self._retry_limit:
                if response is not None:
                    raise _error(response)
                raise OxylabsError(f"{type(failure).__name__}: {failure}") from failure
            self.retries += 1
            # PROTOTYPE: the decided wait is random, between 0 and the ceiling.
            await anyio.sleep(ceiling)
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
    ) -> None:
        self._session = AsyncSession(
            username=username,
            password=password,
            transport=transport,
            retry_limit=retry_limit,
            pending_limit=pending_limit,
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
        self._stack.__exit__(*exc_info)

    def execute(
        self,
        payloads: Payload | Iterable[Payload],
        *,
        realtime: bool = False,
        output_types: Sequence[OutputType] = (),
    ) -> Run:
        if self._portal is None:
            raise RuntimeError("open the session with `with oxy.Session(...)`")
        run = self._portal.call(
            partial(
                self._session.stream,
                payloads,
                realtime=realtime,
                output_types=output_types,
            )
        )
        return Run(self._pull(run))

    def get(self, job_id: str, *, output_types: Sequence[OutputType] = ()) -> Job:
        return self._portal.call(
            partial(self._session.get, job_id, output_types=output_types)
        )

    def _pull(self, run: AsyncRun) -> Iterator[Job]:
        while True:
            try:
                yield self._portal.call(anext, run)
            except StopAsyncIteration:
                return


def _limit_names(body: dict[str, Any]) -> list[str]:
    rendered = bool(body.get("render")) or body.get("xhr") is True
    return ["total-requests", *(["total-render-requests"] if rendered else [])]


def _types(output_types: Sequence[OutputType]) -> dict[str, str] | None:
    return {"type": ",".join(output_types)} if output_types else None


def _message(response: httpx2.Response) -> str:
    json_body = response.headers.get("content-type", "").startswith("application/json")
    return response.json().get("message", "") if json_body and response.content else ""


def _error(response: httpx2.Response) -> OxylabsError:
    return OxylabsError(_message(response), response.status_code)


def _rejection(payload: Payload, response: httpx2.Response) -> Rejection:
    return Rejection(
        payload=payload, status_code=response.status_code, message=_message(response)
    )


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
        results=[_result(result) for result in results],
        data=data,
        upload=upload,
    )


def _result(data: dict[str, Any]) -> Result:
    content = data["content"]
    # The API sends `png` as Base64 text.
    if data["type"] == "png" and content:
        content = base64.b64decode(content)
    return Result(
        page=data["page"],
        type=data["type"],
        status_code=data["status_code"],
        content=content,
        data=data,
    )
