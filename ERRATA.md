# Oxylabs docs errata

This file lists errors and gaps in the Oxylabs docs that live tests found, to report upstream.
GitBook exports the docs to `oxylabs/gitbook-public-english`, which is private, so the docs have no public issue tracker.
Each entry cites the page as published on 2026-09-25, or on 2026-09-28 for the parameter and retention entries, and links the test behind it.

## Statements the API contradicts

### Response Codes: malformed JSON returns 400, not 422

- **Docs:** [Response Codes][response-codes] gives 422 for a bad payload: "Make sure it's a valid JSON object."
- **API:** malformed JSON returned `400 Bad Request` with `"message": "Json error: Unexpected value."`.
- **Evidence:** [Error bodies](docs/research/live-api.md#error-bodies).

### Response Codes: the content endpoint returns 204 for finished jobs

- **Docs:** [Response Codes][response-codes] describes 204 as "You are trying to retrieve a job that has not been completed yet."
- **API:** the content endpoint returned 204 for a `faulted` job, and for page numbers that a `done` job did not fetch.
  Only the undocumented `x-oxylabs-job-status` header tells these apart from a pending job.
- **Evidence:** [A faulted job](docs/research/live-api.md#a-faulted-job) and [The content endpoint](docs/research/live-api.md#the-content-endpoint).

### Response Codes: expired results return 204, not 404

- **Docs:** [Response Codes][response-codes] gives 404 for a job ID that "does not exist or is no longer available."
- **API:** 78 to 97 hours after the jobs finished, the results and content endpoints returned 204 for them, with `x-oxylabs-job-status: done`, or `faulted` for a faulted job.
  Jobs 4 hours old returned 200 from the results endpoint, and a made-up job ID returned 404.
- **Evidence:** [Retention](docs/research/live-api.md#retention).

### Response Codes: a 401 for an unknown username has no message

- **Docs:** [Response Codes][response-codes] lists three 401 messages: `Authorization header not provided`, `Invalid authorization header` and `Client not found`.
- **API:** a made-up username and password returned 401 with an empty body and `content-length: 0`.
  A request without the header returned the documented message.
- **Evidence:** [Error bodies](docs/research/live-api.md#error-bodies).

### Help center: 612 and 613 do not mean a failed submission

- **Docs:** [Response codes for Web Scraper API][help-response-codes] describes 612 and 613 as "Job submission failed."
- **API:** the submission returned 202, and 613 appeared later as the `status_code` of the faulted job's results entry.
  [Response Codes][response-codes] describes them correctly, as a job that Oxylabs failed.
- **Evidence:** [A faulted job](docs/research/live-api.md#a-faulted-job).

### Help center: the API keeps a job for longer than 48 hours

- **Docs:** the [job ID help page][job-id] says "Job IDs are only retained in our system for 48 hours."
- **API:** the status endpoint returned the whole job object 97 hours after the job finished.
- **Evidence:** [Retention](docs/research/live-api.md#retention).

### Realtime: the output sample lacks the `job` object

- **Docs:** the [Realtime][realtime] output sample holds `results` only.
- **API:** every Realtime response held a `job` object beside `results`, with every Push-Pull job field except `_links`.
- **Evidence:** [A done Realtime job](docs/research/live-api.md#a-done-realtime-job).

### Push-Pull: `{n}` in the content endpoint is the page number itself

- **Docs:** [Push-Pull][push-pull] says "`{n}` is the page number starting at `1`."
- **API:** for a job with `start_page: 20` and `pages: 2`, `/results/20/content` and `/results/21/content` returned the pages, and `/results/1/content` returned 204.
  `{n}` matches the URLs in `href_list`, so it starts at 1 only when `start_page` is 1.
- **Evidence:** [The content endpoint](docs/research/live-api.md#the-content-endpoint).

### Push-Pull: the data dictionary types `statuses` and `client_id` wrongly

- **Docs:** the [Push-Pull][push-pull] data dictionary types `statuses` as Integer and `client_id` as String.
- **API:** `statuses` is a list, as the page's own samples show, and `client_id` is a JSON integer.
- **Evidence:** [Push-Pull submission](docs/research/live-api.md#push-pull-submission).

### Quick start: the 429 comes from a rate limit, not a concurrency limit

- **Docs:** [Quick Start][quick-start] describes 429 as "You have exceeded your concurrency limit."
- **API:** the limit counts submissions in a window of about one second.
  `-remaining` returned to 49 while earlier jobs were still `pending`.
  [Rate Limits][rate-limits] describes it correctly, as jobs per second.
- **Evidence:** [The window](docs/research/live-api.md#the-window).

### Usage Statistics: Realtime results count under `mode_callback_count`

- **Docs:** [Usage Statistics][usage-statistics] defines `mode_realtime_count` as "The amount of results, fulfilled via Realtime integration method."
- **API:** one Realtime result added 1 to `mode_callback_count` and left `mode_realtime_count` at 0.
  The fault may lie in the API rather than the docs.
- **Evidence:** [Deltas](docs/research/live-api.md#deltas).

### Usage Statistics: results are not split into HTML and parsed

- **Docs:** [Usage Statistics][usage-statistics] says source-level stats "are further broken down into separate statistics for HTML and parsed results."
  Its sample shows `contenttype_parsed_count` on each product and `parsed` on each source entry.
- **API:** neither field appeared, and two parsed `amazon_search` results counted under `contenttype_html_count`.
  The account predates 2024-09-25, so newer accounts may differ.
- **Evidence:** [Deltas](docs/research/live-api.md#deltas).

### File name templating: most variables do not resolve

- **Docs:** [File name templating][file-name-templating] says a name can use "any input parameter you provide when creating a job, as well as any variable from the `job` object", such as `job_id`, `source` and `created_at`.
- **API:** only `{{ job_id }}`, `{{ source }}`, `{{ query }}` and `{{ extension }}` resolved.
  `{{ created_at }}`, `{{ url }}`, `{{ geo_location }}`, `{{ client_notes }}` and six other fields stayed in the object name as literal text.
- **Evidence:** [Variables](docs/research/cloud-storage.md#variables).

### Push-Pull: a batch takes a `prompt` array

- **Docs:** [Push-Pull][push-pull] allows "up to 5,000 `query` or `url` parameter values within a single batch request."
- **API:** a `perplexity` batch with a `prompt` array created a job for each value.
  The API's own 400 for other input keys also names only `query` and `url`.
- **Evidence:** [Input keys](docs/research/live-parameters.md#input-keys).

### YouTube guide for AI: `youtube_video_trainability` takes no batch

- **Docs:** the [YouTube guide for AI][yt-guide] batches `youtube_video_trainability` with a `query` list.
- **API:** that batch returned 202 with no jobs, and ``Source `youtube_video_trainability` is not available with a batch request.`` for each value.
  A `video_id` list returned 400.
- **Evidence:** [Input keys](docs/research/live-parameters.md#input-keys).

## Behaviour the docs leave out

### Response Codes: Realtime returns 408 past its TTL

- **Docs:** [Integration Methods][integration-methods] sets a 150-second TTL for every connection, and [Response Codes][response-codes] lists no 408.
- **API:** a Realtime job that ran past the TTL returned `408 Request Timeout` with `{"message":"Timed out."}` after 160 seconds, with no job ID.
- **Evidence:** [A Realtime job past the TTL](docs/research/live-api.md#a-realtime-job-past-the-ttl).

### Response Codes: submissions return 202, and Realtime returns 200 even for a faulted job

- **Docs:** [Response Codes][response-codes] lists both 200 and 202, and no page says which one a submission returns.
  [Realtime][realtime] does not say what a faulted job returns.
- **API:** Push-Pull and batch submissions returned `202 Accepted`.
  Realtime returned `200 OK` for a `done` job and for a `faulted` one, whose result carried `status_code: 613`.
- **Evidence:** [Status codes](docs/research/live-api.md#status-codes) and [A faulted Realtime job](docs/research/live-api.md#a-faulted-realtime-job).

### Response Codes: 613 appears only in the results entry

- **Docs:** [Response Codes][response-codes] lists 612 and 613 without saying where they appear.
- **API:** a faulted job kept `statuses` empty, and its results endpoint returned 200 with one entry whose `status_code` was 613.
  613 never appeared as an HTTP status, and no job showed 612.
- **Evidence:** [A faulted job](docs/research/live-api.md#a-faulted-job).

### Push-Pull: the results and content endpoints send `x-oxylabs-job-status`

- **Docs:** [Push-Pull][push-pull] does not mention the header.
- **API:** the results and content endpoints send `x-oxylabs-job-status` with `pending`, `done` or `faulted`.
  The content endpoint returns 204 for both a pending and a faulted job, so only this header tells them apart.
- **Evidence:** [A pending job](docs/research/live-api.md#a-pending-job) and [A faulted job](docs/research/live-api.md#a-faulted-job).

### Push-Pull: a batch lists invalid values under `errors`

- **Docs:** [Push-Pull][push-pull] shows only a batch whose values are all valid.
- **API:** a batch with one invalid `url` returned 202, created a job for the valid value, and listed the other under `errors` with its `message` and `url`.
  A batch whose every value failed also returned 202, with an empty `queries` list.
- **Evidence:** [A batch with invalid values](docs/research/live-api.md#a-batch-with-invalid-values).

### Rate Limits: each batch value and each page counts against the limit

- **Docs:** [Rate Limits][rate-limits] counts job submissions per second, and does not say how a batch or a job with `pages` above 1 counts.
- **API:** each batch value and each page of a `pages: 2` job took 1 from `-remaining`.
  A batch larger than `-remaining` returned 429 for the whole batch and created no job.
- **Evidence:** [What counts against the limit](docs/research/live-api.md#what-counts-against-the-limit) and [Exceeding the limit](docs/research/live-api.md#exceeding-the-limit).

### Rate Limits: the header names carry a UUID, and no header gives a reset time

- **Docs:** [Rate Limits][rate-limits] gives the pattern `x-ratelimit-limit_name-limit`.
  Its only example, a screenshot from December 2023, shows `x-ratelimit-internal-api-default-limit: 12000`.
- **API:** submissions returned `x-ratelimit-total-requests-<uuid>-limit: 50`, and rendered jobs added `x-ratelimit-total-render-requests-<uuid>-limit: 13`.
  Each came with a matching `-remaining` header.
  No response carried `Retry-After` or a reset header, including a 429.
- **Evidence:** [Limits and header names](docs/research/live-api.md#limits-and-header-names).

### Push-Pull: the content endpoint returns `png` as Base64 text

- **Docs:** [Push-Pull][push-pull] says the content endpoint returns a page "as raw content rather than inside a JSON object".
- **API:** for a `render: png` job, the content endpoint returned the Base64 string under `content-type: text/html`, not PNG bytes.
- **Evidence:** [The content endpoint](docs/research/live-api.md#the-content-endpoint).

### Response Codes: the shape of a `statuses` entry

- **Docs:** [Response Codes][response-codes] places upload codes in the `statuses` array, and no page shows an entry.
  Its Status column gives 13000 as `Upload Success` and 13102 as `No Such Path`.
- **API:** an upload added `{"event": "GCS_STORAGE_UPLOAD", "code": 13000, "message": "Upload Successful"}`.
  13102 came with `"message": "No such path"`.
- **Evidence:** [The `statuses` entry](docs/research/cloud-storage.md#the-statuses-entry).

### Response Codes: `statuses` fills after the job finishes

- **Docs:** [Response Codes][response-codes] says to check `statuses` if results do not reach the bucket, and does not say when the entry appears.
- **API:** 13 of 25 jobs showed `done` or `faulted` with an empty `statuses` first.
  A 13000 entry followed within 2.6 seconds, and a 10001 entry after about 20 seconds.
  `updated_at` did not change when the entry appeared.
- **Evidence:** [Timing](docs/research/cloud-storage.md#timing).

### Response Codes: an existing object name gives 10001

- **Docs:** [Response Codes][response-codes] lists 13001 Upload Failed and 13103 Access Denied, and does not say what an existing object name gives.
- **API:** on GCS, an upload to an existing name recorded 10001 `Unexpected Exception` and left the object unchanged.
  Two jobs in a batch whose names resolve to the same path give the same result for the second job.
- **Evidence:** [Failures](docs/research/cloud-storage.md#failures) and [Names in a batch](docs/research/cloud-storage.md#names-in-a-batch).

### Cloud Storage: a faulted job uploads too

- **Docs:** [Cloud Storage][cloud-storage] does not say whether Oxylabs uploads a faulted job.
- **API:** 14 faulted jobs each uploaded an object with a 613 result and recorded 13000.
  Oxylabs did not bill them.
- **Evidence:** [Faulted jobs](docs/research/cloud-storage.md#faulted-jobs).

### File name templating: a name without `.{{ extension }}` is a folder

- **Docs:** [File name templating][file-name-templating] shows that a name ending in `/` gets the default name, and does not say what happens to other names.
- **API:** every `storage_url` that did not end in `.{{ extension }}` became a folder, including `name.json` and `{{ job_id }}`.
  The API appended `/{{ job_id }}.{{ extension }}` to it.
- **Evidence:** [Object names](docs/research/cloud-storage.md#object-names).

### Cloud Storage: the object is always JSON, in a shape unlike `/results`

- **Docs:** [File name templating][file-name-templating] gives the default name `{{ job_id }}.{{ extension }}`, and no page says what the object holds.
- **API:** every object was a JSON document with `results` and `job`, and `{{ extension }}` resolved to `json` for `raw`, `parsed`, `png`, `markdown` and `xhr`.
  The object drops `type` from each result, gives `parse` as an integer and adds `job.client`, which holds the API username.
- **Evidence:** [What the object holds](docs/research/cloud-storage.md#what-the-object-holds) and [Output types](docs/research/cloud-storage.md#output-types).

### Push-Pull: 97 of the 123 sources take no batch

- **Docs:** [Push-Pull][push-pull] documents the batch endpoint without limiting it to any source.
- **API:** only `universal`, the Amazon, Google and Bing sources, the LLM sources, and `youtube_download`, `youtube_metadata` and `youtube_subtitles` took a batch.
  Every other source returned ``Source `<source>` is not available with a batch request.`` for each value.
- **Evidence:** [Sources that take a batch](docs/research/live-parameters.md#sources-that-take-a-batch).

### Unknown parameters return 202 and have no effect

- **Docs:** no page says what the API does with a parameter it does not know.
- **API:** an unknown top-level key, an unknown `context` key, and a key that belongs to another source all returned 202.
  The job object left them out, and the job ran and billed.
- **Evidence:** [Unknown keys](docs/research/live-parameters.md#unknown-keys).

### Rate Limits: a batch over the rendered limit returns 429 as a whole

- **Docs:** [Rate Limits][rate-limits] gives Starter 13 rendered jobs per second, and does not say how a batch counts against that.
- **API:** a batch of 14 rendered values returned 429 with `"message": "Too many requests. (Total Render Dynamic)."`, and created no job.
  A batch of 13 took 13 from the rendered limit.
- **Evidence:** [Rendered batches](docs/research/live-parameters.md#rendered-batches).

### E-Commerce Localization: an Amazon postal code that does not exist faults the job

- **Docs:** [E-Commerce Localization][ecom-loc] takes a postal code or an alpha-2 code on Amazon, and does not say what an invalid value does.
- **API:** a value in the wrong form for the `domain`, such as `United States` on `com`, returned 400.
  A well-formed postal code that does not exist, `99999`, faulted the job after 120 seconds.
- **Evidence:** [Amazon location](docs/research/live-parameters.md#amazon-location).

### Amazon Best Sellers: a batch bills a job for an empty `query`

- **Docs:** [Best Sellers][amz-bestsellers] marks `query`, a browse node ID, as required, and does not say what an empty one does.
- **API:** a batch with two empty `query` values created two jobs.
  Both fetched a page titled "Amazon Best Sellers: Best undefined", ended `done` and billed as rendered results.
  Every other source that takes a batch failed an empty value on its own.
- **Evidence:** [Sources that take a batch](docs/research/live-parameters.md#sources-that-take-a-batch).

[response-codes]: https://developers.oxylabs.io/products/web-scraper-api/response-codes
[help-response-codes]: https://developers.oxylabs.io/help-center/troubleshooting/response-codes-for-web-scraper-api
[job-id]: https://developers.oxylabs.io/help-center/troubleshooting/where-can-i-find-my-scraping-job-id
[integration-methods]: https://developers.oxylabs.io/products/web-scraper-api/integration-methods
[realtime]: https://developers.oxylabs.io/products/web-scraper-api/integration-methods/realtime
[push-pull]: https://developers.oxylabs.io/products/web-scraper-api/integration-methods/push-pull
[quick-start]: https://developers.oxylabs.io/get-started/quick-start-web-scraper-api
[rate-limits]: https://developers.oxylabs.io/products/web-scraper-api/usage-and-billing/rate-limits
[usage-statistics]: https://developers.oxylabs.io/products/web-scraper-api/usage-and-billing/usage-statistics
[cloud-storage]: https://developers.oxylabs.io/products/web-scraper-api/features/result-processing-and-storage/cloud-storage
[file-name-templating]: https://developers.oxylabs.io/products/web-scraper-api/features/result-processing-and-storage/cloud-storage/file-name-templating
[yt-guide]: https://developers.oxylabs.io/api-targets/video-and-social-media/youtube/youtube-scraping-guide-for-ai
[ecom-loc]: https://developers.oxylabs.io/products/web-scraper-api/features/localization/e-commerce-localization
[amz-bestsellers]: https://developers.oxylabs.io/api-targets/e-commerce/amazon/best-sellers
