# oxyscraper

oxyscraper is a Python library and CLI for the Oxylabs Web Scraper API.
The glossary uses Oxylabs' own terms in the meanings Oxylabs gives them.

## Language

### Oxylabs

**Job**: One scrape that the API accepts and runs: one source, one query or URL, and one set of parameters.
Each job has an ID and a status.
_Avoid_: task, request, scrape

**Faulted**: The status of a job that Oxylabs could not complete, even after retrying it.
A faulted job bills nothing.
_Avoid_: failed, errored

**Source**: The value of the `source` parameter, which names the scraper that runs a job, such as `amazon_product` or `universal`.
_Avoid_: scraper, endpoint

**Input key**: The parameter that carries a job's input, such as `query`, `url`, `product_id` or `prompt`.
Each source takes exactly one.
_Avoid_: input field, query key

**Target**: A website that Oxylabs has dedicated sources for, such as Amazon or Google.
_Avoid_: site

**Integration method**: How a client submits a job and receives its result: Realtime, Push-Pull or Proxy Endpoint.
_Avoid_: mode, API type

**Realtime**: The integration method that holds one HTTPS connection open until the job's result or an error returns.

**Push-Pull**: The integration method that submits a job in one request, then fetches its status and results in later requests.

**Batch**: One Push-Pull submission of up to 5,000 queries, URLs or prompts that share every other parameter.
Each value becomes its own job.
_Avoid_: bulk request

**Result**: What a job produces for one page, returned by Realtime or fetched from the Push-Pull results endpoint.
Oxylabs bills per result, and only when the website returned 2xx or 4xx.
_Avoid_: response, output

**Output type**: The format of a result: `raw`, `parsed`, `png`, `markdown` or `xhr`.
_Avoid_: format

**Cloud Storage**: The Oxylabs feature that uploads a job's result to the caller's bucket, after the caller grants Oxylabs write access.
_Avoid_: bucket upload

**Upload**: The object that Cloud Storage writes to the caller's bucket for one job, faulted jobs included.
Oxylabs records its outcome as a code in the job's `statuses`.
_Avoid_: delivery, export

### oxy

These terms name parts of oxy's own API, so Oxylabs' docs do not use them.

**Payload**: A pydantic model of one job's parameters, which oxy sends as the body of a submission.
`Payload` itself accepts any source, and each source that someone has worked on has its own subclass, such as `AmazonProduct`.
_Avoid_: spec, request, query

**Session**: The object that submits jobs and polls them in the background, for as long as its `with` block runs.
Leaving the block stops every run that has not finished.
_Avoid_: client, connection

**Run**: The jobs that one `execute` or `stream` call submits, which oxy returns as each job finishes.
_Avoid_: result, which is one page of one job

**Rejection**: An error that the API returns for a payload instead of a job, so nothing bills.
_Avoid_: failed job, invalid job

**Checkpoint**: The jobs that the API accepted for a run that has not finished, each with the payload it came from, kept at a location the caller names.
A rerun with the same checkpoint fetches those jobs instead of submitting their payloads again.
_Avoid_: record, job record, journal, manifest

**Destination**: The location a caller names for a run's results. oxy writes each done job there as one file, named by the job's ID.
_Avoid_: writer, output, sink

**Progress**: The number of a run's payloads in each state, such as pending, done or faulted, at one moment.
After the run ends, it is the run's summary.
_Avoid_: status, which is one job's; stats
