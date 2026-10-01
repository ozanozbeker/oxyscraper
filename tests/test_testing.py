import base64
import math
import re
from pathlib import Path
from typing import Any

import anyio
import httpx2
import pytest

from oxyscraper import testing
from oxyscraper.testing import FakeOxylabs, Outcome, Rejected

pytestmark = pytest.mark.anyio

DATA = "https://data.oxylabs.io/v1/queries"
REALTIME = "https://realtime.oxylabs.io/v1/queries"
SANDBOX = "https://sandbox.oxylabs.io"
LIMIT = "x-ratelimit-total-requests-00000000-0000-0000-0000-000000000000"
RENDER_LIMIT = "x-ratelimit-total-render-requests-00000000-0000-0000-0000-000000000000"
THROTTLE = (
    "Access to www.amazon.com has been limited to 1 req/s due to a low success rate."
)
# The keys of the recorded `universal` job object, in the API's order (docs/research/live-api.md).
JOB_KEYS = [
    "callback_url",
    "client_id",
    "context",
    "created_at",
    "domain",
    "geo_location",
    "id",
    "limit",
    "locale",
    "pages",
    "parse",
    "parser_type",
    "parser_preset",
    "parsing_instructions",
    "browser_instructions",
    "render",
    "xhr",
    "markdown",
    "url",
    "query",
    "source",
    "start_page",
    "status",
    "storage_type",
    "storage_url",
    "aggregate_name",
    "subdomain",
    "content_encoding",
    "updated_at",
    "user_agent_type",
    "session_info",
    "statuses",
    "client_notes",
    "_links",
]
# Tests that wait run on trio's mock clock only, so their waits take no real time.
on_mock_clock = pytest.mark.parametrize("anyio_backend", ["trio"], indirect=True)


def client(fake: FakeOxylabs) -> httpx2.AsyncClient:
    return httpx2.AsyncClient(transport=fake, auth=("USERNAME", "PASSWORD"))


def universal(path: str = "", **parameters: Any) -> dict[str, Any]:
    return {"source": "universal", "url": f"{SANDBOX}/{path}", **parameters}


async def test_submission(fake: FakeOxylabs) -> None:
    """A submission returns the pending job object with its headers."""
    async with client(fake) as http:
        response = await http.post(DATA, json=universal())
    job = response.json()
    assert response.status_code == 202
    assert list(job) == JOB_KEYS
    assert job == fake.jobs[0]
    assert job["id"] == "7500000000000000001"
    assert job["status"] == "pending"
    assert job["created_at"] == job["updated_at"] == "2026-01-01 00:00:00"
    assert (job["domain"], job["subdomain"]) == ("io", "sandbox")
    assert [link["rel"] for link in job["_links"]] == [
        "self",
        "results",
        "results-content",
        "results-html",
        "results-content-html",
    ]
    assert response.headers["x-oxylabs-job-id"] == job["id"]
    assert response.headers["x-oxyserps-client-name"] == "USERNAME"
    assert response.headers[f"{LIMIT}-remaining"] == "49"
    assert f"{RENDER_LIMIT}-limit" not in response.headers
    assert fake.requests[0].url == DATA


async def test_job_object_keeps_known_keys(fake: FakeOxylabs) -> None:
    """The job object takes the payload's known keys and drops unknown ones."""
    payload = universal(
        render="html",
        status="done",
        foo_bar="x",
        context=[
            {"key": "http_method", "value": "post"},
            {"key": "foo_bar", "value": 1},
        ],
    )
    async with client(fake) as http:
        job = (await http.post(DATA, json=payload)).json()
    context = {item["key"]: item["value"] for item in job["context"]}
    assert (job["render"], job["status"]) == ("html", "pending")
    assert "foo_bar" not in job
    assert context["http_method"] == "post"
    assert "foo_bar" not in context


