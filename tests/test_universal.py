from typing import Any

import pytest
from pydantic import ValidationError

import oxyscraper as oxy

URL = "https://example.com"


def test_source() -> None:
    """`Universal` fixes `source`, and its body holds the URL alone by default."""
    assert oxy.Universal(url=URL).model_dump() == {"source": "universal", "url": URL}
    assert oxy.Universal in oxy.SOURCES
    with pytest.raises(ValidationError, match="source"):
        oxy.Universal.model_validate({"url": URL, "source": "amazon"})


def test_context_fields() -> None:
    """`Universal` moves its typed `context` keys into the `context` list, in the job object's order, before the other items."""
    payload = oxy.Universal(
        url=URL,
        store_id="0123",
        content="aGVsbG89d29ybGQ=",
        http_method="post",
        session_id="abc",
        headers={"X-Test": "1"},
        cookies=[{"key": "a", "value": "1"}],
        follow_redirects=False,
        successful_status_codes=[503],
        force_cookies=True,
        force_headers=True,
        context=[{"key": "proxy_location", "value": "us"}],
        extra={"context": [{"key": "hc_policy", "value": False}]},
    )
    assert payload.model_dump() == {
        "source": "universal",
        "url": URL,
        "context": [
            {"key": "force_headers", "value": True},
            {"key": "force_cookies", "value": True},
            {"key": "successful_status_codes", "value": [503]},
            {"key": "follow_redirects", "value": False},
            {"key": "cookies", "value": [{"key": "a", "value": "1"}]},
            {"key": "headers", "value": {"X-Test": "1"}},
            {"key": "session_id", "value": "abc"},
            {"key": "http_method", "value": "post"},
            {"key": "content", "value": "aGVsbG89d29ybGQ="},
            {"key": "store_id", "value": "0123"},
            {"key": "proxy_location", "value": "us"},
            {"key": "hc_policy", "value": False},
        ],
    }


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("query", "a"),
        ("product_id", "1"),
        ("prompt", "a"),
        ("video_id", "a"),
        ("channel_handle", "@a"),
        ("category_id", "1"),
        ("domain", "com"),
        ("locale", "en_US"),
        ("start_page", 2),
        ("pages", 2),
        ("limit", 10),
    ],
)
def test_left_out(key: str, value: Any) -> None:
    """A parameter that no docs page names for `universal` raises as an unknown keyword."""
    with pytest.raises(
        ValidationError, match=rf"{key}\n  Extra inputs are not permitted"
    ):
        oxy.Universal(url=URL, **{key: value})


def test_left_out_in_extra() -> None:
    """`extra` passes a parameter that the model leaves out."""
    payload = oxy.Universal(url=URL, extra={"pages": 2})
    assert payload.model_dump()["pages"] == 2


@pytest.mark.parametrize(
    "fields",
    [
        {"headers": {"X-Test": "1"}},
        {"headers": {"X-Test": "1"}, "force_headers": False},
        {"headers": {"X-Test": "1"}, "force_cookies": True},
        {"context": [{"key": "headers", "value": {"X-Test": "1"}}]},
        {"extra": {"context": [{"key": "headers", "value": {"X-Test": "1"}}]}},
    ],
)
def test_headers_without_force(fields: dict[str, Any]) -> None:
    """`headers` without `force_headers` raises, because the site receives none and the job bills."""
    with pytest.raises(ValidationError, match="force_headers"):
        oxy.Universal(url=URL, **fields)


@pytest.mark.parametrize(
    "fields",
    [
        {"cookies": [{"key": "a", "value": "1"}]},
        {"cookies": [{"key": "a", "value": "1"}], "force_cookies": False},
        {"cookies": [{"key": "a", "value": "1"}], "force_headers": True},
        {"extra": {"context": [{"key": "cookies", "value": [{"key": "a"}]}]}},
    ],
)
def test_cookies_without_force(fields: dict[str, Any]) -> None:
    """`cookies` without `force_cookies` raises, because the site receives none and the job bills."""
    with pytest.raises(ValidationError, match="force_cookies"):
        oxy.Universal(url=URL, **fields)


@pytest.mark.parametrize(
    "fields",
    [
        {"headers": {"X-Test": "1"}, "force_headers": True},
        {"cookies": [{"key": "a", "value": "1"}], "force_cookies": True},
        {
            "headers": {"X-Test": "1"},
            "extra": {"context": [{"key": "force_headers", "value": True}]},
        },
        {"headers": {}, "cookies": []},
        {"force_headers": True, "force_cookies": False},
    ],
)
def test_headers_and_cookies(fields: dict[str, Any]) -> None:
    """`headers` and `cookies` pass with their `force_*` key, and an empty value passes without it."""
    oxy.Universal(url=URL, **fields)


@pytest.mark.parametrize(
    "user_agent_type",
    [
        "desktop",
        "mobile",
        "mobile_android",
        "mobile_ios",
        "tablet",
        "tablet_android",
        "tablet_ios",
    ],
)
def test_user_agent_type(user_agent_type: str) -> None:
    """`Universal` takes the 7 documented user agent types."""
    payload = oxy.Universal.model_validate(
        {"url": URL, "user_agent_type": user_agent_type}
    )
    assert payload.user_agent_type == user_agent_type


@pytest.mark.parametrize(
    "user_agent_type",
    [
        "desktop_chrome",
        "desktop_edge",
        "desktop_firefox",
        "desktop_opera",
        "desktop_safari",
    ],
)
def test_desktop_user_agent_type(user_agent_type: str) -> None:
    """A `desktop_*` user agent type raises, because it draws from the same agents as `desktop`."""
    with pytest.raises(ValidationError, match="user_agent_type"):
        oxy.Universal.model_validate({"url": URL, "user_agent_type": user_agent_type})


@pytest.mark.parametrize("http_method", ["get", "post", "options"])
def test_http_method(http_method: str) -> None:
    """`http_method` takes the three methods that the API accepts."""
    payload = oxy.Universal.model_validate({"url": URL, "http_method": http_method})
    assert payload.model_dump()["context"] == [
        {"key": "http_method", "value": http_method}
    ]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("http_method", "put"),
        ("cookies", {"a": "1"}),
        ("cookies", [{"key": "a"}]),
        ("headers", [{"key": "X-Test", "value": "1"}]),
        ("successful_status_codes", 503),
    ],
)
def test_values_raise(field: str, value: Any) -> None:
    """A value outside a field's type raises."""
    with pytest.raises(ValidationError, match=field):
        oxy.Universal(url=URL, **{field: value})
