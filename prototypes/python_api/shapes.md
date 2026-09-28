# Four shapes for calling oxy from Python

This file compares four shapes for oxy's Python API, for [Prototype: calling oxy from Python](https://github.com/ozanozbeker/oxyscraper/issues/11).
Every shape covers the same scenarios on the same core.
The maintainer chose SQLModel, with a generic model for sources that have no model of their own, and `oxy_prototype.py` and `tour.py` now run that shape.
The mocks below stay as they were written, so the other three shapes have not run.
The prototype names the run handle `Run`, not `Result`, because the glossary's Result is one page of one job.

## Summary

| Concern | Original | DB-API | SQLAlchemy | SQLModel |
| --- | --- | --- | --- | --- |
| One job | `client.run_job(...)` | `conn.execute(...).fetchone()` | `conn.execute(stmt).one()` | `session.execute(model).one()` |
| Many jobs | `client.run_jobs(query=[...])` | `conn.executemany(...)` | `conn.execute(stmt)` | `session.execute([...])` |
| Per-job parameters | One call per group | A list of mappings | A list of mappings | A list of models |
| A handle for the run | None | The cursor | The `Result` | The `Result` |
| Dry run | `oxy.dry_run(...)` | `oxy.dry_run(...)` | `print(stmt)` | `oxy.dry_run([...])` |
| oxy's own options | Keywords, beside the API's parameters | Keywords, beside a mapping of parameters | `execution_options` | Keywords, beside a model |
| Sync lifecycle | None | `with oxy.connect()` | `with engine.connect()` | `with oxy.Session()` |
| Async precedent | None | None in PEP 249 | `create_async_engine` | `AsyncSession` |
| A misspelt parameter | Bills, with no effect | Bills, with no effect | Bills, with no effect | Raises before billing |

"How are parameters typed?" can add checks for a misspelt parameter to any shape.

## Two constraints that separate the shapes

The scratch runs for this ticket measured both.

- **Background work needs a scope.**
  An async generator that yields inside a task group breaks when the caller stops early: asyncio leaks a `CancelledError`, and trio raises `TrioInternalError`.
  The original's `run_jobs` is such a generator, so it runs no work while the caller's loop body runs.
  A connection or session opened with `with` bounds a task group, so oxy can submit and poll while the caller handles each job.
- **An open blocking portal blocks interpreter exit.**
  The sync client runs the async core through anyio's blocking portal.
  The original opens a portal per call, so it needs no `close()`, but it reuses no connection between calls.
  The other shapes keep one portal open for the `with` block, and a connection opened without `with` has to be closed.

## The original

```python
import oxyscraper as oxy

client = oxy.Client(username=USERNAME, password=PASSWORD)
# Tests pass transport=httpx2.MockTransport(handler).

# One job
job = client.run_job("amazon_product", query="B07FZ8S74R", parse=True)
print(job.status, job.content)

# Many jobs that share parameters, each as it finishes
for job in client.run_jobs("amazon_product", query=asins, parse=True):
    if job.status == "done":
        save(job.input, job.content)

# Per-job parameters take one call per group
for domain, group in asins_by_domain.items():
    for job in client.run_jobs("amazon_product", query=group, domain=domain):
        save(job.input, job.content)

# Realtime
job = client.run_job("amazon_product", query="B07FZ8S74R", realtime=True)

# Dry run, with no credentials
report = oxy.dry_run("amazon_product", query=asins, parse=True)
print(report.job_count, report.max_results)

# Fetch by ID, for the CLI's status and fetch commands and for resume
job = client.fetch("7508980357849459714")


# Async, on asyncio or trio
async def main() -> None:
    async with oxy.AsyncClient(username=USERNAME, password=PASSWORD) as client:
        async for job in client.run_jobs("amazon_product", query=asins):
            save(job.input, job.content)
```

Pros:

