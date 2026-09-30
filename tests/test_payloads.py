import json
import traceback
from collections.abc import Callable
from typing import Any

import pytest
from pydantic import ValidationError

import oxyscraper as oxy
from oxyscraper.testing import FakeOxylabs

Build = Callable[..., oxy.Payload]

STORAGE_URL = "https://key-id:s3cr3t@storage.example.com/bucket/folder"
REDACTED_STORAGE_URL = "https://redacted:redacted@storage.example.com/bucket/folder"


@pytest.fixture(params=["init", "model_validate", "model_validate_json"])
def build(request: pytest.FixtureRequest) -> Build:
    """Build a payload through each entry point that validates one."""

    def build(**fields: Any) -> oxy.Payload:
        if request.param == "init":
            return oxy.Payload(**fields)
        if request.param == "model_validate":
            return oxy.Payload.model_validate(fields)
        return oxy.Payload.model_validate_json(json.dumps(fields))

    return build


def test_body() -> None:
    """The body holds each set field and leaves out each unset one."""
    payload = oxy.Payload(source="universal", url="https://example.com", render="html")
    assert payload.model_dump() == {
        "source": "universal",
        "url": "https://example.com",
        "render": "html",
    }


def test_other_keywords() -> None:
    """A keyword that `Payload` does not type goes into the body as it is."""
    payload = oxy.Payload(
        source="kroger_product", product_id="1", store_id="01100002", nested={"a": 1}
    )
    assert payload.model_dump() == {
        "source": "kroger_product",
        "product_id": "1",
        "store_id": "01100002",
        "nested": {"a": 1},
    }


def test_extra() -> None:
    """`extra` merges into the body, and its `context` items follow the typed ones."""
    payload = oxy.Payload(
        source="universal",
        url="https://example.com",
        context=[{"key": "force_headers", "value": True}],
        extra={"new_param": None, "context": [{"key": "session_id", "value": "abc"}]},
    )
    assert payload.model_dump() == {
        "source": "universal",
        "url": "https://example.com",
        "context": [
            {"key": "force_headers", "value": True},
            {"key": "session_id", "value": "abc"},
        ],
        "new_param": None,
    }


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({}, "no input key"),
        ({"query": "a", "url": "https://example.com"}, "query and url"),
        ({"query": ""}, "query must be a non-empty string"),
        ({"extra": {"query": ""}}, "query must be a non-empty string"),
        ({"extra": {"query": ["a", "b"]}}, "query must be a non-empty string"),
        ({"query": "a", "extra": {"url": "https://example.com"}}, "query and url"),
    ],
)
def test_input_key(build: Build, fields: dict[str, Any], message: str) -> None:
    """A payload needs exactly one input key, holding a non-empty string."""
    with pytest.raises(ValidationError, match=message):
        build(source="universal", **fields)


def test_input_key_in_extra(build: Build) -> None:
    """An input key in `extra` counts as the payload's one input key."""
    payload = build(source="universal", extra={"url": "https://example.com"})
    assert payload.model_dump() == {"source": "universal", "url": "https://example.com"}


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"render": "html", "extra": {"render": "png"}}, "render is set both"),
        ({"store_id": "1", "extra": {"store_id": "2"}}, "store_id is set both"),
        ({"extra": {"source": "google"}}, "source is set both"),
        (
            {
                "context": [{"key": "a", "value": 1}],
                "extra": {"context": [{"key": "a", "value": 2}]},
            },
            "context key a is set twice",
        ),
        (
            {"context": [{"key": "a", "value": 1}, {"key": "a", "value": 2}]},
            "context key a is set twice",
        ),
    ],
)
def test_set_twice(build: Build, fields: dict[str, Any], message: str) -> None:
    """A key set both as a field and in `extra`, or in two `context` items, raises."""
    with pytest.raises(ValidationError, match=message):
        build(source="universal", url="https://example.com", **fields)


def test_extra_skips_literals(build: Build) -> None:
    """`extra` carries a value that an unset field's `Literal` rejects."""
    payload = build(
        source="universal", url="https://example.com", extra={"render": "pdf"}
    )
    assert payload.model_dump()["render"] == "pdf"


@pytest.mark.parametrize("context", [{"key": "a", "value": 1}, [{"value": 1}], ["a"]])
def test_extra_context_shape(build: Build, context: object) -> None:
    """The `context` in `extra` is a list of items with a `key` and a `value`."""
    with pytest.raises(ValidationError, match=r"extra\.context"):
        build(source="universal", url="https://example.com", extra={"context": context})


@pytest.mark.parametrize(
    "fields",
    [
        {"storage_url": "bucket/{{ source }}.{{ extension }}"},
        {"storage_url": "bucket/{{job_id}}.{{ extension }}"},
        {"extra": {"storage_url": "bucket/name.{{ extension }}"}},
    ],
)
def test_storage_url_collision(build: Build, fields: dict[str, Any]) -> None:
    """A `storage_url` that ends in `.{{ extension }}` without `{{ job_id }}` raises."""
    with pytest.raises(ValidationError, match=r"needs \{\{ job_id \}\}"):
        build(
            source="universal", url="https://example.com", storage_type="gcs", **fields
        )


@pytest.mark.parametrize(
    "storage_url",
    [
        "bucket/folder",
        "bucket/name.json",
        "bucket/{{ job_id }}.{{ extension }}",
        "bucket/{{ source }}_{{ job_id }}.{{ extension }}",
    ],
)
def test_storage_url(build: Build, storage_url: str) -> None:
    """A folder, or an object name with `{{ job_id }}`, passes."""
    payload = build(
        source="universal",
        url="https://example.com",
        storage_type="gcs",
        storage_url=storage_url,
    )
    assert payload.model_dump()["storage_url"] == storage_url


