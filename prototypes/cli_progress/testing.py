"""PROTOTYPE, throwaway: `oxyscraper.testing` as a test would call it, to react to.

It answers [Prototype: the fake Oxylabs API](https://github.com/ozanozbeker/oxyscraper/issues/48), `tour.py` runs it through the stand-in in `oxy_standin.py`, and `shapes.md` compares it with the shapes it declined.
It imports nothing from the stand-in, so it can move to `src/oxyscraper/testing.py` on its own.
"""

# ruff: noqa: ANN401, B008, D102, D105, INP001, PLR0911, PLR2004
# pyrefly: ignore-errors

from __future__ import annotations

import base64
import contextlib
import ipaddress
import itertools
import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Literal, Self

import anyio
import httpx2

if TYPE_CHECKING:
    from collections.abc import Callable

OutputType = Literal["raw", "parsed", "png", "markdown", "xhr"]
Content = str | bytes | dict[str, Any] | list[Any]
Endpoint = Literal["submit", "status", "results"]

REALTIME_HOST = "realtime.oxylabs.io"
CLIENT_ID = 123456
LIMIT_UUID = "00000000-0000-0000-0000-000000000000"
# Job times count from here, so the same requests return the same bytes on every run.
EPOCH = datetime(2026, 1, 1, tzinfo=UTC)
REALTIME_TTL = 150.0
REALTIME_TIMEOUT = 160.0
INPUT_KEYS = (
    "query",
    "url",
    "product_id",
    "prompt",
    "video_id",
    "channel_handle",
    "category_id",
)
BATCH_KEYS = ("query", "url", "prompt")
LLM_SOURCES = frozenset({"chatgpt", "gemini", "perplexity"})
# The 26 sources that took a batch on 2026-09-28 (docs/research/live-parameters.md).
BATCH_SOURCES = LLM_SOURCES | {
    "amazon",
    "amazon_bestsellers",
    "amazon_pricing",
    "amazon_product",
    "amazon_search",
    "amazon_sellers",
    "bing",
    "bing_search",
    "google",
    "google_ads",
    "google_ai_mode",
    "google_lens",
    "google_maps",
    "google_scholar",
    "google_search",
    "google_shopping_product",
    "google_shopping_search",
    "google_travel_hotels",
    "google_trends_explore",
    "universal",
    "youtube_download",
    "youtube_metadata",
    "youtube_subtitles",
}
# PROTOTYPE: the real fake lists all 123 documented sources.
SOURCES = BATCH_SOURCES | {
    "ebay_search",
    "target_product",
    "walmart_product",
    "walmart_search",
    "youtube_search",
}
LIMIT_MESSAGES = {
    "total-requests": "Too many requests. (Total Dynamic).",
    "total-render-requests": "Too many requests. (Total Render Dynamic).",
}
# 13001 and 13103 never appeared live, so their messages come from the Response Codes page.
UPLOAD_MESSAGES = {
    10001: "Unexpected Exception",
    13000: "Upload Successful",
    13001: "Upload Failed",
    13102: "No such path",
    13103: "Access Denied",
}
FIRST_FIVE = {
    "force_headers": False,
    "force_cookies": False,
    "hc_policy": True,
    "parse_json_schema": None,
    "parse_json_prompt": None,
}
CONTEXT = {
    "universal": FIRST_FIVE
    | {
        "successful_status_codes": [],
        "follow_redirects": None,
        "cookies": [],
        "headers": [],
        "session_id": None,
        "http_method": "get",
        "content": None,
        "store_id": None,
        "proxy_location": None,
        "delivery_location": None,
        "fulfillment_type": None,
    },
    "amazon_product": FIRST_FIVE
    | {
        "autoselect_variant": False,
        "check_empty_geo": None,
        "safe_search": True,
        "currency": None,
    },
}
# A 1x1 PNG, so an image library opens the default `png` content.
PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
SERVER_ERROR = """<!DOCTYPE html>
<html lang="en">
   <head>
       <meta charset="utf-8" />
       <title>{code} Internal server error</title>
   </head>
   <body>
       <main>
           <h1>{code} Ooops something went wrong :( </h1>
           <p>Something went very very wrong with your request</p>
           <p>When reporting this error, please include the following</p>
           <p>+</p>
           <p>trace_id: {trace_id}</p>
       </main>
   </body>
</html>
"""