async def test_every_source(fake: FakeOxylabs) -> None:
    """The fake takes each of the 123 documented sources, and returns its own job object."""
    catalog = Path(__file__).parents[1] / "docs/research/parameter-catalog.md"
    keys = "|".join(testing._INPUT_KEYS)
    rows = re.findall(
        rf"^\| (?:[^|`]+\| )?`(\w+)` \| `({keys})` \|",
        catalog.read_text(),
        re.MULTILINE,
    )
    sources = dict(rows)

    formats = {
        "target_category": "12345",
        "target_product": "12345678",
        "tiktok_shop_product": "1" * 19,
    }

    def payload(source: str, key: str) -> dict[str, str]:
        value = f"{SANDBOX}/" if key == "url" else formats.get(source, "x")
        domain = {"domain": "com"} if source in testing._REQUIRED_DOMAIN else {}
        return {"source": source, key: value} | domain

    fake = FakeOxylabs(limit=len(sources))
    async with client(fake) as http:
        jobs = [
            (await http.post(DATA, json=payload(source, key))).json()
            for source, key in sources.items()
        ]
    assert len(sources) == 123
    assert [job["source"] for job in jobs] == list(sources)
    assert sorted(len(job) for job in jobs) == [7] * 97 + [8] * 3 + [34] * 23


async def test_short_job_object(fake: FakeOxylabs) -> None:
    """Most sources return the payload, sorted by key, and the job's own fields."""
    payload = {
        "source": "walmart_product",
        "product_id": "11601059297",
        "parse": True,
        "user_agent_type": "mobile",
        "domain": "com",
    }
    async with client(fake) as http:
        job = (await http.post(DATA, json=payload)).json()
    assert job == {key: payload[key] for key in sorted(payload)} | {
        "id": "7500000000000000001",
        "status": "pending",
        "created_at": "2026-01-01 00:00:00",
        "updated_at": "2026-01-01 00:00:00",
        "_links": job["_links"],
    }


@pytest.mark.parametrize(
    ("payload", "key", "value"),
    [
        (
            {"source": "google_trends_explore", "query": "x"},
            "search_type",
            "web_search",
        ),
        ({"source": "google_maps", "query": "x"}, "hotel_occupancy", 2),
        (
            {"source": "youtube_metadata", "query": "x", "parse": True},
            "successful_parse_status_codes",
            [],
        ),
    ],
)
async def test_context_defaults(
    fake: FakeOxylabs, payload: dict[str, Any], key: str, value: object
) -> None:
    """A full job object lists its source's `context` keys, and `parse: true` adds one."""
    async with client(fake) as http:
        job = (await http.post(DATA, json=payload)).json()
    context = {item["key"]: item["value"] for item in job["context"]}
    assert context[key] == value


async def test_batch(fake: FakeOxylabs) -> None:
    """A batch returns one job object per value and counts each value."""
    urls = [f"{SANDBOX}/products", f"{SANDBOX}/products?page=2"]
    async with client(fake) as http:
        response = await http.post(f"{DATA}/batch", json=universal() | {"url": urls})
    answer = response.json()
    assert response.status_code == 202
    assert [job["url"] for job in answer["queries"]] == urls
    assert answer["queries"] == fake.jobs
    assert "errors" not in answer
    assert "x-oxylabs-job-id" not in response.headers
    assert response.headers[f"{LIMIT}-remaining"] == "48"


@on_mock_clock
async def test_status_and_results(fake: FakeOxylabs) -> None:
    """A job stays pending until `after`, then the results endpoint returns it."""
    fake = FakeOxylabs(Outcome(after=2))
    async with client(fake) as http:
        job_id = (await http.post(DATA, json=universal())).json()["id"]
        status = await http.get(f"{DATA}/{job_id}")
        pending = await http.get(f"{DATA}/{job_id}/results")
        await anyio.sleep(2)
        done = await http.get(f"{DATA}/{job_id}/results")
    assert status.json()["status"] == "pending"
    assert "x-oxylabs-job-status" not in status.headers
    assert pending.status_code == 204
    assert pending.headers["x-oxylabs-job-status"] == "pending"
    assert done.headers["x-oxyserps-job-status"] == "done"
    [result] = done.json()["results"]
    assert done.json()["job"]["updated_at"] == "2026-01-01 00:00:02"
    assert result["status_code"] == 200
    assert result["type"] == "raw"
    assert result["updated_at"] == "2026-01-01 00:00:02"
    assert result["_request"]["cookies"] == []


