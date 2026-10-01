# What a live test shows about parameters

This note records what a small billed run against the live Oxylabs API showed about parameters.
It answers [What does a live test show about parameters?](https://github.com/ozanozbeker/oxyscraper/issues/26).
Its questions are the open questions in the [Parameter catalog](parameter-catalog.md#open-questions).
The run took place on 2026-09-28, from 16:47 to 16:58 UTC, on the account with the Starter plan.
It spent 20 results, 6 of them rendered, and Usage Statistics agrees.

Free probes used fault jobs: `universal` jobs for unregistered `.com` names, as [Fault jobs](live-api.md#fault-jobs) describes.
All 23 fault jobs ended `faulted`, and none billed.
The other free probes returned 400 or 429, or were batches whose every value failed.

The samples replace the account's client ID with `123456`, its username with `USERNAME`, and the UUID inside rate-limit header names with the nil UUID.
Every other value is what the API returned, except where `"...": "..."` marks a cut.
The raw captures stay outside the repo.

## Answer

- **Unknown keys.**
  The API returns 202 for an unknown top-level key and for an unknown `context` key, and leaves the key out of the job object.
  Push-Pull, batches and Realtime behave the same, on `universal` and on `amazon_search`.
  A key that belongs to another source, or that belongs in `context`, is left out the same way.
  So a misspelt parameter bills a result and has no effect.
- **Context keys.**
  Each job object lists the `context` keys its source takes, with their defaults.
  `universal` lists 16, `google_search` 18, `amazon_search` 14 and `amazon_product` 9.
  Ten of them appear on no docs page the catalog read, such as `check_empty_geo`, `aomd` and `proxy_location`.
  The LLM sources return a job object of 7 fields, with no `context`.
- **Batch.**
  Only 26 of the 123 documented sources take a batch: `universal`, the Amazon, Google and Bing sources, the LLM sources, and three YouTube sources.
  For the other 97, each value fails with ``Source `<source>` is not available with a batch request``.
  A `prompt` array works, although the docs name only `query` and `url`.
  A `product_id`, `video_id`, `channel_handle` or `category_id` array returns 400, and every source with one of those input keys is among the 97.
- **Empty input.**
  In a batch, an empty value fails on its own for 25 of the 26 batch sources.
  `amazon_bestsellers` created a job for each empty `query`, and both jobs ended `done` and billed.
- **Amazon location.**
  `amazon_product` checks `geo_location` against `domain` at submission.
  `United States` on `com`, `DE` on `nl` and `90210` on `co.uk` returned 400.
  `99999` passed the check, and its job faulted after 120 seconds, unbilled.
  That fits the quirk the earlier client recorded.
  `90210` and `DE` on `com` set the page's delivery location.
- **Rendered batches.**
  A batch with more rendered values than the rendered limit has left returns 429 for the whole batch, and creates no job.
  Its message, `Too many requests. (Total Render Dynamic).`, names the rendered limit.
  Batches of 14 rendered values did this on `universal` and on `google_search`, and a batch of 13 went through.
  The earlier client sent up to 50 values per batch, which fits its quirk.
- **Google faults.**
  4 of 12 `google_search` jobs faulted with 613: 2 of 4 rendered jobs and 2 of 8 others, in batches and alone.
  So neither rendering nor batching explains the faults.
- **SDK payloads.**
  The API knows `universal_ecommerce` and five more sources that only SDK 3.0.0 lists.
  It returns `Unsupported source.` for `amazon_reviews`, `amazon_questions` and `shein_search`.
  A top-level `sort_by` on `amazon_search` has no effect, while `context:sort_by` sorts the results.
  `domain: de` on `google_search` stays in the job object, but the job fetched `google.com`.
- **Feature parameters.**
  `amazon_search` takes `markdown`, `xhr` with `render`, and `parsing_instructions` with `parse`.
  `parsing_instructions` replaces the dedicated parser's output.
  `google_search` takes `markdown` too.
- **Rendered results.**
  Usage Statistics counted 6 rendered results, against the 4 the plan expected.
  The other 2 came from `amazon_bestsellers`, whose results show `is_render_forced: true`.
  The Perplexity job counted as rendered, but it took nothing from the rendered limit.
- **Spend.**
  The run spent 20 results, against the plan's 21.

## Runs

| Run | Time (UTC) | What it sent | Results billed |
| --- | --- | --- | --- |
| Sources | 16:47 | 12 submissions with no input key or an empty one, and one `universal_ecommerce` fault job | 0 |
| Unknown keys | 16:47 | 8 `universal` fault jobs with unknown or misplaced keys, through Push-Pull, a batch and Realtime, and 2 batches with empty values | 0 |
| Rendered batches | 16:47 to 16:48 | `universal` fault batches of 14 and 13 rendered values, and a `google_search` batch of 14 rendered queries | 0 |
| Google | 16:48 to 16:57 | Three 2-query `google_search` batches, two of them rendered, two single jobs and a 3-query batch | 7 |
| Amazon unknown keys | 16:49 | One `amazon_search` job with an unknown top-level key and an unknown `context` key | 1 |
| Batch keys | 16:49 to 16:51 | 2-value batches for five input keys, then `query` batches for four of their sources | 1 |
| Batch map | 16:51 to 16:52 | A batch of two empty values for each of the 123 documented sources | 2 |
| Location | 16:52 to 16:54 | 7 `amazon_product` jobs with different `domain` and `geo_location` values | 3 |
| SDK and features | 16:55 to 16:56 | 5 `amazon_search` jobs and one `google_search` job, each with the parameters under test | 6 |

## Unknown keys

| Payload adds | Source | Endpoint | Status | Key in the job object |
| --- | --- | --- | --- | --- |
| `foo_bar: "x"` | `universal` | Push-Pull | 202 | no |
| `foo_bar: null` | `universal` | Push-Pull | 202 | no |
| `context:foo_bar` | `universal` | Push-Pull | 202 | no |
| `delivery_zip: "10001"` | `universal` | Push-Pull | 202 | no |
| `sort_by: "price_low_to_high"` | `universal` | Push-Pull | 202 | no |
| `context:sort_by` | `universal` | Push-Pull | 202 | no |
| `foo_bar: "x"` | `universal` | batch | 202 | no |
| `foo_bar: "x"` | `universal` | Realtime | 200 | no |
| `foo_bar: "x"` and `context:foo_bar` | `amazon_search` | Push-Pull | 202 | no |
| `sort_by: "price_low_to_high"` | `amazon_search` | Push-Pull | 202 | no, and `context:sort_by` stays `null` |

Every Push-Pull job object held the same 34 fields, whatever the payload added.
The Realtime one held the same fields without `_links`.
Each `context` list held its source's own keys and nothing else.
The `amazon_search` job with the unknown keys ended `done`, billed, and returned the usual parsed page.
So the API checks the keys it knows and leaves out the rest.

This is the submission with an unknown top-level key:

```json
{"source": "universal", "url": "https://oxy-param-uk-14kexa.com/", "foo_bar": "x"}
```

```text
HTTP/1.1 202 Accepted
content-type: application/json
x-ratelimit-total-requests-00000000-0000-0000-0000-000000000000-limit: 50
x-ratelimit-total-requests-00000000-0000-0000-0000-000000000000-remaining: 48
```

```json
{
  "id": "7510379579870071810",
  "source": "universal",
  "url": "https://oxy-param-uk-14kexa.com/",
  "status": "pending",
  "context": [
    {"key": "force_headers", "value": false},
    "..."
  ],
  "...": "..."
}
```

### Probes on 2026-09-29

[Prototype: the CLI](https://github.com/ozanozbeker/oxyscraper/issues/19) sent three Push-Pull submissions at 15:13 UTC, to check the CLI's default input key.
Each returned 400, so none billed.

| Payload | Status | Body |
| --- | --- | --- |
| `{"source": "universal", "query": "https://sandbox.oxylabs.io/products/1"}` | 400 | ``{"message": "Parameter `url` is empty."}`` |
| `{"source": "walmart_product", "query": "436012154"}` | 400 | `{"errors": ["[product_id]: This field is missing.", "[query]: This field was not expected."]}` |
| `{"source": "walmart_product", "product_id": "436012154", "foo_bar": "x"}` | 400 | `{"errors": ["[foo_bar]: This field was not expected."]}` |

`universal` leaves out an unknown key, as the table above shows, so a wrong input key fails only for the missing one.
`walmart_product` rejects any key it does not take.
Its body has an `errors` list of strings and no `message`, beside the usual `instance`, `timestamp` and `trace_id`.

## Input checks

[Match the fake's rejections for the sources that return the payload alone](https://github.com/ozanozbeker/oxyscraper/issues/86) probed the 100 sources whose job object holds the payload alone, on 2026-10-01 from 14:19 to 14:23 UTC.
Each source got three Push-Pull submissions: one without an input key, one with only another source's input key, and one with an empty input.
Malformed and `null` inputs, three Realtime submissions and a `chatgpt` job with `query` followed.
The plan expected every payload to return 400 and spend 0.
The run spent 3 results, on the two `walmart_search` jobs and the `chatgpt` job below.
Usage Statistics agrees, and counts the `chatgpt` result as rendered.

| Payload | Sources | Status | Body |
| --- | --- | --- | --- |
| No input key | The 97 that take no batch, but `walmart_search` | 400 | `{"errors": ["[product_id]: This field is missing."]}`, with the source's own key |
| No `domain` | `grainger_product`, `grainger_search` and `mercadolibre_product` | 400 | `[domain]: This field is missing.` joins the list |
| Another source's input key, such as `category_id` on `walmart_product` | The 97 | 400 | `[category_id]: This field was not expected.` joins the list |
| An empty or `null` input | The 97 | 400 | `{"errors": ["[product_id]: This value should not be blank."]}` |
| No input key, an empty `prompt`, or `category_id` alone | `chatgpt`, `gemini` and `perplexity` | 400 | `{"message": "Query parameter is empty."}` |

- **Order.**
  The API sorts each `errors` list as text.
  So `[category_id]` comes before `[product_id]`, and `[product_id]: Must be` comes before `[product_id]: This value`.
- **`walmart_search`.**
  Without `query`, it returned 202, and the job fetched `https://www.walmart.com/all-departments` and billed.
  Realtime did the same.
  An empty `query` returned 400.
- **Formats.**
  Three sources check the input's format, and an empty input gets both its messages.

  | Source | Message | Values it rejected |
  | --- | --- | --- |
  | `target_product` | `Must be 8 or 10 digits.` | `""`, `1234567`, `123456789` and `1234567a` |
  | `tiktok_shop_product` | `Must be 19 digits for product_id.` | `""`, `123` and `123456789012345678a` |
  | `target_category` | `Must be 5+ characters.` | `""` and `abcd` |

- **LLM sources.**
  `chatgpt` with `query` and no `prompt` returned 202 and created a job.
  On Realtime, `chatgpt` without an input returned the 400 above, not the 422 that [Probes on 2026-09-29](live-api.md#probes-on-2026-09-29) records for an LLM source.
- **Realtime.**
  `walmart_product` without `product_id` returned the same `errors` body on Realtime.
  The Push-Pull body put `errors` after `trace_id`, and the Realtime body put it first.

## Keys by source

[Reject the keys a source does not take](https://github.com/ozanozbeker/oxyscraper/issues/99) mapped the top-level keys of the 97 sources without batches on 2026-10-01, from 14:52 to 14:53 UTC.
Each source got one Push-Pull submission with an empty input and 74 candidate keys: every key in a parameter table of today's target and feature pages, every field of the 34-field job object, and `foo_bar`.
The empty input made each return 400, and its `errors` list named each key the source does not take.
The run spent 0 results.

All 97 take 14 shared keys: `aggregate_name`, `browser_instructions`, `callback_url`, `client_notes`, `geo_location`, `markdown`, `parse`, `parser_type`, `parsing_instructions`, `render`, `storage_type`, `storage_url`, `user_agent_type` and `xhr`.
None of them takes `pages`, `locale`, `context`, `content_encoding` or `parser_preset`.

| Keys beyond the shared ones | Sources |
| --- | --- |
| None | `airbnb`, `alibaba`, `aliexpress`, `allegro_product`, `bedbathandbeyond`, `cdiscount`, `costco`, `ebay`, `etsy`, `etsy_product`, `falabella`, `flipkart`, `grainger`, `indiamart`, `instacart`, `magazineluiza`, `mediamarkt`, `mercadolibre`, `petco`, `rakuten`, `tiktok`, `tiktok_shop_product`, `tiktok_shop_search`, `tokopedia`, `youtube_video_trainability`, `zillow` |
| `domain` | `airbnb_product`, `alibaba_product`, `bedbathandbeyond_product`, `cdiscount_product`, `costco_product`, `dcard_search`, `ebay_product`, `falabella_product`, `flipkart_product`, `grainger_product`, `grainger_search`, `idealo_search`, `indiamart_product`, `indiamart_search`, `instacart_product`, `instacart_search`, `lazada_product`, `magazineluiza_product`, `mediamarkt_product`, `mercadolibre_product`, `mercadolibre_search`, `mercadolivre_product`, `mercadolivre_search`, `rakuten_search` |
| `limit` | `youtube_channel` |
| `start_page` | `lazada` |
| `store_id` | `menards`, `publix`, `publix_product`, `publix_search` |
| `delivery_zip`, `store_id` | `bodegaaurrera`, `lowes`, `lowes_product` |
| `domain`, `start_page` | `alibaba_search`, `aliexpress_search`, `avnet_search`, `bedbathandbeyond_search`, `cdiscount_search`, `costco_search`, `ebay_search`, `falabella_search`, `flipkart_search`, `lazada_search`, `magazineluiza_search`, `mediamarkt_search`, `staples_search`, `tokopedia_search` |
| `domain`, `store_id` | `menards_product` |
| `domain`, `subdomain` | `aliexpress_product` |
| `language`, `location` | `youtube_autocomplete` |
| `delivery_zip`, `domain`, `store_id` | `bestbuy_product` |
| `delivery_zip`, `fulfillment_type`, `store_id` | `kroger`, `kroger_product`, `target`, `target_category`, `target_product`, `target_search`, `walmart` |
| `domain`, `fulfillment_type`, `start_page` | `petco_search` |
| `domain`, `start_page`, `store_id` | `etsy_search` |
| `delivery_zip`, `domain`, `fulfillment_type`, `store_id` | `walmart_product` |
| `brand`, `delivery_zip`, `fulfillment_type`, `price_range`, `store_id` | `kroger_search` |
| `delivery_zip`, `domain`, `fulfillment_type`, `start_page`, `store_id` | `bestbuy_search` |
| `delivery_zip`, `domain`, `fulfillment_type`, `store_id`, `subdomain` | `bodegaaurrera_product`, `bodegaaurrera_search` |
| `delivery_time`, `domain`, `shipping_from`, `start_page`, `store_city`, `store_region` | `allegro_search` |
| `delivery_today_tomorrow`, `delivery_zip`, `domain`, `free_delivery`, `pickup_today`, `store_id` | `lowes_search` |
| `delivery_eligible`, `domain`, `fulfillment_center`, `in_stock_today`, `pickup_at_store_eligible`, `start_page`, `store_id` | `menards_search` |
| `delivery_zip`, `domain`, `fulfillment_speed`, `fulfillment_type`, `max_price`, `min_price`, `sort_by`, `start_page`, `store_id` | `walmart_search` |
| `360`, `3d`, `4k`, `creative_commons`, `duration`, `hd`, `hdr`, `live`, `location`, `purchased`, `sort_by`, `subtitles`, `type`, `upload_date`, `vr180` | `youtube_search`, `youtube_search_max` |

- **Docs.**
  A reader compared each of the 41 current docs pages for these sources with the table, and a second reader checked each mismatch.
  No page names a key that the API rejects, or says that a source lacks a key that it takes.
  The API takes `domain` on 26 sources whose pages leave it out, `start_page` on `bedbathandbeyond_search` and `mediamarkt_search`, and `subdomain` on `aliexpress_product`.
  The run cannot say whether these keys change the page.
  34 of the 97 sources have no page today.
- **Order.**
  A shared type check runs first and returns one `message`.
  The message ``Invalid type for parameter `xhr`, supported types: `boolean`.`` answers a string `xhr`.
  Next, a `url` without a scheme or a host returns ``Parameter `url` is invalid.`` before the field check.
  `pages` gets no range check on these sources, only `[pages]: This field was not expected.`
- **Hosts.**
  These sources skip the host checks of the batch sources.
  `walmart` took `https://10.0.0.1/` and `https://www.walmart.example/` with 202, against the plan.
  Both jobs faulted and billed nothing, and the `.example` job's results entry held `status_code: 10001`, not 613.

## Context keys by source

A job object lists every `context` key its source takes, with its default.
In this table, "the first five" means `force_headers`, `force_cookies`, `hc_policy`, `parse_json_schema` and `parse_json_prompt`.

| Source | `context` keys in the job object |
| --- | --- |
| `universal`, `universal_ecommerce` | the first five, `successful_status_codes`, `follow_redirects`, `cookies`, `headers`, `session_id`, `http_method`, `content`, `store_id`, `proxy_location`, `delivery_location`, `fulfillment_type` |
| `amazon_search` | the first five, `category_id`, `merchant_id`, `check_empty_geo`, `safe_search`, `currency`, `sort_by`, `refinements`, `min_price`, `max_price`, and `successful_parse_status_codes` when `parse` is `true` |
| `amazon_product` | the first five, `autoselect_variant`, `check_empty_geo`, `safe_search`, `currency` |
| `amazon_bestsellers` | the first five, `category_id`, `check_empty_geo`, `safe_search`, `currency` |
| `google_search` | the first five, `results_language`, `safe_search`, `tbm`, `cr`, `filter`, `nfpr`, `tbs`, `fpstate`, `aomd`, `udm`, `limit_per_page`, `disable_scripts`, `expand_aio` |
| `perplexity` | none: the job object holds only `prompt`, `source`, `id`, `status`, `created_at`, `updated_at` and `_links` |

The [Parameter catalog](parameter-catalog.md) found none of `hc_policy`, `parse_json_schema`, `parse_json_prompt`, `check_empty_geo`, `successful_parse_status_codes`, `cr`, `aomd`, `disable_scripts`, `proxy_location` and `delivery_location` on any docs page.
The catalog lists `safe_search` for `google_search` only, and `context:category_id` on Amazon for `amazon_search` only.
Only a SERP Localization hint names `results_language`.

One submission per source lists what that source takes.
A submission bills unless its job faults, and only `universal` has free fault jobs.

## Batches

### Input keys

| Input key | Source | Status | Response |
| --- | --- | --- | --- |
| `product_id` | `walmart_product` | 400 | ``Batch request must contain one array of `query` or `url`.`` |
| `prompt` | `perplexity` | 202 | One job, and `Query parameter is empty.` for the empty value |
| `video_id` | `youtube_video_trainability` | 400 | The same message as `product_id` |
| `channel_handle` | `youtube_channel` | 400 | The same message |
| `category_id` | `target_category` | 400 | The same message |

Each batch held one valid value and one empty value.
The `prompt` batch created a job for the valid value, as a `query` batch does:

```json
{
  "queries": [
    {
      "prompt": "what is the tallest mountain in europe",
      "source": "perplexity",
      "id": "7510380298652148737",
      "status": "pending",
      "created_at": "2026-09-28 16:49:59",
      "updated_at": "2026-09-28 16:49:59",
      "_links": ["..."]
    }
  ],
  "errors": [
    {"message": "Query parameter is empty."}
  ]
}
```

The 400 names only `query` and `url`, so its own message leaves out `prompt`:

```text
HTTP/1.1 400 Bad Request
content-type: application/json
content-length: 195
x-oxylabs-client-id: 123456
x-oxylabs-client-name: USERNAME
x-oxyserps-client-id: 123456
x-oxyserps-client-name: USERNAME

{"message":"Batch request must contain one array of `query` or `url`.","instance":"/v1/queries/batch","timestamp":"2026-09-28T16:49:57.945209373Z","trace_id":"6aba9ab5-223ab675ea71adef26486329"}
```

A `query` array for the four sources that returned 400 got 202, no jobs, and one error per value:

```text
HTTP/1.1 202 Accepted
content-type: application/json
content-length: 182
x-oxylabs-client-id: 123456
x-oxylabs-client-name: USERNAME
x-oxyserps-client-id: 123456
x-oxyserps-client-name: USERNAME

{"queries":[],"errors":[{"message":"Source `walmart_product` is not available with a batch request."},{"message":"Source `walmart_product` is not available with a batch request."}]}
```

### Sources that take a batch

A batch of two empty values creates no job for a source that checks its input, so it maps batch support for free.
The run sent one for each of the 123 documented sources, with the source's own input key, or `query` for the four keys above.

| Error for each empty value | Sources |
| --- | --- |
| ``Parameter `url` is empty.`` | `amazon`, `bing`, `google`, `universal` |
| `Query parameter is empty.` | `amazon_pricing`, `amazon_product`, `amazon_sellers`, `bing_search`, `chatgpt`, `gemini`, `google_ads`, `google_ai_mode`, `google_lens`, `google_maps`, `google_scholar`, `google_search`, `google_shopping_product`, `google_shopping_search`, `google_travel_hotels`, `google_trends_explore`, `perplexity`, `youtube_download`, `youtube_metadata`, `youtube_subtitles` |
| ``Either `query` or `context:merchant_id` parameters must be set.`` | `amazon_search` |
| None: the batch created two jobs | `amazon_bestsellers` |
| ``Source `<source>` is not available with a batch request.`` | The other 97: every source of 36 other targets, such as Walmart, Target and eBay, and `youtube_autocomplete`, `youtube_channel`, `youtube_search`, `youtube_search_max` and `youtube_video_trainability` |

The source check comes before the value check, so the 97 return the same error for any value.
These batches returned 202, and none carried rate-limit headers.

The `amazon_bestsellers` batch created a job for each `query: ""`:

```json
{
  "queries": [
    {"id": "7510380646766773249", "status": "pending", "source": "amazon_bestsellers", "query": "", "domain": "com", "...": "..."},
    {"id": "7510380646766784515", "status": "pending", "source": "amazon_bestsellers", "query": "", "domain": "com", "...": "..."}
  ]
}
```

Both jobs fetched `https://www.amazon.com/Best-Sellers/zgbs/x/?pg=1&language=en_US`, a page titled "Amazon Best Sellers: Best undefined".
Both ended `done` with `status_code: 200` and `is_render_forced: true`, and billed as rendered results.
The [Best Sellers][amz-bestsellers] page marks both `query` and `render` as required.
The batch response carried no rate-limit headers, although it created jobs.
A single `amazon_search` job with `query: ""` returns 400, and the run did not send a single `amazon_bestsellers` one.

## Amazon location

All seven jobs used the ASIN `1492056359`, a book whose ISBN-10 is its ASIN on every marketplace.

| `domain` | `geo_location` | Result | "Deliver to" line | Seconds |
| --- | --- | --- | --- | --- |
| `com` | none | `done` | `Update location` | 3 |
| `com` | `90210` | `done` | `Beverly H... 90210` | 3 |
| `com` | `DE` | `done` | `Germany` | 4 |
| `com` | `99999` | `faulted`, 613, not billed | none | 120 |
| `com` | `United States` | 400 | | |
| `nl` | `DE` | 400 | | |
| `co.uk` | `90210` | 400 | | |

The 400s follow [E-Commerce Localization][ecom-loc].
It takes a postal code inside the marketplace's country and an alpha-2 code outside it, and `nl` takes no custom location.
No page says that a well-formed postal code that does not exist faults the job.
Without `geo_location`, `amazon_search` reported `delivery_postcode: 95054` in this run, and `14205` on 2026-09-24.

```text
HTTP/1.1 400 Bad Request
content-type: application/json
content-length: 197
x-oxylabs-client-id: 123456
x-oxylabs-client-name: USERNAME
x-oxyserps-client-id: 123456
x-oxyserps-client-name: USERNAME

{"message":"Parameter `geo_location` with value `United States` is not valid.","instance":"/v1/queries","timestamp":"2026-09-28T16:52:44.310024763Z","trace_id":"6aba9b5c-ed1fff6e4cb4f4f79765c1a2"}
```

The `99999` job on the results endpoint:

```json
{
  "results": [
    {
      "content": "",
      "created_at": "2026-09-28 16:52:45",
      "updated_at": "2026-09-28 16:54:45",
      "page": 1,
      "url": "https://www.amazon.com/dp/1492056359?language=en_US",
      "job_id": "7510380996424944641",
      "is_render_forced": false,
      "status_code": 613,
      "type": "raw"
    }
  ],
  "job": {
    "id": "7510380996424944641",
    "status": "faulted",
    "source": "amazon_product",
    "query": "1492056359",
    "domain": "com",
    "geo_location": "99999",
    "created_at": "2026-09-28 16:52:45",
    "updated_at": "2026-09-28 16:54:45",
    "statuses": [],
    "...": "..."
  }
}
```

## Rendered batches

A `universal` batch of 14 fault URLs with `render: html` returned 429 and created no job.
Both `-remaining` headers stayed at their limits, so the 429 took nothing.

```text
HTTP/1.1 429 Too Many Requests
date: Mon, 28 Sep 2026 16:47:14 GMT
content-type: application/json
content-length: 180
x-oxylabs-client-id: 123456
x-oxylabs-client-name: USERNAME
x-oxyserps-client-id: 123456
x-oxyserps-client-name: USERNAME
x-ratelimit-total-render-requests-00000000-0000-0000-0000-000000000000-limit: 13
x-ratelimit-total-render-requests-00000000-0000-0000-0000-000000000000-remaining: 13
x-ratelimit-total-requests-00000000-0000-0000-0000-000000000000-limit: 50
x-ratelimit-total-requests-00000000-0000-0000-0000-000000000000-remaining: 50

{"message":"Too many requests. (Total Render Dynamic).","instance":"/v1/queries/batch","timestamp":"2026-09-28T16:47:14.725017265Z","trace_id":"6aba9a12-13213acdbb689ed1beefbb88"}
```

A batch of 13, three seconds later, returned 202 and took 13 from each limit:

```text
HTTP/1.1 202 Accepted
x-ratelimit-total-render-requests-00000000-0000-0000-0000-000000000000-limit: 13
x-ratelimit-total-render-requests-00000000-0000-0000-0000-000000000000-remaining: 0
x-ratelimit-total-requests-00000000-0000-0000-0000-000000000000-limit: 50
x-ratelimit-total-requests-00000000-0000-0000-0000-000000000000-remaining: 37
```

A `google_search` batch of 14 rendered queries returned the same 429 at 16:48:26.
[Exceeding the limit](live-api.md#exceeding-the-limit) found the same behaviour for the total limit, with the message `(Total Dynamic)`.
On Starter, any batch of more than 13 rendered values returns this 429.

### Google faults

Within the limit, `google_search` jobs faulted whatever their rendering or batching.

| Submission | `render` | Query | Result | Seconds |
| --- | --- | --- | --- | --- |
| First batch of 2 | `html` | running shoes | `faulted` | 62 |
| First batch of 2 | `html` | coffee grinder | `done` | 56 |
| Second batch of 2 | none | running shoes | `faulted` | 4 |
| Second batch of 2 | none | coffee grinder | `done` | 3 |
| Third batch of 2 | `html` | running shoes | `done` | 27 |
| Third batch of 2 | `html` | coffee grinder | `faulted` | 39 |
| Single job | none | running shoes | `done` | 5 |
| Single job | none | coffee grinder | `faulted` | 7 |
| Batch of 3 | none | desk lamp | `done` | 7 |
| Batch of 3 | none | running shoes | `done` | 3 |
| Batch of 3 | none | coffee grinder | `done` | 11 |
| Single job with `domain: de` and `markdown: true` | none | running shoes | `done` | 7 |

Each fault was a 613 results entry with empty `content`, as [A faulted job](live-api.md#a-faulted-job) describes.
Rendered jobs took 27 to 62 seconds either way, and the others 3 to 11.

## SDK payloads

### Sources only the SDK lists

The API checks the source before the input.
So a submission without an input key tells a known source from an unknown one, for free.
`no_such_source_xyz` returned `Unsupported source.`, and `amazon_search` without `query` returned its own message.

| Source that only SDK 3.0.0 lists | 400 message without an input key | Known |
| --- | --- | --- |
| `universal_ecommerce` | ``Parameter `url` is empty.`` | yes |
| `google_shopping` | ``Parameter `url` is empty.`` | yes |
| `wayfair` | ``Parameter `url` is empty.`` | yes |
| `google_suggest` | `Query parameter is empty.` | yes |
| `wayfair_search` | `Query parameter is empty.` | yes |
| `youtube_transcript` | `Query parameter is empty.` | yes |
| `amazon_reviews` | `Unsupported source.` | no |
| `amazon_questions` | `Unsupported source.` | no |
| `shein_search` | `Unsupported source.` | no |

A `universal_ecommerce` fault job returned 202 and ended `faulted`.
Its job object matches `universal`, with the same 16 `context` keys.

### `sort_by` on `amazon_search`

| Payload | `context:sort_by` in the job object | Result URL |
| --- | --- | --- |
| top-level `sort_by: "price_low_to_high"`, as SDK 3.0.0 sends it | `null` | `https://www.amazon.com/s?k=usb+c+cable&page=1&language=en_US` |
| `context:sort_by: "price_low_to_high"` | `price_low_to_high` | `https://www.amazon.com/s?k=usb+c+cable&page=1&s=price-asc-rank&language=en_US` |

The run did not send a top-level `refinements`, which SDK 3.0.0 also sends.

### `domain` on `google_search`

The job object kept `"domain": "de"`.
The result's URL was `https://www.google.com/search?q=running+shoes&hl=en&gl=us`, so the job fetched `google.com`.
SDK 3.0.0 sends `domain` on six Google sources, and its main branch has since dropped it ([Parameter catalog](parameter-catalog.md#where-the-docs-and-the-sdk-disagree)).

## Feature parameters

| Source | Parameters | Result `type` | What the result held |
| --- | --- | --- | --- |
| `amazon_search` | `markdown: true` | `markdown` | The page as Markdown, 263,864 characters |
| `amazon_search` | `render: html`, `xhr: true` | `xhr` | 10 captured requests, each with `method`, `url`, `status_code`, `request_headers`, `request_payload`, `response_headers` and `response_body` |
| `amazon_search` | `parse: true`, `parsing_instructions` | `parsed`, with `parser_type: custom` | Only the fields the instructions define |
| `google_search` | `markdown: true` | `markdown` | The page as Markdown |

`parsing_instructions` replaced the dedicated parser's output.
The instructions defined one field, `title`, from the XPath `//title/text()`:

```json
{
  "content": {
    "parse_status_code": 12000,
    "title": "Amazon.com : usb c cable"
  },
  "page": 1,
  "url": "https://www.amazon.com/s?k=usb+c+cable&page=1&language=en_US",
  "job_id": "7510381684525647873",
  "status_code": 200,
  "type": "parsed",
  "parser_type": "custom",
  "parser_preset": null
}
```

[Output types](cloud-storage.md#output-types) already ran `storage_type` on `amazon_search`.

## Usage Statistics

The run read `/v2/stats` for 2026-09-28 before its first job and at 16:57:33, after its last.

| Source title in `/v2/stats` | `all_count` | `render_count` | This run's jobs that ended `done` |
| --- | --- | --- | --- |
| `amazon_bestsellers` | +2 | +2 | 2, with forced rendering |
| `amazon_product` | +3 | 0 | 3 |
| `amazon_search` | +6 | +1 | 6, one with `xhr: true` |
| `google_search` | +8 | +2 | 8, two with `render: html` |
| `llm_perplexity` | +1 | +1 | 1 |

`all_count` matched the run's own count for every source.
`/v2/stats` names the source `llm_perplexity`, while its jobs use `perplexity`.
The `perplexity` batch took 1 from the total limit and carried no rendered-limit header, yet Usage Statistics counted its result as rendered.

## Open questions

- **Google faults.**
  4 of 12 `google_search` jobs faulted within ten minutes, and the run cannot say whether that rate is normal.
- **Forced rendering and the rendered limit.**
  The `amazon_bestsellers` batch carried no rate-limit headers, so the run could not see whether forced rendering takes from the rendered limit.
- **Other sources.**
  The run tested unknown keys on `universal` and `amazon_search`, `geo_location` on `amazon_product`, and feature parameters on `amazon_search` and `google_search` only.
- **`universal_ecommerce`.**
  Its job object matches `universal`, and no page says whether it runs a different scraper.

## Sources

### The live API

The run itself is the primary source.
It sent every call from one machine over HTTP/1.1.

### Oxylabs docs

- [Push-Pull][push-pull] allows "up to 5,000 `query` or `url` parameter values within a single batch request."
- [YouTube guide for AI][yt-guide] batches `youtube_video_trainability` with a `query` list.
- [E-Commerce Localization][ecom-loc] gives Amazon's `geo_location` rules.
- [Rate Limits][rate-limits] gives Starter 13 rendered jobs per second.
- [Traffic and Billing][billing] bills `2xx` and `4xx` results, and neither faulted jobs nor 429s.
- [Perplexity][perplexity] says that rendering is on by default for the LLM sources, and that their Push-Pull submissions include batch queries.
- [Best Sellers][amz-bestsellers] marks `query` and `render` as required.

### Notes

- [Parameter catalog](parameter-catalog.md) lists the open questions this run tested.
- [What a live test shows about the job lifecycle](live-api.md) describes fault jobs and the total limit's 429.
- [What a live test shows about Cloud Storage](cloud-storage.md) ran `storage_type` on `amazon_search`.

[push-pull]: https://developers.oxylabs.io/products/web-scraper-api/integration-methods/push-pull
[yt-guide]: https://developers.oxylabs.io/api-targets/video-and-social-media/youtube/youtube-scraping-guide-for-ai
[ecom-loc]: https://developers.oxylabs.io/products/web-scraper-api/features/localization/e-commerce-localization
[rate-limits]: https://developers.oxylabs.io/products/web-scraper-api/usage-and-billing/rate-limits
[billing]: https://developers.oxylabs.io/products/web-scraper-api/usage-and-billing/billing-information
[perplexity]: https://developers.oxylabs.io/api-targets/llms-and-ai/perplexity
[amz-bestsellers]: https://developers.oxylabs.io/api-targets/e-commerce/amazon/best-sellers
