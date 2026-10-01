"""Code a caller writes against the `universal` model, which `pyrefly check --expectations` checks."""

from typing import Literal, assert_type

import oxyscraper as oxy

URL = "https://httpbin.org/anything"

payload = oxy.Universal(
    url=URL,
    render="html",
    user_agent_type="mobile",
    headers={"X-Test": "1"},
    force_headers=True,
    cookies=[{"key": "a", "value": "1"}],
    force_cookies=True,
    http_method="post",
    content="aGVsbG89d29ybGQ=",
    successful_status_codes=[503],
)
assert_type(payload.source, Literal["universal"])
assert_type(payload.url, str)
assert_type(payload.headers, dict[str, str] | None)
assert_type(payload.session_id, str | None)
payloads: list[oxy.Payload] = [payload, oxy.Universal(url=URL, geo_location="DE")]

oxy.Universal(url=URL, user_agent_type="desktop_chrome")  # E: 'desktop_chrome'
oxy.Universal(url=URL, http_method="put")  # E: 'put'
oxy.Universal(url=URL, domain="com")  # E: Unexpected keyword argument `domain`
oxy.Universal(url=URL, pages=2)  # E: Unexpected keyword argument `pages`
oxy.Universal(url=URL, query="a")  # E: Unexpected keyword argument `query`
oxy.Universal()  # E: Missing argument `url`