@dataclass(frozen=True, kw_only=True)
class Outcome:
    """What Oxylabs does with one job.

    Attributes
    ----------
    status
        The job's final status.
    after
        Seconds from the submission to the final status. `math.inf` keeps the job pending.
    content
        The content of each result, or a function of the page and the output type.
        `None` makes the fake write content from the job's input.
    status_code
        The target's status code in each result of a done job. A faulted job's result holds 613.
    upload
        The code of the Cloud Storage entry in `statuses`, for a job with `storage_type`.
        `None` means that no entry appears.
    upload_after
        Seconds from the final status to the entry.
    expires_after
        Seconds from the final status until the results endpoint returns 204 again.
    """

    status: Literal["done", "faulted"] = "done"
    after: float = 0.0
    content: Content | Callable[[int, OutputType], Content] | None = None
    status_code: int = 200
    upload: int | None = 13000
    upload_after: float = 0.0
    expires_after: float = math.inf


@dataclass(frozen=True)
class Rejected:
    """The error that Oxylabs returns for a payload instead of a job.

    A batch lists `message` under `errors`, and any other submission returns `status_code`.
    """

    message: str
    status_code: int = 400


@dataclass
class _Failure:
    error: int | Exception
    on: Endpoint | None
    times: int | None
    message: str | None


@dataclass
class _Record:
    id: str
    payload: dict[str, Any]
    outcome: Outcome
    created: float
    realtime: bool
    storage_url: str | None

    @property
    def finished(self) -> float:
        return self.created + self.outcome.after


# The fakes that `with` blocks have switched on, innermost last.
_switched_on: list[FakeOxylabs] = []


def switched_on() -> FakeOxylabs | None:
    """Return the fake that a session with no `transport=` uses, if a `with` block set one."""
    return _switched_on[-1] if _switched_on else None


