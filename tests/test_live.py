"""The weekly live suite, which compares the Oxylabs API with `FakeOxylabs` and the models.

Each test sends its requests to Oxylabs and to a fake, so a change in the API fails here before it fails a caller's job.
A run bills about 11 results, so only `pytest -m live` selects it, and `OXY_CAPTURES` names a folder that keeps every exchange.
"""

import json
import os
import re
import uuid
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import anyio
import httpx2
import pytest

import oxyscraper as oxy
from oxyscraper.testing import FakeOxylabs, Outcome

pytestmark = pytest.mark.live

SANDBOX = "https://sandbox.oxylabs.io/products"
DATA = "https://data.oxylabs.io/v1/queries/batch"
# `_sessions` matches this text to send the source's payloads one per request.
NOT_BATCHED = "Source `walmart_product` is not available with a batch request."
UUID = re.compile(r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}")
DIGITS = re.compile(r"\d+")
# The fake's jobs finish after the first check, so both sides return a 204 and then a 200.
AFTER = 1.5


@dataclass(frozen=True)
class Exchange:
    live: bool
    request: httpx2.Request
    response: httpx2.Response


@dataclass(frozen=True)
class Account:
    """The suite's credentials and bucket, which no repr shows, because a failed test prints its arguments."""

    username: str = field(repr=False)
    password: str = field(repr=False)
    bucket: str = field(repr=False)


# The jobs hold the bucket's name, so no repr shows them either.
@dataclass(frozen=True, repr=False)
class Side:
    """The jobs, by source and input, the rejections and the exchanges of one side's runs."""

    jobs: dict[str, oxy.Job]
    rejections: list[tuple[int, str]]
    exchanges: list[Exchange]


@pytest.fixture(autouse=True)
def fake() -> None:
    """Switch off the suite's fake, so a session without `transport=` reaches Oxylabs."""


@pytest.fixture(scope="module")
def account() -> Account:
    names = ["OXY_WSA_USERNAME", "OXY_WSA_PASSWORD", "OXYLAKE_URI"]
    if missing := [name for name in names if not os.environ.get(name)]:
        pytest.fail(f"the live suite needs {', '.join(missing)}")
    return Account(*(os.environ[name] for name in names))


@pytest.fixture(scope="module", autouse=True)
def exchanges() -> Iterator[list[Exchange]]:
    """Record each response of Oxylabs and of every fake, and append it to `OXY_CAPTURES`."""
    recorded: list[Exchange] = []
    folder = os.environ.get("OXY_CAPTURES")
    captures = Path(folder).expanduser() / "exchanges.jsonl" if folder else None
    if captures:
        captures.parent.mkdir(parents=True, exist_ok=True)

    def record(transport: type[httpx2.AsyncBaseTransport]) -> Callable[..., Any]:
        send = transport.handle_async_request

        async def handle(
            self: httpx2.AsyncBaseTransport, request: httpx2.Request
        ) -> httpx2.Response:
            response = await send(self, request)
            await response.aread()
            live = not isinstance(self, FakeOxylabs)
            recorded.append(Exchange(live, request, response))
            if captures:
                line = {
                    "time": datetime.now(UTC).isoformat(),
                    "live": live,
                    "method": request.method,
                    "url": str(request.url),
                    "body": request.content.decode() or None,
                    "status": response.status_code,
                    "http_version": response.http_version,
                    "headers": dict(response.headers),
                    "response": response.text,
                }
                with captures.open("a") as file:
                    file.write(json.dumps(line) + "\n")
            return response

        return handle

    with pytest.MonkeyPatch.context() as monkeypatch:
        for transport in [httpx2.AsyncHTTPTransport, FakeOxylabs]:
            monkeypatch.setattr(transport, "handle_async_request", record(transport))
        yield recorded


