"""PROTOTYPE, throwaway: a stand-in for oxyscraper's Python API as the map has decided it, over a simulated Oxylabs.

`cli.py` imports it in place of `oxyscraper`, so nothing bills.
The simulated API keeps its jobs in a temp folder, so a rerun of a command can resume.
"""

# ruff: noqa: C901, D101, D102, D103, D105, EM101, EM102, FBT001, INP001, PLR0912, PLR0915, PLR2004, PLW2901, S105, TRY003
# pyrefly: ignore-errors

from __future__ import annotations

import json
import shutil
import tempfile
import time
import zlib
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, ClassVar, Literal, Self, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator

if TYPE_CHECKING:
    import os
    from collections.abc import Iterable, Iterator

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
INPUT_KEYS = get_args(InputKey)
# PROTOTYPE: wipe me. The simulated API and the simulated buckets live here.
STATE = Path(tempfile.gettempdir()) / "oxy-cli-prototype"
# The real limit is 10 minutes, and a job with SLOW in its input takes 5 seconds.
PENDING_LIMIT = 3.0
KNOWN_SOURCES = {
    "amazon",
    "amazon_bestsellers",
    "amazon_pricing",
    "amazon_product",
    "amazon_search",
    "amazon_sellers",
    "google_search",
    "universal",
    "walmart_product",
}
AmazonDomain = Literal[
    "ca", "co.jp", "co.uk", "com", "de", "es", "fr", "it", "nl", "pl"
]


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
    payload: Payload = field(repr=False)
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
        counts = [len(rejections), len(unsubmitted), len(unfetched), len(unuploaded)]
        super().__init__(
            "{} rejected, {} unsubmitted, {} unfetched and {} unuploaded".format(
                *counts
            )
        )


@dataclass
class Progress:
    """The counts a `Run` keeps while it runs. [What does oxy report while a run is in progress?] decides the real shape."""

    payloads: int = 0
    matched: int = 0
    skipped: int = 0
    resubmitted: int = 0
    pending: int = 0
    done: int = 0
    faulted: int = 0
    written: int = 0
    uploaded: int = 0
    started: float = field(default_factory=time.monotonic)


class Run:
    def __init__(self, jobs: Iterator[Job], progress: Progress) -> None:
        self._jobs = jobs
        self.progress = progress

    def __iter__(self) -> Iterator[Job]:
        return self._jobs

    def all(self) -> list[Job]:
        return list(self._jobs)


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


