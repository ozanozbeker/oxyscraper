"""`dry_run` and `DryRun`, which list the jobs a run would submit with no credentials and no request."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from oxyscraper._payloads import Payload, _redacted

if TYPE_CHECKING:
    from collections.abc import Iterable


@dataclass(frozen=True, kw_only=True)
class DryRun:
    """The jobs a run would submit.

    Attributes
    ----------
    jobs
        Each job's body, with the credentials in `storage_url` replaced by `redacted:redacted`.
    max_results
        The most results the jobs can bill: the sum of their `pages`, with 1 for a job without it.
        Faulted jobs bill nothing, and a source that ignores `pages` bills 1, so a run can bill less.
    """

    jobs: list[dict[str, Any]]
    max_results: int

    @property
    def job_count(self) -> int:
        """The number of jobs."""
        return len(self.jobs)


def dry_run(payloads: Payload | Iterable[Payload]) -> DryRun:
    """List the jobs that a run of `payloads` would submit, and the most results they can bill.

    It sends no request and needs no credentials.
    oxy never reads the account's remaining results, so a caller who wants a spending limit compares `max_results` with their own.

    Examples
    --------
    ```python
    import oxyscraper as oxy

    report = oxy.dry_run(
        oxy.Payload(source="universal", url="https://example.com", pages=2)
    )
    print(report.job_count, report.max_results)  # 1 2
    ```
    """
    listed = [payloads] if isinstance(payloads, Payload) else list(payloads)
    jobs = [_redacted(payload.model_dump()) for payload in listed]
    return DryRun(jobs=jobs, max_results=sum(job.get("pages", 1) for job in jobs))