class FakeOxylabs(httpx2.AsyncBaseTransport):
    """A transport that answers like the Web Scraper API, and keeps its jobs between sessions.

    Pass it as `transport=`, or open it as a `with` block, which points every session built inside at it.

    Parameters
    ----------
    outcome
        What Oxylabs does with each job, or a function that receives one job's payload as the API received it.
        The default finishes every job at once.
    limit
        Jobs per second, which the rate-limit headers report.
    render_limit
        Rendered jobs per second.

    Attributes
    ----------
    requests
        Every request the fake received, in order.
    jobs
        The job object of each job the fake created, in order, as the submission returned it.
    """

    def __init__(
        self,
        outcome: Outcome | Callable[[dict[str, Any]], Outcome | Rejected] = Outcome(),
        *,
        limit: int = 50,
        render_limit: int = 13,
    ) -> None:
        self.requests: list[httpx2.Request] = []
        self.jobs: list[dict[str, Any]] = []
        self._outcome = outcome
        self._limits = {"total-requests": limit, "total-render-requests": render_limit}
        self._used = dict.fromkeys(self._limits, 0)
        self._window = -math.inf
        self._records: dict[str, _Record] = {}
        self._failures: list[_Failure] = []
        self._ids = itertools.count(7_500_000_000_000_000_001)
        self._traces = itertools.count(1)
        self._zero: float | None = None
        # `tour.py` prints both. They are not part of the calling shape.
        self._last = 0.0
        self._log: list[str] = []

    def fail(
        self,
        error: int | Exception,
        *,
        on: Endpoint | None = None,
        times: int | None = 1,
        message: str | None = None,
    ) -> None:
        """Answer the next requests with an HTTP status, or raise a network error for them.

        A failed request creates no job and counts against no limit.

        Parameters
        ----------
        error
            An HTTP status such as 429 or 503, or an exception such as `httpx2.ConnectError("refused")`.
        on
            The requests that fail: submissions, status checks or results downloads. `None` fails any request.
        times
            How many requests fail. `None` fails every one from now on.
        message
            The `message` of the error body, such as the domain throttle's.
        """
        self._failures.append(_Failure(error, on, times, message))

    def __enter__(self) -> Self:
        _switched_on.append(self)
        return self

    def __exit__(self, *exc_info: object) -> None:
        _switched_on.remove(self)

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        await request.aread()
        self.requests.append(request)
        self._last = now = self._now()
        target = request.url.host.split(".")[0] + request.url.path
        if types := request.url.params.get("type"):
            target += f"?type={types}"
        line = f"{now:7.2f} s  {request.method:<4} {target}"
        try:
            response = await self._respond(request)
        except httpx2.TransportError as error:
            self._log.append(f"{line}  {type(error).__name__}")
            raise
        self._last = self._now()
        self._log.append(
            f"{line}  {response.status_code}{self._note(request, response, now)}"
        )
        return response

    async def _respond(self, request: httpx2.Request) -> httpx2.Response:
        match = re.fullmatch(r"/v1/queries/([^/]+?)(/results)?", request.url.path)
        submission = request.method == "POST" and request.url.path in {
            "/v1/queries",
            "/v1/queries/batch",
        }
        endpoint: Endpoint | None = (
            "submit"
            if submission
            else None
            if match is None or match[1] == "batch"
            else "results"
            if match[2]
            else "status"
        )
        if failure := self._next_failure(endpoint):
            if isinstance(failure.error, Exception):
                raise failure.error
            headers = (
                self._limit_headers(rendered=False) if failure.error == 429 else {}
            )
            return self._error(request, failure.error, failure.message, headers=headers)
        if "authorization" not in request.headers:
            return self._error(request, 401, "Authorization header not provided.")
        if submission:
            try:
                body = json.loads(request.content)
            except json.JSONDecodeError:
                return self._error(request, 400, "Json error: Unexpected value.")
            if request.url.host == REALTIME_HOST:
                return await self._realtime(request, body)
            if request.url.path.endswith("/batch"):
                return self._batch(request, body)
            return self._submit(request, body)
        if endpoint is None or request.method != "GET" or match is None:
            return httpx2.Response(404, json={"message": "Resource not found"})
        return self._get(request, match[1], results=endpoint == "results")

    def _submit(self, request: httpx2.Request, body: dict[str, Any]) -> httpx2.Response:
        decision = self._decide(body)
        if isinstance(decision, Rejected):
            return self._error(request, decision.status_code, decision.message)
        rendered = _rendered(body)
        if name := self._take(body.get("pages", 1), rendered=rendered):
            return self._error(
                request,
                429,
                LIMIT_MESSAGES[name],
                headers=self._limit_headers(rendered=rendered),
            )
        record = self._create(body, decision, realtime=False)
        headers = self._headers(request, record) | self._limit_headers(
            rendered=rendered
        )
        return httpx2.Response(202, json=self._object(record), headers=headers)

    def _batch(self, request: httpx2.Request, body: dict[str, Any]) -> httpx2.Response:
        source = body.get("source")
        lists = [key for key in INPUT_KEYS if isinstance(body.get(key), list)]
        values = body[lists[0]] if lists else []
        headers = self._headers(request)
        if source not in SOURCES:
            errors = [{"message": "Unsupported source."} for _ in values]
            return httpx2.Response(
                202, json={"queries": [], "errors": errors}, headers=headers
            )
        if len(lists) != 1 or lists[0] not in BATCH_KEYS:
            message = "Batch request must contain one array of `query` or `url`."
            return self._error(request, 400, message, headers=headers)
        key = lists[0]
        if source not in BATCH_SOURCES:
            message = f"Source `{source}` is not available with a batch request."
            errors = [{"message": message} for _ in values]
            return httpx2.Response(
                202, json={"queries": [], "errors": errors}, headers=headers
            )
        accepted: list[tuple[dict[str, Any], Outcome]] = []
        errors = []
        for value in values:
            payload = {**body, key: value}
            decision = self._decide(payload)
            if isinstance(decision, Outcome):
                accepted.append((payload, decision))
            # The API repeats an invalid `url`, but not an empty value.
            elif key == "url" and value:
                errors.append({"message": decision.message, "url": value})
            else:
                errors.append({"message": decision.message})
        rendered = _rendered(body)
        if name := self._take(len(accepted) * body.get("pages", 1), rendered=rendered):
            limits = self._limit_headers(rendered=rendered)
            return self._error(
                request, 429, LIMIT_MESSAGES[name], headers=headers | limits
            )
        records = [
            self._create(payload, outcome, realtime=False)
            for payload, outcome in accepted
        ]
        answer: dict[str, Any] = {
            "queries": [self._object(record) for record in records]
        }
        if errors:
            answer["errors"] = errors
        if records:
            headers |= self._limit_headers(rendered=rendered)
        return httpx2.Response(202, json=answer, headers=headers)

    async def _realtime(
        self, request: httpx2.Request, body: dict[str, Any]
    ) -> httpx2.Response:
        if body.get("source") in LLM_SOURCES:
            message = "Realtime integration is not supported for LLM sources. Please use Push-Pull."
            return self._error(request, 422, message)
        if "storage_url" in body or "storage_type" in body:
            message = "Parameter `storage_url` cannot be used with realtime."
            return self._error(request, 400, message)
        decision = self._decide(body)
        if isinstance(decision, Rejected):
            return self._error(request, decision.status_code, decision.message)
        rendered = _rendered(body)
        if name := self._take(body.get("pages", 1), rendered=rendered):
            return self._error(
                request,
                429,
                LIMIT_MESSAGES[name],
                headers=self._limit_headers(rendered=rendered),
            )
        # A Realtime response carries the limits of its submission, not of its return.
        limits = self._limit_headers(rendered=rendered)
        record = self._create(body, decision, realtime=True)
        if decision.after >= REALTIME_TTL:
            await anyio.sleep(REALTIME_TIMEOUT)
            return httpx2.Response(408, json={"message": "Timed out."})
        await anyio.sleep(decision.after)
        answer = {
            "job": self._object(record),
            "results": self._results(record, request.url.params.get("type")),
        }
        return httpx2.Response(
            200, json=answer, headers=self._headers(request, record) | limits
        )

    def _get(
        self, request: httpx2.Request, job_id: str, *, results: bool
    ) -> httpx2.Response:
        if not job_id.isdigit():
            return httpx2.Response(404, json={"message": "Resource not found"})
        record = self._records.get(job_id)
        # The status and results endpoints return 404 for a Realtime job's ID.
        if record is None or record.realtime:
            return self._error(
                request, 404, "Query not found.", headers=self._headers(request)
            )
        if not results:
            return httpx2.Response(
                200, json=self._object(record), headers=self._headers(request, record)
            )
        headers = self._headers(request, record, status=True)
        expired = self._now() >= record.finished + record.outcome.expires_after
        if self._status(record) == "pending" or expired:
            return httpx2.Response(204, headers=headers)
        answer = {
            "results": self._results(record, request.url.params.get("type")),
            "job": self._object(record),
        }
        return httpx2.Response(200, json=answer, headers=headers)

    def _decide(self, payload: dict[str, Any]) -> Outcome | Rejected:
        """Apply the API's own free checks, then ask the test."""
        if payload.get("source") not in SOURCES:
            return Rejected("Unsupported source.")
        keys = [key for key in INPUT_KEYS if payload.get(key)]
        if not keys:
            url = payload["source"] == "universal" or "url" in payload
            return Rejected(
                "Parameter `url` is empty." if url else "Query parameter is empty."
            )
        if message := _url_error(payload.get("url")):
            return Rejected(message)
        return self._outcome(payload) if callable(self._outcome) else self._outcome

    def _next_failure(self, endpoint: Endpoint | None) -> _Failure | None:
        for failure in self._failures:
            if failure.on in {None, endpoint}:
                if failure.times is not None:
                    failure.times -= 1
                    if failure.times == 0:
                        self._failures.remove(failure)
                return failure
        return None

    def _take(self, cost: int, *, rendered: bool) -> str | None:
        """Count a submission against each limit, or name the limit it does not fit."""
        now = self._now()
        closed = now - self._window >= 1
        if closed:
            self._used = dict.fromkeys(self._limits, 0)
        names = [name for name in self._limits if rendered or name == "total-requests"]
        for name in names:
            if self._used[name] + cost > self._limits[name]:
                return name
        # A window opens at the first submission after the last window closed.
        if closed:
            self._window = now
        for name in names:
            self._used[name] += cost
        return None

    def _create(
        self, payload: dict[str, Any], outcome: Outcome, *, realtime: bool
    ) -> _Record:
        job_id = str(next(self._ids))
        storage_url = None
        if payload.get("storage_url"):
            storage_url = _resolve(payload["storage_url"], job_id, payload)
        record = _Record(job_id, payload, outcome, self._now(), realtime, storage_url)
        self._records[job_id] = record
        self.jobs.append(self._object(record) | {"status": "pending"})
        return record

    def _status(self, record: _Record) -> Literal["pending", "done", "faulted"]:
        return "pending" if self._now() < record.finished else record.outcome.status

    def _object(self, record: _Record) -> dict[str, Any]:
        payload, status = record.payload, self._status(record)
        host = httpx2.URL(payload["url"]).host if payload.get("url") else ""
        sent = {item["key"]: item["value"] for item in payload.get("context", [])}
        defaults = CONTEXT.get(payload["source"], FIRST_FIVE)
        # A Realtime job object keeps `updated_at` equal to `created_at`.
        moved = status != "pending" and not record.realtime
        job: dict[str, Any] = {
            "callback_url": None,
            "client_id": CLIENT_ID,
            "context": [
                {"key": key, "value": value} for key, value in (defaults | sent).items()
            ],
            "created_at": self._stamp(record.created),
            "domain": host.rsplit(".", 1)[-1] if host else "com",
            "geo_location": None,
            "id": record.id,
            "limit": 10,
            "locale": None,
            "pages": 1,
            "parse": False,
            "parser_type": None,
            "parser_preset": None,
            "parsing_instructions": None,
            "browser_instructions": None,
            "render": None,
            "xhr": False,
            "markdown": False,
            "url": None,
            "query": "",
            "source": payload["source"],
            "start_page": 1,
            "status": status,
            "storage_type": None,
            "storage_url": None,
            "aggregate_name": None,
            "subdomain": host.split(".")[0] if host.count(".") > 1 else "www",
            "content_encoding": "utf-8",
            "updated_at": self._stamp(record.finished if moved else record.created),
            "user_agent_type": "desktop",
            "session_info": None,
            "statuses": [],
            "client_notes": None,
        }
        # The API leaves an unknown key out of the job object.
        job |= {
            key: value
            for key, value in payload.items()
            if key in job and key != "context"
        }
        job |= {key: payload[key] for key in INPUT_KEYS if key in payload}
        if record.storage_url:
            job["storage_url"] = record.storage_url
            uploaded = record.finished + record.outcome.upload_after
            if record.outcome.upload is not None and self._now() >= uploaded:
                code = record.outcome.upload
                message = UPLOAD_MESSAGES.get(code, "")
                job["statuses"] = [
                    {"event": "GCS_STORAGE_UPLOAD", "code": code, "message": message}
                ]
        if not record.realtime:
            base = f"http://data.oxylabs.io/v1/queries/{record.id}"
            first = job["start_page"]
            pages = [
                f"{base}/results/{page}/content"
                for page in range(first, first + job["pages"])
            ]
            job["_links"] = [
                {"rel": "self", "href": base, "method": "GET"},
                {"rel": "results", "href": f"{base}/results", "method": "GET"},
                {"rel": "results-content", "href_list": pages, "method": "GET"},
            ]
        return job

    def _results(self, record: _Record, types: str | None) -> list[dict[str, Any]]:
        payload, outcome = record.payload, record.outcome
        first = payload.get("start_page", 1)
        if outcome.status == "faulted":
            return [self._entry(record, first, "raw", 613, "")]
        kinds = types.split(",") if types else [_default_type(payload)]
        return [
            self._entry(
                record, page, kind, outcome.status_code, _content(record, page, kind)
            )
            for page in range(first, first + payload.get("pages", 1))
            for kind in kinds
        ]

    def _entry(
        self, record: _Record, page: int, kind: str, status_code: int, content: Any
    ) -> dict[str, Any]:
        entry = {
            "content": content,
            "created_at": self._stamp(record.created),
            "updated_at": self._stamp(record.finished),
            "page": page,
            "url": record.payload.get("url")
            or f"https://www.example.com/{_input(record.payload)}?page={page}",
            "job_id": record.id,
            "is_render_forced": False,
            "status_code": status_code,
            "type": kind,
        }
        if kind == "parsed":
            entry |= {"parser_type": "", "parser_preset": None}
        if record.payload["source"] == "universal":
            sent = None if status_code == 613 else []
            headers = None if status_code == 613 else {"User-Agent": "Mozilla/5.0"}
            entry |= {
                "_request": {"cookies": sent, "headers": headers},
                "_response": {"cookies": sent, "headers": headers},
                "session_info": {"expires_at": None, "id": None, "remaining": None},
            }
        return entry

    def _headers(
        self,
        request: httpx2.Request,
        record: _Record | None = None,
        *,
        status: bool = False,
    ) -> dict[str, str]:
        headers = {"x-oxylabs-client-id": str(CLIENT_ID)}
        realtime = request.url.host == REALTIME_HOST
        if not realtime:
            encoded = request.headers["authorization"].split()[-1]
            with contextlib.suppress(ValueError):
                headers["x-oxylabs-client-name"] = (
                    base64.b64decode(encoded).decode().split(":")[0]
                )
        if record:
            headers["x-oxylabs-job-id"] = record.id
        if record and status:
            headers["x-oxylabs-job-status"] = self._status(record)
        if realtime:
            return headers | {"x-oxylabs-trace-id": self._trace_id()}
        # On the data host, each `x-oxylabs-*` header has an `x-oxyserps-*` twin.
        return headers | {
            name.replace("x-oxylabs", "x-oxyserps"): value
            for name, value in headers.items()
        }

    def _limit_headers(self, *, rendered: bool) -> dict[str, str]:
        used = (
            self._used
            if self._now() - self._window < 1
            else dict.fromkeys(self._limits, 0)
        )
        headers = {}
        for name, limit in self._limits.items():
            if rendered or name == "total-requests":
                prefix = f"x-ratelimit-{name}-{LIMIT_UUID}"
                headers[f"{prefix}-limit"] = str(limit)
                headers[f"{prefix}-remaining"] = str(limit - used[name])
        return headers

    def _error(
        self,
        request: httpx2.Request,
        status_code: int,
        message: str | None = None,
        *,
        headers: dict[str, str] | None = None,
    ) -> httpx2.Response:
        # PROTOTYPE: only a 500 was recorded, as an HTML page, so every 5xx returns that page.
        if status_code >= 500:
            page = SERVER_ERROR.format(code=status_code, trace_id=self._trace_id())
            return httpx2.Response(status_code, html=page)
        # A 401 for an unknown username has an empty body.
        if status_code == 401 and message is None:
            return httpx2.Response(401)
        body = {
            "message": message
            or LIMIT_MESSAGES["total-requests"] * (status_code == 429),
            "instance": request.url.path,
            "timestamp": f"{EPOCH + timedelta(seconds=self._now()):%Y-%m-%dT%H:%M:%S.%f}000Z",
            "trace_id": self._trace_id(),
        }
        return httpx2.Response(status_code, json=body, headers=headers)

    def _note(
        self, request: httpx2.Request, response: httpx2.Response, sent: float
    ) -> str:
        notes = []
        json_body = response.headers.get("content-type") == "application/json"
        answer = response.json() if json_body and response.content else {}
        if request.url.path.endswith("/batch"):
            body = json.loads(request.content)
            values = next(
                (body[key] for key in INPUT_KEYS if isinstance(body.get(key), list)), []
            )
            notes.append(f"{len(values)} values")
            notes += [
                f"error: {error['message']}" for error in answer.get("errors", [])[:1]
            ]
        if status := response.headers.get("x-oxylabs-job-status"):
            notes.append(status)
        elif request.method == "GET" and response.status_code == 200:
            notes.append(answer["status"])
        notes += [f"upload {entry['code']}" for entry in answer.get("statuses", [])]
        for name, limit in self._limits.items():
            prefix = f"x-ratelimit-{name}-{LIMIT_UUID}"
            if remaining := response.headers.get(f"{prefix}-remaining"):
                short = "rendered" if "render" in name else "total"
                notes.append(f"{short} {remaining}/{limit} left")
        if response.status_code >= 400 and "message" in answer:
            notes.append(answer["message"])
        if (waited := self._last - sent) >= 1:
            notes.append(f"answered after {waited:g} s")
        return "  " + ", ".join(notes) if notes else ""

    def _now(self) -> float:
        """Return the seconds since the fake's first request, on the clock of the running backend."""
        now = anyio.current_time()
        if self._zero is None:
            self._zero = now
        return now - self._zero

    def _stamp(self, seconds: float) -> str:
        return f"{EPOCH + timedelta(seconds=seconds):%Y-%m-%d %H:%M:%S}"

    def _trace_id(self) -> str:
        return f"{next(self._traces):08x}-{'0' * 24}"