class Session:
    def __init__(self, *, username: str, password: str) -> None:
        if not username or not password:
            raise ValueError("username and password must not be empty")
        self._password = password
        self._api: _Api | None = None

    def __enter__(self) -> Self:
        self._api = _Api()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._api = None

    def get(self, job_id: str) -> Job:
        self._authorize()
        if job_id not in self._api.jobs:
            raise OxylabsError("Query not found.", 404)
        return self._api.job(job_id)

    def execute(
        self,
        payloads: Payload | Iterable[Payload],
        *,
        realtime: bool = False,
        destination: str | os.PathLike[str] | None = None,
        checkpoint: str | os.PathLike[str] | None = None,
        check_storage: bool = True,
    ) -> Run:
        payloads = _listed(payloads)
        storage = any(payload.storage_type for payload in payloads)
        if storage and destination is not None:
            raise ValueError(
                "destination= cannot take a payload that sets storage_type, because Cloud Storage uploads it"
            )
        if realtime and checkpoint is not None:
            raise ValueError(
                "checkpoint= needs Push-Pull, because Realtime jobs have no status to fetch"
            )
        if realtime and storage:
            raise ValueError("storage_type needs Push-Pull")
        folder = _local(destination) if destination is not None else None
        if folder is not None:
            # The setup check lists the destination before the first submission.
            folder.mkdir(parents=True, exist_ok=True)
        progress = Progress(payloads=len(payloads))
        jobs = self._run(
            payloads,
            folder,
            _local(checkpoint) if checkpoint is not None else None,
            check_storage,
            progress,
        )
        return Run(jobs, progress)

    def _run(
        self,
        payloads: list[Payload],
        folder: Path | None,
        checkpoint: Path | None,
        check_storage: bool,
        progress: Progress,
    ) -> Iterator[Job]:
        api = self._api
        recorded: defaultdict[str, list[str]] = defaultdict(list)
        for path in (
            sorted(checkpoint.glob("*.jsonl"))
            if checkpoint and checkpoint.exists()
            else []
        ):
            for line in path.read_text().splitlines():
                entry = json.loads(line)
                recorded[_canonical(entry["payload"])].append(entry["id"])
        todo: list[Payload] = []
        pending: dict[str, tuple[Payload, float]] = {}
        for payload in payloads:
            ids = recorded[_canonical(payload.to_api())]
            if not ids:
                todo.append(payload)
                continue
            job_id = ids.pop(0)
            progress.matched += 1
            code = api.upload(job_id)[0] if payload.storage_type else None
            if (folder and (folder / f"{job_id}.json").exists()) or code == 13000:
                progress.skipped += 1
            elif api.status(job_id) == "faulted" or code is not None:
                progress.resubmitted += 1
                todo.append(payload)
            else:
                pending[job_id] = (payload, time.monotonic())
        progress.pending = len(pending)

        rejections: list[Rejection] = []
        unsubmitted: list[Payload] = []
        unfetched: list[Job] = []
        unuploaded: list[Job] = []
        failed_urls: set[str] = set()
        stop: OxylabsError | None = None

        firsts: dict[str, Payload] = {}
        if check_storage:
            for payload in todo:
                if payload.storage_url and payload.storage_url not in firsts:
                    firsts[payload.storage_url] = payload
        first_ids = {id(payload) for payload in firsts.values()}
        phases = [
            list(firsts.values()),
            [payload for payload in todo if id(payload) not in first_ids],
        ]

        for number, phase in enumerate(phases):
            if number:
                unsubmitted += [
                    payload for payload in phase if payload.storage_url in failed_urls
                ]
                phase = [
                    payload
                    for payload in phase
                    if payload.storage_url not in failed_urls
                ]
            for start in range(0, len(phase), 50):
                chunk = phase[start : start + 50]
                if stop is None and self._password == "wrong":
                    stop = OxylabsError("", 401)
                if stop is not None:
                    unsubmitted += chunk
                    continue
                accepted = []
                for payload in chunk:
                    body = payload.to_api()
                    if body["source"] not in KNOWN_SOURCES:
                        rejections.append(
                            Rejection(
                                payload=payload,
                                status_code=400,
                                message="Unsupported source.",
                            )
                        )
                    else:
                        accepted.append((api.submit(body), payload))
                if accepted and checkpoint is not None:
                    checkpoint.mkdir(parents=True, exist_ok=True)
                    lines = [
                        json.dumps({"id": job_id, "payload": payload.to_api()}) + "\n"
                        for job_id, payload in accepted
                    ]
                    (checkpoint / f"{accepted[0][0]}.jsonl").write_text("".join(lines))
                for job_id, payload in accepted:
                    pending[job_id] = (payload, time.monotonic())
                progress.pending = len(pending)

            while pending:
                time.sleep(0.05)
                for job_id, (payload, since) in list(pending.items()):
                    status = api.status(job_id)
                    if status == "pending":
                        if time.monotonic() - since > PENDING_LIMIT:
                            unfetched.append(api.job(job_id))
                            del pending[job_id]
                        continue
                    del pending[job_id]
                    job = api.job(job_id)
                    if job.upload is not None:
                        if job.upload.code == 13000:
                            progress.uploaded += 1
                        else:
                            unuploaded.append(job)
                            failed_urls.add(payload.storage_url)
                    elif status == "done" and folder is not None:
                        body = {
                            "results": [result.data for result in job.results],
                            "job": job.data,
                        }
                        (folder / f"{job_id}.json").write_text(
                            json.dumps(body, separators=(",", ":")) + "\n"
                        )
                        progress.written += 1
                    progress.done += status == "done"
                    progress.faulted += status == "faulted"
                    progress.pending = len(pending)
                    yield job
                progress.pending = len(pending)

        if stop is not None or rejections or unsubmitted or unfetched or unuploaded:
            error = IncompleteRunError(
                rejections=rejections,
                unsubmitted=unsubmitted,
                unfetched=unfetched,
                unuploaded=unuploaded,
            )
            raise error from stop
        if checkpoint is not None:
            shutil.rmtree(checkpoint, ignore_errors=True)

    def _authorize(self) -> None:
        if self._password == "wrong":
            raise OxylabsError("", 401)


