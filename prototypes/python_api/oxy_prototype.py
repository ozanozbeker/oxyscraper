"""PROTOTYPE, throwaway: the SQLModel-shaped Python API for oxyscraper, to react to.

It answers [Prototype: calling oxy from Python](https://github.com/ozanozbeker/oxyscraper/issues/11), `tour.py` runs it against a fake API, and `shapes.md` compares it with the other shapes.
Retries, pacing, the job record and writers stay out, because other tickets on the map decide them.
"""

# ruff: noqa: BLE001, D102, D105, FBT001, INP001, PLR2004
# pyrefly: ignore-errors

from __future__ import annotations

import base64
import contextlib
import itertools
import json
from contextlib import AsyncExitStack, ExitStack
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial
from typing import TYPE_CHECKING, Annotated, Any, ClassVar, Literal, Self

import anyio
import httpx2
from anyio.from_thread import start_blocking_portal
from pydantic import BaseModel, ConfigDict, Field, model_validator

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
# Starter's limit. "How does oxy schedule submissions and status checks?" replaces it with the rate-limit headers.
JOBS_PER_SECOND = 50
POLL_INTERVAL = 0.5
# Both Oxylabs hosts allow 100 HTTP/2 streams (docs/research/httpx2.md).
MAX_REQUESTS = 100
BUFFER = 100

OutputType = Literal["raw", "parsed", "png", "markdown", "xhr"]
Content = str | bytes | dict[str, Any] | list[Any]
UserAgentType = Literal[
    "desktop",
    "mobile",
    "mobile_android",
    "mobile_ios",
    "tablet",
    "tablet_android",
    "tablet_ios",
]
AmazonDomain = Literal[
    "ae", "ca", "cn", "co.jp", "co.uk", "com", "com.au", "com.be", "com.br", "com.mx", "com.tr", "de",
    "eg", "es", "fr", "ie", "in", "it", "nl", "pl", "sa", "se", "sg",
]  # fmt: skip


class Payload(BaseModel):
    """One job's parameters, for any source.

    It types the parameters that most sources share and passes every other keyword through, so a source with no model of its own still runs.
    """

    model_config = ConfigDict(extra="allow")
    # Fields the API reads from the `context` list rather than the top level.
    CONTEXT: ClassVar[frozenset[str]] = frozenset()

    source: str
    render: Literal["html", "png", ""] | None = None
    parse: bool | None = None
    user_agent_type: UserAgentType | None = None
    callback_url: str | None = None
    geo_location: str | None = None
    locale: str | None = None
    domain: str | None = None
    start_page: Annotated[int, Field(ge=1)] | None = None
    pages: Annotated[int, Field(ge=1)] | None = None

    @model_validator(mode="after")
    def _one_input_key(self) -> Self:
        if len([key for key in INPUT_KEYS if key in self.to_api()]) != 1:
            msg = f"set exactly one input key: {', '.join(INPUT_KEYS)}"
            raise ValueError(msg)
        return self

    def to_api(self) -> dict[str, Any]:
        """Return the JSON body the API receives for this job."""
        data = self.model_dump(exclude_none=True)
        passthrough = data.pop("extra", {})
        context = [
            {"key": key, "value": data.pop(key)}
            for key in sorted(self.CONTEXT)
            if key in data
        ]
        if context:
            data["context"] = [*data.get("context", []), *context]
        return {**data, **passthrough}


class AmazonProduct(Payload):
    """An `amazon_product` job, typed from the parameter catalog."""

    model_config = ConfigDict(extra="forbid")
    CONTEXT: ClassVar[frozenset[str]] = frozenset({"currency", "autoselect_variant"})

    source: Literal["amazon_product"] = "amazon_product"
    query: Annotated[str, Field(pattern=r"^[0-9A-Z]{10}$", description="An ASIN.")]
    domain: AmazonDomain | None = None
    render: Literal["html", "png"] | None = None
    currency: str | None = None
    autoselect_variant: bool | None = None
    # Parameters this model does not type yet, sent as they are.
    extra: dict[str, Any] = Field(default_factory=dict)