@pytest.fixture(scope="module")
def runs(account: Account, exchanges: list[Exchange]) -> tuple[Side, Side]:
    """Run the billed payloads on Oxylabs, then on a fake whose jobs end as Oxylabs' did."""
    pushed: list[oxy.Payload] = [
        oxy.Universal(url=f"{SANDBOX}/1"),
        oxy.Universal(url=f"{SANDBOX}/2"),
        oxy.Universal(
            url=f"{SANDBOX}/3",
            storage_type="gcs",
            storage_url=f"{account.bucket}/oxyscraper-live",
        ),
        oxy.Universal(url=f"{SANDBOX}/4", follow_redirects=True),
        oxy.Universal(url=unregistered(), render="html"),
        oxy.Amazon(
            url="https://www.amazon.com/gp/help/customer/display.html?nodeId=508510"
        ),
        oxy.AmazonBestsellers(query="172541", parse=True),
        oxy.AmazonPricing(query="1492056359", parse=True),
        oxy.AmazonProduct(query="1492056359", parse=True),
        oxy.AmazonSearch(query="usb c cable", parse=True),
        oxy.AmazonSellers(query="A2OL0VKAHK1LYK", parse=True),
    ]
    realtime: list[oxy.Payload] = [
        oxy.Universal(url=f"{SANDBOX}/5"),
        oxy.Universal(url=unregistered()),
        oxy.Universal(url="https://10.0.0.1/"),
    ]

    def run(transport: FakeOxylabs | None = None) -> Side:
        start = len(exchanges)
        with oxy.Session(
            username=account.username,
            password=account.password,
            transport=transport,
        ) as session:
            # Both runs start before either collects, so they run at once.
            started = [
                session.execute(pushed),
                session.execute(realtime, realtime=True),
            ]
            jobs: list[oxy.Job] = []
            rejections: list[oxy.Rejection] = []
            for each in started:
                try:
                    jobs += each.all()
                except oxy.IncompleteRunError as error:
                    if error.unsubmitted or error.unfetched or error.unuploaded:
                        raise
                    jobs += error.jobs
                    rejections += error.rejections
        return Side(
            jobs={f"{job.source} {job.input}": job for job in jobs},
            rejections=sorted((each.status_code, each.message) for each in rejections),
            exchanges=exchanges[start:],
        )

    live = run()

    def mirror(payload: dict[str, Any]) -> Outcome:
        value = next(str(payload[key]) for key in ["query", "url"] if payload.get(key))
        job = live.jobs.get(f"{payload['source']} {value}")
        if job is None:
            return Outcome(after=AFTER)
        return Outcome(
            status="faulted" if job.status == "faulted" else "done",
            after=AFTER,
            upload=job.upload.code if job.upload else 13000,
        )

    return live, run(FakeOxylabs(mirror))


def unregistered() -> str:
    """Return a URL on an unregistered `.com` name, whose job faults and bills nothing."""
    return f"https://oxyscraper-{uuid.uuid4().hex[:16]}.com/"


def shape(data: Mapping[str, Any]) -> dict[str, str]:
    """Return the JSON type of each key, and of each `context` item as `context:<key>`."""
    found = {key: type(value).__name__ for key, value in data.items()}
    for item in data.get("context") or []:
        found[f"context:{item['key']}"] = type(item["value"]).__name__
    return found


def headers(response: httpx2.Response) -> dict[str, str]:
    """Return the shape of the headers that the API sets, with each name's UUID and numbers replaced.

    oxy cannot budget from a `-remaining` count without its `-limit`, so those names stay out.
    Any other `x-ratelimit-*` name fails the comparison until oxy reads it, as [Does oxy pace by the rate-limit headers that carry only a remaining count?](https://github.com/ozanozbeker/oxyscraper/issues/132) decides.
    """

    def kept(name: str) -> bool:
        if name.startswith("x-ratelimit-") and name.endswith("-remaining"):
            return f"{name.removesuffix('-remaining')}-limit" in response.headers
        return name.startswith("x-") or name == "content-type"

    return shape(
        {
            DIGITS.sub("<n>", UUID.sub("<uuid>", name)): value
            for name, value in response.headers.items()
            if kept(name)
        }
    )


def mismatches(
    live: Mapping[str, dict[str, str]], fake: Mapping[str, dict[str, str]]
) -> dict[str, dict[str, tuple[str | None, str | None]]]:
    """Return each key whose type differs between the sides, as `(live, fake)`."""
    found = {}
    for name in live.keys() | fake.keys():
        left, right = live.get(name, {}), fake.get(name, {})
        if differ := {
            key: (left.get(key), right.get(key))
            for key in left.keys() | right.keys()
            if left.get(key) != right.get(key)
        }:
            found[name] = differ
    return found