class _Api:
    """The simulated Oxylabs: a job's status follows from the time since the API accepted it."""

    def __init__(self) -> None:
        self.path = STATE / "api.json"
        self.jobs: dict[str, dict[str, Any]] = (
            json.loads(self.path.read_text()) if self.path.exists() else {}
        )

    def submit(self, body: dict[str, Any]) -> str:
        value = _input(body)
        seconds = (
            5.0
            if "SLOW" in value.upper()
            else 0.3 + zlib.crc32(value.encode()) % 12 / 10
        )
        job_id = str(
            7_500_000_000_000_000_000
            + time.time_ns() // 1000 * 100
            + len(self.jobs) % 100
        )
        self.jobs[job_id] = {
            "body": body,
            "created": time.time(),
            "seconds": seconds,
            "faulted": "FAULT" in value.upper(),
        }
        STATE.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.jobs))
        return job_id

    def status(self, job_id: str) -> Literal["pending", "done", "faulted"]:
        job = self.jobs[job_id]
        if time.time() < job["created"] + job["seconds"]:
            return "pending"
        return "faulted" if job["faulted"] else "done"

    def upload(self, job_id: str) -> tuple[int | None, str | None]:
        if self.status(job_id) == "pending":
            return None, None
        if "wrong" in self.jobs[job_id]["body"]["storage_url"]:
            return 13001, "Upload Failed"
        return 13000, "Upload Succeeded"

    def job(self, job_id: str) -> Job:
        record = self.jobs[job_id]
        body, status = record["body"], self.status(job_id)
        created = _stamp(record["created"])
        finished = _stamp(record["created"] + record["seconds"])
        data = {
            **body,
            "id": job_id,
            "status": status,
            "created_at": created,
            "updated_at": created if status == "pending" else finished,
        }
        value = _input(body)
        results: list[Result] = []
        upload = None
        if body.get("storage_type"):
            code, message = self.upload(job_id)
            data["statuses"] = (
                []
                if code is None
                else [{"event": "GCS_STORAGE_UPLOAD", "code": code, "message": message}]
            )
            upload = Upload(
                storage_url=f"{body['storage_url']}/{job_id}.json",
                code=code,
                message=message,
            )
        elif status != "pending":
            for page in range(1, body.get("pages", 1) + 1):
                if status == "faulted":
                    kind, code, content = "raw", 613, ""
                elif body.get("parse"):
                    kind, code, content = (
                        "parsed",
                        200,
                        {"title": f"Result for {value}", "page": page, "price": 19.99},
                    )
                else:
                    kind, code, content = (
                        "raw",
                        200,
                        f"<html><title>{value}</title></html>",
                    )
                result = {
                    "content": content,
                    "created_at": created,
                    "updated_at": finished,
                    "page": page,
                    "job_id": job_id,
                    "status_code": code,
                    "type": kind,
                }
                results.append(
                    Result(
                        page=page,
                        type=kind,
                        status_code=code,
                        content=content,
                        data=result,
                    )
                )
        return Job(
            id=job_id,
            status=status,
            source=body["source"],
            input=value,
            payload=Payload.model_validate(body),
            results=results,
            data=data,
            upload=upload,
        )


def _listed(payloads: Payload | Iterable[Payload]) -> list[Payload]:
    return [payloads] if isinstance(payloads, Payload) else list(payloads)


def _canonical(body: dict[str, Any]) -> str:
    return json.dumps(body, sort_keys=True)


def _input(body: dict[str, Any]) -> str:
    return next(str(body[key]) for key in INPUT_KEYS if key in body)


def _local(location: str | os.PathLike[str]) -> Path:
    """Map a URL to a folder under `STATE`, because the prototype writes to local disk only."""
    text = str(location)
    if "://" in text:
        scheme, _, rest = text.partition("://")
        return STATE / "buckets" / scheme / rest
    return Path(text)


def _stamp(seconds: float) -> str:
    return datetime.fromtimestamp(seconds, UTC).strftime("%Y-%m-%d %H:%M:%S")
