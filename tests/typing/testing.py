"""Code a caller writes against the fake, which `pyrefly check --expectations` checks."""

from typing import Any, assert_type

import httpx2

import oxyscraper as oxy
from oxyscraper.testing import FakeOxylabs, Outcome, Rejected


def outcome(payload: dict[str, Any]) -> Outcome | Rejected:
    if "url" not in payload:
        return Rejected("Nope.", status_code=422)
    return Outcome(after=5, content=lambda page, kind: f"{page} {kind}")


with FakeOxylabs(outcome, limit=100, render_limit=20) as fake:
    assert_type(fake, FakeOxylabs)
    assert_type(fake.requests, list[httpx2.Request])
    assert_type(fake.jobs, list[dict[str, Any]])
    fake.fail(503, on="results", times=None)
    fake.fail(httpx2.ReadTimeout("no answer"), message="Slow.")
    oxy.Session(username="USERNAME", password="PASSWORD", transport=fake)  # noqa: S106
    fake.fail(503, on="content")  # E: 'content'
    fake.fail("503")  # E: '503'

FakeOxylabs(Outcome(status="faulted", upload=None, expires_after=60))
FakeOxylabs(Outcome(status="pending"))  # E: 'pending'
FakeOxylabs(lambda _: None)  # E: -> None
FakeOxylabs(limit=1.5)  # E: `float`
Outcome(content=lambda page: f"{page}")  # E: (page: int)
Rejected(status_code=400)  # E: Missing argument `message`