@on_mock_clock
async def test_faulted_job(fake: FakeOxylabs) -> None:
    """A faulted job's one result holds 613 and no content."""
    fake = FakeOxylabs(Outcome(status="faulted", after=17))
    async with client(fake) as http:
        job_id = (await http.post(DATA, json=universal(pages=2))).json()["id"]
        await anyio.sleep(17)
        answer = (await http.get(f"{DATA}/{job_id}/results?type=parsed")).json()
    [result] = answer["results"]
    assert answer["job"]["status"] == "faulted"
    assert (result["status_code"], result["content"], result["type"]) == (
        613,
        "",
        "raw",
    )
    assert result["_request"] == {"cookies": None, "headers": None}


async def test_content(fake: FakeOxylabs) -> None:
    """A done job returns one result per page and output type, with the test's content."""

    def content(page: int, kind: str) -> dict[str, int] | bytes:
        return {"page": page} if kind == "parsed" else f"page {page}".encode()

    fake = FakeOxylabs(Outcome(content=content, status_code=404))
    payload = {
        "source": "amazon_search",
        "query": "usb c cable",
        "pages": 2,
        "start_page": 5,
        "parse": True,
    }
    async with client(fake) as http:
        job_id = (await http.post(DATA, json=payload)).json()["id"]
        answer = (await http.get(f"{DATA}/{job_id}/results?type=raw,parsed")).json()
    results = [(r["page"], r["type"], r["content"]) for r in answer["results"]]
    assert results == [
        (5, "raw", base64.b64encode(b"page 5").decode()),
        (5, "parsed", {"page": 5}),
        (6, "raw", base64.b64encode(b"page 6").decode()),
        (6, "parsed", {"page": 6}),
    ]
    assert {r["status_code"] for r in answer["results"]} == {404}
    assert answer["results"][0]["url"] == "https://www.example.com/usb c cable?page=5"
    assert answer["results"][1]["parser_type"] == ""
    assert "_request" not in answer["results"][0]
    assert answer["job"]["_links"][2]["href_list"][-1].endswith("/results/6/content")


@pytest.mark.parametrize(
    ("payload", "carried"),
    [
        ({"source": "walmart_product", "product_id": "1"}, True),
        ({"source": "youtube_video_trainability", "video_id": "x"}, True),
        ({"source": "youtube_search", "query": "x"}, False),
        ({"source": "chatgpt", "prompt": "x"}, False),
    ],
)
async def test_target_request(
    fake: FakeOxylabs, payload: dict[str, Any], carried: bool
) -> None:
    """A result carries the target's request and response on most sources that take no batch."""
    async with client(fake) as http:
        job_id = (await http.post(DATA, json=payload)).json()["id"]
        [result] = (await http.get(f"{DATA}/{job_id}/results")).json()["results"]
    assert ("_request" in result) is carried


@pytest.mark.parametrize(
    ("parameters", "kind", "content"),
    [
        ({}, "raw", "<!doctype html><html><title>B0</title><p>Page 1</p></html>"),
        (
            {"parse": True},
            "parsed",
            {"title": "B0", "page": 1, "parse_status_code": 12000},
        ),
        ({"markdown": True}, "markdown", "# B0\n\nPage 1."),
        ({"render": "html", "xhr": True}, "xhr", []),
        ({"render": "png"}, "png", testing._PNG),
    ],
)
async def test_default_content(
    fake: FakeOxylabs, parameters: dict[str, Any], kind: str, content: object
) -> None:
    """Without content, the fake writes the job's default output type from its input."""
    payload = {"source": "amazon_product", "query": "B0", **parameters}
    async with client(fake) as http:
        job_id = (await http.post(DATA, json=payload)).json()["id"]
        [result] = (await http.get(f"{DATA}/{job_id}/results")).json()["results"]
    assert (result["type"], result["content"]) == (kind, content)


@on_mock_clock
async def test_pending_and_expired_jobs(fake: FakeOxylabs) -> None:
    """`after=math.inf` keeps a job pending, and `expires_after` empties its results."""

    def outcome(payload: dict[str, Any]) -> Outcome:
        return Outcome(
            after=math.inf if "stuck" in payload["url"] else 0, expires_after=60
        )

    fake = FakeOxylabs(outcome)
    async with client(fake) as http:
        stuck = (await http.post(DATA, json=universal("stuck"))).json()["id"]
        done = (await http.post(DATA, json=universal("done"))).json()["id"]
        before = await http.get(f"{DATA}/{done}/results")
        await anyio.sleep(3600)
        after = await http.get(f"{DATA}/{done}/results")
        pending = await http.get(f"{DATA}/{stuck}/results")
    assert before.status_code == 200
    assert after.status_code == 204
    assert after.headers["x-oxylabs-job-status"] == "done"
    assert pending.headers["x-oxylabs-job-status"] == "pending"


