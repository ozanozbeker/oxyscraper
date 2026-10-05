"""A fake of the Oxylabs Web Scraper API, for oxy's tests, the docs and callers' tests.

`FakeOxylabs` returns responses in the shapes that `docs/research/live-api.md` recorded, and its behaviour is public API under SemVer.
It imports nothing from the rest of oxy, because the sessions import it to find the fake that a `with` block switched on.
"""

from __future__ import annotations

import base64
import contextlib
import ipaddress
import itertools
import json
import math
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Literal, Self, get_args

import anyio
import httpx2
from typing_extensions import override

from oxyscraper._payloads import _CREDENTIALS, _integer

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["FakeOxylabs", "Outcome", "Rejected"]

_OutputType = Literal["raw", "parsed", "png", "markdown", "xhr"]
_Content = str | bytes | dict[str, Any] | list[Any]
_Endpoint = Literal["submit", "status", "results"]
_Status = Literal["pending", "done", "faulted"]
_Limit = Literal["total-requests", "total-render-requests"]

_OUTPUT_TYPES: tuple[_OutputType, ...] = get_args(_OutputType)
_REALTIME_HOST = "realtime.oxylabs.io"
_CLIENT_ID = "123456"
_CLIENT_NAME = "USERNAME"
_LIMIT_UUID = "00000000-0000-0000-0000-000000000000"
# Job times count from here, so the same requests return the same bytes on every run.
_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)
_REALTIME_TTL = 150.0
_REALTIME_TIMEOUT = 160.0
_FIRST_ID = 7_500_000_000_000_000_001
_INPUT_KEYS = (
    "query",
    "url",
    "product_id",
    "prompt",
    "video_id",
    "channel_handle",
    "category_id",
)
_BATCH_KEYS = ("query", "url", "prompt")
_URL_SOURCES = frozenset({"amazon", "bing", "google", "universal"})
_MAX_PAGES = 20
_PAGE_LIMITS = {"google_ads": 10, "google_search": 10}
# These sources fetch one page and read `pages: 1` (docs/research/live-api.md#a-job-larger-than-the-limit, live-amazon.md#top-level-parameters).
_ONE_PAGE = frozenset({"amazon", "amazon_product", "amazon_sellers", "universal"})
_LLM_SOURCES = frozenset({"chatgpt", "gemini", "perplexity"})
_LIMIT_MESSAGES: dict[_Limit, str] = {
    "total-requests": "Too many requests. (Total Dynamic).",
    "total-render-requests": "Too many requests. (Total Render Dynamic).",
}
# 13001 and 13103 never appeared live, so their messages come from the Response Codes page.
_UPLOAD_MESSAGES = {
    10001: "Unexpected Exception",
    13000: "Upload Successful",
    13001: "Upload Failed",
    13102: "No such path",
    13103: "Access Denied",
}
# The job object keys that the API sets, whatever the payload holds.
_SERVER_KEYS = frozenset(
    {
        "_links",
        "client_id",
        "context",
        "created_at",
        "id",
        "session_info",
        "status",
        "statuses",
        "storage_url",
        "updated_at",
    }
)
_FIRST_FIVE: dict[str, Any] = {
    "force_headers": False,
    "force_cookies": False,
    "hc_policy": True,
    "parse_json_schema": None,
    "parse_json_prompt": None,
}
# The sources with a full job object, and the `context` keys and defaults that each lists.
# Every other source returns a job object of the payload alone (docs/research/live-job-objects.md).
_CONTEXT: dict[str, dict[str, Any]] = {
    "amazon": _FIRST_FIVE
    | {
        "check_empty_geo": None,
        "safe_search": True,
        "cookies": [],
        "headers": [],
        "currency": None,
    },
    "amazon_bestsellers": _FIRST_FIVE
    | {
        "category_id": None,
        "check_empty_geo": None,
        "safe_search": True,
        "currency": None,
    },
    "amazon_pricing": _FIRST_FIVE
    | {
        "condition": None,
        "check_empty_geo": None,
        "safe_search": True,
        "currency": None,
    },
    "amazon_product": _FIRST_FIVE
    | {
        "autoselect_variant": False,
        "check_empty_geo": None,
        "safe_search": True,
        "currency": None,
    },
    "amazon_search": _FIRST_FIVE
    | {
        "category_id": None,
        "merchant_id": None,
        "check_empty_geo": None,
        "safe_search": True,
        "currency": None,
        "sort_by": None,
        "refinements": None,
        "min_price": None,
        "max_price": None,
    },
    "amazon_sellers": _FIRST_FIVE
    | {"check_empty_geo": None, "safe_search": True, "currency": None},
    "bing": _FIRST_FIVE,
    "bing_search": _FIRST_FIVE | {"safe_search": None},
    "google": _FIRST_FIVE,
    "google_ads": _FIRST_FIVE
    | {"disable_scripts": False, "expand_aio": False, "adstest": False},
    "google_ai_mode": _FIRST_FIVE,
    "google_lens": _FIRST_FIVE | {"keywords": None},
    "google_maps": _FIRST_FIVE | {"hotel_occupancy": 2, "hotel_dates": None},
    "google_scholar": _FIRST_FIVE,
    "google_search": _FIRST_FIVE
    | {
        "results_language": None,
        "safe_search": None,
        "tbm": None,
        "cr": None,
        "filter": None,
        "nfpr": None,
        "tbs": None,
        "fpstate": None,
        "aomd": None,
        "udm": None,
        "limit_per_page": [],
        "disable_scripts": False,
        "expand_aio": False,
    },
    "google_shopping_product": _FIRST_FIVE,
    "google_shopping_search": _FIRST_FIVE
    | {"sort_by": None, "min_price": None, "max_price": None, "tbs": None},
    "google_travel_hotels": _FIRST_FIVE
    | {
        "hotel_occupancy": 2,
        "hotel_dates": None,
        "hotel_classes": [],
        "adults": None,
        "children": None,
    },
    "google_trends_explore": _FIRST_FIVE
    | {
        "search_type": "web_search",
        "date_from": None,
        "date_to": None,
        "category_id": None,
    },
    "universal": _FIRST_FIVE
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
    "youtube_download": _FIRST_FIVE
    | {
        "download_type": "audio_video",
        "video_quality": "720",
        "audio_format": None,
        "audio_language": None,
        "video_format": None,
        "start_at": None,
        "end_at": None,
    },
    "youtube_metadata": _FIRST_FIVE,
    "youtube_subtitles": _FIRST_FIVE | {"language_code": None, "subtitle_origin": None},
}
# Each of the 129 sources without batches takes the shared keys and those of its row (docs/research/live-parameters.md#keys-by-source, live-job-objects.md#new-sources).
# The maintainer edits the table by hand when a caller or a live run finds a mismatch with the API.
_SHARED_KEYS = frozenset(
    {
        "aggregate_name",
        "browser_instructions",
        "callback_url",
        "client_notes",
        "geo_location",
        "markdown",
        "parse",
        "parser_type",
        "parsing_instructions",
        "render",
        "storage_type",
        "storage_url",
        "user_agent_type",
        "xhr",
    }
)
_DOMAIN = frozenset({"domain"})
_PAGED = _DOMAIN | {"start_page"}
_STORE = frozenset({"delivery_zip", "fulfillment_type", "store_id"})
_KROGER_SEARCH = _STORE | {"brand", "price_range"}
_YOUTUBE_FILTERS = frozenset(
    {
        "360",
        "3d",
        "4k",
        "creative_commons",
        "duration",
        "hd",
        "hdr",
        "live",
        "location",
        "purchased",
        "sort_by",
        "subtitles",
        "type",
        "upload_date",
        "vr180",
    }
)
_TAKES: dict[str, frozenset[str]] = {
    "airbnb": frozenset(),
    "airbnb_product": _DOMAIN,
    "alibaba": frozenset(),
    "alibaba_product": _DOMAIN,
    "alibaba_search": _PAGED,
    "aliexpress": frozenset(),
    "aliexpress_product": frozenset({"domain", "subdomain"}),
    "aliexpress_search": _PAGED,
    "allegro_product": frozenset(),
    "allegro_search": frozenset(
        {
            "delivery_time",
            "domain",
            "shipping_from",
            "start_page",
            "store_city",
            "store_region",
        }
    ),
    "avnet_search": _PAGED,
    "bakersplus_product": _STORE,
    "bakersplus_search": _KROGER_SEARCH,
    "bedbathandbeyond": frozenset(),
    "bedbathandbeyond_product": _DOMAIN,
    "bedbathandbeyond_search": _PAGED,
    "bestbuy_product": frozenset({"delivery_zip", "domain", "store_id"}),
    "bestbuy_search": frozenset(
        {"delivery_zip", "domain", "fulfillment_type", "start_page", "store_id"}
    ),
    "bodegaaurrera": frozenset({"delivery_zip", "store_id"}),
    "bodegaaurrera_product": frozenset(
        {"delivery_zip", "domain", "fulfillment_type", "store_id", "subdomain"}
    ),
    "bodegaaurrera_search": frozenset(
        {"delivery_zip", "domain", "fulfillment_type", "store_id", "subdomain"}
    ),
    "cdiscount": frozenset(),
    "cdiscount_product": _DOMAIN,
    "cdiscount_search": _PAGED,
    "citymarket_product": _STORE,
    "citymarket_search": _KROGER_SEARCH,
    "costco": frozenset(),
    "costco_product": _DOMAIN,
    "costco_search": _PAGED,
    "dcard_search": _DOMAIN,
    "dillons_product": _STORE,
    "dillons_search": _KROGER_SEARCH,
    "ebay": frozenset(),
    "ebay_product": _DOMAIN,
    "ebay_search": _PAGED,
    "etsy": frozenset(),
    "etsy_product": frozenset(),
    "etsy_search": frozenset({"domain", "start_page", "store_id"}),
    "falabella": frozenset(),
    "falabella_product": _DOMAIN,
    "falabella_search": _PAGED,
    "flipkart": frozenset(),
    "flipkart_product": _DOMAIN,
    "flipkart_search": _PAGED,
    "foodfourless_product": _STORE,
    "foodfourless_search": _STORE,
    "fredmeyer_product": _STORE,
    "fredmeyer_search": _KROGER_SEARCH,
    "frysfood_product": _STORE,
    "frysfood_search": _KROGER_SEARCH,
    "gerbes_product": _STORE,
    "gerbes_search": _KROGER_SEARCH,
    "grainger": frozenset(),
    "grainger_product": _DOMAIN,
    "grainger_search": _DOMAIN,
    "harristeeter_product": _STORE,
    "harristeeter_search": _KROGER_SEARCH,
    "idealo_search": _DOMAIN,
    "indiamart": frozenset(),
    "indiamart_product": _DOMAIN,
    "indiamart_search": _DOMAIN,
    "instacart": frozenset(),
    "instacart_product": _DOMAIN,
    "instacart_search": _DOMAIN,
    "kingsoopers_product": _STORE,
    "kingsoopers_search": _KROGER_SEARCH,
    "kroger": _STORE,
    "kroger_product": _STORE,
    "kroger_search": _KROGER_SEARCH,
    "lazada": frozenset({"start_page"}),
    "lazada_product": _DOMAIN,
    "lazada_search": _PAGED,
    "lowes": frozenset({"delivery_zip", "store_id"}),
    "lowes_product": frozenset({"delivery_zip", "store_id"}),
    "lowes_search": frozenset(
        {
            "delivery_today_tomorrow",
            "delivery_zip",
            "domain",
            "free_delivery",
            "pickup_today",
            "store_id",
        }
    ),
    "magazineluiza": frozenset(),
    "magazineluiza_product": _DOMAIN,
    "magazineluiza_search": _PAGED,
    "marianos_product": _STORE,
    "marianos_search": _KROGER_SEARCH,
    "mediamarkt": frozenset(),
    "mediamarkt_product": _DOMAIN,
    "mediamarkt_search": _PAGED,
    "menards": frozenset({"store_id"}),
    "menards_product": frozenset({"domain", "store_id"}),
    "menards_search": frozenset(
        {
            "delivery_eligible",
            "domain",
            "fulfillment_center",
            "in_stock_today",
            "pickup_at_store_eligible",
            "start_page",
            "store_id",
        }
    ),
    "mercadolibre": frozenset(),
    "mercadolibre_product": _DOMAIN,
    "mercadolibre_search": _DOMAIN,
    "mercadolivre_product": _DOMAIN,
    "mercadolivre_search": _DOMAIN,
    "metromarket_product": _STORE,
    "metromarket_search": _KROGER_SEARCH,
    "petco": frozenset(),
    "petco_search": frozenset({"domain", "fulfillment_type", "start_page"}),
    "picknsave_product": _STORE,
    "picknsave_search": _KROGER_SEARCH,
    "publix": frozenset({"store_id"}),
    "publix_product": frozenset({"store_id"}),
    "publix_search": frozenset({"store_id"}),
    "qfc_product": _STORE,
    "qfc_search": _KROGER_SEARCH,
    "rakuten": frozenset(),
    "rakuten_search": _DOMAIN,
    "ralphs_product": _STORE,
    "ralphs_search": _KROGER_SEARCH,
    "safeway_product": frozenset({"zip_code"}),
    "safeway_search": frozenset({"zip_code"}),
    "smithsfoodanddrug_product": _STORE,
    "smithsfoodanddrug_search": _KROGER_SEARCH,
    "staples_search": _PAGED,
    "target": _STORE,
    "target_category": _STORE,
    "target_product": _STORE,
    "target_search": _STORE,
    "tiktok": frozenset(),
    "tiktok_shop_product": frozenset(),
    "tiktok_shop_search": frozenset(),
    "tokopedia": frozenset(),
    "tokopedia_search": _PAGED,
    "walmart": _STORE,
    "walmart_product": frozenset(
        {"delivery_zip", "domain", "fulfillment_type", "store_id"}
    ),
    "walmart_search": frozenset(
        {
            "delivery_zip",
            "domain",
            "fulfillment_speed",
            "fulfillment_type",
            "max_price",
            "min_price",
            "sort_by",
            "start_page",
            "store_id",
        }
    ),
    "youtube_autocomplete": frozenset({"language", "location"}),
    "youtube_channel": frozenset({"limit"}),
    "youtube_search": _YOUTUBE_FILTERS,
    "youtube_search_max": _YOUTUBE_FILTERS,
    "youtube_video_trainability": frozenset(),
    "zillow": frozenset(),
}
# The 123 sources that the docs listed on 2026-09-24 (docs/research/parameter-catalog.md), and the 32 they added by 2026-09-30 (docs/research/live-job-objects.md#new-sources).
_SOURCES = frozenset(_CONTEXT) | _LLM_SOURCES | frozenset(_TAKES)
# The 26 sources that took a batch on 2026-09-28 are the LLM sources and those with a full job object (docs/research/live-parameters.md).
_BATCH_SOURCES = _LLM_SOURCES | frozenset(_CONTEXT)
# The names of the 129 other sources give their input keys, except these three (docs/research/live-parameters.md#input-checks).
_NAMED_KEYS = {
    "target_category": "category_id",
    "youtube_channel": "channel_handle",
    "youtube_video_trainability": "video_id",
}
# The key that each of these sources requires besides its input.
_REQUIRED = {
    "grainger_product": "domain",
    "grainger_search": "domain",
    "mercadolibre_product": "domain",
    "safeway_product": "zip_code",
    "safeway_search": "zip_code",
}
# `walmart_search` without `query` fetches walmart.com/all-departments.
_OPTIONAL_INPUT = frozenset({"walmart_search"})
_FORMATS = {
    "target_category": (re.compile(r".{5,}", re.DOTALL), "Must be 5+ characters."),
    "target_product": (re.compile(r"\d{8}|\d{10}"), "Must be 8 or 10 digits."),
    "tiktok_shop_product": (
        re.compile(r"\d{19}"),
        "Must be 19 digits for product_id.",
    ),
}
_ASIN = re.compile(r"[A-Z0-9]+")
_ASIN_LENGTH = 10
# Of the 129, these return results without the target's request and response.
_BARE_RESULTS = frozenset({"youtube_channel", "youtube_search", "youtube_search_max"})
# A 1x1 PNG, so an image library opens the default `png` content.
_PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAAABJRU5ErkJggg=="
# The API returned this page with a 500, so every 5xx returns it.
_SERVER_ERROR = """<!DOCTYPE html>
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
_JOB_PATH = re.compile(r"/v1/queries/(?P<id>[^/]+?)(?P<results>/results)?")


@dataclass(frozen=True, kw_only=True)
class Outcome:
    """What Oxylabs does with one job.

    Attributes
    ----------
    status
        The job's final status.
    after
        Seconds from the submission to the final status.
        `math.inf` keeps the job pending.
    content
        The content of each result, or a function of the page and the output type.
        `None` makes the fake write content from the job's input.
        The fake sends `bytes` as Base64 text, as the API sends `png` content.
    status_code
        The target's status code in each result of a done job.
        A faulted job's one result holds 613.
    upload
        The code of the Cloud Storage entry in `statuses`, for a job with `storage_url`.
        `None` writes no entry.
        The API's job object of the payload alone has no `statuses`, so the fake's has none either.
    upload_after
        Seconds from the final status to the entry.
    expires_after
        Seconds from the final status until the results endpoint returns 204 again.
    """

    status: Literal["done", "faulted"] = "done"
    after: float = 0.0
    content: _Content | Callable[[int, _OutputType], _Content] | None = None
    status_code: int = 200
    upload: int | None = 13000
    upload_after: float = 0.0
    expires_after: float = math.inf


@dataclass(frozen=True)
class Rejected:
    """The error that Oxylabs returns for a payload instead of a job.

    A batch lists `message` under `errors`, and any other submission returns `status_code`.

    Attributes
    ----------
    message
        The `message` of the error body.
    status_code
        The HTTP status of a submission that is not a batch.
    """

    message: str
    status_code: int = 400


@dataclass(frozen=True)
class _Invalid(Rejected):
    """The 400 of a source that takes no batch, which lists each failed field under `errors`."""

    errors: list[str] = field(default_factory=list)


@dataclass
class _Failure:
    error: int | Exception
    on: _Endpoint | None
    times: int | None
    message: str | None


@dataclass(frozen=True, kw_only=True)
class _Job:
    id: str
    payload: dict[str, Any]
    outcome: Outcome
    created: float
    realtime: bool
    storage_url: str | None

    @property
    def finished(self) -> float:
        return self.created + self.outcome.after


# The fakes of the open `with FakeOxylabs()` blocks, innermost last.
_fakes: list[FakeOxylabs] = []


def _switched_on() -> FakeOxylabs | None:
    """Return the fake that a session built without `transport=` uses."""
    return _fakes[-1] if _fakes else None


class FakeOxylabs(httpx2.AsyncBaseTransport):
    """An httpx2 transport that returns the Web Scraper API's responses, and keeps its jobs between sessions.

    Pass it as `transport=`, or open it as a `with` block, which points every session built inside at it.
    The block sets a module global, so it reaches a session that another thread builds, and the innermost block wins.

    The fake applies the API's free checks and rate limits, and its time is `anyio.current_time()`, counted from its first request.
    So trio's `MockClock` runs a job's delays in a fraction of a second.

    Parameters
    ----------
    outcome
        What Oxylabs does with each job, or a function that receives each job's payload as the API received it.
        A batch calls the function once per value, and a `Rejected` rejects that payload.
        The default finishes every job at once.
    limit
        The total limit of each one-second window, which counts every job's `pages`.
    render_limit
        The rendered limit, which counts only payloads with `render` or `xhr: true`.

    Attributes
    ----------
    requests
        Every request the fake received, in order.
    jobs
        The job object of each job the fake created, in order, as its submission returned it.
    """

    def __init__(
        self,
        outcome: Outcome | Callable[[dict[str, Any]], Outcome | Rejected] = Outcome(),  # noqa: B008
        *,
        limit: int = 50,
        render_limit: int = 13,
    ) -> None:
        self.requests: list[httpx2.Request] = []
        self.jobs: list[dict[str, Any]] = []
        self._outcome = outcome
        self._limits: dict[_Limit, int] = {
            "total-requests": limit,
            "total-render-requests": render_limit,
        }
        self._used: dict[_Limit, int] = dict.fromkeys(self._limits, 0)
        self._window = -math.inf
        self._jobs: dict[str, _Job] = {}
        self._failures: list[_Failure] = []
        self._ids = itertools.count(_FIRST_ID)
        self._traces = itertools.count(1)
        self._zero: float | None = None

    def fail(
        self,
        error: int | Exception,
        *,
        on: Literal["submit", "status", "results"] | None = None,
        times: int | None = 1,
        message: str | None = None,
    ) -> None:
        """Return an HTTP status for the next matching requests, or raise an exception for them.

        A failed request creates no job and counts against no limit.

        Parameters
        ----------
        error
            An HTTP status such as 429 or 503, or an exception such as `httpx2.ReadTimeout("no answer")`.
            A 5xx returns the HTML page that the API returned for a 500.
        on
            The requests that fail: submissions, status checks or results downloads.
            `None` fails any request.
        times
            How many requests fail.
            `None` fails every request from now on.
        message
            The `message` of the error body, such as the domain throttle's.
            `None` sends the limit's message with a 429, an empty body with a 401, and the reason phrase otherwise.

        Raises
        ------
        ValueError
            If `times` is below 1.
        """
        if times is not None and times < 1:
            msg = (
                f"times must be at least 1, or None to fail every request, not {times}"
            )
            raise ValueError(msg)
        self._failures.append(_Failure(error, on, times, message))

    def __enter__(self) -> Self:
        """Point every session built inside the block at this fake."""
        _fakes.append(self)
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Stop pointing new sessions at this fake."""
        # The fake's innermost block ends first, so its last entry goes, not its first.
        del _fakes[len(_fakes) - 1 - _fakes[::-1].index(self)]

    @override
    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        await request.aread()
        self.requests.append(request)
        # Start the clock here, because a failure or a 404 below never reads it.
        self._now()
        path = request.url.path
        endpoint: _Endpoint | None = None
        job_id: str | None = None
        if request.method == "POST" and path in {"/v1/queries", "/v1/queries/batch"}:
            endpoint = "submit"
        elif request.method == "GET" and (match := _JOB_PATH.fullmatch(path)):
            endpoint = "results" if match["results"] else "status"
            job_id = match["id"]
        if failure := self._next_failure(endpoint):
            return self._fail(request, failure)
        # nginx returns this 404 for a path that the API does not serve, before any check.
        if endpoint is None or (job_id is not None and not job_id.isdigit()):
            return httpx2.Response(404, json={"message": "Resource not found"})
        if "authorization" not in request.headers:
            return self._error(request, 401, "Authorization header not provided.")
        if job_id is not None:
            return self._get(request, job_id, results=endpoint == "results")
        return await self._submission(request)

    def _fail(self, request: httpx2.Request, failure: _Failure) -> httpx2.Response:
        if isinstance(failure.error, Exception):
            raise failure.error
        too_many = failure.error == httpx2.codes.TOO_MANY_REQUESTS
        limits = self._limit_headers(rendered=False) if too_many else {}
        return self._error(request, failure.error, failure.message, headers=limits)

    async def _submission(self, request: httpx2.Request) -> httpx2.Response:
        try:
            body = json.loads(request.content)
        except ValueError:
            body = None
        if not isinstance(body, dict):
            return self._error(request, 400, "Json error: Unexpected value.")
        if request.url.host == _REALTIME_HOST:
            return await self._realtime(request, body)
        if request.url.path.endswith("/batch"):
            return self._batch(request, body)
        return self._submit(request, body)

    def _submit(self, request: httpx2.Request, body: dict[str, Any]) -> httpx2.Response:
        decision = self._decide(body)
        if isinstance(decision, Rejected):
            return self._reject(request, decision)
        rendered = _rendered(body)
        if limit := self._take(_pages(body), rendered=rendered):
            return self._too_many(request, limit, rendered=rendered)
        job = self._create(body, decision, realtime=False)
        answer = self._object(job, "pending")
        self.jobs.append(answer)
        headers = self._headers(request, job) | self._limit_headers(rendered=rendered)
        return httpx2.Response(202, json=answer, headers=headers)

    def _batch(self, request: httpx2.Request, body: dict[str, Any]) -> httpx2.Response:
        source = body.get("source")
        lists = [key for key in _INPUT_KEYS if isinstance(body.get(key), list)]
        headers = self._headers(request)
        if source not in _SOURCES:
            values: list[Any] = body[lists[0]] if lists else []
            errors = [{"message": "Unsupported source."} for _ in values]
            return httpx2.Response(
                202, json={"queries": [], "errors": errors}, headers=headers
            )
        if len(lists) != 1 or lists[0] not in _BATCH_KEYS:
            message = "Batch request must contain one array of `query` or `url`."
            return self._error(request, 400, message)
        key = lists[0]
        values = body[key]
        if source not in _BATCH_SOURCES:
            message = f"Source `{source}` is not available with a batch request."
            errors = [{"message": message} for _ in values]
            return httpx2.Response(
                202, json={"queries": [], "errors": errors}, headers=headers
            )
        accepted: list[tuple[dict[str, Any], Outcome]] = []
        errors: list[dict[str, Any]] = []
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
        if accepted and (
            limit := self._take(len(accepted) * _pages(body), rendered=rendered)
        ):
            return self._too_many(request, limit, rendered=rendered)
        jobs = [
            self._object(self._create(payload, outcome, realtime=False), "pending")
            for payload, outcome in accepted
        ]
        self.jobs += jobs
        answer: dict[str, Any] = {"queries": jobs}
        if errors:
            answer["errors"] = errors
        if jobs:
            headers |= self._limit_headers(rendered=rendered)
        return httpx2.Response(202, json=answer, headers=headers)

    async def _realtime(
        self, request: httpx2.Request, body: dict[str, Any]
    ) -> httpx2.Response:
        decision = self._decide(body, realtime=True)
        if isinstance(decision, Rejected):
            return self._reject(request, decision)
        rendered = _rendered(body)
        if limit := self._take(_pages(body), rendered=rendered):
            return self._too_many(request, limit, rendered=rendered)
        # A Realtime response carries the limits of its submission, not of its return.
        limits = self._limit_headers(rendered=rendered)
        job = self._create(body, decision, realtime=True)
        if decision.after >= _REALTIME_TTL:
            await anyio.sleep(_REALTIME_TIMEOUT)
            return httpx2.Response(408, json={"message": "Timed out."})
        await anyio.sleep(decision.after)
        answer = self._object(job, decision.status)
        self.jobs.append(answer)
        results = self._results(job, request.url.params.get("type"))
        headers = self._headers(request, job) | limits
        return httpx2.Response(
            200, json={"job": answer, "results": results}, headers=headers
        )

    def _get(
        self, request: httpx2.Request, job_id: str, *, results: bool
    ) -> httpx2.Response:
        job = self._jobs.get(job_id)
        # The status and results endpoints return 404 for a Realtime job's ID.
        if job is None or job.realtime:
            return self._error(request, 404, "Query not found.")
        status = self._status(job)
        if not results:
            return httpx2.Response(
                200, json=self._object(job, status), headers=self._headers(request, job)
            )
        headers = self._headers(request, job, status=status)
        expired = self._now() >= job.finished + job.outcome.expires_after
        if status == "pending" or expired:
            headers["content-type"] = "application/json"
            return httpx2.Response(204, headers=headers)
        answer = {
            "results": self._results(job, request.url.params.get("type")),
            "job": self._object(job, status),
        }
        return httpx2.Response(200, json=answer, headers=headers)

    def _decide(
        self, payload: dict[str, Any], *, realtime: bool = False
    ) -> Outcome | Rejected:
        """Apply the API's free checks, then the test's outcome."""
        rejected = _check(payload) or _storage_error(payload)
        if rejected is None and realtime:
            rejected = _realtime_error(payload)
        if rejected:
            return rejected
        if isinstance(self._outcome, Outcome):
            return self._outcome
        return self._outcome(payload)

    def _next_failure(self, endpoint: _Endpoint | None) -> _Failure | None:
        for failure in self._failures:
            if failure.on in {None, endpoint}:
                if failure.times is not None:
                    failure.times -= 1
                    if failure.times == 0:
                        self._failures.remove(failure)
                return failure
        return None

    def _take(self, cost: int, *, rendered: bool) -> _Limit | None:
        """Count a submission against each limit, or return the limit it does not fit."""
        now = self._now()
        closed = now - self._window >= 1
        if closed:
            self._used = dict.fromkeys(self._limits, 0)
        limits = self._counted(rendered=rendered)
        for limit in limits:
            if self._used[limit] + cost > self._limits[limit]:
                return limit
        # A window opens at the first submission after the last window closed.
        if closed:
            self._window = now
        for limit in limits:
            self._used[limit] += cost
        return None

    def _counted(self, *, rendered: bool) -> list[_Limit]:
        return [
            limit for limit in self._limits if rendered or limit == "total-requests"
        ]

    def _create(
        self, payload: dict[str, Any], outcome: Outcome, *, realtime: bool
    ) -> _Job:
        job_id = str(next(self._ids))
        storage_url = payload.get("storage_url")
        job = _Job(
            id=job_id,
            payload=payload,
            outcome=outcome,
            created=self._now(),
            realtime=realtime,
            storage_url=_resolve(storage_url, job_id, payload)
            if isinstance(storage_url, str)
            else None,
        )
        self._jobs[job_id] = job
        return job

    def _status(self, job: _Job) -> _Status:
        return "pending" if self._now() < job.finished else job.outcome.status

    def _object(self, job: _Job, status: _Status) -> dict[str, Any]:
        """Return the job object as the API returns it while the job has `status`."""
        payload = job.payload
        created = self._stamp(job.created)
        # A Realtime job object keeps `updated_at` equal to `created_at`.
        finished = status != "pending" and not job.realtime
        updated = self._stamp(job.finished) if finished else created
        if payload["source"] in _CONTEXT:
            obj = self._parameters(job, status, created, updated)
        else:
            obj = {key: payload[key] for key in sorted(payload)} | {
                "id": job.id,
                "status": status,
                "created_at": created,
                "updated_at": updated,
            }
            if job.storage_url:
                obj["storage_url"] = job.storage_url
        if not job.realtime:
            base = f"http://data.oxylabs.io/v1/queries/{job.id}"
            first = _first_page(payload)
            pages = [
                f"{base}/results/{page}/content"
                for page in range(first, first + obj.get("pages", 1))
            ]
            obj["_links"] = [
                {"rel": "self", "href": base, "method": "GET"},
                {"rel": "results", "href": f"{base}/results", "method": "GET"},
                {"rel": "results-content", "href_list": pages, "method": "GET"},
                {
                    "rel": "results-html",
                    "href": f"{base}/results?type=raw",
                    "method": "GET",
                },
                {
                    "rel": "results-content-html",
                    "href_list": [f"{page}?type=raw" for page in pages],
                    "method": "GET",
                },
            ]
        return obj

    def _parameters(
        self, job: _Job, status: _Status, created: str, updated: str
    ) -> dict[str, Any]:
        """Return the fields of a job object that lists every parameter."""
        payload = job.payload
        url = payload.get("url")
        host = httpx2.URL(url).host if isinstance(url, str) else ""
        context = _CONTEXT[payload["source"]]
        # Only Amazon and `youtube_metadata` showed this key for `parse: true`, so the fake extends it to all 23 sources.
        if payload.get("parse") is True:
            context = context | {"successful_parse_status_codes": []}
        sent = _sent_context(payload)
        obj: dict[str, Any] = {
            "callback_url": None,
            "client_id": int(_CLIENT_ID),
            # The API leaves an unknown `context` key out of the job object.
            "context": [
                {"key": key, "value": sent.get(key, value)}
                for key, value in context.items()
            ],
            "created_at": created,
            "domain": host.rsplit(".", 1)[-1] if host else "com",
            "geo_location": None,
            "id": job.id,
            "limit": 10,
            # A `google` job for a URL without `hl` read "".
            "locale": "" if payload["source"] == "google" else None,
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
            # A source that takes `query` reads `null` without one.
            "query": "" if payload["source"] in _URL_SOURCES else None,
            "source": payload["source"],
            "start_page": 1,
            "status": status,
            "storage_type": None,
            "storage_url": job.storage_url,
            "aggregate_name": None,
            "subdomain": host.split(".")[0] if host.count(".") > 1 else "www",
            "content_encoding": "utf-8",
            "updated_at": updated,
            "user_agent_type": "desktop",
            "session_info": None,
            "statuses": [],
            "client_notes": None,
        }
        # The API leaves an unknown key out of the job object.
        obj |= {
            key: value
            for key, value in payload.items()
            if key in obj and key not in _SERVER_KEYS
        }
        obj |= {key: payload[key] for key in _INPUT_KEYS if key in payload}
        obj |= {"pages": _fetched(payload), "start_page": _first_page(payload)}
        code = job.outcome.upload
        uploaded = job.finished + job.outcome.upload_after
        if (
            job.storage_url
            and status != "pending"
            and code is not None
            and self._now() >= uploaded
        ):
            message = _UPLOAD_MESSAGES.get(code, "")
            obj["statuses"] = [
                {"event": "GCS_STORAGE_UPLOAD", "code": code, "message": message}
            ]
        return obj

    def _results(self, job: _Job, types: str | None) -> list[dict[str, Any]]:
        payload, outcome = job.payload, job.outcome
        first = _first_page(payload)
        if outcome.status == "faulted":
            return [self._entry(job, first, "raw", 613, "")]
        requested: list[str] = types.split(",") if types else []
        kinds = [kind for name in requested for kind in _OUTPUT_TYPES if kind == name]
        return [
            self._entry(job, page, kind, outcome.status_code, _content(job, page, kind))
            for page in range(first, first + _fetched(payload))
            for kind in kinds or [_default_type(payload)]
        ]

    def _entry(
        self,
        job: _Job,
        page: int,
        kind: _OutputType,
        status_code: int,
        content: str | dict[str, Any] | list[Any],
    ) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "content": content,
            "created_at": self._stamp(job.created),
            "updated_at": self._stamp(job.finished),
            "page": page,
            "url": job.payload.get("url")
            or f"https://www.example.com/{_input(job.payload)}?page={page}",
            "job_id": job.id,
            "is_render_forced": False,
            "status_code": status_code,
            "type": kind,
        }
        if kind == "parsed":
            entry |= {"parser_type": "", "parser_preset": None}
        source = job.payload["source"]
        if source == "universal" or (source in _TAKES and source not in _BARE_RESULTS):
            faulted = job.outcome.status == "faulted"
            sent: list[Any] | None = None if faulted else []
            headers = None if faulted else {"User-Agent": "Mozilla/5.0"}
            entry |= {
                "_request": {"cookies": sent, "headers": headers},
                "_response": {"cookies": sent, "headers": headers},
                "session_info": {"expires_at": None, "id": None, "remaining": None},
            }
        return entry

    def _headers(
        self,
        request: httpx2.Request,
        job: _Job | None = None,
        *,
        status: _Status | None = None,
    ) -> dict[str, str]:
        headers = {"x-oxylabs-client-id": _CLIENT_ID}
        realtime = request.url.host == _REALTIME_HOST
        if not realtime:
            headers["x-oxylabs-client-name"] = _CLIENT_NAME
        if job:
            headers["x-oxylabs-job-id"] = job.id
        if status:
            headers["x-oxylabs-job-status"] = status
        if realtime:
            return headers | {"x-oxylabs-trace-id": self._trace_id()}
        # On the data host, each `x-oxylabs-*` header has an `x-oxyserps-*` twin.
        return headers | {
            name.replace("x-oxylabs", "x-oxyserps"): value
            for name, value in headers.items()
        }

    def _limit_headers(self, *, rendered: bool) -> dict[str, str]:
        in_window = self._now() - self._window < 1
        headers: dict[str, str] = {}
        for limit in self._counted(rendered=rendered):
            used = self._used[limit] if in_window else 0
            prefix = f"x-ratelimit-{limit}-{_LIMIT_UUID}"
            headers[f"{prefix}-limit"] = str(self._limits[limit])
            headers[f"{prefix}-remaining"] = str(self._limits[limit] - used)
        return headers

    def _too_many(
        self, request: httpx2.Request, limit: _Limit, *, rendered: bool
    ) -> httpx2.Response:
        headers = self._limit_headers(rendered=rendered)
        return self._error(request, 429, _LIMIT_MESSAGES[limit], headers=headers)

    def _reject(self, request: httpx2.Request, rejected: Rejected) -> httpx2.Response:
        if isinstance(rejected, _Invalid):
            return self._error(request, rejected.status_code, errors=rejected.errors)
        return self._error(request, rejected.status_code, rejected.message)

    def _error(
        self,
        request: httpx2.Request,
        status_code: int,
        message: str | None = None,
        *,
        errors: list[str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx2.Response:
        if status_code >= httpx2.codes.INTERNAL_SERVER_ERROR:
            page = _SERVER_ERROR.format(code=status_code, trace_id=self._trace_id())
            return httpx2.Response(status_code, html=page)
        # A 401 for an unknown username has an empty body.
        if status_code == httpx2.codes.UNAUTHORIZED and message is None:
            return httpx2.Response(401)
        if message is None:
            message = (
                _LIMIT_MESSAGES["total-requests"]
                if status_code == httpx2.codes.TOO_MANY_REQUESTS
                else httpx2.codes.get_reason_phrase(status_code)
            )
        body = ({"errors": errors} if errors else {"message": message}) | {
            "instance": request.url.path,
            "timestamp": f"{_EPOCH + timedelta(seconds=self._now()):%Y-%m-%dT%H:%M:%S.%f}000Z",
            "trace_id": self._trace_id(),
        }
        # Realtime and a 401 leave out the client headers.
        client = (
            {}
            if status_code == httpx2.codes.UNAUTHORIZED
            or request.url.host == _REALTIME_HOST
            else self._headers(request)
        )
        return httpx2.Response(status_code, json=body, headers=client | (headers or {}))

    def _now(self) -> float:
        """Return the seconds since the fake's first request, on the running backend's clock."""
        now = anyio.current_time()
        if self._zero is None:
            self._zero = now
        return now - self._zero

    def _stamp(self, seconds: float) -> str:
        return f"{_EPOCH + timedelta(seconds=seconds):%Y-%m-%d %H:%M:%S}"

    def _trace_id(self) -> str:
        return f"{next(self._traces):08x}-{'0' * 24}"


def _check(payload: dict[str, Any]) -> Rejected | None:
    """Return the API's free rejection of a payload, if it has one."""
    source = payload.get("source")
    if source not in _SOURCES:
        return Rejected("Unsupported source.")
    if source in _TAKES:
        return _field_check(source, payload)
    return (
        _pages_error(source, payload)
        or _page_error("start_page", payload.get("start_page"))
        or _input_error(source, payload)
        or _source_error(source, payload)
    )


def _input_error(source: str, payload: dict[str, Any]) -> Rejected | None:
    """Return the free 400 for the input of a source that takes a batch."""
    # Any other input key is unknown to these sources, so the API leaves it out, except `url`.
    if source in _URL_SOURCES:
        url = payload.get("url")
        return _url_error(url) if url else Rejected("Parameter `url` is empty.")
    if "url" in payload:
        return Rejected(f"Source `{source}` is not available with url parameter.")
    if source == "amazon_search":
        if payload.get("query") or _sent_context(payload).get("merchant_id"):
            return None
        message = "Either `query` or `context:merchant_id` parameters must be set."
        return Rejected(message)
    # `amazon_bestsellers` bills a page for an empty, unknown or missing `query`.
    if (
        source == "amazon_bestsellers"
        or payload.get("query")
        or (source in _LLM_SOURCES and payload.get("prompt"))
    ):
        return None
    return Rejected("Query parameter is empty.")


def _source_error(source: str, payload: dict[str, Any]) -> Rejected | None:
    """Return the free 400 for a value that one source requires."""
    asin = str(payload.get("query"))
    parsers = {"parser_type", "parser_preset", "parsing_instructions"}
    match source:
        case "google_ai_mode" if payload.get("render") not in {"html", "png"}:
            message = "Parameter `render` for this source can only be set to one of: html, png."
        case "youtube_download" if "storage_url" not in payload:
            message = "Parameter `storage_url` must be provided for this source."
        case "youtube_metadata" if payload.get("parse") is not True:
            message = "Parameter `parse` must be enabled for this source."
        # The fake has no dedicated parser, so it rejects `parse` for every page.
        case "universal" if payload.get("parse") is True and not parsers & set(payload):
            message = f"Parsing `{payload['url']}` url is allowed only with `parser_type` or `parsing_instructions` parameter."
        case "amazon_pricing" | "amazon_product" if len(asin) < _ASIN_LENGTH:
            message = "ASIN length is not valid."
        case "amazon_pricing" | "amazon_product" if not _ASIN.fullmatch(asin):
            message = "ASIN should only contain alphanumeric values."
        case _:
            return None
    return Rejected(message)


def _field_check(source: str, payload: dict[str, Any]) -> Rejected | None:
    """Apply the checks of a source without batches."""
    # The form of a `url` comes before the fields, and these sources skip its host checks.
    url = payload.get("url")
    if url and (rejected := _url_error(url, hosts=False)):
        return rejected
    errors = _field_errors(source, payload)
    return _Invalid("", errors=errors) if errors else None


def _field_errors(source: str, payload: dict[str, Any]) -> list[str]:
    """Return the `errors` list of a source without batches, sorted as the API sorts it."""
    key = _input_key(source)
    takes = _SHARED_KEYS | _TAKES[source] | {"source", key}
    errors = [
        f"[{name}]: This field was not expected."
        for name in payload
        if name not in takes
    ]
    if (required := _REQUIRED.get(source)) and required not in payload:
        errors.append(f"[{required}]: This field is missing.")
    # These sources take any int, 0 included, and no text.
    start_page = payload.get("start_page")
    if (
        "start_page" in takes
        and "start_page" in payload
        and type(start_page) is not int
    ):
        errors.append("[start_page]: This value should be of type int.")
    value = payload.get(key)
    if key not in payload and source not in _OPTIONAL_INPUT:
        errors.append(f"[{key}]: This field is missing.")
    elif key in payload and not value:
        errors.append(f"[{key}]: This value should not be blank.")
    if source in _FORMATS and isinstance(value, str):
        pattern, message = _FORMATS[source]
        if not pattern.fullmatch(value):
            errors.append(f"[{key}]: {message}")
    return sorted(errors)


def _input_key(source: str) -> str:
    if source in _NAMED_KEYS:
        return _NAMED_KEYS[source]
    if source.endswith("_product"):
        return "product_id"
    return "query" if "_" in source else "url"


def _realtime_error(payload: dict[str, Any]) -> Rejected | None:
    if payload["source"] in _LLM_SOURCES:
        message = "Realtime integration is not supported for LLM sources. Please use Push-Pull."
        return Rejected(message, status_code=422)
    if "storage_url" in payload or "storage_type" in payload:
        return Rejected("Parameter `storage_url` cannot be used with realtime.")
    return None


def _storage_error(payload: dict[str, Any]) -> Rejected | None:
    storage_url = payload.get("storage_url")
    if payload.get("storage_type") not in {"s3_compatible", "tos"} or not isinstance(
        storage_url, str
    ):
        return None
    # A raw `/`, `?` or `#` in the secret ends the host, so the API reads the rest of the secret as a port.
    try:
        userinfo = httpx2.URL(storage_url).userinfo
    except httpx2.InvalidURL:
        return Rejected("Parameter `storage_url` must be a valid url.")
    if b":" not in userinfo:
        return Rejected("Parameter `storage_url` must contain a valid user info.")
    return None


def _pages_error(source: str, payload: dict[str, Any]) -> Rejected | None:
    if error := _page_error("pages", payload.get("pages")):
        return error
    pages = _pages(payload)
    if pages > _MAX_PAGES:
        return Rejected(f"Parameter `pages` should not exceed {_MAX_PAGES}.")
    if pages > _PAGE_LIMITS.get(source, _MAX_PAGES):
        return Rejected(
            f"Parameter `pages` cannot exceed {_PAGE_LIMITS[source]} for this source."
        )
    return None


def _page_error(key: str, value: object) -> Rejected | None:
    """Return the free 400 for a `pages` or `start_page` on a source that takes a batch, which also takes digits as text."""
    if value is None:
        return None
    number = _integer(value)
    if number is None:
        return Rejected(
            f"Invalid type for parameter `{key}`, supported types: `integer, string`."
        )
    if number < 1:
        return Rejected(f"Parameter `{key}` should be a positive integer.")
    return None


def _url_error(url: object, *, hosts: bool = True) -> Rejected | None:
    try:
        parsed = httpx2.URL(url) if isinstance(url, str) else None
    except httpx2.InvalidURL:
        parsed = None
    if parsed is None or parsed.scheme not in {"http", "https"} or not parsed.host:
        return Rejected("Parameter `url` is invalid.")
    if not hosts:
        return None
    with contextlib.suppress(ValueError):
        ipaddress.ip_address(parsed.host)
        return Rejected("The hostname cannot be an ip address.")
    if parsed.host.rsplit(".", 1)[-1] in {"invalid", "test", "example"}:
        return Rejected("Parameter `url` has invalid top level domain format.")
    return None


def _sent_context(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        item["key"]: item.get("value")
        for item in payload.get("context", [])
        if isinstance(item, dict) and "key" in item
    }


def _rendered(payload: dict[str, Any]) -> bool:
    return bool(payload.get("render")) or payload.get("xhr") is True


def _pages(payload: dict[str, Any]) -> int:
    return _integer(payload.get("pages")) or 1


def _fetched(payload: dict[str, Any]) -> int:
    return 1 if payload["source"] in _ONE_PAGE else _pages(payload)


def _first_page(payload: dict[str, Any]) -> int:
    first = payload.get("start_page")
    return 1 if first is None else int(first)


def _input(payload: dict[str, Any]) -> str:
    return next((str(payload[key]) for key in _INPUT_KEYS if payload.get(key)), "")


def _default_type(payload: dict[str, Any]) -> _OutputType:
    if payload.get("parse"):
        return "parsed"
    if payload.get("markdown"):
        return "markdown"
    if payload.get("xhr"):
        return "xhr"
    return "png" if payload.get("render") == "png" else "raw"


def _content(
    job: _Job, page: int, kind: _OutputType
) -> str | dict[str, Any] | list[Any]:
    content = job.outcome.content
    if callable(content):
        content = content(page, kind)
    if content is None:
        value = _input(job.payload)
        defaults: dict[_OutputType, _Content] = {
            "raw": f"<!doctype html><html><title>{value}</title><p>Page {page}</p></html>",
            "parsed": {"title": value, "page": page, "parse_status_code": 12000},
            "markdown": f"# {value}\n\nPage {page}.",
            "png": _PNG,
            "xhr": [],
        }
        content = defaults[kind]
    return base64.b64encode(content).decode() if isinstance(content, bytes) else content


def _resolve(storage_url: str, job_id: str, payload: dict[str, Any]) -> str:
    """Resolve a `storage_url` as the API does at submission, and redact its credentials."""
    name = storage_url
    # A name that does not end in `.{{ extension }}` names a folder.
    # `youtube_download` names its object `<query>_<job id>.{{ extension }}` instead, which the fake leaves out.
    if not name.endswith(".{{ extension }}"):
        name = name.rstrip("/") + "/{{ job_id }}.{{ extension }}"
    variables = {
        "job_id": job_id,
        "source": payload["source"],
        "query": str(payload.get("query", "")),
        "extension": "json",
    }
    for variable, value in variables.items():
        name = name.replace("{{ " + variable + " }}", value)
    return _CREDENTIALS.sub("redacted:redacted", name)