def send(
    account: Account, body: dict[str, Any]
) -> tuple[httpx2.Response, httpx2.Response]:
    """Send one batch to Oxylabs and to a fake."""

    async def post(transport: FakeOxylabs | None) -> httpx2.Response:
        auth = (account.username, account.password)
        async with httpx2.AsyncClient(
            auth=auth, transport=transport, http2=True
        ) as client:
            return await client.post(DATA, json=body)

    return anyio.run(post, None), anyio.run(post, FakeOxylabs())


def test_responses_come_over_http2(runs: tuple[Side, Side]) -> None:
    live, _ = runs
    versions = {
        (each.request.url.host, each.response.http_version) for each in live.exchanges
    }
    assert versions == {
        ("data.oxylabs.io", "HTTP/2"),
        ("realtime.oxylabs.io", "HTTP/2"),
    }


def test_job_objects_match_the_fake(runs: tuple[Side, Side]) -> None:
    live, fake = runs
    assert (
        mismatches(
            {name: shape(job.data) for name, job in live.jobs.items()},
            {name: shape(job.data) for name, job in fake.jobs.items()},
        )
        == {}
    )


def test_results_match_the_fake(runs: tuple[Side, Side]) -> None:
    live, fake = runs

    def results(side: Side) -> dict[str, dict[str, str]]:
        return {
            f"{name} results[{index}]": shape(result.data)
            for name, job in side.jobs.items()
            for index, result in enumerate(job.results)
        }

    assert mismatches(results(live), results(fake)) == {}


def test_headers_match_the_fake(runs: tuple[Side, Side]) -> None:
    def kinds(side: Side) -> dict[str, dict[str, str]]:
        found: dict[str, dict[str, str]] = {}
        for each in side.exchanges:
            request, response = each.request, each.response
            # A retried 429 or 5xx depends on the moment, not on the API's shapes.
            if response.status_code == 429 or response.status_code >= 500:
                continue
            path = re.sub(r"\d+", "<id>", request.url.path)
            kind = f"{request.method} {request.url.host}{path} {response.status_code}"
            found.setdefault(kind, {}).update(headers(response))
        return found

    live, fake = runs
    assert mismatches(kinds(live), kinds(fake)) == {}


def test_rejections_match_the_fake(runs: tuple[Side, Side]) -> None:
    live, fake = runs
    assert [code for code, _ in live.rejections] == [400]
    assert fake.rejections == live.rejections


def test_models_type_context_keys_their_job_objects_list(
    runs: tuple[Side, Side],
) -> None:
    live, _ = runs
    models = [(type(job.payload), job) for job in live.jobs.values() if job.payload]
    assert {model for model, _ in models} >= set(oxy.SOURCES)
    untyped = {
        model.__name__: sorted(
            set(model._CONTEXT) - {item["key"] for item in job.data.get("context", [])}
        )
        for model, job in models
    }
    assert {name: keys for name, keys in untyped.items() if keys} == {}


def test_cloud_storage_records_the_upload(runs: tuple[Side, Side]) -> None:
    live, _ = runs
    uploads = [job.upload for job in live.jobs.values() if job.upload]
    assert [upload.code for upload in uploads] == [13000]


def test_a_rendered_batch_larger_than_the_limit_returns_429(account: Account) -> None:
    urls = [unregistered() for _ in range(14)]
    live, fake = send(account, {"source": "universal", "url": urls, "render": "html"})
    assert live.status_code == 429
    assert fake.status_code == live.status_code
    assert fake.json()["message"] == live.json()["message"]
    assert shape(fake.json()) == shape(live.json())
    assert headers(fake) == headers(live)


def test_a_source_without_batches_returns_the_text_oxy_matches(
    account: Account,
) -> None:
    live, fake = send(account, {"source": "walmart_product", "query": ["", ""]})
    assert live.status_code == 202
    assert live.json() == {"queries": [], "errors": [{"message": NOT_BATCHED}] * 2}
    assert fake.json() == live.json()
    assert headers(fake) == headers(live)


def test_prompt_works_as_a_batch_key(account: Account) -> None:
    live, fake = send(account, {"source": "chatgpt", "prompt": ["", ""]})
    assert live.status_code == 202
    assert fake.status_code == live.status_code
    assert fake.json() == live.json()
    assert headers(fake) == headers(live)
