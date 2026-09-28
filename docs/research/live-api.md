# What a live test shows about the job lifecycle

This note records what a small billed run against the live Oxylabs API showed about the job lifecycle.
It answers [What does a live test show about the job lifecycle?](https://github.com/ozanozbeker/oxyscraper/issues/9).
Its questions are the open questions in [What the docs state about the job lifecycle](job-lifecycle.md).
The run took place on 2026-09-24, on an account with the Starter plan.
Its jobs ran from 20:02 to 21:01 UTC, and its reads of Usage Statistics went on to 21:31 UTC.
It spent 13 results, 2 of them rendered.

The billed jobs used `universal` on Oxylabs' practice site, `https://sandbox.oxylabs.io/`, and `amazon_search`.
Free comparison jobs, called fault jobs below, used hosts that do not resolve.
The API rejects `.invalid`, `.test` and `.example` hosts and IP addresses at submission.
So each fault job used its own unregistered `.com` name, such as `https://oxy-fault-4-q7x2k9.com/`.
Of 177 fault jobs, 174 ended `faulted` and 3 ended `done` and were billed, as [Fault jobs](#fault-jobs) describes.

The samples replace the account's client ID with `123456`, its username with `USERNAME`, and the UUID inside rate-limit header names with the nil UUID.
Every other value is what the API returned, except where a placeholder or `"...": "..."` marks a cut.
The raw captures stay outside the repo.

## Answer

The run settles most of the open questions on rate limits, submission, results, Realtime and Usage Statistics.
It contradicts the docs on the 422 code, the Realtime response body, the content endpoint's page numbers and the Usage Statistics fields.

- **Rate limit.**
  Push-Pull submissions, batches and Realtime share one limit of 50 jobs per second, which matches Starter ([Rate Limits][rate-limits]).
  A rendered job also counts against a second limit of 13.
  A window opens at the first submission and lasts about one second.
  `-remaining` recovers with time, even while earlier jobs are still `pending`.
- **Headers.**
  Every accepted submission returns `x-ratelimit-total-requests-<uuid>-limit` and `-remaining`.
  A rendered one adds `x-ratelimit-total-render-requests-<uuid>-limit` and `-remaining`.
  No response carries `Retry-After` or a reset header, including a 429.
  Status and results GETs carry no rate-limit headers, and 110 of them in 10 seconds returned no 429.
- **Counting.**
  Each value of a batch and each page of a `pages: 2` job takes 1 from `-remaining`.
  A submission that returns 400 or 429 takes nothing.
  A batch larger than `-remaining` returns 429 for the whole batch and creates no job.
- **Submission codes.**
  Push-Pull submissions and batches return `202 Accepted`.
  Realtime returns `200 OK`, also for a faulted job.
  A batch with an invalid value returns 202, creates jobs for the valid values, and lists the invalid ones under `errors`.
- **Faulted jobs.**
  A faulted job keeps `statuses` empty, and 613 appears only as the `status_code` of its one results entry.
  The results endpoint returns 200 with empty `content`.
  The content endpoint returns 204, as it does for a pending job.
  Only an undocumented `x-oxylabs-job-status` header distinguishes the two.
- **Pages.**
  A `pages: 2` job produces two billed results.
  A page past the last one returned 200 with Amazon's "No results" page, so its job ended `done` and billed both pages.
  The content endpoint takes the page number itself, such as 20 and 21 for `start_page: 20`.
  For that job, pages 1, 2 and 3 returned 204.
- **Realtime.**
  A Realtime response carries a `job` object and an `x-oxylabs-job-id` header.
  The docs' Realtime sample shows no `job` object.
  The status and results endpoints return 404 for that job ID.
  A job that ran past the 150-second TTL returned 408 after 160 seconds, with no job ID.
  Usage Statistics never counted it.
- **Errors.**
  Error bodies carry a top-level `message`, and most add `instance`, `timestamp` and `trace_id`.
  Malformed JSON returns 400, not the documented 422.
  An unknown username returns 401 with an empty body.
- **Usage Statistics.**
  `all_count` counts billed results only: faulted jobs, 400s and 429s never appear in it.
  Realtime results count under `mode_callback_count`.
  No field splits parsed results from HTML ones.
  A finished job appeared within 3 minutes, but some reads returned counts from minutes earlier.
  Its days are not Vilnius days: a job that finished at 21:00 UTC counted under the UTC date.
- **Fault jobs.**
  A host that does not resolve does not guarantee a free job.
  3 of 177 such jobs ended `done` with a 200 page from a `lighttpd` server, and billed.

## Runs

Each finding below names the run that produced it.

| Run | Time (UTC) | What it sent | Results billed |
| --- | --- | --- | --- |
| Errors | 20:02 | Calls that return 400, 401 and 404, and one with malformed JSON | 0 |
| Faults | 20:03 to 20:05 | One Push-Pull job, one Realtime job and a 2-value batch, for hosts that do not resolve | 0 |
| Window | 20:06 | 7 fault jobs over 12 seconds | 0 |
| Sandbox | 20:07 | One Push-Pull job, a status poll at 10 per second, a 2-value batch and one Realtime job, with 4 fault jobs | 4 |
| Amazon | 20:09 | Two `amazon_search` jobs with `pages: 2`, each between 4 fault jobs | 4 |
| Render | 20:10 to 20:13 | One `render: png` job between 2 fault jobs, and one Realtime `render: html` job whose browser instructions wait 180 seconds | 1 |
| Burst | 20:14 | A batch of 51 fault URLs, then 51 concurrent fault jobs | 0 |
| Pacing | 20:15 to 20:17 | 101 fault jobs at set spacings, and three sets of 400s between fault jobs | 3 |
| XHR | 21:00 to 21:01 | 10 status GETs, then one `xhr: true` job | 1 |

A loop also read `/v2/stats?group_by=day` every 60 seconds from 20:03.

## Rate limits and headers

### Limits and header names

Every accepted submission returned one limit, and a rendered one returned two.

| Header | Value | Returned on |
| --- | --- | --- |
| `x-ratelimit-total-requests-<uuid>-limit` | `50` | Every accepted Push-Pull, batch and Realtime submission, and every 429 |
| `x-ratelimit-total-requests-<uuid>-remaining` | `49` down to `0` | The same responses |
| `x-ratelimit-total-render-requests-<uuid>-limit` | `13` | The `render: png` and `xhr: true` submissions |
| `x-ratelimit-total-render-requests-<uuid>-remaining` | `12` | The same responses |

Both names carry the same UUID, and it did not change during the run.
The values match Starter's 50 jobs per second and 13 rendered jobs per second ([Rate Limits][rate-limits]).
The docs' example name, `x-ratelimit-internal-api-default-limit`, appeared on no response.
A client has to match the names by prefix and suffix, because the UUID is part of each name.
No response carried `Retry-After` or a reset header.
Responses with 400, 401, 404 and 408 carry no rate-limit headers.

Push-Pull and Realtime share the limit.
In the Sandbox run, a Realtime submission read 48 right after a Push-Pull fault job read 49 in the same window.
A Realtime response carries the value from its submission, not from the moment it returns.
The Faults run's Realtime job returned after 24 seconds and read 47, the value of its submission window.

### The window

The limit counts submissions in a window of about one second, and `-remaining` recovers with time.
In the Window run, three fault jobs within 0.47 seconds read 49, 48 and 47.
A fourth, 0.75 seconds after the third, read 49 while the first three were still `pending`.
So the limit caps a rate, not the number of pending jobs.
The quick start's name for it, a concurrency limit, does not fit ([Quick Start][quick-start]).

The window does not follow wall-clock seconds.
In the Pacing run, 15 submissions 1.25 seconds apart all read 49.
15 submissions 0.6 seconds apart read 48 and 49 in strict alternation.
Wall-clock windows cannot produce that alternation, and neither can a sliding one-second window.
So each window opens at the first submission after the previous window closes.
At 1-second spacing, 60 submissions read 49 or 48 with no pattern, because the API received each one close to the moment the previous window closed.
In the Sandbox run, a submission sent at 20:07:20.04 still read 45, because its window had opened at 20:07:19.04.

### What counts against the limit

| Submission | Change in `-remaining` | Measurement | Run |
| --- | --- | --- | --- |
| One Push-Pull or Realtime job | 1 | Consecutive fault jobs read 49, 48, 47 | Window |
| A batch of 2 values | 2 | A fault job, the batch and a fault job read 49, 47 and 46 | Sandbox |
| A job with `pages: 2` | 2 | Two fault jobs, the job and two fault jobs read 49, 48, 46, 45 and 44, for both jobs | Amazon |
| A rendered job | 1 from each limit | The `png` job read 12 of 13 and 48 of 50 | Render |
| A submission that returns 400 | 0 | A fault job, three 400s and a fault job read 49 and 48, three times | Pacing |
| A batch that returns 429 | 0 | The 429 read 49, and the next submission read 48 | Burst |
| 10 status GETs | 0 | The `xhr` job right after them read 49 | XHR |

### Exceeding the limit

In the Burst run, a batch of 51 fault URLs returned 429 for the whole batch.
It created no job and left `-remaining` at 49.

```text
HTTP/1.1 429 Too Many Requests
date: Thu, 24 Sep 2026 20:14:13 GMT
content-type: application/json
content-length: 173
x-oxylabs-client-id: 123456
x-oxylabs-client-name: USERNAME
x-oxyserps-client-id: 123456
x-oxyserps-client-name: USERNAME
x-ratelimit-total-requests-00000000-0000-0000-0000-000000000000-limit: 50
x-ratelimit-total-requests-00000000-0000-0000-0000-000000000000-remaining: 49

{"message":"Too many requests. (Total Dynamic).","instance":"/v1/queries/batch","timestamp":"2026-09-24T20:14:13.286184145Z","trace_id":"6ab58495-b1e1049bbf37a8620d42629f"}
```

The run then sent 51 single submissions within 9 milliseconds over one HTTP/2 connection.
Fifty returned 202 and one returned 429.
The accepted ones read `-remaining` values from 49 down to 0 with repeats, such as five that read 34.
So the value is not exact under concurrency.
The count itself held, because exactly one of the 51 returned 429.
All 50 jobs ended `faulted` within 40 seconds.
This is the first 429, as HTTP/2 returned it:

```text
HTTP/2 429
date: Thu, 24 Sep 2026 20:14:40 GMT
content-type: application/json
content-length: 167
x-oxylabs-client-id: 123456
x-oxylabs-client-name: USERNAME
x-oxyserps-client-id: 123456
x-oxyserps-client-name: USERNAME
x-ratelimit-total-requests-00000000-0000-0000-0000-000000000000-limit: 50
x-ratelimit-total-requests-00000000-0000-0000-0000-000000000000-remaining: 0

{"message":"Too many requests. (Total Dynamic).","instance":"/v1/queries","timestamp":"2026-09-24T20:14:40.692756408Z","trace_id":"6ab584b0-89e71c2c26378abd3b6860ad"}
```

The run did not exceed the rendered limit, so the body of that 429 is unknown.
No response named a domain, so the domain throttle never returned its 429 during the run ([Rate Limits][rate-limits]).

### Status and results requests

In the Sandbox run, one job received 100 status GETs and 10 results GETs over HTTP/2 in 10 seconds.
Every status GET returned 200, and the results GETs returned 204 twice and then 200 eight times.
None returned 429, and none carried a rate-limit header.
None of the run's 696 GETs on the status, results and content endpoints carried one, and neither did any read of `/v2/stats`.
In the XHR run, a submission right after 10 status GETs read 49, so GETs do not count against the submission limit.

## Submission and batch

### Status codes

| Call | Status line |
| --- | --- |
| Push-Pull submission | `HTTP/1.1 202 Accepted` |
| Batch, including one with invalid values | `HTTP/1.1 202 Accepted` |
| Realtime job that ends `done` or `faulted` | `HTTP/1.1 200 OK` |
| Realtime job past the TTL | `HTTP/1.1 408 Request Timeout` |
| Submission over the limit | `HTTP/1.1 429 Too Many Requests` |
| Invalid parameter or malformed JSON | `HTTP/1.1 400 Bad Request` |

The docs list both 200 and 202 without saying which one a submission returns ([Response Codes][response-codes]).

### Push-Pull submission

A Push-Pull submission returned the job object with `status: pending` in 0.15 to 0.41 seconds.
The median over 130 submissions was 0.17 seconds.
The object holds every parameter with its default, 16 `context` entries, `client_id` as an integer and `id` as a string.
`x-oxylabs-client-name` holds the API username, and `x-oxylabs-client-id` holds the numeric client ID.
On `data.oxylabs.io`, each `x-oxylabs-*` header has an `x-oxyserps-*` twin with the same value.
`_links` URLs use `http://`, as the docs say ([Push-Pull][push-pull]).
This is the Sandbox run's submission in full:

```text
HTTP/1.1 202 Accepted
date: Thu, 24 Sep 2026 20:07:07 GMT
content-type: application/json
content-length: 1850
x-oxylabs-client-id: 123456
x-oxylabs-client-name: USERNAME
x-oxylabs-job-id: 7508980357849459714
x-oxyserps-client-id: 123456
x-oxyserps-client-name: USERNAME
x-oxyserps-job-id: 7508980357849459714
x-ratelimit-total-requests-00000000-0000-0000-0000-000000000000-limit: 50
x-ratelimit-total-requests-00000000-0000-0000-0000-000000000000-remaining: 49
```

```json
{
  "callback_url": null,
  "client_id": 123456,
  "context": [
    {"key": "force_headers", "value": false},
    {"key": "force_cookies", "value": false},
    {"key": "hc_policy", "value": true},
    {"key": "parse_json_schema", "value": null},
    {"key": "parse_json_prompt", "value": null},
    {"key": "successful_status_codes", "value": []},
    {"key": "follow_redirects", "value": null},
    {"key": "cookies", "value": []},
    {"key": "headers", "value": []},
    {"key": "session_id", "value": null},
    {"key": "http_method", "value": "get"},
    {"key": "content", "value": null},
    {"key": "store_id", "value": null},
    {"key": "proxy_location", "value": null},
    {"key": "delivery_location", "value": null},
    {"key": "fulfillment_type", "value": null}
  ],
  "created_at": "2026-09-24 20:07:07",
  "domain": "io",
  "geo_location": null,
  "id": "7508980357849459714",
  "limit": 10,
  "locale": null,
  "pages": 1,
  "parse": false,
  "parser_type": null,
  "parser_preset": null,
  "parsing_instructions": null,
  "browser_instructions": null,
  "render": null,
  "xhr": false,
  "markdown": false,
  "url": "https://sandbox.oxylabs.io/",
  "query": "",
  "source": "universal",
  "start_page": 1,
  "status": "pending",
  "storage_type": null,
  "storage_url": null,
  "aggregate_name": null,
  "subdomain": "sandbox",
  "content_encoding": "utf-8",
  "updated_at": "2026-09-24 20:07:07",
  "user_agent_type": "desktop",
  "session_info": null,
  "statuses": [],
  "client_notes": null,
  "_links": [
    {
      "rel": "self",
      "href": "http://data.oxylabs.io/v1/queries/7508980357849459714",
      "method": "GET"
    },
    {
      "rel": "results",
      "href": "http://data.oxylabs.io/v1/queries/7508980357849459714/results",
      "method": "GET"
    },
    {
      "rel": "results-content",
      "href_list": [
        "http://data.oxylabs.io/v1/queries/7508980357849459714/results/1/content"
      ],
      "method": "GET"
    },
    {
      "rel": "results-html",
      "href": "http://data.oxylabs.io/v1/queries/7508980357849459714/results?type=raw",
      "method": "GET"
    },
    {
      "rel": "results-content-html",
      "href_list": [
        "http://data.oxylabs.io/v1/queries/7508980357849459714/results/1/content?type=raw"
      ],
      "method": "GET"
    }
  ]
}
```

The `amazon_search` submission in the Amazon run returned the same headers, with `-remaining: 46` after two fault jobs.

### Batch

A batch returns `{"queries": [...]}` with one full job object per value, as the docs show ([Push-Pull][push-pull]).
The batch response has no `x-oxylabs-job-id` header.
This is the Sandbox run's 2-value batch:

```text
HTTP/1.1 202 Accepted
date: Thu, 24 Sep 2026 20:07:19 GMT
content-type: application/json
transfer-encoding: chunked
x-oxylabs-client-id: 123456
x-oxylabs-client-name: USERNAME
x-oxyserps-client-id: 123456
x-oxyserps-client-name: USERNAME
x-ratelimit-total-requests-00000000-0000-0000-0000-000000000000-limit: 50
x-ratelimit-total-requests-00000000-0000-0000-0000-000000000000-remaining: 47
```

```json
{
  "queries": [
    {
      "id": "7508980408936054785",
      "status": "pending",
      "source": "universal",
      "url": "https://sandbox.oxylabs.io/products",
      "created_at": "2026-09-24 20:07:19",
      "...": "..."
    },
    {
      "id": "7508980408931885057",
      "status": "pending",
      "source": "universal",
      "url": "https://sandbox.oxylabs.io/products?page=2",
      "created_at": "2026-09-24 20:07:19",
      "...": "..."
    }
  ]
}
```

### A batch with invalid values

In the Faults run, a `url` batch held one fault URL and the value `not a url`.
It returned 202, created a job for the fault URL, and listed the other value under `errors`:

```text
HTTP/1.1 202 Accepted
date: Thu, 24 Sep 2026 20:04:45 GMT
content-type: application/json
content-length: 1933
x-oxylabs-client-id: 123456
x-oxylabs-client-name: USERNAME
x-oxyserps-client-id: 123456
x-oxyserps-client-name: USERNAME
x-ratelimit-total-requests-00000000-0000-0000-0000-000000000000-limit: 50
x-ratelimit-total-requests-00000000-0000-0000-0000-000000000000-remaining: 48
```

```json
{
  "queries": [
    {
      "id": "7508979763290092545",
      "status": "pending",
      "source": "universal",
      "url": "https://oxy-fault-7-q7x2k9.com/",
      "...": "..."
    }
  ],
  "errors": [
    {
      "message": "Parameter `url` is invalid.",
      "url": "not a url"
    }
  ]
}
```

In the Errors run, a batch with an unknown `source` failed on every value and still returned 202.
Its `queries` list is empty, and its `errors` entries carry no `url`:

```text
HTTP/1.1 202 Accepted
date: Thu, 24 Sep 2026 20:02:05 GMT
content-type: application/json
content-length: 94
x-oxylabs-client-id: 123456
x-oxylabs-client-name: USERNAME
x-oxyserps-client-id: 123456
x-oxyserps-client-name: USERNAME
```

```json
{
  "queries": [],
  "errors": [
    {
      "message": "Unsupported source."
    },
    {
      "message": "Unsupported source."
    }
  ]
}
```

## Statuses and results

### A pending job

Right after submission, the status endpoint returned 200 with `status: pending`.
The results and content endpoints returned 204 with an empty body and an `x-oxylabs-job-status` header.
The docs list the 204 but not the header ([Response Codes][response-codes]).

```text
HTTP/1.1 204 No Content
date: Thu, 24 Sep 2026 20:04:45 GMT
content-type: application/json
x-oxylabs-client-id: 123456
x-oxylabs-client-name: USERNAME
x-oxylabs-job-id: 7508979760408563713
x-oxylabs-job-status: pending
x-oxyserps-client-id: 123456
x-oxyserps-client-name: USERNAME
x-oxyserps-job-id: 7508979760408563713
x-oxyserps-job-status: pending
```

In the Sandbox run, a `universal` job on the sandbox site went from submission to `done` in about 2.3 seconds.
The status endpoint returns no rate-limit headers:

```text
HTTP/2 200
date: Thu, 24 Sep 2026 20:07:08 GMT
content-type: application/json
vary: Accept-Encoding
x-oxylabs-client-id: 123456
x-oxylabs-client-name: USERNAME
x-oxylabs-job-id: 7508980357849459714
x-oxyserps-client-id: 123456
x-oxyserps-client-name: USERNAME
x-oxyserps-job-id: 7508980357849459714
content-encoding: gzip
```

### A done job

The results endpoint returned one entry per page, with the job object.
`universal` entries carry `_request`, `_response` and `session_info`, beyond the fields the docs list ([Push-Pull][push-pull]).

```json
{
  "results": [
    {
      "content": "<!DOCTYPE html><html lang=\"en\">CONTENT</html>",
      "created_at": "2026-09-24 20:07:07",
      "updated_at": "2026-09-24 20:07:09",
      "page": 1,
      "url": "https://sandbox.oxylabs.io/",
      "job_id": "7508980357849459714",
      "is_render_forced": false,
      "status_code": 200,
      "type": "raw",
      "_request": {
        "cookies": [],
        "headers": {
          "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWeb...",
          "...": "..."
        }
      },
      "_response": {
        "cookies": [],
        "headers": {
          "Content-Type": "text/html; charset=utf-8",
          "Date": "Thu, 24 Sep 2026 20:07:09 GMT",
          "Server": "cloudflare",
          "...": "..."
        }
      },
      "session_info": {
        "expires_at": null,
        "id": null,
        "remaining": null
      }
    }
  ],
  "job": {
    "id": "7508980357849459714",
    "status": "done",
    "source": "universal",
    "url": "https://sandbox.oxylabs.io/",
    "query": "",
    "created_at": "2026-09-24 20:07:07",
    "updated_at": "2026-09-24 20:07:09",
    "statuses": [],
    "...": "..."
  }
}
```

### A faulted job

All 173 faulted Push-Pull jobs returned the same shape.
The status endpoint returns `status: faulted` with an empty `statuses` list, and `updated_at` holds the fault time.
The results endpoint returns 200 with one entry, whose `status_code` is 613 and whose `content` is an empty string.
The content endpoint returns 204, as it does for a pending job.
On the content endpoint, only `x-oxylabs-job-status` distinguishes a faulted job from a pending one.
No job showed 612.
613 appears only in the results entry: not as an HTTP status, and not in `statuses` ([Response Codes][response-codes]).
Push-Pull fault jobs took 7 to 39 seconds from `created_at` to `updated_at`, with a median of 17.

This is the Faults run's Push-Pull job on the results endpoint:

```text
HTTP/1.1 200 OK
date: Thu, 24 Sep 2026 20:04:59 GMT
content-type: application/json
transfer-encoding: chunked
vary: Accept-Encoding
x-oxylabs-client-id: 123456
x-oxylabs-client-name: USERNAME
x-oxylabs-job-id: 7508979760408563713
x-oxylabs-job-status: faulted
x-oxyserps-client-id: 123456
x-oxyserps-client-name: USERNAME
x-oxyserps-job-id: 7508979760408563713
x-oxyserps-job-status: faulted
content-encoding: gzip
```

```json
{
  "results": [
    {
      "content": "",
      "created_at": "2026-09-24 20:04:44",
      "updated_at": "2026-09-24 20:04:58",
      "page": 1,
      "url": "https://oxy-fault-4-q7x2k9.com/",
      "job_id": "7508979760408563713",
      "is_render_forced": false,
      "status_code": 613,
      "type": "raw",
      "_request": {
        "cookies": null,
        "headers": null
      },
      "_response": {
        "cookies": null,
        "headers": null
      },
      "session_info": {
        "expires_at": null,
        "id": null,
        "remaining": null
      }
    }
  ],
  "job": {
    "id": "7508979760408563713",
    "status": "faulted",
    "source": "universal",
    "url": "https://oxy-fault-4-q7x2k9.com/",
    "query": "",
    "created_at": "2026-09-24 20:04:44",
    "updated_at": "2026-09-24 20:04:58",
    "statuses": [],
    "...": "..."
  }
}
```

The same job on the content endpoint:

```text
HTTP/1.1 204 No Content
date: Thu, 24 Sep 2026 20:04:59 GMT
content-type: application/json
x-oxylabs-client-id: 123456
x-oxylabs-client-name: USERNAME
x-oxylabs-job-id: 7508979760408563713
x-oxylabs-job-status: faulted
x-oxyserps-client-id: 123456
x-oxyserps-client-name: USERNAME
x-oxyserps-job-id: 7508979760408563713
x-oxyserps-job-status: faulted
```

### A job with `pages: 2`

In the Amazon run, `amazon_search` for `usb c cable` with `pages: 2` and `parse: true` returned one job with one `parsed` entry per page.
Both pages returned `status_code: 200` and `parse_status_code: 12000`, and `last_visible_page` was 20.
The job finished 6 seconds after submission.
Parsed entries add `parser_type` and `parser_preset`.
`amazon_search` entries carry no `_request`, `_response` or `session_info`.

```json
{
  "results": [
    {
      "content": {
        "delivery_postcode": "14205",
        "last_visible_page": 20,
        "page": 1,
        "parse_status_code": 12000,
        "query": "usb c cable",
        "refinements": {
          "...": "..."
        },
        "results": {
          "paid": [
            {
              "...": "..."
            }
          ],
          "organic": [
            {
              "asin": "B088NRLMPV",
              "pos": 1,
              "title": "Anker USB C to USB C Cable, 60W Fast Charging Cable (2-Pack, 6 ft, Black)",
              "price": 9.99,
              "currency": "USD",
              "rating": 4.7,
              "reviews_count": 88600,
              "is_sponsored": false,
              "url": "/Anker-Charging-MacBook-Galaxy-Charger/dp/B088NRLMPV/ref=sr_1_1?...",
              "...": "..."
            },
            "..."
          ],
          "suggested": [],
          "amazons_choices": [
            {
              "...": "..."
            }
          ]
        },
        "total_results_count": 70000,
        "url": "https://www.amazon.com/s?k=usb+c+cable&page=1&language=en_US"
      },
      "created_at": "2026-09-24 20:09:27",
      "updated_at": "2026-09-24 20:09:31",
      "page": 1,
      "url": "https://www.amazon.com/s?k=usb+c+cable&page=1&language=en_US",
      "job_id": "7508980946444499969",
      "is_render_forced": false,
      "status_code": 200,
      "type": "parsed",
      "parser_type": "",
      "parser_preset": null
    },
    {
      "...": "..."
    }
  ],
  "job": {
    "id": "7508980946444499969",
    "status": "done",
    "source": "amazon_search",
    "query": "usb c cable",
    "pages": 2,
    "start_page": 1,
    "parse": true,
    "created_at": "2026-09-24 20:09:27",
    "updated_at": "2026-09-24 20:09:33",
    "statuses": [],
    "...": "..."
  }
}
```

### A page past the end

The second Amazon job set `start_page: 20`, `pages: 2` and `parse: false`, so its second page lay past `last_visible_page`.
Both pages returned `status_code: 200`, and the job ended `done` with an empty `statuses` list.
Page 21 holds Amazon's "No results for" page with no search results, and Usage Statistics counts it as a result.
So a page past the end neither fails nor faults the job, and it is billed.

```json
{
  "results": [
    {
      "content": "<!doctype html><html lang=\"en-us\">CONTENT</html>",
      "created_at": "2026-09-24 20:09:35",
      "updated_at": "2026-09-24 20:09:41",
      "page": 20,
      "url": "https://www.amazon.com/s?k=usb+c+cable&page=20&language=en_US",
      "job_id": "7508980980925889537",
      "is_render_forced": false,
      "status_code": 200,
      "type": "raw"
    },
    {
      "content": "<!doctype html><html lang=\"en-us\">CONTENT</html>",
      "created_at": "2026-09-24 20:09:35",
      "updated_at": "2026-09-24 20:09:43",
      "page": 21,
      "url": "https://www.amazon.com/s?k=usb+c+cable&page=21&language=en_US",
      "job_id": "7508980980925889537",
      "is_render_forced": false,
      "status_code": 200,
      "type": "raw"
    }
  ],
  "job": {
    "id": "7508980980925889537",
    "status": "done",
    "source": "amazon_search",
    "query": "usb c cable",
    "pages": 2,
    "start_page": 20,
    "parse": false,
    "created_at": "2026-09-24 20:09:35",
    "updated_at": "2026-09-24 20:09:43",
    "statuses": [],
    "_links": [
      {
        "...": "..."
      },
      {
        "rel": "results-content",
        "href_list": [
          "http://data.oxylabs.io/v1/queries/7508980980925889537/results/20/content",
          "http://data.oxylabs.io/v1/queries/7508980980925889537/results/21/content"
        ],
        "method": "GET"
      },
      {
        "...": "..."
      }
    ]
  }
}
```

### The content endpoint

The content endpoint takes the page number that `href_list` lists, not a position counted from 1.
For the job with `start_page: 20`, `/results/20/content` and `/results/21/content` returned the pages.
`/results/1/content`, `/results/2/content` and `/results/3/content` returned 204 with `x-oxylabs-job-status: done`.
The Push-Pull page says `{n}` starts at 1, which holds only when `start_page` is 1 ([Push-Pull][push-pull]).

The `Content-Type` depends on the output type.

| Output type | `Content-Type` | Body | Run |
| --- | --- | --- | --- |
| `raw` | `text/html` | The page's HTML | Sandbox |
| `parsed` | `application/json` | The parsed object on its own | Amazon |
| `png` | `text/html` | Base64 text that starts with `iVBORw0KGgo` | Render |
| `xhr` | `application/json` | The list on its own, `[]` for the sandbox site | XHR |

The `png` body is Base64 text, not PNG bytes, under a `text/html` header.
The results endpoint returns the same Base64 string in `content`, with `type: png`.
The docs describe `png` content as Base64 ([JS Rendering][js-rendering]).
This is the Render run's `png` job on the content endpoint:

```text
HTTP/1.1 200 OK
date: Thu, 24 Sep 2026 20:11:05 GMT
content-type: text/html
transfer-encoding: chunked
vary: Accept-Encoding
x-oxylabs-client-id: 123456
x-oxylabs-client-name: USERNAME
x-oxylabs-job-id: 7508981262732783617
x-oxylabs-job-status: done
x-oxyserps-client-id: 123456
x-oxyserps-client-name: USERNAME
x-oxyserps-job-id: 7508981262732783617
x-oxyserps-job-status: done
content-encoding: gzip

iVBORw0KGgoAAAANSUhEUgAAB3EAAAQ8CAIAAAADrvOlAAAQAElEQVR4nOzdBXjUWBuG4QCF4u7u7lDB3d3d3Rd3l2Vxd3d3d5fi...
```

The `png` job took 20 seconds, against about 2 seconds for the same page without rendering.

### An `xhr: true` job

In the XHR run, a `universal` job for the sandbox site set `render: html` and `xhr: true`.
Its submission carried both limits, so `xhr: true` counts as a rendered job.
The job finished 15 seconds after submission.
Its default output is one `xhr` entry whose `content` is a list, as the docs say ([XHR capture][xhr]).
For the sandbox home page, the list came back empty.
`?type=raw,xhr` returned two entries: `raw` with the HTML as a string, and `xhr` with the list.

```text
HTTP/1.1 202 Accepted
date: Thu, 24 Sep 2026 21:00:32 GMT
content-type: application/json
transfer-encoding: chunked
x-oxylabs-client-id: 123456
x-oxylabs-client-name: USERNAME
x-oxylabs-job-id: 7508993802242110465
x-oxyserps-client-id: 123456
x-oxyserps-client-name: USERNAME
x-oxyserps-job-id: 7508993802242110465
x-ratelimit-total-render-requests-00000000-0000-0000-0000-000000000000-limit: 13
x-ratelimit-total-render-requests-00000000-0000-0000-0000-000000000000-remaining: 12
x-ratelimit-total-requests-00000000-0000-0000-0000-000000000000-limit: 50
x-ratelimit-total-requests-00000000-0000-0000-0000-000000000000-remaining: 49
```

```json
{
  "results": [
    {
      "content": [],
      "created_at": "2026-09-24 21:00:32",
      "updated_at": "2026-09-24 21:00:47",
      "page": 1,
      "url": "https://sandbox.oxylabs.io/",
      "job_id": "7508993802242110465",
      "is_render_forced": false,
      "status_code": 200,
      "type": "xhr",
      "_request": {
        "cookies": [],
        "headers": {
          "...": "..."
        }
      },
      "_response": {
        "cookies": [],
        "headers": {
          "...": "..."
        }
      },
      "session_info": {
        "expires_at": null,
        "id": null,
        "remaining": null
      }
    }
  ],
  "job": {
    "id": "7508993802242110465",
    "status": "done",
    "source": "universal",
    "url": "https://sandbox.oxylabs.io/",
    "render": "html",
    "xhr": true,
    "created_at": "2026-09-24 21:00:32",
    "updated_at": "2026-09-24 21:00:47",
    "statuses": [],
    "...": "..."
  }
}
```

### Timestamps

`created_at` and `updated_at` hold UTC as `YYYY-MM-DD HH:MM:SS`, without an offset.
In the Sandbox run, a submission whose `Date` header read `Thu, 24 Sep 2026 20:07:07 GMT` returned `created_at: "2026-09-24 20:07:07"`.
A Realtime job object keeps `updated_at` equal to `created_at`, and only its result entry's `updated_at` holds the finish time.

### Error bodies

Most error bodies are JSON objects with `message`, `instance`, `timestamp` and `trace_id`.
The 408 and the nginx 404 carry `message` alone.
No response used the `errors` object that the JS Rendering page shows, but the run sent no invalid browser instructions ([JS Rendering][js-rendering]).

| Call | Status | `message` | Run |
| --- | --- | --- | --- |
| Unknown `source`, through Push-Pull or Realtime | 400 | `Unsupported source.` | Errors |
| A `.invalid`, `.test` or `.example` host | 400 | `` Parameter `url` has invalid top level domain format. `` | Faults |
| An IP address as the host | 400 | `The hostname cannot be an ip address.` | Faults |
| Malformed JSON | 400 | `Json error: Unexpected value.` | Errors |
| No `Authorization` header | 401 | `Authorization header not provided.` | Errors |
| A made-up username and password | 401 | None: the body is empty | Errors |
| A made-up numeric job ID, on the status, results or content endpoint | 404 | `Query not found.` | Errors |
| A non-numeric job ID | 404 | `Resource not found` | Errors |
| Realtime past the TTL | 408 | `Timed out.` | Render |
| Over the limit | 429 | `Too many requests. (Total Dynamic).` | Burst |

The docs give 422 for an invalid JSON payload, but malformed JSON returned 400 ([Response Codes][response-codes]).
The 401 for a made-up username has no body, no `Content-Type` and no `Date`, only `content-length: 0`.
The 404 for a non-numeric ID comes from nginx: it carries `server: nginx`, no `x-oxylabs-*` headers, and only `message`.
The Realtime host leaves the `x-oxylabs-client-*` headers off its 400.

```text
HTTP/1.1 400 Bad Request
date: Thu, 24 Sep 2026 20:02:06 GMT
content-type: application/json
content-length: 161
x-oxylabs-client-id: 123456
x-oxylabs-client-name: USERNAME
x-oxyserps-client-id: 123456
x-oxyserps-client-name: USERNAME

{"message":"Json error: Unexpected value.","instance":"/v1/queries","timestamp":"2026-09-24T20:02:06.413693701Z","trace_id":"6ab581be-b557a6f670a180725553e485"}
```

```text
HTTP/1.1 401 Unauthorized
date: Thu, 24 Sep 2026 20:02:06 GMT
content-type: application/json
content-length: 165

{"message":"Authorization header not provided.","instance":"/v1/queries","timestamp":"2026-09-24T20:02:06.78951901Z","trace_id":"6ab581be-68f0754fad6d6a03058c48b5"}
```

```text
HTTP/1.1 401 Unauthorized
content-length: 0
```

```text
HTTP/1.1 404 Not Found
date: Thu, 24 Sep 2026 20:02:05 GMT
content-type: application/json
content-length: 168
x-oxylabs-client-id: 123456
x-oxylabs-client-name: USERNAME
x-oxyserps-client-id: 123456
x-oxyserps-client-name: USERNAME

{"message":"Query not found.","instance":"/v1/queries/7000000000000000001","timestamp":"2026-09-24T20:02:05.912883835Z","trace_id":"6ab581bd-083b3a41811692f83a7ed0dc"}
```

```text
HTTP/1.1 404 Not Found
server: nginx
date: Thu, 24 Sep 2026 20:02:06 GMT
content-type: application/json
transfer-encoding: chunked
content-encoding: gzip

{"message": "Resource not found"}
```

```text
HTTP/1.1 400 Bad Request
date: Thu, 24 Sep 2026 20:02:05 GMT
content-type: application/json
content-length: 151

{"message":"Unsupported source.","instance":"/v1/queries","timestamp":"2026-09-24T20:02:05.653069059Z","trace_id":"6ab581bd-259ce41e9af06ab163662d22"}
```

## Realtime responses

### A done Realtime job

In the Sandbox run, a Realtime job for the sandbox site returned `200 OK` after 5.3 seconds.
The body holds a `job` object and a `results` list, while the docs' Realtime sample shows only `results` ([Realtime][realtime]).
The job object carries every Push-Pull field except `_links`.
The headers carry `x-oxylabs-job-id`, `x-oxylabs-trace-id` and the rate-limit headers.
They carry no `x-oxylabs-client-name` and no `x-oxyserps-*` twins.

```text
HTTP/1.1 200 OK
date: Thu, 24 Sep 2026 20:07:25 GMT
content-type: application/json
transfer-encoding: chunked
x-oxylabs-client-id: 123456
x-oxylabs-job-id: 7508980415521124353
x-oxylabs-trace-id: 6ab582f9-ee60ebfb90e1bcf44892862b
x-ratelimit-total-requests-00000000-0000-0000-0000-000000000000-limit: 50
x-ratelimit-total-requests-00000000-0000-0000-0000-000000000000-remaining: 48
```

```json
{
  "job": {
    "id": "7508980415521124353",
    "status": "done",
    "source": "universal",
    "url": "https://sandbox.oxylabs.io/",
    "query": "",
    "created_at": "2026-09-24 20:07:21",
    "updated_at": "2026-09-24 20:07:21",
    "statuses": [],
    "...": "..."
  },
  "results": [
    {
      "_request": {
        "cookies": [],
        "headers": {
          "...": "..."
        }
      },
      "_response": {
        "cookies": [],
        "headers": {
          "...": "..."
        }
      },
      "content": "<!DOCTYPE html><html lang=\"en\">CONTENT</html>",
      "created_at": "2026-09-24 20:07:21",
      "is_render_forced": false,
      "job_id": "7508980415521124353",
      "page": 1,
      "session_info": {
        "expires_at": null,
        "id": null,
        "remaining": null
      },
      "status_code": 200,
      "type": "raw",
      "updated_at": "2026-09-24 20:07:25",
      "url": "https://sandbox.oxylabs.io/"
    }
  ]
}
```

### A faulted Realtime job

In the Faults run, a Realtime job for a fault host returned `200 OK` after 24.0 seconds.
Its `job.status` is `faulted`, and its one result has `status_code: 613` and empty `content`.
So a Realtime client has to read `job.status` or `status_code`, because the HTTP status is 200 either way.

```text
HTTP/1.1 200 OK
date: Thu, 24 Sep 2026 20:05:09 GMT
content-type: application/json
content-length: 1640
x-oxylabs-client-id: 123456
x-oxylabs-job-id: 7508979764070211585
x-oxylabs-trace-id: 6ab5825d-d50bbbdaec65f6a2048260ba
x-ratelimit-total-requests-00000000-0000-0000-0000-000000000000-limit: 50
x-ratelimit-total-requests-00000000-0000-0000-0000-000000000000-remaining: 47
```

```json
{
  "job": {
    "id": "7508979764070211585",
    "status": "faulted",
    "source": "universal",
    "url": "https://oxy-fault-5-q7x2k9.com/",
    "query": "",
    "created_at": "2026-09-24 20:04:45",
    "updated_at": "2026-09-24 20:04:45",
    "statuses": [],
    "...": "..."
  },
  "results": [
    {
      "_request": {
        "cookies": null,
        "headers": null
      },
      "_response": {
        "cookies": null,
        "headers": null
      },
      "content": "",
      "created_at": "2026-09-24 20:04:45",
      "is_render_forced": false,
      "job_id": "7508979764070211585",
      "page": 1,
      "session_info": {
        "expires_at": null,
        "id": null,
        "remaining": null
      },
      "status_code": 613,
      "type": "raw",
      "updated_at": "2026-09-24 20:05:09",
      "url": "https://oxy-fault-5-q7x2k9.com/"
    }
  ]
}
```

### A Realtime job past the TTL

In the Render run, a Realtime job set `render: html` and three `wait` browser instructions of 60 seconds each.
The API accepted the instructions.
It returned `408 Request Timeout` after 160.6 seconds, with no job ID and no rate-limit headers.
The docs give the 150-second TTL but not this response, and the response-codes page lists no 408 ([Integration Methods][integration-methods], [Response Codes][response-codes]).
Usage Statistics never counted it, which suggests that the timeout was not billed.

```text
HTTP/1.1 408 Request Timeout
date: Thu, 24 Sep 2026 20:13:23 GMT
content-type: application/json
content-length: 25

{"message":"Timed out."}
```

### Looking up a Realtime job

The status and results endpoints returned 404 `Query not found.` for both Realtime job IDs from the run.
They did so 1 second after the Realtime response, and again 11 and 13 minutes later.
So the Push-Pull endpoints cannot fetch a Realtime result later.
The job ID help page mentions the Realtime job ID only for support requests ([job ID help][job-id]).

## Usage Statistics counts

### Deltas

The run read `/v2/stats?group_by=day` before its first job, every 60 seconds during the run, right after its last job, and 31 minutes later.
Only `universal` and `amazon_search` belong to this run.
Another client used the same account during the run, on a source this run did not use, so the table leaves its counts out.
The read right after the run and the read 31 minutes later gave the same deltas against the first read.

| Source | Jobs that ended `done` | `all_count` | `mode_callback_count` | `mode_realtime_count` | `render_count` |
| --- | --- | --- | --- | --- | --- |
| `universal` | 9: the Sandbox run's 4, the `png` and `xhr` jobs, and 3 fault jobs | +9 | +9 | 0 | +2 |
| `amazon_search` | 2, with 2 pages each | +4 | +4 | 0 | 0 |

`all_count` rose by exactly one per page of each job that ended `done`.
The 174 faulted jobs, the 400s and the 429s never appeared.
The two `amazon_search` jobs with `pages: 2` added 4, so each page is one result, including the page past the end.
The Realtime job that returned 200 counted under `mode_callback_count`, and `mode_realtime_count` did not change.
No day in the account's history of 357 days shows a `mode_realtime_count` above 0.
The Realtime job that returned 408 never appeared: `render_count` rose by 2, for the `png` and `xhr` jobs only.

Source entries carry no `parsed` key, and products carry `contenttype_html_count` but no `contenttype_parsed_count`.
The two parsed `amazon_search` results counted under `contenttype_html_count`.
So `/v2/stats` cannot tell parsed results from HTML ones, although the docs describe that split ([Usage Statistics][usage-statistics]).

### Timing and stale reads

Each finished job appeared in `all_count` 7 to 175 seconds after its `updated_at`.
Reads are not monotonic.
The reads at 20:09:17, 20:10:18 and 20:11:18 returned counts that matched reads from 3 to 6 minutes earlier.
At 20:10:18, every delta was back to 0.
The read at 20:12:19 returned current counts again.
Later, the other client's count fell by 5 between reads at 21:00:41 and 21:01:41, although a count cannot fall.

### Timezone

The run tested two day boundaries: UTC, which `created_at` uses, and Europe/Vilnius, the time zone of Oxylabs' home city.
The `xhr` job finished at 21:00:47 UTC, which is 00:00:47 on 2026-09-25 in Vilnius.
It counted under `2026-09-24`.

The endpoint also rejects a `date_from` after its current date:

```text
HTTP/1.1 400 Bad Request
date: Thu, 24 Sep 2026 21:31:05 GMT
content-type: application/json
content-length: 187
x-oxylabs-client-id: 123456
x-oxylabs-client-name: USERNAME
x-oxyserps-client-id: 123456
x-oxyserps-client-name: USERNAME

{"message":"Field `date_from` could not be greater than current date.","instance":"/v2/stats","timestamp":"2026-09-24T21:31:05.366391338Z","trace_id":"6ab59699-40967df86a0e77ec3a871735"}
```

A probe sent `date_from=2026-09-25` every minute from 20:32 to 21:33 UTC, and all 62 probes returned this 400.
So the day grouping and the date check both still used 2026-09-24 at 21:33 UTC.
That rules out Vilnius time and every other time zone at UTC+3 or further east.
UTC fits every observation, but the probe stopped at 21:33 UTC, so any zone from UTC+2 westward also fits.
A `date_to` after the current date is accepted.

### Response shape

With `group_by=day`, `data` is a list with one entry per `date`, and each entry holds a `products` list.
Without a date filter, the endpoint returned 357 days in no fixed order.
This account, created before 2024-09-25, splits usage into `serp_scraper_api`, `ecommerce_scraper_api` and `web_scraper_api`.
`universal` counts under `web_scraper_api`, and `amazon_search` under `ecommerce_scraper_api`.
`average_response_time` is a JSON integer on some entries and a float on others.
This sample keeps the live shape, with placeholder numbers:

```json
{
  "meta": {
    "group_by": "day",
    "date_from": "2026-09-23",
    "date_to": "2026-09-26",
    "source": null,
    "product": null
  },
  "data": [
    {
      "date": "2026-09-24",
      "products": [
        {
          "all_count": 10,
          "mode_callback_count": 10,
          "mode_realtime_count": 0,
          "mode_superapi_count": 0,
          "contenttype_html_count": 10,
          "render_count": 2,
          "geo_location_count": 0,
          "average_response_time": 8.5,
          "request_traffic": 20000,
          "response_traffic": 100000,
          "title": "web_scraper_api",
          "sources": [
            {
              "all_count": 10,
              "mode_callback_count": 10,
              "mode_realtime_count": 0,
              "mode_superapi_count": 0,
              "render_count": 2,
              "geo_location_count": 0,
              "average_response_time": 8.5,
              "request_traffic": 20000,
              "response_traffic": 100000,
              "title": "universal"
            }
          ]
        },
        {
          "...": "..."
        }
      ]
    }
  ]
}
```

## Fault jobs

The run needed jobs that end `faulted`, because Oxylabs does not bill them ([Traffic and Billing][billing]).
The API rejects `.invalid`, `.test` and `.example` hosts, and IP addresses, with 400.
So the run used unregistered `.com` names that return NXDOMAIN, one second-level name per job.
Of 177 such jobs, 174 ended `faulted` with 613.
3 ended `done`, and each returned `status_code: 200` with the same 488-byte page.
The page came from a `lighttpd` server and redirects to `/cgi-bin/`.
It looks like a router's web interface, which suggests that a resolver on the exit node's network returned an address for the name.
Usage Statistics counted all three as results.
So about one fault job in 60 billed.
A test that needs free jobs cannot rely on a host that does not resolve.

## Open questions

### Retention

A later session can fetch these jobs at 24, 48 and 72 hours after their finish times, for free.
The Push-Pull page states at least 24 hours, and the job ID help page says 48 ([Push-Pull][push-pull], [job ID help][job-id]).

| Job ID | Source | Status | Finished (UTC) |
| --- | --- | --- | --- |
| `7508979760408563713` | `universal` fault host | `faulted` | 2026-09-24 20:04:58 |
| `7508980357849459714` | `universal` | `done` | 2026-09-24 20:07:09 |
| `7508980408931885057` | `universal`, batch | `done` | 2026-09-24 20:07:22 |
| `7508980408936054785` | `universal`, batch | `done` | 2026-09-24 20:07:23 |
| `7508980946444499969` | `amazon_search`, `parse: true` | `done` | 2026-09-24 20:09:33 |
| `7508980980925889537` | `amazon_search`, `start_page: 20` | `done` | 2026-09-24 20:09:43 |
| `7508981262732783617` | `universal`, `render: png` | `done` | 2026-09-24 20:11:03 |
| `7508993802242110465` | `universal`, `xhr: true` | `done` | 2026-09-24 21:00:47 |

### Not settled

- Do API users under one account share a limit, and when does the domain throttle return its 429?
  No 429 in the run named a domain, even after 177 jobs failed on distinct names.
  Oxylabs support can answer both.
- What does a 429 on the rendered limit return, and do forced rendering and LLM sources count as rendered?
  Exceeding it takes 14 rendered submissions in one window, and each of them could bill, so the run did not try.
- When does 612 appear instead of 613?
- Can any endpoint return a Realtime job after its response?
  The status and results endpoints cannot, and a job past the TTL returns no ID at all.
- Why do Realtime results count under `mode_callback_count`?
  The account's history has no Realtime count on any day, so this may apply to every Realtime job.
- What are the `x-oxyserps-*` headers for, and do they ever differ from their `x-oxylabs-*` twins?
- Do the days in `/v2/stats` follow UTC?
  A `date_from` of the next UTC date, sent just after 00:00 UTC, returns 200 if they do, and costs nothing.

## Sources

### The live API

The run itself is the primary source.
It sent every call from one machine, with HTTP/1.1 for single calls and HTTP/2 for the poll and the burst.

### Oxylabs docs

- [Rate Limits][rate-limits] gives the plan limits and the `x-ratelimit-*` header pattern that the run confirmed.
- [Push-Pull][push-pull] documents the job object, batches, `_links` and the content endpoint's `{n}`.
- [Realtime][realtime] shows the Realtime sample without a `job` object.
- [Response Codes][response-codes] lists 204, 422, 524, 612 and 613.
- [Integration Methods][integration-methods] gives the 150-second TTL.
- [JS Rendering][js-rendering] documents `render: png` as Base64, browser instructions and the `errors` body.
- [XHR capture][xhr] documents `xhr: true` and its default output.
- [Usage Statistics][usage-statistics] documents the `parsed` split and `mode_realtime_count`.
- [Traffic and Billing][billing] states that faulted jobs and 429s are not billed.
- [Quick Start][quick-start] calls the 429 a concurrency limit.
- [job ID help][job-id] gives the 48-hour job ID retention and `x-oxylabs-job-id`.

### Notes

- [What the docs state about the job lifecycle](job-lifecycle.md) lists the open questions this run tested.

[integration-methods]: https://developers.oxylabs.io/products/web-scraper-api/integration-methods
[realtime]: https://developers.oxylabs.io/products/web-scraper-api/integration-methods/realtime
[push-pull]: https://developers.oxylabs.io/products/web-scraper-api/integration-methods/push-pull
[response-codes]: https://developers.oxylabs.io/products/web-scraper-api/response-codes
[rate-limits]: https://developers.oxylabs.io/products/web-scraper-api/usage-and-billing/rate-limits
[billing]: https://developers.oxylabs.io/products/web-scraper-api/usage-and-billing/billing-information
[usage-statistics]: https://developers.oxylabs.io/products/web-scraper-api/usage-and-billing/usage-statistics
[xhr]: https://developers.oxylabs.io/products/web-scraper-api/features/result-processing-and-storage/output-types/capturing-network-requests-fetch-xhr
[js-rendering]: https://developers.oxylabs.io/products/web-scraper-api/features/js-rendering-and-browser-control
[quick-start]: https://developers.oxylabs.io/get-started/quick-start-web-scraper-api
[job-id]: https://developers.oxylabs.io/help-center/troubleshooting/where-can-i-find-my-scraping-job-id