@on_mock_clock
async def test_uploads(fake: FakeOxylabs) -> None:
    """A job with `storage_url` gets its `statuses` entry after `upload_after`."""

    def outcome(payload: dict[str, Any]) -> Outcome:
        match payload["url"].removeprefix(f"{SANDBOX}/"):
            case "late":
                return Outcome(after=2, upload=10001, upload_after=20)
            case "never":
                return Outcome(upload=None)
        return Outcome()

    fake = FakeOxylabs(outcome)
    storage = {"storage_type": "gcs", "storage_url": "bucket/run"}
    async with client(fake) as http:
        submitted = [
            (await http.post(DATA, json=universal(name, **storage))).json()
            for name in ("late", "never")
        ]
        s3 = universal(
            storage_type="s3_compatible",
            storage_url="https://key:secret@example.com/bucket/{{ source }}-{{ job_id }}.{{ extension }}",
        )
        resolved = (await http.post(DATA, json=s3)).json()["storage_url"]
        late, never = submitted[0]["id"], submitted[1]["id"]
        await anyio.sleep(10)
        early = (await http.get(f"{DATA}/{late}")).json()["statuses"]
        await anyio.sleep(12)
        entry = (await http.get(f"{DATA}/{late}")).json()["statuses"]
        missing = (await http.get(f"{DATA}/{never}")).json()["statuses"]
    assert [job["statuses"] for job in submitted] == [[], []]
    assert submitted[0]["storage_url"] == f"bucket/run/{late}.json"
    assert (
        resolved
        == "https://redacted:redacted@example.com/bucket/universal-7500000000000000003.json"
    )
    assert early == []
    assert entry == [
        {
            "event": "GCS_STORAGE_UPLOAD",
            "code": 10001,
            "message": "Unexpected Exception",
        }
    ]
    assert missing == []


async def test_outcome_function(fake: FakeOxylabs) -> None:
    """A function receives each batch value's payload, and a `Rejected` rejects it."""
    received: list[dict[str, Any]] = []

    def outcome(payload: dict[str, Any]) -> Outcome | Rejected:
        received.append(payload)
        if payload["url"].endswith("wrong"):
            return Rejected("Parameter `geo_location` is not valid.", status_code=422)
        return Outcome()

    fake = FakeOxylabs(outcome)
    urls = [f"{SANDBOX}/right", f"{SANDBOX}/wrong"]
    async with client(fake) as http:
        batch = (
            await http.post(f"{DATA}/batch", json=universal() | {"url": urls})
        ).json()
        single = await http.post(DATA, json=universal("wrong"))
    assert [payload["url"] for payload in received] == [*urls, f"{SANDBOX}/wrong"]
    assert [job["url"] for job in batch["queries"]] == urls[:1]
    assert batch["errors"] == [
        {"message": "Parameter `geo_location` is not valid.", "url": urls[1]}
    ]
    assert single.status_code == 422
    assert single.json()["message"] == "Parameter `geo_location` is not valid."


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"source": "unknown", "query": "x"}, "Unsupported source."),
        ({"source": "universal"}, "Parameter `url` is empty."),
        ({"source": "amazon_product", "query": ""}, "Query parameter is empty."),
        (universal(pages=0), "Parameter `pages` should be a positive integer."),
        (universal(pages=21), "Parameter `pages` should not exceed 20."),
        (
            {"source": "google_search", "query": "x", "pages": 11},
            "Parameter `pages` cannot exceed 10 for this source.",
        ),
        ({"source": "universal", "url": "not a url"}, "Parameter `url` is invalid."),
        ({"source": "universal", "url": "https://"}, "Parameter `url` is invalid."),
        ({"source": "universal", "url": ["x"]}, "Parameter `url` is invalid."),
        ({"source": "universal", "url": "https://[::1"}, "Parameter `url` is invalid."),
        (
            {"source": "universal", "url": "https://10.0.0.1/"},
            "The hostname cannot be an ip address.",
        ),
        (
            {"source": "universal", "url": "https://sandbox.oxylabs.test/"},
            "Parameter `url` has invalid top level domain format.",
        ),
    ],
)
async def test_free_checks(
    fake: FakeOxylabs, payload: dict[str, Any], message: str
) -> None:
    """A payload that the API rejects for free gets its 400, and no job."""
    async with client(fake) as http:
        response = await http.post(DATA, json=payload)
    assert response.status_code == 400
    assert response.json()["message"] == message
    assert response.headers["x-oxylabs-client-id"] == "123456"
    assert f"{LIMIT}-limit" not in response.headers
    assert fake.jobs == []


