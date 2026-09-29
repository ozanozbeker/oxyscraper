# What the docs state about the job lifecycle

This note records what the Oxylabs docs state about a job, from submission to result, for Realtime and Push-Pull.
It answers [#2](https://github.com/ozanozbeker/oxyscraper/issues/2), and [#9](https://github.com/ozanozbeker/oxyscraper/issues/9) tests its open questions against the live API.
It covers the docs as published on 2026-09-24.

## Answer

The docs cover every Push-Pull step: submit a job, poll its status, then fetch its result within 24 hours.
They leave open how pages and batches count against the rate limit, what a faulted job returns, and what Cloud Storage writes.

- **Endpoints.**
  `POST https://realtime.oxylabs.io/v1/queries` takes one Realtime job and returns its result on the same connection ([Realtime][realtime]).
  `POST https://data.oxylabs.io/v1/queries` takes one Push-Pull job, and `POST https://data.oxylabs.io/v1/queries/batch` takes a batch of up to 5,000 ([Push-Pull][push-pull]).
  `GET https://data.oxylabs.io/v1/queries/{id}` returns the job and its `status` ([Push-Pull][push-pull]).
  `GET https://data.oxylabs.io/v1/queries/{id}/results` returns the result as JSON, and `GET .../results/{n}/content` returns page `n` on its own ([Push-Pull][push-pull]).
  Both results endpoints and Realtime take `?type=` with one or more output types: `raw`, `parsed`, `png`, `markdown`, `xhr` ([Multi-format Output][multi-format]).
  No page documents an endpoint that lists jobs, cancels a job, or returns the status of many jobs at once.
- **Statuses.**
  A job is `pending`, `done` or `faulted`, and a `faulted` job is not billed ([Push-Pull][push-pull]).
  The results endpoint returns 204 while a job is incomplete, and 404 once its ID is unknown or no longer available ([Response Codes][response-codes]).
  Results stay retrievable for at least 24 hours after the job finishes ([Push-Pull][push-pull]).
  A help-center page says Oxylabs keeps job IDs for 48 hours ([job ID help][job-id]).
  No page says what the results endpoint returns for a `faulted` job.
- **Response shapes.**
  A submission and the status endpoint both return the job object: `id` as a string, `status`, the parameters, `statuses` and `_links` ([Push-Pull][push-pull]).
  A batch returns `{"queries": [...]}` with one job object per query or URL ([Push-Pull][push-pull]).
  The results endpoint returns `{"results": [...], "job": {...}}`, with one entry per page and per output type, in no fixed order ([Push-Pull][push-pull], [Multi-format Output][multi-format]).
  A query with `pages: 2` is one job with one `results` entry per page ([Amazon Search][amazon-search]).
  `_links` URLs use `http://`, and the docs tell clients to switch them to `https://` ([Push-Pull][push-pull]).
- **Realtime.**
  Every API connection has a 150-second TTL ([Integration Methods][integration-methods]).
  The docs ask for a 180-second client timeout on rendered Realtime jobs ([JS Rendering][js-rendering]).
  The Realtime sample returns `results` without a `job` object, and a help-center page says Realtime also returns the job ID in an `x-oxylabs-job-id` header ([Realtime][realtime], [job ID help][job-id]).
  Realtime is not available for `chatgpt`, `gemini`, `perplexity` or `youtube_download` ([LLMs and AI][llms-and-ai], [YouTube Downloader][youtube-downloader]).
- **Rate limits and headers.**
  The limit counts job submissions per second, and the plan sets it: Starter allows 50 jobs per second in total and 13 rendered jobs per second ([Rate Limits][rate-limits]).
  Every job submission returns `x-ratelimit-<name>-limit` and `x-ratelimit-<name>-remaining`, and more than one limit can apply ([Rate Limits][rate-limits]).
  The only example is `x-ratelimit-internal-api-default-limit: 12000`, with no window, no reset header and no `Retry-After` ([Rate Limits][rate-limits]).
  Below 40% success on a domain over 5 minutes, the API limits that domain to 1 request per second and returns a 429 whose `message` names the domain ([Rate Limits][rate-limits]).
  A 429 is not billed ([Traffic and Billing][billing]).
- **Codes.**
  The HTTP codes are 200, 202, 204, 400, 401, 403, 404, 422, 429, 500 and 524 ([Response Codes][response-codes]).
  612 and 613 mark a job that Oxylabs failed, and neither is billed ([Response Codes][response-codes]).
  Parser codes 12000 to 12009 sit in `parse_status_code` inside a parsed result's `content` ([Response Codes][response-codes]).
  Upload codes 10001, 13000, 13001, 13102 and 13103 sit in the job's `statuses` list, and a failed upload leaves the job `done` ([Response Codes][response-codes]).
  No page shows a non-empty `statuses` list, so the shape of an entry is unknown.
- **Cloud Storage on a batch.**
  The storage parameters work on the batch endpoint: the YouTube Downloader batch example sends `storage_type` and `storage_url` to `/v1/queries/batch` ([YouTube Downloader][youtube-downloader], [README][readme]).
  The job's `storage_url` shows the resolved object path at submission ([File name templating][file-name-templating]).
- **Usage Statistics.**
  `GET https://data.oxylabs.io/v2/stats` is free and returns result counts, response times and traffic, per product and per source ([Usage Statistics][usage-statistics]).
  It groups by `day`, `month` or `year`, and filters by date and `source` ([Usage Statistics][usage-statistics]).
  It returns no plan allowance and no remaining result count.
- **Result Aggregator.**
  It collects many jobs' results into one file and uploads it to the caller's bucket, at most an hour later ([Result Aggregator][result-aggregator]).
  Its own endpoints under `/v1/aggregators` manage aggregators, and a job joins one through the `aggregate_name` parameter ([Result Aggregator][result-aggregator]).
  It changes storage only for jobs that set `aggregate_name`.
  For those jobs, the docs give no per-job delivery status, so an upload check cannot cover them.

## The comparison's four questions

An earlier comparison of Oxylabs clients listed four questions that the docs leave open.
The docs settle one of them.

| Question | What the docs state | Status |
| --- | --- | --- |
| How does a query with `pages` above 1 count against the jobs-per-second limit? | The Amazon Search sample shows one job ID for a two-page query. No page says how pages count against the limit or the bill. | Open |
| Do the storage parameters work on the batch endpoint? | Yes. The YouTube Downloader batch example sends them to `/v1/queries/batch`, and the README says batch jobs can upload to S3 or GCS. | Settled |
| Does the results endpoint still return a job that uploaded to a bucket? | The Cloud Storage page calls the upload an alternative to `/results`, and says nothing more. | Open |
| What does the results endpoint return for a faulted job? | No page says. | Open |

The comparison's other statements about the API match the docs.
Four facts extend them.
LLM sources batch on `prompt` as well as `query` and `url` ([Changelog][changelog]).
Cloud Storage also supports BytePlus TOS through `storage_type: tos` ([Cloud Storage][cloud-storage]).
The upload codes also include 10001, 13001 and 13102 ([Response Codes][response-codes]).
A help-center page says Oxylabs keeps job IDs for 48 hours, beyond the 24 hours the Push-Pull page guarantees ([job ID help][job-id]).

## Endpoints

| Purpose | Endpoint |
| --- | --- |
| Realtime: submit one job and receive its result | `POST https://realtime.oxylabs.io/v1/queries` |
| Push-Pull: submit one job | `POST https://data.oxylabs.io/v1/queries` |
| Push-Pull: submit a batch | `POST https://data.oxylabs.io/v1/queries/batch` |
| Read a job and its status | `GET https://data.oxylabs.io/v1/queries/{id}` |
| Read a result as JSON | `GET https://data.oxylabs.io/v1/queries/{id}/results` |
| Read one page's content on its own | `GET https://data.oxylabs.io/v1/queries/{id}/results/{n}/content` |
| Read usage statistics | `GET https://data.oxylabs.io/v2/stats` |
| List the IPs that send callbacks | `GET https://data.oxylabs.io/v1/info/callbacker_ips` |
| Manage aggregators | `https://data.oxylabs.io/v1/aggregators`, listed under [Result Aggregator](#result-aggregator) |

Every integration method authenticates with HTTP Basic auth ([README][readme]).
`n` in the content endpoint is the page number, starting at 1 ([Push-Pull][push-pull]).

### Output types and `?type=`

The Realtime endpoint and both results endpoints take `?type=` ([Push-Pull][push-pull], [Realtime][realtime]).
It takes one output type or a comma-separated list, such as `?type=parsed,raw` ([Multi-format Output][multi-format]).
Without it, the endpoint returns the job's default output, which follows from `render`, `parse`, `xhr` and `markdown` ([Push-Pull][push-pull], [Markdown Output][markdown], [XHR capture][xhr]).
The default-output tables call `raw` "html", and the Realtime table calls `parsed` "json" ([Push-Pull][push-pull], [Realtime][realtime]).
The `type` field of each result uses `raw` and `parsed`.
A job must enable an output type in its parameters before `?type=` can return it ([Multi-format Output][multi-format]).
Realtime omits a requested type that the job did not enable, while the Push-Pull results endpoint returns it with an empty `content` string ([Multi-format Output][multi-format]).

### Links and other forms

`_links` holds `self`, `results` and `results-content`, plus `results-html` and `results-content-html`, which add `?type=raw` ([Push-Pull][push-pull]).
Entries whose `rel` starts with `results-content` carry `href_list`, one URL per page, instead of `href` ([Push-Pull][push-pull]).
The API returns these URLs with `http://`, and the docs tell clients to switch to `https://` before calling them ([Push-Pull][push-pull]).
Target pages also show a GET form of the Realtime endpoint, with parameters in the query string and an `access_token` parameter ([Amazon Search][amazon-search]).
No page explains how to get that token.

## Job statuses and retention

A job has one of three statuses ([Push-Pull][push-pull]).

| `status` | Meaning |
| --- | --- |
| `pending` | The job has not finished. |
| `done` | The job finished, and the results endpoint returns its result. |
| `faulted` | Oxylabs could not complete the job. It is not billed. |

The Scheduler lists the same three values for `result_status` ([Scheduler][scheduler]).
`updated_at` holds the finish time once a job is `done` or `faulted` ([Push-Pull][push-pull]).
`statuses` holds codes from the scraping, parsing and upload steps ([Push-Pull][push-pull], [Response Codes][response-codes]).
The Push-Pull data dictionary types `statuses` as Integer, but every sample shows an empty list ([Push-Pull][push-pull]).

The results endpoint returns 204 for a job that has not finished ([Response Codes][response-codes]).
It returns 404 for a job ID that does not exist or is no longer available ([Response Codes][response-codes]).
The status endpoint returns the job object with its current `status` instead ([Push-Pull][push-pull]).
A result stays retrievable for at least 24 hours after the job finishes ([Push-Pull][push-pull]).
The job ID help page says Oxylabs keeps job IDs for 48 hours ([job ID help][job-id]).

The docs recommend no polling interval.
Oxylabs' linked Python example polls the status endpoint every 5 seconds, and fetches results only when `status` is `done` ([Push-Pull example][push-pull-example]).
A callback replaces polling: the API sends a POST with the job object to `callback_url` when the job completes ([Push-Pull][push-pull]).

## Submission response

A Push-Pull submission returns the job object at once, with `status: pending` ([Push-Pull][push-pull]).
The sample echoes the submitted parameters and fills in defaults such as `pages: 1` and `user_agent_type: desktop` ([Push-Pull][push-pull]).
Push-Pull returns `id` as a string, while the Scheduler returns job IDs as JSON integers ([Push-Pull][push-pull], [Scheduler][scheduler]).
With Cloud Storage set, `storage_url` holds the resolved object path ([Push-Pull][push-pull], [File name templating][file-name-templating]).

This sample from the Push-Pull page drops most echoed parameters:

```json
{
  "id": "12345678900987654321",
  "status": "pending",
  "source": "universal",
  "url": "https://www.example.com",
  "query": "",
  "pages": 1,
  "start_page": 1,
  "render": null,
  "parse": false,
  "callback_url": "https://your.callback.url",
  "storage_type": "s3",
  "storage_url": "YOUR_BUCKET_NAME/12345678900987654321.json",
  "aggregate_name": null,
  "created_at": "2026-09-03 00:00:01",
  "updated_at": "2026-09-03 00:00:01",
  "statuses": [],
  "...": "...",
  "_links": [
    {
      "rel": "self",
      "href": "http://data.oxylabs.io/v1/queries/12345678900987654321",
      "method": "GET"
    },
    {
      "rel": "results",
      "href": "http://data.oxylabs.io/v1/queries/12345678900987654321/results",
      "method": "GET"
    },
    {
      "rel": "results-content",
      "href_list": [
        "http://data.oxylabs.io/v1/queries/12345678900987654321/results/1/content"
      ],
      "method": "GET"
    }
  ]
}
```

## Batch submission

A batch takes a list for its input key and a single value for every other parameter ([Push-Pull][push-pull]).
The Push-Pull page names `query` and `url` as the list keys ([Push-Pull][push-pull]).
LLM sources also accept a batch of up to 5,000 `prompt` values ([Changelog][changelog]).
Each value becomes its own job, and the response lists one job object per value under `queries` ([Push-Pull][push-pull]).
Each entry carries the same fields as a single job response ([Push-Pull][push-pull]).
With `callback_url` set, the API sends one callback per job ([Push-Pull][push-pull]).
No page says how a batch counts against the rate limit, or what a batch with one invalid value returns.

The Push-Pull page shows this batch, trimmed here:

```json
{
  "source": "google_shopping_search",
  "query": ["adidas", "nike", "reebok"],
  "callback_url": "https://your.callback.url"
}
```

```json
{
  "queries": [
    {
      "id": "12345678900987654321",
      "query": "adidas",
      "source": "google_shopping_search",
      "status": "pending",
      "...": "..."
    },
    {
      "id": "12345678901234567890",
      "query": "nike",
      "source": "google_shopping_search",
      "status": "pending",
      "...": "..."
    },
    "..."
  ]
}
```

## Results response

The results endpoint returns `results`, a list of entries, and `job`, the job object ([Push-Pull][push-pull]).
Each entry holds `content`, `type`, `page`, `url`, `job_id`, `status_code`, `created_at` and `updated_at` ([Push-Pull][push-pull]).
`status_code` is the HTTP status the website returned for that page ([Response Codes][response-codes]).
`content` is a string for `raw`, `markdown` and `png`, an object for `parsed`, and a list for `xhr` ([Multi-format Output][multi-format]).
`png` content is Base64 ([Realtime][realtime], [README][readme]).
Parsed `content` holds `parse_status_code` ([Realtime][realtime]).
Some sources add `_request`, `_response` and `session_info` to each entry ([Push-Pull][push-pull]).
With several output types, each type is its own entry, and the order is not fixed ([Multi-format Output][multi-format]).

```json
{
  "results": [
    {
      "content": "<!doctype html><html>CONTENT</html>",
      "type": "raw",
      "page": 1,
      "url": "https://www.example.com",
      "job_id": "12345678900987654321",
      "status_code": 200,
      "is_render_forced": false,
      "created_at": "2026-09-03 00:00:01",
      "updated_at": "2026-09-03 00:00:15"
    }
  ],
  "job": {
    "id": "12345678900987654321",
    "status": "done",
    "...": "..."
  }
}
```

The content endpoint returns one page's content on its own, without the JSON wrapper, and takes the same `?type=` values ([Push-Pull][push-pull]).

### A query with `pages` above 1

`pages` sets how many result pages one job fetches, starting at `start_page` ([Amazon Search][amazon-search]).
The Amazon Search sample with `pages: 2` returns one job ID and one `results` entry per page ([Amazon Search][amazon-search]).
The job's `_links` list the content endpoint once per page in `href_list` ([Push-Pull][push-pull]).
No page says whether such a job counts as one job or several against the rate limit, or as one billed result or several.

```json
{
  "results": [
    {
      "content": {
        "page": 2,
        "query": "nirvana tshirt",
        "last_visible_page": 3,
        "parse_status_code": 12000,
        "...": "..."
      },
      "page": 2,
      "job_id": "7335269853705561089",
      "status_code": 200,
      "...": "..."
    },
    {
      "...": "..."
    }
  ],
  "job": {
    "id": "7335269853705561089",
    "source": "amazon_search",
    "query": "nirvana tshirt",
    "start_page": 2,
    "pages": 2,
    "status": "done",
    "...": "..."
  }
}
```

## Realtime

Realtime holds the HTTPS connection open until the job's result or an error returns in the response body ([Realtime][realtime]).
Every API connection has a TTL of 150 seconds ([Integration Methods][integration-methods]).
In rare cases a connection times out before the response, for example under system load ([Integration Methods][integration-methods]).
For rendered jobs, the docs ask for a client timeout of 180 seconds on Realtime ([JS Rendering][js-rendering]).
The Realtime sample returns `results` without a `job` object ([Realtime][realtime]).
Each entry carries `job_id`, and the job ID help page says Realtime also returns an `x-oxylabs-job-id` header ([Realtime][realtime], [job ID help][job-id]).
Realtime has no batch ([README][readme]).
LLM sources and `youtube_download` run only through Push-Pull ([LLMs and AI][llms-and-ai], [YouTube Downloader][youtube-downloader]).
No page says what Realtime returns for a job that faults, or for one that runs past the TTL.

## Rate limits and headers

The rate limit counts job submissions per second, and the plan sets it ([Rate Limits][rate-limits]).

| Plan | Results (maximum) | Total jobs/s | Rendered jobs/s |
| --- | --- | --- | --- |
| Free trial | 2,000 | 10 | 3 |
| Micro | 98,000 | 50 | 13 |
| Starter | 220,000 | 50 | 13 |
| Advanced | 622,500 | 50 | 13 |
| Venture | 1,350,000 | 50 | 13 |
| Business | 3,330,000 | 100 | 25 |
| Corporate | 8,000,000 | 100 | 25 |
| Custom+ | Custom | Custom | Custom |

The rate-limits page attaches the limit to the user account ([Rate Limits][rate-limits]).
An account can hold several API users, and no page says whether they share one limit ([Dashboard 101][dashboard]).
No page names a limit for status checks or result downloads.
The quick start describes a 429 as exceeding a "concurrency limit", while the rate-limits page describes jobs per second ([Quick Start][quick-start], [Rate Limits][rate-limits]).
The API renders some page types even without `render` ([JS Rendering][js-rendering]).
No page says whether those jobs count against the rendered limit.

### Headers

Every job submission returns `x-ratelimit-<name>-limit` and `x-ratelimit-<name>-remaining` ([Rate Limits][rate-limits]).
The first gives the limit, and the second gives what remains ([Rate Limits][rate-limits]).
More than one limit can apply, each under its own name ([Rate Limits][rate-limits]).
The page's only example is a screenshot of one response, trimmed here:

```text
HTTP/1.1 200 OK
Content-Type: text/html; charset=UTF-8
x-oxylabs-content-status-code: 200
x-ratelimit-internal-api-default-limit: 12000
x-ratelimit-internal-api-default-remaining: 11999
x-oxylabs-traffic-generated: 77603
x-oxylabs-job-id: 7140365864557110273
```

The screenshot shows a `text/html` response dated December 2023.
The page does not say which integration method returned it.
Its limit of 12000 matches no plan's jobs per second, and the page gives no window.
No page mentions a `Retry-After` header or a reset header.
The README and the job ID help page document `x-oxylabs-job-id` ([README][readme], [job ID help][job-id]).
No page documents the other `x-oxylabs-*` headers in the screenshot.

### Domain throttling

The API tracks the success rate of the client's jobs on each domain ([Rate Limits][rate-limits]).
Below 40% over the last 5 minutes, it limits requests to that domain to 1 per second until the rate recovers ([Rate Limits][rate-limits]).
A throttled request returns 429 with this body ([Rate Limits][rate-limits]):

```json
{
  "message": "Access to {domain} has been limited to 1 req/s due to a low success rate. If you are using custom headers or cookies, ensure they are correct, then try again. The normal request limit will be restored automatically when the success rate improves."
}
```

No page shows the body of an account-level 429.
No page says whether the throttle applies at submission or while the job runs.

## Response codes

The response-codes page files these under HTTP codes ([Response Codes][response-codes]).

| Code | Status | Meaning |
| --- | --- | --- |
| 200 | OK | The request succeeded. |
| 202 | Accepted | The API accepted the request. |
| 204 | No Content | The job has not finished. |
| 400 | Multiple error messages | The request is malformed, and the body names the problem. |
| 401 | Authorization header not provided, Invalid authorization header, Client not found | The credentials are missing or wrong. |
| 403 | Forbidden | The account has no access to the resource. |
| 404 | Not Found | The job ID does not exist or is no longer available. |
| 422 | Unprocessable Entity | The payload is invalid. The docs suggest checking that it is a valid JSON object. |
| 429 | Too many requests | The client exceeded the rate limit. |
| 500 | Internal Server Error | Oxylabs has an internal error. |
| 524 | Timeout | The service is unavailable. |
| 612 | Undefined Internal Error | Oxylabs failed the job, and a retry costs nothing. |
| 613 | Faulted After Too Many Retries | Oxylabs failed the job after retrying it, and a retry costs nothing. |

No page says where 612 and 613 appear: as the HTTP status, in `statuses`, or in a result's `status_code`.
The help-center copy of the table describes both as "Job submission failed" ([help-center codes][help-response-codes]).
The Scheduler records job creation as `create_status_code: 202` ([Scheduler][scheduler]).
No page says whether a Push-Pull submission returns 200 or 202.

### Parser, upload and other codes

Parser codes sit in `parse_status_code` inside a parsed result's `content` ([Response Codes][response-codes]).
12000 means success, 12004 and 12005 mean partial success, 12003 means the page is not supported, 12007 means unknown, and 12002, 12006, 12008 and 12009 mean failure ([Response Codes][response-codes]).
A parse that fails on some Custom Parser instructions still leaves the job successful ([Custom Parser][custom-parser]).
That result carries 12005 and a `_warnings` list, and it is billed ([Custom Parser][custom-parser]).

Upload codes sit in the job's `statuses` list ([Response Codes][response-codes]).

| Code | Status | Meaning |
| --- | --- | --- |
| 10001 | Unexpected Exception | An unexpected error occurred. |
| 13000 | Upload Success | The upload succeeded. |
| 13001 | Upload Failed | The upload failed. |
| 13102 | No Such Path | No bucket has that name. |
| 13103 | Access Denied | The bucket lacks the permissions Oxylabs needs. |

A failed upload leaves the job `done` ([Response Codes][response-codes]).
Session codes 15001 to 15003 and target codes, such as YouTube's 11201 to 11211, exist as well ([Response Codes][response-codes]).

### Error bodies

The docs show two shapes for an error body.
Browser-instruction validation returns 400 with an `errors` object ([JS Rendering][js-rendering]):

```json
{
  "errors": {
    "message": "Unsupported action type `unsupported-wait`, choose from 'click,fetch_resource,input,scroll,scroll_to_bottom,wait,wait_for_element'"
  }
}
```

YouTube Downloader's trimming validation returns 400 with a top-level `message` field ([YouTube Downloader][youtube-downloader]).
The domain throttle's 429 also uses a top-level `message` ([Rate Limits][rate-limits]).
No page shows the body of a 401, 403, 404, 422 or account-level 429.

## Billing

Oxylabs bills per result ([Traffic and Billing][billing]).
A result is billed when the website returned 2xx or 4xx, even when its content lacks the expected data ([Traffic and Billing][billing]).
Failures with 5xx and 6xx codes are not billed, and neither is a 429 ([Traffic and Billing][billing]).
A failure caused on the client's side is billed ([Traffic and Billing][billing]).
The monthly allowance depends on the target and on rendering ([pricing help][pricing]).
Starter gets 247,500 Amazon results, 110,000 Google results, 90,000 other results or 76,154 rendered results ([pricing help][pricing]).
The rate-limits page lists 220,000 results for Starter instead ([Rate Limits][rate-limits]).

## Cloud Storage in the lifecycle

Cloud Storage works only with Push-Pull ([Cloud Storage][cloud-storage]).
`storage_type` takes `gcs`, `s3`, `tos` or `s3_compatible` ([Cloud Storage][cloud-storage]).
The storage parameters work on the batch endpoint ([YouTube Downloader][youtube-downloader], [README][readme]).
`youtube_download` requires them ([YouTube Downloader][youtube-downloader]).
The default object name is `{{ job_id }}.{{ extension }}` ([File name templating][file-name-templating]).
`storage_url` accepts templates built from any input parameter or job field, and the job's `storage_url` shows the resolved path at submission ([File name templating][file-name-templating]).
Other pages give other names ([Cloud Storage][cloud-storage], [YouTube Downloader][youtube-downloader]).
The Cloud Storage page gives `job_ID.json`.
Its BytePlus TOS section gives `{query_id}_{timestamp}.html` and `{query_id}_results.json`.
YouTube Downloader gives `{video_id}_{job_id}.mp4`.
Upload codes sit in `statuses`, and a failed upload leaves the job `done` ([Response Codes][response-codes]).
No page says what the uploaded object holds, or whether the results endpoint still returns an uploaded job.

## Usage Statistics

`GET https://data.oxylabs.io/v2/stats` returns usage counts, and it is free ([Usage Statistics][usage-statistics]).
By default it covers all time and all sources ([Usage Statistics][usage-statistics]).

| Parameter | Values |
| --- | --- |
| `group_by` | `day`, `month` or `year` |
| `date_from` | A date in `Y-m-d` format |
| `date_to` | A date in `Y-m-d` format |
| `source` | Any `source` value |
| `product` | `serp_scraper_api`, `ecommerce_scraper_api` or `web_scraper_api`, for accounts created before 2024-09-25 |

`meta` echoes the parameters, and `data.products` holds one entry per product with a `sources` list ([Usage Statistics][usage-statistics]).
Each entry holds `all_count`, a count per integration method, `render_count`, `geo_location_count`, `average_response_time` in seconds, and traffic in bytes ([Usage Statistics][usage-statistics]).
`mode_callback_count` counts Push-Pull results, `mode_realtime_count` counts Realtime and `mode_superapi_count` counts Proxy Endpoint ([Usage Statistics][usage-statistics]).
Source entries carry `parsed`, because the endpoint splits each source into HTML and parsed results ([Usage Statistics][usage-statistics]).

```json
{
  "meta": {
    "group_by": null,
    "date_from": null,
    "date_to": null,
    "source": null,
    "product": null
  },
  "data": {
    "products": [
      {
        "title": "serp_scraper_api",
        "all_count": 5837,
        "mode_callback_count": 5514,
        "mode_realtime_count": 315,
        "mode_superapi_count": 8,
        "contenttype_parsed_count": 56,
        "contenttype_html_count": 5781,
        "render_count": 3,
        "geo_location_count": 2330,
        "average_response_time": 88.54,
        "request_traffic": 4685091,
        "response_traffic": 602064208,
        "sources": [
          {
            "title": "serp_source1",
            "parsed": false,
            "all_count": 5616,
            "...": "..."
          }
        ]
      }
    ]
  }
}
```

The endpoint returns no plan allowance and no remaining result count.
The Dashboard API covers only Datacenter Proxies and Headless Browser ([Changelog][changelog]).
No page says whether `all_count` counts only billed results, or how soon a finished job appears in it.

## Result Aggregator

Result Aggregator collects the results of many jobs into one file and uploads it to the caller's bucket ([Result Aggregator][result-aggregator]).
It supports S3, GCS and S3-compatible storage ([Result Aggregator][result-aggregator]).

| Action | Endpoint |
| --- | --- |
| Create an aggregator | `POST https://data.oxylabs.io/v1/aggregators` |
| Read one, with its usage counts | `GET https://data.oxylabs.io/v1/aggregators/{name}` |
| List aggregators | `GET https://data.oxylabs.io/v1/aggregators` |
| Delete an aggregator | `DELETE https://data.oxylabs.io/v1/aggregators/{name}` |
| Deliver the current file now | `POST https://data.oxylabs.io/v1/aggregators/{name}/trigger` |

An aggregator needs `name`, `storage_type` and `storage_url` ([Result Aggregator][result-aggregator]).
Optional parameters set `file_output_type` and the delivery triggers ([Result Aggregator][result-aggregator]).
`file_output_type` takes `json`, `jsonl`, `gzip_json` or `gzip_jsonl`.
`max_size_bytes` caps a file at up to 1 GB, and `max_result_count` caps its result count.
`schedule` takes a cron expression that fires at least hourly.
`callback_url` is optional too.
The page's example creates this aggregator:

```json
{
  "name": "amazon_hourly",
  "storage_type": "s3",
  "storage_url": "s3://my_bucket/batches",
  "max_result_count": 10000,
  "max_size_bytes": 524288000,
  "schedule": "0 */1 * * *"
}
```

A job joins an aggregator through `aggregate_name`, and then needs no storage parameters ([Result Aggregator][result-aggregator]).
The aggregator closes and uploads a file when its schedule fires, or when the file reaches `max_size_bytes` or `max_result_count` ([Result Aggregator][result-aggregator]).
It names each file by timestamp and aggregator name, such as `2024-08-08T01:00:00.000-00:00-amazon_hourly.jsonl` ([Result Aggregator][result-aggregator]).

Result Aggregator changes nothing for a job without `aggregate_name`.
For a job with it, the aggregator uploads the result up to an hour after the job finishes, in a file shared with other jobs.
The docs give no per-job delivery status for such a job, and do not say whether the results endpoint still returns it.
`aggregate_name` is a job parameter, so an open parameter set passes it through without oxy managing aggregators.
Managing aggregators uses its own endpoints, as the Scheduler does.

## Open questions

[#9](https://github.com/ozanozbeker/oxyscraper/issues/9) tests these against the live API.
Each question names the smallest test that settles it.
The docs already show the batch response shape, but #9 still needs a live sample as a fixture.

### Rate limits

- Which `x-ratelimit-*` headers come back on a Realtime submission, a Push-Pull submission and a batch, with which names and values?
  Test: record every header of one of each.
- Does a batch of N values lower `-remaining` by N?
  Test: read `-remaining` before and after a 2-value batch.
- What does a batch larger than the remaining budget return: a 429 for the whole batch, or some jobs accepted?
  Test: submit a batch above the per-second limit, such as 60 values on a 50 jobs/s plan, which bills every job it creates.
- Does a job with `pages: 2` lower `-remaining` by 1 or 2, and add 1 or 2 billed results?
  Test: submit one `pages: 2` job, and read `-remaining` and `/v2/stats` `all_count` before and after.
- What window does each limit cover, and does `-remaining` recover with time or when pending jobs finish?
  Test: submit 5 jobs in one second, then 1 job per second for a minute, and compare `-remaining` with time and with the pending count.
- Which limit covers rendered jobs, and do `xhr: true`, forced rendering and LLM sources count as rendered?
  Test: compare the headers of a `render: html` job with those of a plain job.
- Do status and results requests carry `x-ratelimit-*` headers, count against a limit, or return 429 when polled fast?
  Test: poll one job's status at 10 requests per second for 10 seconds.
- Does any response carry `Retry-After` or a reset header, and what body does an account-level 429 return?
  Test: exceed the jobs-per-second limit once, such as 60 single submissions in one second on a 50 jobs/s plan, and record the 429 in full.
- Do API users under one account share one limit?
  Test: compare `-remaining` across two API users, or ask Oxylabs support.
- Does the domain throttle return its 429 at submission, or fault the job later, and what happens to a batch that includes a throttled domain?
  Test: ask Oxylabs support, because a small test cannot push a domain below 40% success.

### Submission and batch

- Do single and batch submissions return 200 or 202?
  Test: record the status line of each.
- What does a batch with one invalid value return: a 400 for the whole batch, or jobs for the valid values?
  Test: submit a 2-value `url` batch where one value is not a URL.

### Statuses and results

- What do the status and results endpoints return for a `faulted` job, and where do 612 and 613 appear?
  Test: submit a payload likely to fault, such as a `universal` job for a domain that does not resolve, and record both endpoints.
- What do the results, content and status endpoints return for a pending job, and for an unknown ID?
  Test: call all three right after submission, then again with a made-up ID.
- How long does the results endpoint return a finished job: 24 hours, 48 hours or longer?
  Test: fetch one job's results at 24, 48 and 72 hours after it finishes.
- What does a multi-page job return when one page fails: `done` with that page's `status_code`, or `faulted`?
  Test: submit an `amazon_search` job with `pages: 2` and `start_page` past the last page.
- Which timezone do `created_at` and `updated_at` use?
  Test: compare them with the `Date` header of the same response.
- Which error body shape do 400, 401, 404 and 422 use: an `errors` object or a top-level `message`?
  Test: submit an unknown source, use a wrong password, request a made-up job ID, and send malformed JSON.
- What `Content-Type` does the content endpoint return, and does it return `png` as bytes or Base64?
  Test: fetch a `render: png` job through the content endpoint.

### Cloud Storage

- What does a `statuses` entry look like after a successful upload and after a denied one?
  Test: upload one job to a writable bucket, expecting 13000, and one to a bucket without write access, expecting 13103.
- Does the results endpoint still return a job that uploaded to a bucket?
  Test: fetch the results of both jobs above.
- What does the uploaded object hold, and what does `{{ extension }}` resolve to for each output type?
  Test: upload one job each with `parse: true`, `render: png` and `markdown: true`, then list and read the objects.
- In a batch, does each job's `storage_url` resolve a per-job template such as `{{ query }}`?
  Test: submit a 2-value batch with `storage_url` set to `bucket/{{ query }}.{{ extension }}`.

### Realtime responses

- Does a Realtime response carry a `job` object, an `x-oxylabs-job-id` header and `x-ratelimit-*` headers?
  Test: submit one Realtime job.
- What does Realtime return for a job that faults, and for one that runs past the 150-second TTL?
  Test: send the faulting payload through Realtime, and send a `render: html` job with three 60-second `wait` browser instructions.
- Is a job that runs past the TTL still billed, and does the status endpoint return it?
  Test: look up the job ID from the TTL test above.

### Usage Statistics counts

- Does `all_count` count only billed results, or also faulted jobs and 429s?
  Test: compare `/v2/stats?group_by=day` before and after the test run with the jobs the run created.
- How soon does a finished job appear, and which timezone do `date_from` and `date_to` use?
  Test: read `/v2/stats?group_by=day` right after the run and an hour later.

### Aggregated jobs

These matter only if oxy supports aggregators.

- For a job with `aggregate_name`, does the results endpoint still return the result, and does `statuses` record the delivery?
  Test: create an aggregator, route one job to it, call the trigger endpoint, then read the job.
- What does one record of an aggregated file hold?
  Test: read the file the trigger above delivers.

## Support answers

Oxylabs support answered three of the open questions on 2026-09-29, for [Ask Oxylabs support what the rate limits mean](https://github.com/ozanozbeker/oxyscraper/issues/25).
Each answer cites only the docs, so none states a fact that the docs lack.

- **Do API users under one account share one limit?**
  Support said yes, and quoted 10 requests per API key and 100 requests across all API keys of one client.
  Those numbers are the Dashboard API's limits ([Dashboard API][dashboard-api]).
  The rate-limits page holds neither number and gives no limit per API user ([Rate Limits][rate-limits]), so the question stays open.
  Test: two API users each submit fault jobs in the same second, and the run compares their `-remaining` values and the UUIDs in their header names.
  [Fault jobs](live-api.md#fault-jobs) describes those jobs.
- **What does the UUID in the header names identify?**
  Support confirmed that no page says.
- **Does the domain throttle return its 429 at submission?**
  Support said yes, because the page gives the 429 as the response to a request made while the limit is in effect ([Rate Limits][rate-limits]).
  That is a reading of the page, not a statement about the API.
- **What happens when an account uses up its monthly results?**
  Support said that Oxylabs bills no overage, and that the account has to buy more results.
  The dashboard's Top up adds results for the current billing period ([Dashboard 101][dashboard]).
  Support did not say what a submission returns once the results are used up.

## Sources

### Oxylabs docs

- [Integration Methods][integration-methods] gives the 150-second TTL.
- [Realtime][realtime] documents the Realtime endpoint, its default output and a response sample.
- [Push-Pull][push-pull] documents the endpoints, statuses, job object, batches, results and callbacks.
- [Response Codes][response-codes] lists the HTTP, parser, upload and session codes.
- [Rate Limits][rate-limits] gives the plan limits, the `x-ratelimit-*` headers and domain throttling.
- [Traffic and Billing][billing] states what Oxylabs bills.
- [Usage Statistics][usage-statistics] documents `/v2/stats`.
- [Result Aggregator][result-aggregator] documents the `/v1/aggregators` endpoints and `aggregate_name`.
- [Cloud Storage][cloud-storage] lists the storage types and object names, and states that Cloud Storage works only with Push-Pull.
- [File name templating][file-name-templating] gives the default template and the resolved `storage_url`.
- [Multi-format Output][multi-format] documents `?type=` lists and how Realtime and Push-Pull differ.
- [Markdown Output][markdown] and [XHR capture][xhr] state the default output that `markdown` and `xhr` set.
- [JS Rendering][js-rendering] covers forced rendering, the 180-second timeout and the `errors` body.
- [Custom Parser][custom-parser] shows that a partial parse leaves the job successful and billed.
- [Scheduler][scheduler] shows `create_status_code: 202`, integer job IDs and the `result_status` values.
- [Amazon Search][amazon-search] shows a `pages: 2` sample and the GET form with `access_token`.
- [LLMs and AI][llms-and-ai] states that LLM sources run only through Push-Pull, and documents `prompt`.
- [YouTube Downloader][youtube-downloader] shows a batch with storage parameters and a 400 with `message`.
- [Quick Start][quick-start] calls the 429 a concurrency limit.
- [Dashboard 101][dashboard] shows several API users per account, and the Top up that adds results.
- [Dashboard API][dashboard-api] gives the Dashboard API's own rate limits, which support quoted.
- [job ID help][job-id] gives the 48-hour job ID retention and `x-oxylabs-job-id`.
- [help-center codes][help-response-codes] describes 612 and 613 as failed submissions.
- [pricing help][pricing] lists the monthly results per target and plan.
- [Changelog][changelog] records batches of `prompt` values and the Dashboard API's scope.

### Oxylabs on GitHub

- [README][readme] states Basic auth, batch uploads to S3 or GCS, Base64 screenshots and `x-oxylabs-job-id`.
- [Push-Pull example][push-pull-example] polls the status endpoint every 5 seconds.

[integration-methods]: https://developers.oxylabs.io/products/web-scraper-api/integration-methods
[realtime]: https://developers.oxylabs.io/products/web-scraper-api/integration-methods/realtime
[push-pull]: https://developers.oxylabs.io/products/web-scraper-api/integration-methods/push-pull
[response-codes]: https://developers.oxylabs.io/products/web-scraper-api/response-codes
[rate-limits]: https://developers.oxylabs.io/products/web-scraper-api/usage-and-billing/rate-limits
[billing]: https://developers.oxylabs.io/products/web-scraper-api/usage-and-billing/billing-information
[usage-statistics]: https://developers.oxylabs.io/products/web-scraper-api/usage-and-billing/usage-statistics
[result-aggregator]: https://developers.oxylabs.io/products/web-scraper-api/features/result-processing-and-storage/result-aggregator
[cloud-storage]: https://developers.oxylabs.io/products/web-scraper-api/features/result-processing-and-storage/cloud-storage
[file-name-templating]: https://developers.oxylabs.io/products/web-scraper-api/features/result-processing-and-storage/cloud-storage/file-name-templating
[multi-format]: https://developers.oxylabs.io/products/web-scraper-api/features/result-processing-and-storage/output-types/multi-format-output
[markdown]: https://developers.oxylabs.io/products/web-scraper-api/features/result-processing-and-storage/output-types/markdown-output
[xhr]: https://developers.oxylabs.io/products/web-scraper-api/features/result-processing-and-storage/output-types/capturing-network-requests-fetch-xhr
[js-rendering]: https://developers.oxylabs.io/products/web-scraper-api/features/js-rendering-and-browser-control
[custom-parser]: https://developers.oxylabs.io/products/web-scraper-api/features/custom-parser/getting-started
[scheduler]: https://developers.oxylabs.io/products/web-scraper-api/features/scheduler
[amazon-search]: https://developers.oxylabs.io/api-targets/e-commerce/amazon/search
[llms-and-ai]: https://developers.oxylabs.io/api-targets/llms-and-ai
[youtube-downloader]: https://developers.oxylabs.io/api-targets/video-and-social-media/youtube/youtube-downloader
[quick-start]: https://developers.oxylabs.io/get-started/quick-start-web-scraper-api
[dashboard]: https://developers.oxylabs.io/help-center/dashboard/web-scraper-api-101-navigating-the-dashboard
[dashboard-api]: https://developers.oxylabs.io/dashboard/dashboard-api
[job-id]: https://developers.oxylabs.io/help-center/troubleshooting/where-can-i-find-my-scraping-job-id
[help-response-codes]: https://developers.oxylabs.io/help-center/troubleshooting/response-codes-for-web-scraper-api
[pricing]: https://developers.oxylabs.io/help-center/billing-and-payments/how-does-web-scraper-api-pricing-work
[changelog]: https://developers.oxylabs.io/changelog
[readme]: https://github.com/oxylabs/web-scraper-api
[push-pull-example]: https://github.com/oxylabs/product-integrations/tree/master/scraper-apis/Python/push_pull