def test_body_keeps_secret() -> None:
    """The body keeps the credentials in `storage_url`, because oxy sends it."""
    payload = oxy.Payload(
        source="universal",
        url="https://example.com",
        storage_type="s3_compatible",
        storage_url=STORAGE_URL,
    )
    assert payload.model_dump()["storage_url"] == STORAGE_URL


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        (
            {"storage_url": STORAGE_URL},
            f"Payload(source='universal', url='https://example.com', storage_type='tos', storage_url='{REDACTED_STORAGE_URL}')",
        ),
        (
            {"extra": {"storage_url": STORAGE_URL}},
            f"Payload(source='universal', url='https://example.com', storage_type='tos', extra={{'storage_url': '{REDACTED_STORAGE_URL}'}})",
        ),
    ],
)
def test_repr(fields: dict[str, Any], expected: str) -> None:
    """`repr` shows the set fields, with the credentials in `storage_url` redacted."""
    payload = oxy.Payload(
        source="universal", url="https://example.com", storage_type="tos", **fields
    )
    assert repr(payload) == expected


@pytest.mark.parametrize(
    "fields",
    [
        {"storage_url": STORAGE_URL},
        {"url": "https://example.com", "extra": [STORAGE_URL]},
        {"url": "https://example.com", "storage_url": STORAGE_URL, "render": "pdf"},
        {
            "url": "https://example.com",
            "storage_url": STORAGE_URL.replace(
                "folder", "{{ source }}.{{ extension }}"
            ),
        },
    ],
)
def test_errors_redact(build: Build, fields: dict[str, Any]) -> None:
    """A validation error never shows the credentials in `storage_url`."""
    with pytest.raises(ValidationError) as caught:
        build(source="universal", storage_type="s3_compatible", **fields)
    assert "s3cr3t" not in "".join(traceback.format_exception(caught.value))
    assert "s3cr3t" not in repr(caught.value.errors())


@pytest.mark.parametrize(
    "call",
    [
        lambda: oxy.Payload.model_validate_json(f'{{"storage_url": "{STORAGE_URL}"'),
        lambda: oxy.Payload.model_validate(STORAGE_URL),
    ],
)
def test_errors_redact_any_input(call: Callable[[], object]) -> None:
    """An error for input that is not a payload at all also hides the credentials."""
    with pytest.raises(ValidationError) as caught:
        call()
    assert "s3cr3t" not in "".join(traceback.format_exception(caught.value))
    assert "redacted:redacted" in repr(caught.value.errors())


def test_frozen() -> None:
    """Assignment raises, so an assignment cannot skip the checks."""
    payload = oxy.Payload(source="universal", url="https://example.com")
    with pytest.raises(ValidationError, match="frozen"):
        payload.url = ""  # pyrefly: ignore[read-only]


def test_round_trip(build: Build) -> None:
    """A body in the API's shape builds a payload with the same body."""
    body = {
        "source": "universal",
        "url": "https://example.com",
        "render": "html",
        "store_id": "01100002",
        "context": [{"key": "force_headers", "value": True}],
    }
    assert build(**body).model_dump() == body


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("render", ""),
        ("user_agent_type", "desktop_safari"),
        ("content_encoding", "utf-8"),
        ("storage_type", "s3_compatible"),
        ("pages", "2"),
    ],
)
def test_typed_values(build: Build, field: str, value: object) -> None:
    """A typed field takes each value that the API accepts."""
    build(source="universal", url="https://example.com", **{field: value})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("render", "pdf"),
        ("user_agent_type", "desktop_brave"),
        ("content_encoding", "gzip"),
        ("storage_type", "azure"),
        ("pages", 0),
        ("start_page", -1),
        ("context", [{"key": "a"}]),
    ],
)
def test_typed_values_raise(build: Build, field: str, value: object) -> None:
    """A typed field raises for a value that the API rejects."""
    with pytest.raises(ValidationError, match=field):
        build(source="universal", url="https://example.com", **{field: value})


def test_dry_run(fake: FakeOxylabs) -> None:
    """A dry run lists each redacted body and totals the jobs and the most results they bill."""
    payloads = [
        oxy.Payload(
            source="universal",
            url="https://example.com",
            pages=3,
            storage_type="tos",
            storage_url=STORAGE_URL,
        ),
        oxy.Payload(source="walmart_product", product_id="436012154"),
        oxy.Payload(source="universal", url="https://example.org", extra={"pages": 5}),
    ]
    report = oxy.dry_run(payload for payload in payloads)
    assert report.jobs == [
        {
            "source": "universal",
            "url": "https://example.com",
            "pages": 3,
            "storage_type": "tos",
            "storage_url": REDACTED_STORAGE_URL,
        },
        {"source": "walmart_product", "product_id": "436012154"},
        {"source": "universal", "url": "https://example.org", "pages": 5},
    ]
    assert report.job_count == 3
    assert report.max_results == 9
    assert fake.requests == []


def test_dry_run_one_payload() -> None:
    """A dry run takes one payload as well as an iterable of them."""
    report = oxy.dry_run(oxy.Payload(source="universal", url="https://example.com"))
    assert report.jobs == [{"source": "universal", "url": "https://example.com"}]
    assert report.job_count == 1
    assert report.max_results == 1