@pytest.mark.parametrize(
    ("payload", "errors"),
    [
        (
            {"source": "walmart_product"},
            ["[product_id]: This field is missing."],
        ),
        (
            {"source": "walmart_product", "query": "436012154"},
            [
                "[product_id]: This field is missing.",
                "[query]: This field was not expected.",
            ],
        ),
        (
            {"source": "grainger_search"},
            ["[domain]: This field is missing.", "[query]: This field is missing."],
        ),
        (
            {"source": "youtube_channel", "category_id": "x"},
            [
                "[category_id]: This field was not expected.",
                "[channel_handle]: This field is missing.",
            ],
        ),
        ({"source": "walmart", "url": ""}, ["[url]: This value should not be blank."]),
        (
            {"source": "walmart_search", "query": None},
            ["[query]: This value should not be blank."],
        ),
        (
            {"source": "target_product", "product_id": ""},
            [
                "[product_id]: Must be 8 or 10 digits.",
                "[product_id]: This value should not be blank.",
            ],
        ),
        (
            {"source": "target_product", "product_id": "1234567a"},
            ["[product_id]: Must be 8 or 10 digits."],
        ),
        (
            {"source": "tiktok_shop_product", "product_id": "123"},
            ["[product_id]: Must be 19 digits for product_id."],
        ),
        (
            {"source": "target_category", "category_id": "abcd"},
            ["[category_id]: Must be 5+ characters."],
        ),
        (
            {"source": "walmart_product", "product_id": "1", "foo_bar": "x"},
            ["[foo_bar]: This field was not expected."],
        ),
        (
            {"source": "walmart_product", "product_id": "", "pages": 25},
            [
                "[pages]: This field was not expected.",
                "[product_id]: This value should not be blank.",
            ],
        ),
    ],
)
@pytest.mark.parametrize("url", [DATA, REALTIME])
async def test_field_errors(
    fake: FakeOxylabs, url: str, payload: dict[str, Any], errors: list[str]
) -> None:
    """A source that takes no batch lists each failed field under `errors`, with no `message`."""
    async with client(fake) as http:
        response = await http.post(url, json=payload)
    answer = response.json()
    assert response.status_code == 400
    assert answer["errors"] == errors
    assert "message" not in answer
    assert fake.jobs == []


async def test_keys_a_source_takes(fake: FakeOxylabs) -> None:
    """A source takes the shared keys and its own, and checks only the form of a `url` before them."""
    async with client(fake) as http:
        youtube = await http.post(
            DATA, json={"source": "youtube_search", "query": "x", "render": "html"}
        )
        invalid = await http.post(
            DATA, json={"source": "walmart", "url": "not a url", "foo_bar": "x"}
        )
        ip_address = await http.post(
            DATA, json={"source": "walmart", "url": "https://10.0.0.1/"}
        )
    assert youtube.status_code == ip_address.status_code == 202
    assert invalid.json()["message"] == "Parameter `url` is invalid."


async def test_inputs_the_api_takes(fake: FakeOxylabs) -> None:
    """`walmart_search` takes no `query`, and an LLM source takes `query` but no other key."""
    async with client(fake) as http:
        browse = await http.post(DATA, json={"source": "walmart_search"})
        job_id = browse.json()["id"]
        [result] = (await http.get(f"{DATA}/{job_id}/results")).json()["results"]
        query = await http.post(DATA, json={"source": "chatgpt", "query": "x"})
        other = await http.post(DATA, json={"source": "chatgpt", "category_id": "x"})
        realtime = await http.post(REALTIME, json={"source": "chatgpt"})
    assert browse.status_code == query.status_code == 202
    assert result["url"] == "https://www.example.com/?page=1"
    assert other.json()["message"] == "Query parameter is empty."
    assert (realtime.status_code, realtime.json()["message"]) == (
        400,
        "Query parameter is empty.",
    )