- It has the fewest names, and one job takes one call.
- Parameters are plain keyword arguments, and a list under the input key mirrors Oxylabs' batch payload.
- The sync client holds no resources, so it needs no `with` and no `close()`.

Cons:

- `run_jobs` returns a bare iterator, so no object holds the run's summary, its rejected values or its pending job IDs.
- Per-job parameters need one call per group.
- oxy's own options share the keyword namespace with the API's parameters, so a future Oxylabs parameter named `realtime` would collide.
- The dry run repeats the call's arguments.
- `run_jobs` submits nothing until the loop starts, and no work runs while the loop body runs.

## DB-API

```python
import oxyscraper as oxy

conn = oxy.connect(username=USERNAME, password=PASSWORD)
# Tests pass transport=httpx2.MockTransport(handler).

# One job
job = conn.execute("amazon_product", {"query": "B07FZ8S74R", "parse": True}).fetchone()

# Many jobs, each as it finishes; the mappings can differ, which covers per-job parameters
rows = [{"query": asin, "domain": domain, "parse": True} for asin, domain in pairs]
cur = conn.executemany("amazon_product", rows)
for job in cur:
    save(job.input, job.content)

# Or in chunks for a writer
cur = conn.executemany("amazon_product", rows)
while chunk := cur.fetchmany(100):
    write(chunk)

# Realtime
job = conn.execute("amazon_product", {"query": "B07FZ8S74R"}, realtime=True).fetchone()

# Dry run: PEP 249 has none, so it stays a function
report = oxy.dry_run("amazon_product", rows)

# Fetch by ID
job = conn.fetch("7508980357849459714")

# Errors take PEP 249's names
try:
    conn.execute("amazon_product", {"query": "B07FZ8S74R"}).fetchone()
except oxy.ProgrammingError:  # 400, such as an invalid parameter
    ...
except oxy.OperationalError:  # 401, 429, 5xx and network errors
    ...

conn.close()


# Async, in psycopg 3's style
async def main() -> None:
    async with await oxy.AsyncConnection.connect(
        username=USERNAME, password=PASSWORD
    ) as conn:
        cur = await conn.executemany("amazon_product", rows)
        async for job in cur:
            save(job.input, job.content)
```

Pros:

- Anyone who has used `sqlite3` or psycopg knows the verbs.
- `executemany` with a list of mappings covers per-job parameters, and oxy groups the mappings that share every parameter but the input into batches.
- Each call returns its own cursor, which is a handle for the run, and `fetchmany(n)` returns fixed-size chunks for a writer.
- PEP 249's exception names give "How does oxy handle each kind of failure?" a hierarchy that users already catch.
- The API's parameters sit in a mapping, so oxy's own options can be keywords without a collision.

Cons:

- PEP 249 leaves the results of `executemany` undefined, so oxy defines them itself.
- `commit`, `rollback`, `description` and `callproc` mean nothing here, because a submitted job bills and has no rows.
- PEP 249 has no async standard, so the async API copies one driver's style.
- It has no statement object, so the dry run repeats the call's arguments.
- Parameters move from keyword arguments into mappings.

## SQLAlchemy

```python
import oxyscraper as oxy

# Statements: what to run, built with no credentials and no request
one = oxy.submit("amazon_product", query="B07FZ8S74R", parse=True)
many = oxy.submit("amazon_product", query=asins, parse=True)
print(many)  # The dry run: the job count, the most results it can bill, each payload

engine = oxy.create_engine(username=USERNAME, password=PASSWORD)
# Tests pass transport=httpx2.MockTransport(handler).

with engine.connect() as conn:
    # One job
    job = conn.execute(one).one()

    # Many jobs, each as it finishes
    for job in conn.execute(many):
        save(job.input, job.content)

    # Per-job parameters: the statement holds the shared ones, the list the rest
    rows = [{"query": asin, "domain": domain} for asin, domain in pairs]
    for job in conn.execute(oxy.submit("amazon_product", parse=True), rows):
        save(job.input, job.content)

    # oxy's own options stay apart from the API's parameters
    job = conn.execute(one.execution_options(realtime=True)).one()

    # Chunks for a writer
    for chunk in conn.execute(many).partitions(100):
        write(chunk)

    # Fetch by ID, and resume from the job record
    job = conn.execute(oxy.fetch("7508980357849459714")).one()
    for job in conn.execute(oxy.fetch(pending_ids)):
        save(job.input, job.content)


# Async, on asyncio or trio: execute buffers, stream yields each job as it finishes
async def main() -> None:
    engine = oxy.create_async_engine(username=USERNAME, password=PASSWORD)
    async with engine.connect() as conn:
        job = (await conn.execute(one)).one()
        async for job in await conn.stream(many):
            save(job.input, job.content)
```

