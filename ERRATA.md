# Oxylabs docs errata

This file lists errors and gaps in the Oxylabs docs that live tests found, to report upstream.
GitBook exports the docs to `oxylabs/gitbook-public-english`, which is private, so the docs have no public issue tracker.
Each entry cites the page as published on 2026-09-25, or on 2026-09-28 for the parameter and retention entries, and links the test behind it.
The two entries on storage endpoints, the entry on a 400's `errors` list, the entries from the `universal` and Amazon runs and the entry on LLM sources through Realtime cite the pages as published on 2026-09-29.
The entries on `pages` limits and on a job larger than a rate limit cite the pages as published on 2026-09-30.

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

### Any Domain: `content_encoding` defaults to `utf-8`, not `base64`

- **Docs:** [Any Domain][any-domain] gives `base64` as the default of `content_encoding`.
- **API:** a job without it showed `"content_encoding": "utf-8"` in its job object.
  A PNG fetched without it came back as text with escaped bytes, which do not decode, and with `base64` it came back as Base64.
- **Evidence:** [Rendering and output types](docs/research/live-universal.md#rendering-and-output-types).

### Any Domain: a session lasts 25 minutes, not 10

- **Docs:** [Any Domain][any-domain] says a `session_id` keeps its proxy "for up to 10 minutes".
  [Proxy Location][proxy-loc] says "up to 25 minutes or 100 requests".
- **API:** the result's `session_info` gave an `expires_at` 25 minutes after the session's first job, and a `remaining` of 99, then 98.
- **Evidence:** [Sessions](docs/research/live-universal.md#sessions).

### Any Domain: headers and cookies need their `force_*` key

- **Docs:** [Any Domain][any-domain] lists `context:headers` and `context:cookies` without `force_headers` or `force_cookies`, and its "All parameters" example sends both without them.
  [Headers, Cookies, Method][headers] adds the `force_*` key.
- **API:** without the `force_*` key, the job ran and billed, and the site received neither the header nor the cookie.
- **Evidence:** [Headers, cookies and method](docs/research/live-universal.md#headers-cookies-and-method).

### Any Domain: the "All parameters" example returns 400

- **Docs:** [Any Domain][any-domain] shows an example with "all available parameters", which sends `parse: true` for `https://example.com` with no instructions.
- **API:** the example as written returned 400 with ``Parsing `https://example.com` url is allowed only with `parser_type` or `parsing_instructions` parameter.``
- **Evidence:** [Headers, cookies and method](docs/research/live-universal.md#headers-cookies-and-method).

### Proxy Location: `Germany` exits in Lithuania

- **Docs:** [Proxy Location][proxy-loc] lists `Germany` among the countries that `geo_location` selects.
- **API:** in four jobs, `Germany` and `DE` gave exit IPs that Cloudflare, ipinfo.io and ip-api.com place in Lithuania.
  `France`, `United Kingdom` and `Japan` gave exit IPs in those countries.
- **Evidence:** [Location](docs/research/live-universal.md#location).

### List of parsing functions: a wrong `_args` shape can work or fail differently

- **Docs:** [List of parsing functions][functions] says "Using the wrong shape does not fail the job: the field comes back `null`, `parse_status_code` is `12005`, and `_warnings` contains *received arguments of invalid type `array`* (or `str`)."
- **API:** `xpath`, `xpath_one` and `css` with a bare string returned their usual output, with no warning.
  `join` and `average` with an array returned `null` with `Failed to process function`.
  `select_nth`, `regex_search` and `regex_find_all` behaved as documented.
- **Evidence:** [Mistakes the API accepts](docs/research/live-universal.md#mistakes-the-api-accepts).

### JS Rendering: `wait_time_s` takes 0

- **Docs:** [JS Rendering & Browser Control][js] restricts `wait_time_s` to "0 < `wait_time_s` <= 60", with a default of 0.
- **API:** `wait_time_s: 0` returned 202, and `-1` returned 400 with "Input should be greater than or equal to 0".
  `timeout_s: 0` returned 400, as documented.
- **Evidence:** [Checks at submission](docs/research/live-universal.md#checks-at-submission).

### JS Rendering: an instruction after `fetch_resource` returns 500

- **Docs:** [JS Rendering & Browser Control][js] says that after `fetch_resource`, "any subsequent instructions will not be executed".
  It also says that "any inconsistency in regards to instruction format will result in a `400`".
- **API:** a `wait`, a `click` or a second `fetch_resource` after `fetch_resource` returned 500 with an HTML error page, and created no job.
  A `filter` that is not a valid regex did the same.
  All 9 such submissions returned 500.
- **Evidence:** [A 500 at submission](docs/research/live-universal.md#a-500-at-submission).

### JS Rendering: `on_error: error` does not stop the instructions

- **Docs:** [JS Rendering & Browser Control][js] says that `on_error: "error"`, the default, "Stops the execution of browser instructions."
- **API:** after a `wait_for_element` that failed, the next `click` ran, with `on_error` unset, `error` or `skip`.
  After a `click` on a missing selector, which gives a warning, the next instruction ran too.
- **Evidence:** [Effects](docs/research/live-universal.md#effects).

### JS Rendering: errors appear under `browser_instructions_errors`

- **Docs:** [JS Rendering & Browser Control][js] puts errors and warnings "under the keys `browser_instructions_error` or `browser_instructions_warnings`".
- **API:** errors appeared under `browser_instructions_errors`, and warnings under `browser_instructions_warnings`.
- **Evidence:** [Effects](docs/research/live-universal.md#effects).

### Amazon URL: the API alters the URL, and runs some URLs as another source

- **Docs:** [URL][amz-url] says "We do not strip any parameters or alter your URLs in any other way."
- **API:** every `amazon` job appended `language=<locale>` to its URL.
  A product URL became an `amazon_product` job and a search URL an `amazon_search` job, and Usage Statistics counted them under those sources.
  A `domain` sent beside the URL became the URL's own domain in the job object.
- **Evidence:** [The `amazon` source](docs/research/live-amazon.md#the-amazon-source).

### Amazon Product, Pricing, Best Sellers and URL: `com` takes 67 currencies, not USD alone

- **Docs:** the four pages link [`currency_new.json`][currency-new], which lists USD alone for `com`: "While the US Amazon marketplace supports multiple currencies, for now, we only support the default currency, USD."
- **API:** all six Amazon sources accepted the 67 codes for `com` that [`Amazon_search_currency_values.json`][currency-search] lists, and the [Search][amz-search] page links that file.
  `XYZ` on `com` returned a 400 that listed the 67 codes, on every source.
- **Evidence:** [Currencies](docs/research/live-amazon.md#currencies) and [Location rules](docs/research/live-amazon.md#location-rules).

### Amazon Pricing: the currency example returns 400, and `context:currency` has no effect

- **Docs:** [Pricing][amz-pricing] documents `context:currency`, and its code example sends `AUD` on `nl`.
- **API:** the example returned 400 with ``Context parameter with key `currency` for domain `nl` is not valid. Available values: `EUR`.``
  `GBP` on `de` passed the check and billed, and the parsed offers kept their prices in euros.
- **Evidence:** [Locales and currencies](docs/research/live-amazon.md#locales-and-currencies).

### Amazon Best Sellers: the currency example has no effect

- **Docs:** [Best Sellers][amz-bestsellers] sends `AUD` on `com` in its code example.
- **API:** the example billed, and its prices stayed in USD.
  The Search page's currency file gives the reason: on `com`, a currency other than USD needs a `geo_location` outside the US, "Otherwise, the desired currency will not be applied."
  The Best Sellers page and the currency file it links do not say so.
- **Evidence:** [Locales and currencies](docs/research/live-amazon.md#locales-and-currencies).

### Domain and Locale: `ae` defaults to Arabic, not English

- **Docs:** [Domain and Locale][domain-locale] marks `en_AE`, English, as the default for `ae`, and says a caller who wants the default need not send `locale`.
- **API:** without `locale`, an `ae` job fetched its URL with `language=ar_AE`, and the page came back in Arabic.
  `locale: en_AE` returned it in English.
- **Evidence:** [Domains and defaults](docs/research/live-amazon.md#domains-and-defaults).

### E-Commerce Localization: `com.be` and `nl` take a delivery location, and `ae` takes any value

- **Docs:** [E-Commerce Localization][ecom-loc] says "`cn`, `com.tr`, `com.be`, and `nl` do not support custom delivery locations."
  It says `ae` "Accepts UAE city names as `geo_location`, e.g., `"geo_location": "Abu Dhabi"`, or 2-letter country codes."
- **API:** `cn` and `com.tr` returned 400 for every value.
  `DE` on `com.be` set the delivery location to Germany, and `NL` on `nl` set it to 1079 Amsterdam.
  `ae` ran no check, and `90210` set a delivery location named "90210".
- **Evidence:** [Locations](docs/research/live-amazon.md#locations) and [Location rules](docs/research/live-amazon.md#location-rules).

### Amazon Search: `min_price: 0` passes, and sets no filter

- **Docs:** [Search][amz-search] says `context:min_price` and `context:max_price` "Must be positive integers."
- **API:** `min_price: -100` returned 400 with ``Parameter `context:min_price` must be a positive integer.``
  `min_price: 0` returned 202 and billed, and the URL carried no price filter.
- **Evidence:** [Free checks](docs/research/live-amazon.md#free-checks) and [Sorting and filters](docs/research/live-amazon.md#sorting-and-filters).

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
  A job's pages also count against the rendered limit, and they count even where the job fetches one page: a `universal` job with `pages: 3` took 3, although its job object read `pages: 1`.
- **Evidence:** [What counts against the limit](docs/research/live-api.md#what-counts-against-the-limit), [Exceeding the limit](docs/research/live-api.md#exceeding-the-limit) and [A job larger than the limit](docs/research/live-api.md#a-job-larger-than-the-limit).

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

### Cloud Storage: an endpoint that does not resolve leaves `statuses` empty

- **Docs:** [Response Codes][response-codes] says to "check `statuses` if results do not arrive in your storage", and lists 13001 Upload Failed and 13102 No Such Path.
- **API:** two fault jobs set `storage_type` to `s3_compatible` and `tos`, with a `storage_url` whose host does not resolve.
  Both ended `faulted`, and 48 minutes later `statuses` was still empty.
- **Evidence:** [An endpoint that does not resolve](docs/research/cloud-storage.md#an-endpoint-that-does-not-resolve).

### Cloud Storage: the job object hides the credentials in `storage_url`

- **Docs:** [Cloud Storage][cloud-storage] puts the access key and secret in `storage_url` for `tos` and `s3_compatible`.
  [File name templating][file-name-templating] says the job's `storage_url` shows the resolved path, and does not say what happens to the credentials.
- **API:** the submission and the status endpoint returned `https://redacted:redacted@<host>/bucket/folder/<job_id>.json`.
- **Evidence:** [An endpoint that does not resolve](docs/research/cloud-storage.md#an-endpoint-that-does-not-resolve).

### Push-Pull: 97 of the 123 sources take no batch

- **Docs:** [Push-Pull][push-pull] documents the batch endpoint without limiting it to any source.
- **API:** only `universal`, the Amazon, Google and Bing sources, the LLM sources, and `youtube_download`, `youtube_metadata` and `youtube_subtitles` took a batch.
  Every other source returned ``Source `<source>` is not available with a batch request.`` for each value.
- **Evidence:** [Sources that take a batch](docs/research/live-parameters.md#sources-that-take-a-batch).

### Unknown parameters return 202 and have no effect

- **Docs:** no page says what the API does with a parameter it does not know.
- **API:** on `universal` and `amazon_search`, an unknown top-level key, an unknown `context` key, and a key that belongs to another source all returned 202.
  The job object left them out, and the job ran and billed.
  `walmart_product` returned 400 for an unknown key instead, with `[foo_bar]: This field was not expected.`
- **Evidence:** [Unknown keys](docs/research/live-parameters.md#unknown-keys) and [Probes on 2026-09-29](docs/research/live-parameters.md#probes-on-2026-09-29).

### Response Codes: a 400 can list its errors under `errors`, with no `message`

- **Docs:** [Response Codes][response-codes] says a 400's body "has a more specific error message", and does not give its shape.
- **API:** most 400s carried a `message` string.
  `walmart_product` with a missing or unknown key returned an `errors` list of strings and no `message`, such as `["[product_id]: This field is missing.", "[query]: This field was not expected."]`.
  A mistake in `parsing_instructions` returned an `errors` list of objects with `_fn`, `_fn_idx`, `_msg` and `_path`.
  A mistake in `browser_instructions` returned an `errors` object with a `message`, and for a failed check the `instruction` and pydantic's `validation_errors`.
- **Evidence:** [Probes on 2026-09-29](docs/research/live-parameters.md#probes-on-2026-09-29), [Mistakes the API returns 400 for](docs/research/live-universal.md#mistakes-the-api-returns-400-for) and [Checks at submission](docs/research/live-universal.md#checks-at-submission).

### Rate Limits: a batch over the rendered limit returns 429 as a whole

- **Docs:** [Rate Limits][rate-limits] gives Starter 13 rendered jobs per second, and does not say how a batch counts against that.
- **API:** a batch of 14 rendered values returned 429 with `"message": "Too many requests. (Total Render Dynamic)."`, and created no job.
  A batch of 13 took 13 from the rendered limit.
- **Evidence:** [Rendered batches](docs/research/live-parameters.md#rendered-batches).

### Rate Limits: a job larger than a limit returns 429 every time

- **Docs:** [Rate Limits][rate-limits] gives each plan's limits, and does not say what a job whose pages exceed one returns.
- **API:** a rendered job with `pages: 14`, against Starter's rendered limit of 13, returned 429 with `"message": "Too many requests. (Total Render Dynamic)."` in 6 of 6 fresh windows, on `universal`, `amazon_search` and `bing_search`.
  It took nothing from either limit, and a rendered job with `pages: 13` was accepted.
- **Evidence:** [A job larger than the limit](docs/research/live-api.md#a-job-larger-than-the-limit).

### E-Commerce Localization: an Amazon postal code that does not exist faults the job

- **Docs:** [E-Commerce Localization][ecom-loc] takes a postal code or an alpha-2 code on Amazon, and does not say what an invalid value does.
- **API:** a value in the wrong form for the `domain`, such as `United States` on `com`, returned 400.
  A well-formed postal code that does not exist, `99999`, faulted the job after 120 seconds.
- **Evidence:** [Amazon location](docs/research/live-parameters.md#amazon-location).

### Amazon Best Sellers: an empty or unknown `query` bills a rendered page

- **Docs:** [Best Sellers][amz-bestsellers] marks `query`, a browse node ID, as required, and does not say what an empty or unknown one does.
- **API:** a batch with two empty `query` values created two jobs.
  A single submission with `query: ""` and one with `query: "abc"` created a job each.
  Every such job fetched a page titled "Amazon Best Sellers: Best undefined", ended `done` and billed as a rendered result.
  Every other source that takes a batch failed an empty value on its own.
- **Evidence:** [Sources that take a batch](docs/research/live-parameters.md#sources-that-take-a-batch) and [Input and page rules](docs/research/live-amazon.md#input-and-page-rules).

### Any Domain: `universal` takes `context` keys that no page names

- **Docs:** [Any Domain][any-domain], [Headers, Cookies, Method][headers] and [E-Commerce Localization][ecom-loc] name 10 `context` keys for `universal`.
- **API:** the job object lists 16.
  `hc_policy`, `parse_json_schema`, `parse_json_prompt`, `proxy_location` and `delivery_location` appear on no page.
  `fulfillment_type` appears only for Walmart's non-US domains.
- **Evidence:** [Context keys](docs/research/live-universal.md#context-keys) and [Context keys by source](docs/research/live-parameters.md#context-keys-by-source).

### Any Domain: a redirect faults the job when `follow_redirects` is `false`

- **Docs:** [Any Domain][any-domain] describes `follow_redirects` and `successful_status_codes`, and says redirects are followed "up to a limit of 10 links".
- **API:** with `follow_redirects: false`, a 302 faulted the job, unbilled.
  `successful_status_codes: [302]` returned 400 with ``Context `successful_status_codes` value 302 is not supported (nor other status codes from the same family)``.
  A chain of 11 redirects faulted the job with `status_code: 400` in its results entry.
- **Evidence:** [Redirects and status codes](docs/research/live-universal.md#redirects-and-status-codes).

### Any Domain: a page with an empty body faults the job

- **Docs:** [Traffic and Billing][billing] bills `2xx` and `4xx` results, and [Any Domain][any-domain] says `successful_status_codes` returns the content of the codes it lists.
- **API:** empty pages with status 200, 404 and 503 faulted the job, unbilled, even with 503 in `successful_status_codes`.
  A 404 page with a body, and a 503 page with a body and 503 in `successful_status_codes`, ended `done` and billed.
- **Evidence:** [Redirects and status codes](docs/research/live-universal.md#redirects-and-status-codes).

### Headers, Cookies, Method: a custom `User-Agent` has no effect

- **Docs:** [Headers, Cookies, Method][headers] says the API sends custom headers "together with the predefined headers set".
- **API:** with `force_headers: true`, a custom `X-Oxy-Test` header reached the site, and a custom `User-Agent` did not.
  The site received Oxylabs' own agent.
- **Evidence:** [Headers, cookies and method](docs/research/live-universal.md#headers-cookies-and-method).

### Headers, Cookies, Method: `http_method` also takes `OPTIONS`

- **Docs:** [Headers, Cookies, Method][headers] describes `GET`, the default, and `POST`.
- **API:** `put` returned 400 with `HTTP method put is not supported. Supported methods are: GET, POST, OPTIONS.`
  `options` and `POST` returned 202.
- **Evidence:** [Values the API checks](docs/research/live-universal.md#values-the-api-checks).

### User Agent Type: five more values pass, and pick no browser

- **Docs:** [User Agent Type][uat] lists seven values.
- **API:** `desktop_chrome`, `desktop_edge`, `desktop_firefox`, `desktop_opera` and `desktop_safari`, which SDK 3.0.0 sends, returned 202 and billed.
  In 20 jobs, 4 received an agent of the browser the value names, and the rest received other desktop browsers.
  Any other value returned 400.
- **Evidence:** [User agent types](docs/research/live-universal.md#user-agent-types).

### Proxy Location: an unknown `geo_location` bills with no location

- **Docs:** [Proxy Location][proxy-loc] lists the values `geo_location` supports, and does not say what another value does.
- **API:** `universal` accepted every string, including `Atlantis`, lowercase `de` and `90210`.
  `Atlantis` and `de` billed, and their exit IPs were in the US.
  `DE` gave the same exit IP as `Germany`, and `FR` the same as `France`.
- **Evidence:** [Location](docs/research/live-universal.md#location).

### Custom Parser: submission checks the structure, not the arguments

- **Docs:** [Custom Parser: Getting started][parser-start] says that instructions "referencing a non-existent function are rejected upon submission", and does not say what else is.
- **API:** a missing `_fn`, a `_fns` that is not a list, an `_items` or field that is not an object, an unknown key in a function entry, empty instructions and an unknown `_on_error` returned 400.
  Any `_args`, an invalid XPath and an invalid regex returned 202, and the job billed with `parse_status_code: 12005`.
- **Evidence:** [Mistakes the API returns 400 for](docs/research/live-universal.md#mistakes-the-api-returns-400-for) and [Mistakes the API accepts](docs/research/live-universal.md#mistakes-the-api-accepts).

### Custom Parser: `_on_error` also takes `warn` and `error`

- **Docs:** [Parsing instruction examples][parse-examples] describes `"_on_error": "suppress"` only.
- **API:** `_on_error: ignore` returned 400 with ``Invalid `_on_error` value `ignore`, must be one of suppress, warn, error``.
  `warn` behaved like the default.
  `error` put the failure under `_errors` and set `parse_status_code: 12004`, and the result billed.
- **Evidence:** [`_on_error`](docs/research/live-universal.md#_on_error).

### Custom Parser: `parse` without instructions names an undocumented `parser_type`

- **Docs:** [Any Domain][any-domain] says `parse: true` returns parsed data "as long as a dedicated parser exists for the submitted URL's page type", and no page documents a `parser_type` parameter.
- **API:** `parse: true` without instructions, for a page with no dedicated parser, returned 400 with ``Parsing `<url>` url is allowed only with `parser_type` or `parsing_instructions` parameter``.
  `parser_type: custom` and `parser_type: preset` returned 202, and other values returned 400.
  A `custom` job without instructions billed with `parse_status_code: 12003`.
- **Evidence:** [`parse` without instructions](docs/research/live-universal.md#parse-without-instructions).

### JS Rendering: `scroll` takes no `x` or `y`

- **Docs:** [JS Rendering & Browser Control][js] gives `scroll` the arguments `x: int` and `y: int`.
- **API:** `scroll` without `x` and `y` returned 202 and billed, and the page did not scroll.
- **Evidence:** [Checks at submission](docs/research/live-universal.md#checks-at-submission) and [Effects](docs/research/live-universal.md#effects).

### JS Rendering: instructions that run too long fault the job

- **Docs:** [JS Rendering & Browser Control][js] limits each `wait_time_s` to 60 seconds, and sets no limit on a list of instructions.
- **API:** five `wait` instructions of 60 seconds returned 202, and the job faulted with 613 after 325 seconds, unbilled.
- **Evidence:** [Effects](docs/research/live-universal.md#effects).

### Amazon: the sources take `context` keys that no page names

- **Docs:** the Amazon pages name eight `context` keys between them, and [Sellers][amz-sellers] names none.
- **API:** every Amazon job object lists `force_headers`, `force_cookies`, `hc_policy`, `parse_json_schema`, `parse_json_prompt`, `check_empty_geo` and `safe_search`, and `parse: true` adds `successful_parse_status_codes`.
  `amazon_pricing` lists `condition`, `amazon_sellers` lists `currency`, `amazon_bestsellers` lists `category_id`, and `amazon` lists `cookies` and `headers`.
  No page names `check_empty_geo`, `parse_json_schema`, `parse_json_prompt` or `condition`.
  `hc_policy` and `successful_parse_status_codes` appear only in a sample job object on [Google AI Mode][g-ai-mode].
  `condition: new` added `&condition=new` to the offers URL, and `check_empty_geo: true` without a `geo_location` faulted the job.
  `category_id: electronics` on `amazon_bestsellers` left the job `pending` for at least 44 minutes.
- **Evidence:** [Context keys by source](docs/research/live-amazon.md#context-keys-by-source).

### Domain and Locale: the API takes `co.za`

- **Docs:** [Domain and Locale][domain-locale] lists 23 Amazon domains, and neither currency file lists `co.za`.
- **API:** `co.za` passed every check, and its job fetched `amazon.co.za` with `language=en_ZA` and prices in ZAR.
  Its checks allow the locale `en_ZA` and the currency `ZAR`.
- **Evidence:** [Domains](docs/research/live-amazon.md#domains) and [Domains and defaults](docs/research/live-amazon.md#domains-and-defaults).

### Amazon currency files: `cn` and `ie` are missing, and `ie` runs no check

- **Docs:** [`currency_new.json`][currency-new] and [`Amazon_search_currency_values.json`][currency-search] list 21 domains, and neither lists `cn` or `ie`.
- **API:** `cn` allows `CNY` only.
  `ie` runs no currency check: `XYZ`, `USD` and `eur` passed, and `XYZ` billed with prices in EUR.
- **Evidence:** [Currencies](docs/research/live-amazon.md#currencies).

### E-Commerce Localization: eight Amazon domains run no `geo_location` check

- **Docs:** [E-Commerce Localization][ecom-loc] takes a postal code inside the marketplace's country and a 2-letter country code outside it.
- **API:** `ae`, `com.be`, `eg`, `ie`, `pl`, `sa`, `se` and `sg` accepted every value, including `90210` and lowercase `de`.
  `90210` on `pl` faulted the job at once, and `90210` on `ae` billed.
  On `com`, `XX` passed and billed with Amazon's default location.
- **Evidence:** [Locations](docs/research/live-amazon.md#locations) and [Location rules](docs/research/live-amazon.md#location-rules).

### User Agent Type: a rendered job ignores it

- **Docs:** [User Agent Type][uat] and the Amazon pages describe `user_agent_type` as the device type, and do not tie it to rendering.
- **API:** `mobile` returned Amazon's mobile page on every Amazon source that ran without rendering.
  With `render: html` on `amazon_product`, and on `amazon_bestsellers`, which Oxylabs always renders, `mobile` returned the desktop page.
- **Evidence:** [Top-level parameters](docs/research/live-amazon.md#top-level-parameters).

### Amazon Product, Pricing and Sellers: an input that passes the check can bill a 404 page

- **Docs:** [Product][amz-product] and [Pricing][amz-pricing] take a "10-symbol ASIN code", and [Sellers][amz-sellers] a seller ID.
  No page says what an input that does not exist does.
- **API:** an ASIN shorter than 10 characters returned ``ASIN length is not valid.``, and a lowercase one ``ASIN should only contain alphanumeric values.``
  An 11-character ASIN, an ASIN that does not exist and the seller ID `abc` returned 202, and each billed a 404 page.
- **Evidence:** [Input and page rules](docs/research/live-amazon.md#input-and-page-rules).

### Amazon: the docs give no page limits

- **Docs:** [Search][amz-search], [Pricing][amz-pricing] and [Best Sellers][amz-bestsellers] document `start_page` and `pages` without a limit, and the other three pages do not document them.
- **API:** `pages` above 20 returned ``Parameter `pages` should not exceed 20``.
  A page past the last billed on `amazon_search` and `amazon_pricing`, and faulted on `amazon_bestsellers`.
  On `amazon_product`, `amazon_sellers` and `amazon`, `pages: 2` became 1, and `start_page: 2` billed the first page labelled as page 2.
- **Evidence:** [Free checks](docs/research/live-amazon.md#free-checks), [Top-level parameters](docs/research/live-amazon.md#top-level-parameters) and [Input and page rules](docs/research/live-amazon.md#input-and-page-rules).

### Google and Bing: the docs give no page limits

- **Docs:** [Google Search][g-search], [Google Ads][g-ads], [Local Search][g-local], [Shopping Search][g-shopping-search] and [Bing Search][bing-search] describe `pages` as "Number of pages to retrieve.", without a limit.
- **API:** `pages` above 20 returned ``Parameter `pages` should not exceed 20.`` on all five, and on `universal`, `google_travel_hotels` and `chatgpt`, whose pages do not document it.
  `google_search` returned ``Parameter `pages` cannot exceed 10 for this source.`` for 11 and for 20, and `google_ads` for 20.
- **Evidence:** [A job larger than the limit](docs/research/live-api.md#a-job-larger-than-the-limit).

### Amazon: the page types that `amazon` parses are not listed

- **Docs:** the [Amazon][amazon] overview limits parsing on `amazon` to "URLs of specific Amazon page types", and links [Domain and Locale][domain-locale], which lists no page types.
- **API:** `parse: true` with a help page URL returned ``Parsing with `url` parameter is not allowed for `amazon` source.``
  Product and search URLs ran as `amazon_product` and `amazon_search` jobs, which parse.
- **Evidence:** [The `amazon` source](docs/research/live-amazon.md#the-amazon-source).

### Amazon Product: a `parse` that is not a boolean becomes `false`

- **Docs:** [Product][amz-product] says `parse` "Returns parsed data when set to `true`".
- **API:** `parse: "yes"` returned 202, the job object held `parse: false`, and the job billed a raw result.
- **Evidence:** [Input and page rules](docs/research/live-amazon.md#input-and-page-rules).

### JS Rendering: `render: ""` faults an `amazon_bestsellers` job

- **Docs:** [JS Rendering & Browser Control][js] says Oxylabs enforces rendering on some page types, and that `"render": ""` disables it.
  Its list of those page types names `amazon_bestsellers`.
- **API:** `render: ""` set `is_render_forced: false`, and both such jobs faulted with 613 after 77 and 97 seconds, unbilled.
  So every billed `amazon_bestsellers` result is rendered.
- **Evidence:** [Forced rendering](docs/research/live-amazon.md#forced-rendering).

### Rate Limits: a job that Oxylabs renders by force carries no rendered-limit header

- **Docs:** [Rate Limits][rate-limits] gives Starter 13 rendered jobs per second, and does not say whether a job that Oxylabs renders by force counts against that.
- **API:** every `amazon_bestsellers` submission without `render` carried only the total limit's headers, and the one with `render: html` carried the rendered limit's too.
  Usage Statistics counted all 15 of the run's `amazon_bestsellers` results as rendered.
- **Evidence:** [Forced rendering](docs/research/live-amazon.md#forced-rendering).

### Response Codes: a faulted job can have no results entry

- **Docs:** [Response Codes][response-codes] gives 612 and 613 for a job that Oxylabs failed, and does not say what the results endpoint returns for one.
- **API:** two `cn` jobs faulted after 5 and 6 minutes, and the results endpoint returned 204 with `x-oxylabs-job-status: faulted` for them, still 22 and 28 minutes later.
  An `amazon_search` job with `90210` on `pl` faulted in the second it was created, and its one results entry carried `status_code: 400`.
- **Evidence:** [Faulted and stuck jobs](docs/research/live-amazon.md#faulted-and-stuck-jobs).

### LLMs and AI: Realtime returns 422 for an LLM source

- **Docs:** [LLMs and AI][llms-and-ai] says "Realtime and Proxy Endpoint are not available" for `chatgpt`, `gemini` and `perplexity`, and does not say what Realtime returns for them.
  [Response Codes][response-codes] gives 422 for a payload that is not a valid JSON object.
- **API:** a Realtime job for each of the three sources returned `422` in 0.13 seconds, with `"message": "Realtime integration is not supported for LLM sources. Please use Push-Pull."`.
  The response carried no job ID, no `x-oxylabs-*` headers and no rate-limit headers.
- **Evidence:** [Probes on 2026-09-29](docs/research/live-api.md#probes-on-2026-09-29).

[response-codes]: https://developers.oxylabs.io/products/web-scraper-api/response-codes
[help-response-codes]: https://developers.oxylabs.io/help-center/troubleshooting/response-codes-for-web-scraper-api
[job-id]: https://developers.oxylabs.io/help-center/troubleshooting/where-can-i-find-my-scraping-job-id
[integration-methods]: https://developers.oxylabs.io/products/web-scraper-api/integration-methods
[llms-and-ai]: https://developers.oxylabs.io/api-targets/llms-and-ai
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
[any-domain]: https://developers.oxylabs.io/api-targets/overview
[headers]: https://developers.oxylabs.io/products/web-scraper-api/features/http-context-and-job-management/headers-cookies-method
[uat]: https://developers.oxylabs.io/products/web-scraper-api/features/http-context-and-job-management/user-agent-type
[proxy-loc]: https://developers.oxylabs.io/products/web-scraper-api/features/localization/proxy-location
[js]: https://developers.oxylabs.io/products/web-scraper-api/features/js-rendering-and-browser-control
[functions]: https://developers.oxylabs.io/products/web-scraper-api/features/custom-parser/writing-instructions-manually/list-of-functions
[parse-examples]: https://developers.oxylabs.io/products/web-scraper-api/features/custom-parser/writing-instructions-manually/parsing-instruction-examples
[parser-start]: https://developers.oxylabs.io/products/web-scraper-api/features/custom-parser/getting-started
[billing]: https://developers.oxylabs.io/products/web-scraper-api/usage-and-billing/billing-information
[amazon]: https://developers.oxylabs.io/api-targets/e-commerce/amazon
[amz-product]: https://developers.oxylabs.io/api-targets/e-commerce/amazon/product
[amz-search]: https://developers.oxylabs.io/api-targets/e-commerce/amazon/search
[amz-pricing]: https://developers.oxylabs.io/api-targets/e-commerce/amazon/pricing
[amz-sellers]: https://developers.oxylabs.io/api-targets/e-commerce/amazon/sellers
[amz-url]: https://developers.oxylabs.io/api-targets/e-commerce/amazon/url
[domain-locale]: https://developers.oxylabs.io/products/web-scraper-api/features/localization/domain-locale
[currency-search]: https://files.gitbook.com/v0/b/gitbook-x-prod.appspot.com/o/spaces%2FzrXw45naRpCZ0Ku9AjY1%2Fuploads%2FIAHLazcDOwZSiZ6s8IJt%2FAmazon_search_currency_values.json?alt=media
[currency-new]: https://files.gitbook.com/v0/b/gitbook-x-prod.appspot.com/o/spaces%2FzrXw45naRpCZ0Ku9AjY1%2Fuploads%2FNNybEQaVnTrc9ymR1NGE%2Fcurrency_new.json?alt=media
[g-ai-mode]: https://developers.oxylabs.io/api-targets/search-engines/google/ai-mode
[g-search]: https://developers.oxylabs.io/api-targets/search-engines/google/search/search
[g-ads]: https://developers.oxylabs.io/api-targets/search-engines/google/ads
[g-local]: https://developers.oxylabs.io/api-targets/search-engines/google/search/local-search
[g-shopping-search]: https://developers.oxylabs.io/api-targets/search-engines/google/shopping/shopping-search
[bing-search]: https://developers.oxylabs.io/api-targets/search-engines/bing/search