async def test_batch_checks(fake: FakeOxylabs) -> None:
    """A batch lists the values the API rejects under `errors`."""
    async with client(fake) as http:
        unknown = await http.post(
            f"{DATA}/batch", json={"source": "x", "query": ["a", "b"]}
        )
        product_ids = await http.post(
            f"{DATA}/batch",
            json={"source": "walmart_product", "product_id": ["1", "2"]},
        )
        no_batch = await http.post(
            f"{DATA}/batch", json={"source": "walmart_product", "query": ["1", "2"]}
        )
        values = await http.post(
            f"{DATA}/batch", json={"source": "universal", "url": ["not a url", ""]}
        )
    unavailable = "Source `walmart_product` is not available with a batch request."
    assert unknown.json() == {
        "queries": [],
        "errors": [{"message": "Unsupported source."}] * 2,
    }
    assert product_ids.status_code == 400
    assert product_ids.json()["message"] == (
        "Batch request must contain one array of `query` or `url`."
    )
    assert no_batch.status_code == 202
    assert no_batch.json() == {"queries": [], "errors": [{"message": unavailable}] * 2}
    assert f"{LIMIT}-limit" not in no_batch.headers
    assert values.json()["errors"] == [
        {"message": "Parameter `url` is invalid.", "url": "not a url"},
        {"message": "Parameter `url` is empty."},
    ]
    assert fake.jobs == []


async def test_errors(fake: FakeOxylabs) -> None:
    """Malformed JSON, a missing header and an unknown job get the API's errors."""
    async with client(fake) as http:
        malformed = await http.post(DATA, content=b"{")
        missing = await http.get(f"{DATA}/7000000000000000001")
        not_numeric = await http.get(f"{DATA}/abc")
        content = await http.get(f"{DATA}/7500000000000000001/results/1/content")
    async with httpx2.AsyncClient(transport=fake) as anonymous:
        unauthorized = await anonymous.post(DATA, json=universal())
    assert malformed.json()["message"] == "Json error: Unexpected value."
    assert missing.status_code == 404
    assert missing.json()["message"] == "Query not found."
    assert missing.json()["instance"] == "/v1/queries/7000000000000000001"
    assert not_numeric.json() == content.json() == {"message": "Resource not found"}
    assert "x-oxylabs-client-id" not in not_numeric.headers
    assert unauthorized.status_code == 401
    assert unauthorized.json()["message"] == "Authorization header not provided."
    assert "x-oxylabs-client-id" not in unauthorized.headers


@on_mock_clock
async def test_rate_limit_window(fake: FakeOxylabs) -> None:
    """A submission that does not fit its window returns 429, which takes nothing."""
    fake = FakeOxylabs(limit=5)
    urls = [f"{SANDBOX}/{n}" for n in range(5)]
    remaining: list[str] = []
    async with client(fake) as http:
        full = await http.post(f"{DATA}/batch", json=universal() | {"url": urls})
        over = await http.post(DATA, json=universal())
        for wait in (1, 0.6, 0.6, 0.6):
            await anyio.sleep(wait)
            response = await http.post(DATA, json=universal())
            remaining.append(response.headers[f"{LIMIT}-remaining"])
    assert full.headers[f"{LIMIT}-remaining"] == "0"
    assert over.status_code == 429
    assert over.json()["message"] == "Too many requests. (Total Dynamic)."
    assert over.headers[f"{LIMIT}-limit"] == "5"
    assert over.headers[f"{LIMIT}-remaining"] == "0"
    # Each window opens at the first submission after the last one closed.
    assert remaining == ["4", "3", "4", "3"]
    assert len(fake.jobs) == 9


