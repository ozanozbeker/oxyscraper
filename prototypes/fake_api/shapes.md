# Calling shapes for the fake Oxylabs API

This file compares the shapes a test could use to drive `oxyscraper.testing.FakeOxylabs`, for [Prototype: the fake Oxylabs API](https://github.com/ozanozbeker/oxyscraper/issues/48).
`testing.py` and `tour.py` run the first shape under each heading.
The other shapes below have not run.

## Summary

| Concern | Built | Declined |
| --- | --- | --- |
| What a job does | `FakeOxylabs(outcome)`, where `outcome` is an `Outcome` or a function of the payload | Magic inputs, rules registered on the fake, a list in submission order |
| A rejection | The API's own free checks, and `Rejected(message)` from the function | A `status="rejected"` on `Outcome` |
| A 429, a 5xx, a network error | `fake.fail(error, on=, times=, message=)` | A handler hook, fields on `Outcome` |
| Cloud Storage | `Outcome(upload=, upload_after=)` | A 10001 that the fake derives from two equal object names |
| A job that stays pending | `Outcome(after=math.inf)` | A `"pending"` status |
| Jobs between sessions | The fake holds them, and httpx2's `aclose()` changes nothing | A file, as the CLI prototype used |
| The switch | `with FakeOxylabs() as fake:` | `oxy.testing.override(fake)`, an environment variable, a pytest plugin |
| A guard against real requests | None: an autouse fixture opens a fake for every test | `oxyscraper.testing.ALLOW_REQUESTS = False` |
| Reading back | `fake.requests` and `fake.jobs` | A typed record per job |
| Time | `anyio.current_time()`, counted from the fake's first request | `time.monotonic()` |

The public names are `FakeOxylabs`, `Outcome` and `Rejected`.

## What the prototype measured

The runs used httpx2 2.13.1, anyio 4.15.1, trio 0.34.0 and pydantic 2.13.5 on Python 3.11.
No request reached Oxylabs.

- **`aclose()`.** httpx2 calls `aclose()` on a transport it was given, each time a client closes.
  Two clients on one fake called it twice.
  `FakeOxylabs` keeps the base class's empty `aclose()`, so a second session reads the first one's jobs.
- **Timeouts.** httpx2's timeouts never run against the fake.
  A transport that slept 600 seconds under a 5-second timeout returned its response, because httpcore2 applies the timeouts and a custom transport replaces it.
  So a test injects a timeout as an exception, with `fake.fail(httpx2.ReadTimeout("no answer"))`.
- **The mock clock.**
  Scenario 4 waits for the 10-minute pending limit in 0.25 seconds of real time.
  Scenario 9 moves the clock 75 minutes in the same time.
- **Sync sessions.**
  A sync Push-Pull run whose job finishes at once took 1.14 seconds, because the first status check comes 1 second after the submission.
  The same run with `realtime=True` took 0.00 seconds, and so did `session.get`.
  So each Push-Pull test through `Session` costs at least a second.
- **A sync session on the mock clock.**
  `start_blocking_portal("trio", {"clock": MockClock(autojump_threshold=0)})` ran the same sync run in 0.02 seconds, and the pending limit in 0.26 seconds.
  A loop body that slept 0.3 seconds a job still received every job.
  This needs trio where the tests run, and it moves the session from asyncio to trio.
- **Where the switch can live.**
  A `ContextVar` set in the caller's thread reached the coroutines that a blocking portal ran.
  A `ContextVar` set in one Quarto cell was still set in the next cell, under Quarto 1.10.18, ipykernel 7.4.0 and IPython 9.17.1.
  So a module global and a `ContextVar` both work for a test and for a docs page.
  In a `ThreadPoolExecutor` thread and in a `threading.Thread`, the `ContextVar` read its default, and the module global reached the session built there.

## What the fake copies from the API

Each rule comes from `docs/research/`.

- An unknown source returns 400, and a batch for one returns 202 with one error per value.
- A missing or empty input returns 400, or an entry in a batch's `errors`.
- A `url` with no host, with an IP address, or under `.invalid`, `.test` or `.example` returns 400.
- A list under `product_id`, `video_id`, `channel_handle` or `category_id` returns 400.
- A batch for a source that takes none returns 202 with no jobs.
- A submission that does not fit a limit returns 429 as a whole, and takes nothing.
- Realtime returns 422 for an LLM source, 400 for `storage_url`, 200 for a faulted job, and 408 after 160 seconds for a job that runs past 150.
- The status and results endpoints return 404 for a Realtime job's ID.
- The results endpoint returns 204 for a pending job and for expired results, and `x-oxylabs-job-status` tells them apart.
- The job object leaves out a key that the API does not know.
- `storage_url` resolves at submission, with its credentials replaced by `redacted:redacted`.

The prototype leaves out the content endpoint, which oxy never calls, and each source's own job object.
It knows 31 sources, and the real fake lists all 123.

## What a job does

### Built: a function of the payload

```python
from oxyscraper.testing import FakeOxylabs, Outcome, Rejected

FakeOxylabs()  # every job finishes at once
FakeOxylabs(Outcome(after=2))  # every job takes 2 seconds
FakeOxylabs(Outcome(status="faulted"))  # every job faults


def outcome(payload: dict[str, Any]) -> Outcome | Rejected:
    match payload["query"]:
        case "B0FAULT001":
            return Outcome(status="faulted", after=17)
        case "B0GONE0001":
            return Outcome(status_code=404, content="<html>Not found</html>")
        case "B0WRONG001":
            return Rejected(
                "Parameter `geo_location` with value `United States` is not valid."
            )
    return Outcome(content=json.loads(FIXTURE.read_text()))


fake = FakeOxylabs(outcome)
```

The function receives one job's payload as the API received it, so a batch calls it once per value.
The same two cases are `TestModel` and `FunctionModel` in pydantic-ai.

Pros:

- One argument covers every case, and a type checker reads `Outcome`'s fields.
- The payload decides, so the order of submissions does not matter.
  oxy groups payloads into batches, so a test cannot predict that order.
- A closure changes the outcome between two runs, such as a payload that faults once.

Cons:

- The payload is a `dict` in the API's shape, so `sort_by` sits inside `context`.
- A test that faults one input still writes a function.

### Declined: magic inputs

```python
fake = FakeOxylabs()
session.execute(oxy.Universal(url="https://sandbox.oxylabs.io/FAULT"))
session.execute(oxy.Universal(url="https://sandbox.oxylabs.io/SLOW"))
```

Both earlier prototypes used this shape.

Pros:

- It needs no access to the fake, so it works through the CLI's stdin and in a docs page.

Cons:

- Each magic word becomes public API, and it cannot carry content, a delay or an upload code.
- An `AmazonProduct` takes a 10-character ASIN, so the word has to fit the model's pattern.
- A reader of the test sees no reason for the fault.

### Declined: rules registered on the fake

```python
fake = FakeOxylabs()
fake.when(query="B0FAULT001").fault(after=17)
fake.when(source="universal").done(content="<html>fixture</html>", after=2)
```

respx and pytest-httpx use this shape for HTTP responses.

Pros:

- Each rule reads as one statement.

Cons:

- The matcher and its methods add about six public names.
- Two rules that match one payload need a documented order.
- Every rule is a function of the payload, which the built shape takes directly.

### Declined: a list in submission order

```python
fake = FakeOxylabs(jobs=[Outcome(), Outcome(status="faulted"), Outcome(after=600)])
```

Cons:

- oxy decides the order of submissions, so the second outcome reaches a payload that the test cannot name.

### Content for several results

`Outcome.content` takes one value for every result, or a function of the page and the output type.

```python
Outcome(content={"title": "Anker USB C Cable"})
Outcome(content=lambda page, type: FIXTURES[page, type])
```

The payload sets the pages, and `output_types=` sets the types, as they do on the API.
`bytes` content goes out as Base64 text, so a `png` fixture comes back as the same bytes.

## A 429, a 5xx and a network error

### Built: `fail`

```python
fake.fail(429, on="submit", times=2)
fake.fail(503, on="results")
fake.fail(httpx2.ReadTimeout("no answer"), on="status")
fake.fail(503, times=None)  # an outage
fake.fail(
    429, on="submit", message="Access to www.amazon.com has been limited to 1 req/s ..."
)
fake.fail(401, times=None)  # a wrong password
```

A failure belongs to a request, not to a job: one 429 answers a batch of 50 values.
So it stays out of `Outcome`.

Not built: a submission that creates its job and then loses the response.
A test sees no difference in how oxy retries it, only a second job in `fake.jobs`.

### Declined: a handler hook

```python
codes = iter([429, 429])


def handler(request: httpx2.Request) -> httpx2.Response | None:
    if request.method == "POST" and (code := next(codes, None)):
        return httpx2.Response(code)
    return None


fake = FakeOxylabs(intercept=handler)
```

Pros:

- It adds one argument, and it has `MockTransport`'s shape.

Cons:

- Every test writes its own counter, and builds the API's error body by hand.
- A caller who tests a Dagster asset has to learn httpx2.

## The switch

### Built: the fake is the `with` block

```python
def test_asset_writes_each_job() -> None:
    with FakeOxylabs(outcome) as fake:
        materialize([amazon_products])  # builds its own Session
    assert len(fake.jobs) == 3


def test_cli_prints_each_job() -> None:
    with FakeOxylabs():
        result = CliRunner().invoke(
            app, ["run", "universal", "https://sandbox.oxylabs.io/"]
        )
```

Every `Session` and `AsyncSession` built inside the block, without `transport=`, uses the fake.
An explicit `transport=` wins.
`responses.RequestsMock`, respx and moto's `mock_aws` have this shape.

A docs page has no block that spans its cells, so its hidden setup cell uses the standard library:

```python
# | include: false
from contextlib import ExitStack
from oxyscraper.testing import FakeOxylabs

ExitStack().enter_context(FakeOxylabs())
```

The switch is a module global, so it also reaches a session that another thread builds.

### Declined: `override`

```python
fake = FakeOxylabs()
with oxy.testing.override(fake):
    ...
```

In pydantic-ai, `agent.override(model=TestModel())` has this shape, but it is a method of the object it changes.
No such object exists in oxy, so `override` would be a fourth public name that only enters the fake.

### Declined: an environment variable

```sh
OXY_FAKE=1 oxy run universal https://sandbox.oxylabs.io/
```

It is the only switch that reaches a subprocess, such as a docs page that runs the CLI in a shell cell.
It cannot carry an outcome, so it needs magic inputs as well.
`CliRunner` runs the CLI in the test's process, so oxy's own tests do not need it.

### Declined: a pytest plugin

A `pytest11` entry point would give every environment with oxyscraper a `fake_oxylabs` fixture.
The fixture is three lines in a caller's `conftest.py`, and the plugin would load in every pytest run.

## A guard against real requests

### Built: none

```python
@pytest.fixture(autouse=True)
def fake() -> Iterator[FakeOxylabs]:
    with FakeOxylabs() as fake:
        yield fake
```

With this fixture, no session in a test reaches Oxylabs, and a test reads the same fixture to set outcomes.
In pydantic-ai, an override belongs to one agent, so it needs `ALLOW_MODEL_REQUESTS` as well.
The switch in oxy covers the process, so the fixture is the guard.

### Declined: a flag

```python
oxyscraper.testing.ALLOW_REQUESTS = False
```

It would raise where the fixture above answers, and it adds a module global that a test sets by assignment.

## Reading back

```python
assert [job["query"] for job in fake.jobs] == ["B07FZ8S74R", "B08N5WRWNW"]
assert fake.requests[0].url.path == "/v1/queries/batch"
```

`fake.jobs` holds each job object as its submission returned it, so it needs no type of its own.
`fake.requests` holds httpx2's `Request` objects.

## Time

The fake counts seconds from its first request, on the clock of the backend that runs it.
Job IDs count up from `7500000000000000001`, and `created_at` counts from 2026-01-01.
So the same requests return the same bytes, and a docs page renders the same output on every build.

Two sessions share the fake's times only while they share a clock.
Two sync sessions do, because asyncio reads the machine's monotonic clock.
Each trio run has its own clock, so two trio runs do not.

## For other tickets

- [How does oxy schedule submissions and status checks?](https://github.com/ozanozbeker/oxyscraper/issues/14) sends each source's first payloads as a batch.
  A list under `product_id`, `video_id`, `channel_handle` or `category_id` returns 400, and [How does oxy handle each kind of failure?](https://github.com/ozanozbeker/oxyscraper/issues/13) turns a 400 on a batch into a rejection of every payload in it.
  So oxy batches only `query`, `url` and `prompt`, as the stand-in does.
- [How is oxy tested, with and without spending credits?](https://github.com/ozanozbeker/oxyscraper/issues/23) runs `Session` tests on real time, where each Push-Pull run takes at least a second.
