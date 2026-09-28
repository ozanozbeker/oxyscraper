# oxyscraper

oxyscraper is a Python library and CLI for the Oxylabs Web Scraper API.
The glossary uses Oxylabs' own terms in the meanings Oxylabs gives them.

## Language

### Oxylabs

**Job**: One scrape that the API accepts and runs: one source, one query or URL, and one set of parameters.
Each job has an ID and a status.
_Avoid_: task, request, scrape

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