@on_mock_clock
async def test_rendered_limit(fake: FakeOxylabs) -> None:
    """A payload with `render` or `xhr: true` also counts against the rendered limit."""
    fake = FakeOxylabs(render_limit=2)
    urls = [f"{SANDBOX}/{n}" for n in range(3)]
    async with client(fake) as http:
        rendered = await http.post(DATA, json=universal(render="html"))
        xhr = await http.post(DATA, json=universal(xhr=True))
        batch = await http.post(
            f"{DATA}/batch", json=universal(render="html") | {"url": urls}
        )
        await anyio.sleep(1)
        large = [
            await http.post(DATA, json=universal(render="html", pages=3))
            for _ in range(2)
        ]
    assert rendered.headers[f"{RENDER_LIMIT}-remaining"] == "1"
    assert xhr.headers[f"{RENDER_LIMIT}-remaining"] == "0"
    assert xhr.headers[f"{LIMIT}-remaining"] == "48"
    assert batch.status_code == 429
    assert batch.json()["message"] == "Too many requests. (Total Render Dynamic)."
    # A payload larger than a limit gets its 429 in every window, with the limits in full.
    assert [response.status_code for response in large] == [429, 429]
    assert large[1].headers[f"{RENDER_LIMIT}-remaining"] == "2"
    assert large[1].headers[f"{LIMIT}-remaining"] == "50"


@on_mock_clock
async def test_realtime(fake: FakeOxylabs) -> None:
    """Realtime returns the job object and its results in one response."""

    def outcome(payload: dict[str, Any]) -> Outcome:
        return (
            Outcome(status="faulted", after=24)
            if "fault" in payload["url"]
            else Outcome(after=3)
        )

    fake = FakeOxylabs(outcome)
    async with client(fake) as http:
        started = anyio.current_time()
        done = await http.post(REALTIME, json=universal("done"))
        took = anyio.current_time() - started
        faulted = await http.post(REALTIME, json=universal("fault"))
        job_id = done.json()["job"]["id"]
        lookup = await http.get(f"{DATA}/{job_id}/results")
    job, [result] = done.json()["job"], done.json()["results"]
    assert took == 3
    assert list(done.json()) == ["job", "results"]
    assert (job["status"], result["status_code"]) == ("done", 200)
    assert job["created_at"] == job["updated_at"] == "2026-01-01 00:00:00"
    assert result["updated_at"] == "2026-01-01 00:00:03"
    assert "_links" not in job
    assert fake.jobs == [job, faulted.json()["job"]]
    assert done.headers["x-oxylabs-job-id"] == job_id
    assert done.headers["x-oxylabs-trace-id"]
    assert done.headers[f"{LIMIT}-remaining"] == "49"
    assert "x-oxylabs-client-name" not in done.headers
    assert "x-oxyserps-client-id" not in done.headers
    assert faulted.status_code == 200
    assert faulted.json()["results"][0]["status_code"] == 613
    assert lookup.status_code == 404
    assert lookup.json()["message"] == "Query not found."


@on_mock_clock
async def test_realtime_timeout(fake: FakeOxylabs) -> None:
    """A Realtime job that runs 150 seconds or longer returns 408 after 160 seconds."""
    fake = FakeOxylabs(Outcome(after=150))
    async with client(fake) as http:
        started = anyio.current_time()
        response = await http.post(REALTIME, json=universal())
        took = anyio.current_time() - started
    assert (response.status_code, took) == (408, 160)
    assert response.json() == {"message": "Timed out."}
    assert "x-oxylabs-job-id" not in response.headers
    assert fake.jobs == []


@pytest.mark.parametrize(
    ("payload", "status_code", "message"),
    [
        (
            {"source": "perplexity", "prompt": "x"},
            422,
            "Realtime integration is not supported for LLM sources. Please use Push-Pull.",
        ),
        (
            universal(storage_type="gcs", storage_url="bucket/run"),
            400,
            "Parameter `storage_url` cannot be used with realtime.",
        ),
        ({"source": "unknown", "query": "x"}, 400, "Unsupported source."),
    ],
)
async def test_realtime_rejections(
    fake: FakeOxylabs, payload: dict[str, Any], status_code: int, message: str
) -> None:
    """Realtime rejects an LLM source, a `storage_url` and the free checks."""
    async with client(fake) as http:
        response = await http.post(REALTIME, json=payload)
    assert (response.status_code, response.json()["message"]) == (status_code, message)
    assert "x-oxylabs-client-id" not in response.headers