def _rendered(payload: dict[str, Any]) -> bool:
    return bool(payload.get("render")) or payload.get("xhr") is True


def _input(payload: dict[str, Any]) -> str:
    return next(str(payload[key]) for key in INPUT_KEYS if key in payload)


def _default_type(payload: dict[str, Any]) -> OutputType:
    if payload.get("parse"):
        return "parsed"
    if payload.get("markdown"):
        return "markdown"
    if payload.get("xhr"):
        return "xhr"
    return "png" if payload.get("render") == "png" else "raw"


def _content(record: _Record, page: int, kind: str) -> Any:
    content = record.outcome.content
    if callable(content):
        content = content(page, kind)
    if content is None:
        value = _input(record.payload)
        content = {
            "raw": f"<!doctype html><html><title>{value}</title><p>Page {page}</p></html>",
            "parsed": {"title": value, "page": page, "parse_status_code": 12000},
            "markdown": f"# {value}\n\nPage {page}.",
            "png": PNG,
            "xhr": [],
        }[kind]
    # The API sends `png` content as Base64 text.
    return base64.b64encode(content).decode() if isinstance(content, bytes) else content


def _url_error(url: Any) -> str | None:
    if url is None:
        return None
    try:
        parsed = httpx2.URL(url)
    except (httpx2.InvalidURL, TypeError):
        return "Parameter `url` is invalid."
    if parsed.scheme not in {"http", "https"} or not parsed.host:
        return "Parameter `url` is invalid."
    with contextlib.suppress(ValueError):
        ipaddress.ip_address(parsed.host)
        return "The hostname cannot be an ip address."
    if parsed.host.rsplit(".", 1)[-1] in {"invalid", "test", "example"}:
        return "Parameter `url` has invalid top level domain format."
    return None


def _resolve(storage_url: str, job_id: str, payload: dict[str, Any]) -> str:
    """Resolve a `storage_url` as the API does at submission."""
    name = storage_url
    # Any `storage_url` that does not end in `.{{ extension }}` names a folder.
    if not name.endswith(".{{ extension }}"):
        name = name.rstrip("/") + "/{{ job_id }}.{{ extension }}"
    variables = {
        "job_id": job_id,
        "source": payload["source"],
        "query": payload.get("query", ""),
        "extension": "json",
    }
    for variable, value in variables.items():
        name = name.replace("{{ " + variable + " }}", value)
    return re.sub(r"://[^/@:]+:[^/@]+@", "://redacted:redacted@", name)
