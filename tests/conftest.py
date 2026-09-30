from collections.abc import Iterator

import pytest
from trio.testing import MockClock

from oxyscraper.testing import FakeOxylabs


@pytest.fixture(autouse=True)
def fake() -> Iterator[FakeOxylabs]:
    """Switch on a fake for every test, so no test reaches Oxylabs."""
    with FakeOxylabs() as fake:
        yield fake


@pytest.fixture(params=["asyncio", "trio"])
def anyio_backend(request: pytest.FixtureRequest) -> object:
    """Run each async test on asyncio, and on trio with a clock that skips every wait."""
    if request.param == "trio":
        return "trio", {"clock": MockClock(autojump_threshold=0)}
    return request.param