async def test_realtime_rate_limit(fake: FakeOxylabs) -> None:
    """A Realtime submission shares the limit with Push-Pull."""
    fake = FakeOxylabs(limit=1)
    async with client(fake) as http:
        accepted = await http.post(DATA, json=universal())
        response = await http.post(REALTIME, json=universal())
    assert accepted.status_code == 202
    assert response.status_code == 429
    assert response.headers[f"{LIMIT}-remaining"] == "0"


async def test_fail(fake: FakeOxylabs) -> None:
    """`fail()` fails the next matching requests, which create no job and take nothing."""
    fake.fail(429, on="submit", times=2)
    fake.fail(429, message=THROTTLE)
    fake.fail(503, on="results")
    fake.fail(403, on="status")
    async with client(fake) as http:
        submissions = [await http.post(DATA, json=universal()) for _ in range(4)]
        job_id = submissions[-1].json()["id"]
        results = await http.get(f"{DATA}/{job_id}/results")
        status = await http.get(f"{DATA}/{job_id}")
        accepted = await http.get(f"{DATA}/{job_id}")
    codes = [response.status_code for response in submissions]
    assert codes == [429, 429, 429, 202]
    assert submissions[0].json()["message"] == "Too many requests. (Total Dynamic)."
    assert submissions[0].headers[f"{LIMIT}-remaining"] == "50"
    assert submissions[2].json()["message"] == THROTTLE
    assert submissions[3].headers[f"{LIMIT}-remaining"] == "49"
    assert len(fake.jobs) == 1
    assert results.status_code == 503
    assert "trace_id: " in results.text
    assert results.headers["content-type"] == "text/html; charset=utf-8"
    assert (status.status_code, status.json()["message"]) == (403, "Forbidden")
    assert accepted.status_code == 200


async def test_fail_every_request(fake: FakeOxylabs) -> None:
    """`times=None` fails every matching request, and the fake raises a given exception."""
    fake.fail(401, times=None)
    async with client(fake) as http:
        responses = [await http.post(DATA, json=universal()) for _ in range(3)]
    assert {response.status_code for response in responses} == {401}
    assert {response.content for response in responses} == {b""}

    other = FakeOxylabs()
    other.fail(httpx2.ReadTimeout("no answer"), on="results")
    async with client(other) as http:
        job_id = (await http.post(DATA, json=universal())).json()["id"]
        with pytest.raises(httpx2.ReadTimeout, match="no answer"):
            await http.get(f"{DATA}/{job_id}/results")
        after = await http.get(f"{DATA}/{job_id}/results")
    assert after.status_code == 200


def test_fail_times() -> None:
    """`fail()` raises for `times` below 1."""
    with pytest.raises(ValueError, match="times must be at least 1"):
        FakeOxylabs().fail(429, times=0)


async def test_switch(fake: FakeOxylabs) -> None:
    """The innermost `with` block wins, and reaches another thread."""
    assert testing._switched_on() is fake
    with FakeOxylabs() as inner:
        assert await anyio.to_thread.run_sync(testing._switched_on) is inner
    assert testing._switched_on() is fake


async def test_jobs_outlive_a_client(fake: FakeOxylabs) -> None:
    """A second client fetches the jobs that a first one submitted."""
    async with client(fake) as first:
        job_id = (await first.post(DATA, json=universal())).json()["id"]
    async with client(fake) as second:
        response = await second.get(f"{DATA}/{job_id}/results")
    assert response.json()["job"]["id"] == job_id


@on_mock_clock
async def test_same_requests_same_bytes(fake: FakeOxylabs) -> None:
    """Two fakes that receive the same requests return the same bytes."""

    async def run(fake: FakeOxylabs) -> list[bytes]:
        async with client(fake) as http:
            submitted = await http.post(DATA, json=universal())
            await anyio.sleep(5)
            job_id = submitted.json()["id"]
            error = await http.post(DATA, json={"source": "unknown", "query": "x"})
            results = await http.get(f"{DATA}/{job_id}/results")
        return [submitted.content, error.content, results.content]

    assert await run(FakeOxylabs()) == await run(FakeOxylabs())
