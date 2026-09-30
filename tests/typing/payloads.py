"""Code a caller writes against payloads, which `pyrefly check --expectations` checks."""

from typing import Any, Literal, assert_type

import oxyscraper as oxy

URL = "https://example.com"

payload = oxy.Payload(source="walmart_product", product_id="436012154", store_id="1")
assert_type(payload.source, str)
assert_type(payload.product_id, str | None)
assert_type(payload.render, Literal["html", "png", ""] | None)
assert_type(payload.storage_type, Literal["gcs", "s3", "tos", "s3_compatible"] | None)
assert_type(payload.pages, int | None)
assert_type(payload.extra, dict[str, Any])
assert_type(payload.model_dump(), dict[str, Any])
assert_type(oxy.SOURCES, tuple[type[oxy.Payload], ...])

oxy.Payload(
    source="universal",
    url=URL,
    user_agent_type="desktop_safari",
    context=[{"key": "force_headers", "value": True}],
    extra={"new_param": [1, 2]},
)
oxy.Payload(source="universal", url=URL, render="htm")  # E: 'htm'
oxy.Payload(source="universal", url=URL, user_agent_type="dektop")  # E: 'dektop'
oxy.Payload(source="universal", url=URL, storage_type="azure")  # E: 'azure'
oxy.Payload(url=URL)  # E: Missing argument `source`
payload.url = URL  # E: Cannot set field `url`

report = oxy.dry_run([payload])
assert_type(report, oxy.DryRun)
assert_type(report.jobs, list[dict[str, Any]])
assert_type(report.job_count, int)
assert_type(report.max_results, int)
oxy.dry_run(payload)
oxy.dry_run("universal")  # E: not assignable
