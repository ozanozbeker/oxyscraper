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

fields: oxy.ParsingInstructions = {
    "title": {"_on_error": "warn", "_fns": [{"_fn": "xpath_one", "_args": "//h1"}]},
    "items": {"_fns": [{"_fn": "css", "_args": [".item"]}], "_items": {}},
}
pipeline: list[oxy.ParsingFunction] = [
    {"_fn": "xpath", "_args": ["//p/text()"]},
    {"_fn": "regex_search", "_args": ["{(.*)}", 1]},
    {"_fn": "select_nth", "_args": -1},
    {"_fn": "join"},
]
actions: list[oxy.BrowserInstruction] = [
    {"type": "click", "selector": {"type": "css", "value": "a"}, "on_error": "skip"},
    {"type": "fetch_resource", "filter": "/api"},
]
parsed = oxy.Payload(
    source="universal",
    url=URL,
    render="html",
    parse=True,
    parsing_instructions=fields | {"price": {"_fns": pipeline}},
    browser_instructions=actions,
)
assert_type(parsed.parsing_instructions, oxy.ParsingInstructions | None)
assert_type(parsed.browser_instructions, list[oxy.BrowserInstruction] | None)
pipeline.append({"_fn": "XPATH", "_args": ["//a"]})  # E: not assignable
pipeline.append({"_fn": "select_nth", "_args": "1"})  # E: not assignable
fields["title"] = {"_on_error": "ignore"}  # E: 'ignore'
actions.append({"type": "wait", "wait_time": 5})  # E: not assignable
actions.append({"type": "scroll", "x": 0})  # E: not assignable

report = oxy.dry_run([payload])
assert_type(report, oxy.DryRun)
assert_type(report.jobs, list[dict[str, Any]])
assert_type(report.job_count, int)
assert_type(report.max_results, int)
oxy.dry_run(payload)
oxy.dry_run("universal")  # E: not assignable
