"""Code a caller writes against sessions, which `pyrefly check --expectations` checks."""

from datetime import datetime
from typing import Any, Literal, assert_type

import oxyscraper as oxy

payload = oxy.Payload(source="universal", url="https://example.com")

with oxy.Session(username="USERNAME", password="PASSWORD") as session:  # noqa: S106
    run = session.execute([payload], output_types=["raw", "png"])
    assert_type(run, oxy.Run)
    assert_type(run.one(), oxy.Job)
    assert_type(run.all(), list[oxy.Job])
    for jobs in run.partitions(10):
        assert_type(jobs, list[oxy.Job])
    job = session.get("7500000000000000001")
    assert_type(job.status, Literal["pending", "done", "faulted"])
    assert_type(job.finished_at, datetime | None)
    assert_type(job.payload, oxy.Payload | None)
    assert_type(job.upload, oxy.Upload | None)
    assert_type(job.content, str | bytes | dict[str, Any] | list[Any])
    assert_type(job.results[0].type, Literal["raw", "parsed", "png", "markdown", "xhr"])
    session.execute(payload, output_types=["html"])  # E: output_types

oxy.Session(username="USERNAME")  # E: Missing argument `password`
oxy.Session("USERNAME", password="PASSWORD")  # noqa: S106  # E: passed by name


async def stream() -> None:
    async with oxy.AsyncSession(username="USERNAME", password="PASSWORD") as session:  # noqa: S106
        run = await session.stream(payload)
        assert_type(run, oxy.AsyncRun)
        async for job in run:
            assert_type(job, oxy.Job)
        assert_type(await run.all(), list[oxy.Job])
        assert_type(await session.execute(payload), oxy.Run)