Pros:

- The statement separates what to run from running it.
  Printing it is the dry run, the job record can store it, and the CLI builds the same object from its arguments.
- `oxy.fetch(ids)` makes status, fetch and resume one more statement, so they return the same `Result`.
- `execution_options` keeps oxy's options apart from the API's parameters, with no collision and no mappings.
- The engine holds only settings, so it is safe to build at import time, and `with engine.connect()` bounds the portal, the connection pool and any background work.
- SQLAlchemy's `create_async_engine` and `stream()` give the async API a design to copy, and `stream()` runs inside the connection's scope.
- A list of mappings covers per-job parameters, and `Result` gives `one()`, `all()`, `first()` and `partitions()`.

Cons:

- One job takes the most lines: a statement, an engine, a connection and a call.
- It has the most names to build and document: statement, engine, connection, result and their async twins.
- "Engine" and "statement" come from SQL and appear nowhere in Oxylabs' docs, so the glossary has to define them.
- Async has two calls, `execute` to buffer and `stream` to yield as jobs finish.

## SQLModel

```python
import oxyscraper as oxy
from oxyscraper.sources import AmazonProduct

# Models: one class per source
spec = AmazonProduct(query="B07FZ8S74R", parse=True, geo_location="90210")
# ValidationError before billing
AmazonProduct(query="B07FZ8S74R", geo_loaction="90210")
# An unknown parameter still reaches the API
AmazonProduct(query="B07FZ8S74R", extra={"new_param": 1})

with oxy.Session(username=USERNAME, password=PASSWORD) as session:
    # Tests pass transport=httpx2.MockTransport(handler).
    job = session.execute(spec).one()

    # Many jobs; models can differ, and oxy batches the ones that share parameters
    specs = [AmazonProduct(query=asin, domain=domain) for asin, domain in pairs]
    for job in session.execute(specs):
        save(job.input, job.content)

    job = session.execute(spec, realtime=True).one()
    job = session.get("7508980357849459714")  # fetch by ID, like Session.get

print(oxy.dry_run(specs))


# Async
async def main() -> None:
    async with oxy.AsyncSession(username=USERNAME, password=PASSWORD) as session:
        async for job in await session.stream(specs):
            save(job.input, job.content)
```

Pros:

- A misspelt or mistyped parameter raises before anything is billed.
  The API leaves an unknown key out of the job and still bills it, so only a check before submission reports the mistake.
- An editor completes each source's parameters, and each model documents its source.
- A list of models covers per-job parameters.

Cons:

- 123 sources need a model each.
  The docs name the wrong source on seven pages, and the SDK differs from them on 33 of 120 sources, so only billed runs can check a model.
- A new Oxylabs parameter needs a release, or `extra=` until one ships.
- It needs pydantic for validation, which "What does oxy depend on, and what goes in extras?" decides.
- Results stay untyped, because models for parsed content are out of scope, so the models cover only the request.
- It answers "How are parameters typed?" more than it answers this ticket: a model can build the same statement as `oxy.submit()`, so models can build statements for the SQLAlchemy shape later without changing a call.