class AmazonSearch(Payload):
    """An `amazon_search` job, typed from the parameter catalog."""

    model_config = ConfigDict(extra="forbid")
    # A top-level `sort_by` bills and has no effect on this source (docs/research/live-parameters.md).
    CONTEXT: ClassVar[frozenset[str]] = frozenset(
        {"sort_by", "currency", "min_price", "max_price"}
    )

    source: Literal["amazon_search"] = "amazon_search"
    query: Annotated[str, Field(min_length=1)]
    domain: AmazonDomain | None = None
    render: Literal["html", "png"] | None = None
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
    min_price: Annotated[int, Field(gt=0, description="In cents.")] | None = None
    max_price: Annotated[int, Field(gt=0, description="In cents.")] | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


# The sources someone has worked on. Every other source runs through `Payload`.
SOURCES = (AmazonProduct, AmazonSearch)


@dataclass(frozen=True, kw_only=True)
class Result:
    """What a job produces for one page, in one output type."""

    page: int
    type: OutputType
    status_code: int
    content: Content = field(repr=False)
    created_at: datetime
    updated_at: datetime
    data: dict[str, Any] = field(repr=False)


@dataclass(frozen=True, kw_only=True)
class Job:
    """One job and its results.

    `data` keeps the job object as the API returned it, so a field oxy does not type stays readable.
    """

    id: str
    status: Literal["pending", "done", "faulted"]
    source: str
    input: str
    created_at: datetime
    finished_at: datetime | None
    results: list[Result] = field(repr=False)
    data: dict[str, Any] = field(repr=False)

    @property
    def content(self) -> Content:
        """Return the content of the job's only result."""
        if len(self.results) != 1:
            msg = f"job {self.id} has {len(self.results)} results, so read job.results"
            raise ValueError(msg)
        return self.results[0].content


@dataclass(frozen=True, kw_only=True)
class DryRun:
    """The jobs a run would submit, built without a request or credentials."""

    jobs: list[dict[str, Any]]
    max_results: int

    @property
    def job_count(self) -> int:
        return len(self.jobs)


class OxylabsError(Exception):
    """The API returned an error status, or rejected values in a batch."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(
            message if status_code is None else f"{status_code} {message}".strip()
        )
        self.status_code = status_code


def dry_run(payloads: Payload | Iterable[Payload]) -> DryRun:
    """List the jobs that `execute` would submit, and the most results they can bill."""
    jobs = [payload.to_api() for payload in _listed(payloads)]
    return DryRun(jobs=jobs, max_results=sum(job.get("pages", 1) for job in jobs))


class Run:
    """The jobs of one `execute` call.

    It is not named `Result`, because the glossary's Result is one page of one job.
    """

    def __init__(self, jobs: Iterator[Job]) -> None:
        self._jobs = jobs

    def __iter__(self) -> Iterator[Job]:
        return self._jobs

    def all(self) -> list[Job]:
        return list(self._jobs)

    def one(self) -> Job:
        jobs = self.all()
        if len(jobs) != 1:
            msg = f"expected one job, got {len(jobs)}"
            raise ValueError(msg)
        return jobs[0]

    def partitions(self, size: int) -> Iterator[list[Job]]:
        while chunk := list(itertools.islice(self._jobs, size)):
            yield chunk


class AsyncRun:
    """The jobs of one `stream` call, each as it finishes."""

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
        return [job async for job in self]


class AsyncSession:
    """Run jobs inside an `async with` block, on asyncio or trio.

    The block bounds the task group that submits and polls in the background, because an async generator cannot hold background tasks across a `yield`.
    Leaving the block stops unfinished runs, and their jobs stay on Oxylabs for at least 24 hours.
    """

    def __init__(
        self,
        *,
        username: str,
        password: str,
        transport: httpx2.AsyncBaseTransport | None = None,
    ) -> None:
        self._http = httpx2.AsyncClient(
            auth=(username, password),
            transport=transport,
            # httpx2's read timeout applies per chunk, and rendered Realtime jobs need 180 s.
            timeout=httpx2.Timeout(5, read=180),
            headers={"user-agent": "oxyscraper-prototype"},
        )
        self._requests = anyio.CapacityLimiter(MAX_REQUESTS)
        self._no_batch: set[str] = set()
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
        """Run the jobs, and return them all once the last one finishes."""
        run = await self.stream(payloads, realtime=realtime, output_types=output_types)
        return Run(iter(await run.all()))

    async def stream(
        self,
        payloads: Payload | Iterable[Payload],
        *,
        realtime: bool = False,
        output_types: Sequence[OutputType] = (),
    ) -> AsyncRun:
        """Start the jobs now, and return them each as it finishes."""
        if self._tasks is None:
            msg = "open the session with `async with oxy.AsyncSession(...) as session`"
            raise RuntimeError(msg)
        bodies = [payload.to_api() for payload in _listed(payloads)]
        send, receive = anyio.create_memory_object_stream[Job | Exception](BUFFER)
        self._tasks.start_soon(self._run, bodies, send, realtime, output_types)
        return AsyncRun(receive)

    async def get(self, job_id: str, *, output_types: Sequence[OutputType] = ()) -> Job:
        """Return a job by ID, with its results once it has finished."""
        if job := await self._results(job_id, output_types):
            return job
        return _job((await self._send("GET", f"{DATA}/{job_id}")).json(), [])

    async def _run(
        self,
        bodies: list[dict[str, Any]],
        send: MemoryObjectSendStream[Job | Exception],
        realtime: bool,
        output_types: Sequence[OutputType],
    ) -> None:
        async with send:
            try:
                if realtime:
                    await self._run_realtime(bodies, send, output_types)
                else:
                    await self._run_push_pull(bodies, send, output_types)
            except anyio.BrokenResourceError:
                pass
            except Exception as error:
                # The caller's loop raises it, rather than the session's task group.
                with contextlib.suppress(anyio.BrokenResourceError):
                    await send.send(error)

    async def _run_push_pull(
        self,
        bodies: list[dict[str, Any]],
        send: MemoryObjectSendStream[Job | Exception],
        output_types: Sequence[OutputType],
    ) -> None:
        queue = _batches(bodies)
        pending: list[str] = []
        rejected: list[str] = []
        window, used = 0.0, 0
        while queue or pending:
            if anyio.current_time() - window >= 1:
                window, used = anyio.current_time(), 0
            while queue and used + _cost(queue[0]) <= JOBS_PER_SECOND:
                used += _cost(queue[0])
                ids, errors = await self._submit(*queue.pop(0))
                pending += ids
                rejected += errors
            for job in await self._poll(pending, output_types):
                pending.remove(job.id)
                await send.send(job)
            if queue or pending:
                await anyio.sleep(POLL_INTERVAL)
        if rejected:
            msg = f"the API rejected {len(rejected)} of {len(bodies)} values: {'; '.join(rejected)}"
            raise OxylabsError(msg)

    async def _run_realtime(
        self,
        bodies: list[dict[str, Any]],
        send: MemoryObjectSendStream[Job | Exception],
        output_types: Sequence[OutputType],
    ) -> None:
        async def one(body: dict[str, Any]) -> None:
            await send.send(await self._realtime(body, output_types))

        async with anyio.create_task_group() as tg:
            for start in range(0, len(bodies), JOBS_PER_SECOND):
                if start:
                    await anyio.sleep(1)
                for body in bodies[start : start + JOBS_PER_SECOND]:
                    tg.start_soon(one, body)

    async def _submit(
        self, key: str, shared: dict[str, Any], values: list[str]
    ) -> tuple[list[str], list[str]]:
        source = shared["source"]
        if source not in self._no_batch:
            body = (
                await self._send("POST", f"{DATA}/batch", json={**shared, key: values})
            ).json()
            errors = [error["message"] for error in body.get("errors", [])]
            if (
                body["queries"]
                or not errors
                or "not available with a batch request" not in errors[0]
            ):
                return [job["id"] for job in body["queries"]], errors
            # 97 of 123 sources take no batch (docs/research/live-parameters.md), so their values go one per request.
            self._no_batch.add(source)
        ids = [
            (await self._send("POST", DATA, json={**shared, key: value})).json()["id"]
            for value in values
        ]
        return ids, []

    async def _poll(
        self, job_ids: list[str], output_types: Sequence[OutputType]
    ) -> list[Job]:
        finished: list[Job] = []

        async def check(job_id: str) -> None:
            if job := await self._results(job_id, output_types):
                finished.append(job)

        async with anyio.create_task_group() as tg:
            for job_id in job_ids:
                tg.start_soon(check, job_id)
        return finished

    async def _results(
        self, job_id: str, output_types: Sequence[OutputType]
    ) -> Job | None:
        response = await self._send(
            "GET", f"{DATA}/{job_id}/results", output_types=output_types
        )
        # A 204 means the job is pending, so one request both polls and fetches.
        if response.status_code == 204:
            return None
        body = response.json()
        return _job(body["job"], body["results"])

    async def _realtime(
        self, body: dict[str, Any], output_types: Sequence[OutputType]
    ) -> Job:
        body = (
            await self._send("POST", REALTIME, json=body, output_types=output_types)
        ).json()
        return _job(body["job"], body["results"])

    async def _send(
        self,
        method: str,
        url: str,
        *,
        json: dict[str, Any] | None = None,
        output_types: Sequence[OutputType] = (),
    ) -> httpx2.Response:
        params = {"type": ",".join(output_types)} if output_types else None
        async with self._requests:
            response = await self._http.request(method, url, json=json, params=params)
        if response.is_error:
            message = response.json().get("message", "") if response.content else ""
            raise OxylabsError(message, response.status_code)
        return response


class Session:
    """Run `AsyncSession` from sync code, through an anyio blocking portal that lives as long as the `with` block.

    A portal left open blocks interpreter exit, so the session only opens inside `with`.
    """

    def __init__(
        self,
        *,
        username: str,
        password: str,
        transport: httpx2.AsyncBaseTransport | None = None,
    ) -> None:
        self._session = AsyncSession(
            username=username, password=password, transport=transport
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
        """Start the jobs now, and return them each as it finishes."""
        if self._portal is None:
            msg = "open the session with `with oxy.Session(...) as session`"
            raise RuntimeError(msg)
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
        """Return a job by ID, with its results once it has finished."""
        return self._portal.call(
            partial(self._session.get, job_id, output_types=output_types)
        )

    def _pull(self, run: AsyncRun) -> Iterator[Job]:
        while True:
            try:
                yield self._portal.call(anext, run)
            except StopAsyncIteration:
                return


def _listed(payloads: Payload | Iterable[Payload]) -> list[Payload]:
    return [payloads] if isinstance(payloads, Payload) else list(payloads)


def _batches(
    bodies: list[dict[str, Any]],
) -> list[tuple[str, dict[str, Any], list[str]]]:
    """Group jobs that share every parameter but the input, and split each group to fit the rate limit."""
    groups: dict[str, tuple[str, dict[str, Any], list[str]]] = {}
    for body in bodies:
        key = next(key for key in INPUT_KEYS if key in body)
        shared = {name: value for name, value in body.items() if name != key}
        groups.setdefault(json.dumps(shared, sort_keys=True), (key, shared, []))[
            2
        ].append(body[key])
    # Each page counts against the limit, as each batch value does.
    return [
        (key, shared, values[start : start + size])
        for key, shared, values in groups.values()
        for size in [max(1, JOBS_PER_SECOND // shared.get("pages", 1))]
        for start in range(0, len(values), size)
    ]


def _cost(batch: tuple[str, dict[str, Any], list[str]]) -> int:
    return len(batch[2]) * batch[1].get("pages", 1)


def _job(data: dict[str, Any], results: list[dict[str, Any]]) -> Job:
    parsed = [_result(result) for result in results]
    # A Realtime job object keeps `updated_at` equal to `created_at`, so the finish time comes from its results.
    finished = max(
        [_time(data["updated_at"]), *(result.updated_at for result in parsed)]
    )
    return Job(
        id=data["id"],
        status=data["status"],
        source=data["source"],
        input=next((data[key] for key in INPUT_KEYS if data.get(key)), ""),
        created_at=_time(data["created_at"]),
        finished_at=None if data["status"] == "pending" else finished,
        results=parsed,
        data=data,
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
        created_at=_time(data["created_at"]),
        updated_at=_time(data["updated_at"]),
        data=data,
    )


def _time(value: str) -> datetime:
    # The API writes UTC with no offset.
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
