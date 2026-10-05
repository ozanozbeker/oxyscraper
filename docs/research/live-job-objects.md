# What a live test shows about each source's job object

This note records the job object that each documented source returns, for the fake in `oxyscraper.testing`.
It answers [Record each source's job object for the fake](https://github.com/ozanozbeker/oxyscraper/issues/62).
The run took place on 2026-09-30, from 21:49 to 22:10 UTC, on the account with the Starter plan.
It spent 96 results, 26 of them rendered, and Usage Statistics agrees.

The run sent one Push-Pull job for each of the 114 documented sources that no earlier note records.
[Context keys by source](live-amazon.md#context-keys-by-source), [Context keys](live-universal.md#context-keys) and [Context keys by source](live-parameters.md#context-keys-by-source) record the other nine: `universal`, the six Amazon sources, `google_search` and `perplexity`.
Each payload held only `source` and the input key, so each job object shows the API's defaults.
Each input came from the source's docs sample, and each URL source took its target's home page, so that the API kept the URL source instead of running a dedicated one.
Five sources have no docs page any more, and the samples of two hold placeholders, so the run chose those seven inputs.

The samples replace the account's client ID with `123456`.
Every other value is what the API returned, except where `"...": "..."` marks a cut.
The raw captures stay outside the repo.

## Answer

- **Two shapes.**
  23 sources return the job object of 34 fields that [Unknown keys](live-parameters.md#unknown-keys) describes: `universal`, the six Amazon sources, the 13 Google and Bing sources, and `youtube_download`, `youtube_metadata` and `youtube_subtitles`.
  They are the 26 sources that take a batch, less the three LLM sources.
  The other 100 return the payload's keys, sorted by name, then `id`, `status`, `created_at`, `updated_at` and `_links`.
  Their job object holds no `context`, no `client_id` and no default.
- **Defaults.**
  The 34-field objects differ only in their `context` lists, and in `google`, which sets `locale` to `""`.
  `parse: true` added `successful_parse_status_codes: []` to the list of `youtube_metadata`, as it does on Amazon.
- **Keys the docs name.**
  The job objects of `google_ads`, `google_maps` and `google_shopping_search` leave out `context` keys that their pages document.
  Jobs that sent those keys kept none of them, as the API does for an unknown key.
- **Required parameters.**
  Six payloads returned 400 for a parameter that the docs mark as required, and passed once they carried it.
- **Finished jobs.**
  The status endpoint returned the object of the submission, with a new `status` and `updated_at`, for both shapes.
- **Forced rendering.**
  28 sources ran rendered without `render`, and the file of forced domains that the docs link matches only some of them.
- **Docs.**
  No source page of today's docs names 35 of the 123 sources, and all 35 took a job.
  Today's docs name 32 sources that the [Parameter catalog](parameter-catalog.md) of 2026-09-24 does not, and the API knows all 32.
  [New sources](#new-sources) maps their keys and job objects.

## Runs

| Run | Time (UTC) | What it sent | Results billed |
| --- | --- | --- | --- |
| First | 21:49 to 21:50 | One job for each of the 114 sources | 90 |
| Retry | 21:50 | The six rejected payloads again, each with the parameter its 400 named | 5 |
| Extra | 21:56 | One job each on `google_ads`, `google_maps` and `google_shopping_search` with the `context` keys their job objects leave out, and one `walmart_product` job with four parameters | 1 |
| New sources | 22:09 | Each of the 32 sources that the docs added after the catalog, without an input | 0 |

Every call went over HTTP/2.

## The short job object

The `walmart_product` job of the extra run sent `parse`, `user_agent_type`, `domain` and `delivery_zip`.
Its job object kept all four, and added no default:

```json
{
  "delivery_zip": "10001",
  "domain": "com",
  "parse": true,
  "product_id": "11601059297",
  "source": "walmart_product",
  "user_agent_type": "mobile",
  "id": "7511182106265915393",
  "status": "pending",
  "created_at": "2026-09-30 21:56:05",
  "updated_at": "2026-09-30 21:56:05",
  "_links": ["..."]
}
```

`_links` holds the same five links as in a 34-field object.
The 100 sources are the 97 that take no batch and the three LLM sources.

## Context keys

This table lists the `context` keys of the 15 sources with a 34-field object that no earlier note records.
Each list starts with the first five keys that [Context keys by source](live-parameters.md#context-keys-by-source) names: `force_headers`, `force_cookies`, `hc_policy`, `parse_json_schema` and `parse_json_prompt`.

| Source | Keys after the first five, with their defaults |
| --- | --- |
| `bing`, `google`, `google_ai_mode`, `google_scholar`, `google_shopping_product`, `youtube_metadata` | none |
| `bing_search` | `safe_search: null` |
| `google_ads` | `disable_scripts: false`, `expand_aio: false`, `adstest: false` |
| `google_lens` | `keywords: null` |
| `google_maps` | `hotel_occupancy: 2`, `hotel_dates: null` |
| `google_shopping_search` | `sort_by`, `min_price`, `max_price` and `tbs`, all `null` |
| `google_travel_hotels` | `hotel_occupancy: 2`, `hotel_dates: null`, `hotel_classes: []`, `adults: null`, `children: null` |
| `google_trends_explore` | `search_type: "web_search"`, then `date_from`, `date_to` and `category_id`, all `null` |
| `youtube_download` | `download_type: "audio_video"`, `video_quality: "720"`, then `audio_format`, `audio_language`, `video_format`, `start_at` and `end_at`, all `null` |
| `youtube_subtitles` | `language_code: null`, `subtitle_origin: null` |

`youtube_metadata` requires `parse: true`, so its list also ends with `successful_parse_status_codes: []`.
No source page of today's docs names `adstest`, `disable_scripts`, `audio_format` or `video_format`.
The pages give other defaults for four keys: `sort_by` is `r` on [Shopping Search][g-shopping-search], `adults` is `2` on [Travel Hotels][g-hotels], `audio_language` is `default` on [YouTube Downloader][yt-download], and `hotel_occupancy` has none on [Local Search][g-local].

## Keys the job object leaves out

| Source | `context` keys sent | Keys in the job object |
| --- | --- | --- |
| `google_ads` | `udm: 14`, `tbs: "qdr:d"`, `nfpr: true` | none of the three |
| `google_maps` | `nfpr: true` | not `nfpr` |
| `google_shopping_search` | `nfpr: true` | not `nfpr` |

[Google Ads][g-ads] documents `udm`, `tbm`, `tbs` and `nfpr`, and [Local Search][g-local] and [Shopping Search][g-shopping-search] document `nfpr`.
All three jobs faulted with 613, so the run could not see whether the keys changed the page that Google returned.

## Rejections

| Payload | Status | Body |
| --- | --- | --- |
| `google_ai_mode` without `render` | 400 | ``{"message": "Parameter `render` for this source can only be set to one of: html, png."}`` |
| `grainger_product`, `grainger_search` and `mercadolibre_product` without `domain` | 400 | `{"errors": ["[domain]: This field is missing."]}` |
| `youtube_download` without `storage_url` | 400 | ``{"message": "Parameter `storage_url` must be provided for this source."}`` |
| `youtube_metadata` without `parse` | 400 | ``{"message": "Parameter `parse` must be enabled for this source."}`` |

Each body also carried `instance`, `timestamp` and `trace_id`.
The docs mark each of these parameters as required.
The `google_ai_mode` message allows `png`, while [Google AI Mode][g-ai-mode] asks for `html`.
The retry sent `render: html` on `google_ai_mode`, `domain: com` on Grainger, `domain: com.co` on Mercado Libre and `parse: true` on `youtube_metadata`.
`youtube_download` took `storage_type: gcs`, a `storage_url`, and a video ID that no video has.
With the parameter, each job object held it: the short objects of Grainger and Mercado Libre have 8 fields.

## Results

Of the 118 jobs, 96 ended `done` and billed one result each, and 21 faulted with 613.
`google_shopping_product`, whose docs sample holds a placeholder instead of a product token, was still `pending` 20 minutes after its submission.

| Run | Sources whose job faulted |
| --- | --- |
| First | `airbnb_product`, `aliexpress`, `avnet_search`, `bing_search`, `costco_search`, `google_ads`, `google_lens`, `google_maps`, `google_shopping_search`, `kroger`, `kroger_product`, `kroger_search`, `mercadolibre_search`, `petco`, `petco_search`, `tokopedia_search`, `walmart` |
| Retry | `youtube_download`, as planned |
| Extra | `google_ads`, `google_maps`, `google_shopping_search` |

Of the 11 Google and Bing jobs of the first two runs that finished, 5 faulted, and all 3 of the extra run faulted.

The results entries of `universal` and of the short e-commerce sources carry `_request`, `_response` and `session_info`.
The entries of the other 34-field sources, and of `chatgpt`, `gemini`, `youtube_channel`, `youtube_search` and `youtube_search_max`, do not.
Nor does the `perplexity` entry of [Batches](live-parameters.md#batches).

## Forced rendering

28 sources ran with `is_render_forced: true` in their results entries, although no payload sent `render`.
None of their submissions carried the rendered limit's headers.
[JS Rendering & Browser Control][js] links a file of the domains whose pages Oxylabs renders by force, with the page types for each.
The jobs follow that file for Allegro, Etsy, Grainger, Kroger, Lazada and Publix, whose every source ran rendered, and for `google_maps`.
They do not follow it for these targets:

| Target | Page types in the file | Rendered | Not rendered, and `done` |
| --- | --- | --- | --- |
| Bed Bath & Beyond | `all` | `bedbathandbeyond_search` | `bedbathandbeyond`, `bedbathandbeyond_product` |
| Costco | `products; categories (url)` | none | `costco_product` |
| eBay | `all` | `ebay`, `ebay_search` | `ebay_product` |
| Lowe's | `product` | `lowes_product`, `lowes_search` | `lowes` |
| Menards | `all` | `menards_product`, `menards_search` | `menards` |
| Mercado Libre | `all` | `mercadolibre_search` | `mercadolibre`, `mercadolibre_product` |
| Target | `all` | `target`, `target_product` | `target_category`, `target_search` |
| TikTok | `all;search;user` | none | `tiktok`, `tiktok_shop_product`, `tiktok_shop_search` |

The file also lists Petco as `all`, and both Petco jobs faulted without rendering.

## `youtube_download` and Cloud Storage

The job's `storage_url` named a folder.
At submission, the API resolved it to `<folder>/<query>_<job id>.{{ extension }}`, and the job object kept `{{ extension }}` after the job faulted.
[YouTube Downloader][yt-download] names the object `{video_id}_{job_id}.mp4` or `.m4a`, and [Object names](cloud-storage.md#object-names) found `<folder>/<job id>.json` for other sources.
`statuses` stayed empty 15 minutes after the fault.

## Docs changes since the catalog

The [llms.txt index][llms] of 2026-09-30 lists 98 pages under `api-targets`.
The [Parameter catalog](parameter-catalog.md) read the docs on 2026-09-24, when each source had its own page.
Today most targets have one page, and no current source page names these 35 sources:

- the URL source of every target but Google and Bing: `airbnb`, `alibaba`, `aliexpress`, `amazon`, `bedbathandbeyond`, `bodegaaurrera`, `cdiscount`, `costco`, `ebay`, `etsy`, `falabella`, `flipkart`, `grainger`, `indiamart`, `instacart`, `kroger`, `lazada`, `lowes`, `magazineluiza`, `mediamarkt`, `menards`, `mercadolibre`, `petco`, `publix`, `rakuten`, `target`, `tiktok`, `tokopedia`, `walmart` and `zillow`
- `airbnb_product`, `avnet_search`, `magazineluiza_product`, `staples_search` and `tokopedia_search`

Their old pages, such as `api-targets/e-commerce/avnet.md`, return a "Page Not Found" page with status 200.
All 35 took a job in this run.
The index also names 32 sources that the catalog lacks: the `_product` and `_search` sources of `bakersplus`, `citymarket`, `dillons`, `foodfourless`, `fredmeyer`, `frysfood`, `gerbes`, `harristeeter`, `kingsoopers`, `marianos`, `metromarket`, `picknsave`, `qfc`, `ralphs`, `safeway` and `smithsfoodanddrug`.
The run sent each of them without an input, which the API rejects for free.
Each returned 400 with an `errors` list that named its input key, such as `[product_id]: This field is missing.`, so the API knows all 32.
`safeway_product` and `safeway_search` also listed `[zip_code]: This field is missing.`

## New sources

[Add the 32 grocery sources to the fake](https://github.com/ozanozbeker/oxyscraper/issues/127) probed the 32 sources that the docs added after the catalog, on 2026-10-05 from 14:16 to 14:17 UTC.
Each source got one Push-Pull submission with an empty input and the 74 candidate keys of [Keys by source](live-parameters.md#keys-by-source), then a batch of two empty `query` values.
Ten Safeway submissions with an empty `query` tried values of `zip_code`.
These spent 0 results.
From 14:17 to 14:20 UTC, one Push-Pull job per source sent its docs sample of 2026-09-30.
The plan expected at most 32 results, and the run billed 22, 7 of them rendered.
Usage Statistics agrees.

| Target | Source | Input key | Keys beyond the shared ones |
| --- | --- | --- | --- |
| Baker's Plus | `bakersplus_product` | `product_id` | `delivery_zip`, `fulfillment_type`, `store_id` |
| Baker's Plus | `bakersplus_search` | `query` | `brand`, `delivery_zip`, `fulfillment_type`, `price_range`, `store_id` |
| City Market | `citymarket_product` | `product_id` | `delivery_zip`, `fulfillment_type`, `store_id` |
| City Market | `citymarket_search` | `query` | `brand`, `delivery_zip`, `fulfillment_type`, `price_range`, `store_id` |
| Dillons | `dillons_product` | `product_id` | `delivery_zip`, `fulfillment_type`, `store_id` |
| Dillons | `dillons_search` | `query` | `brand`, `delivery_zip`, `fulfillment_type`, `price_range`, `store_id` |
| Food 4 Less | `foodfourless_product` | `product_id` | `delivery_zip`, `fulfillment_type`, `store_id` |
| Food 4 Less | `foodfourless_search` | `query` | `delivery_zip`, `fulfillment_type`, `store_id` |
| Fred Meyer | `fredmeyer_product` | `product_id` | `delivery_zip`, `fulfillment_type`, `store_id` |
| Fred Meyer | `fredmeyer_search` | `query` | `brand`, `delivery_zip`, `fulfillment_type`, `price_range`, `store_id` |
| Fry's Food | `frysfood_product` | `product_id` | `delivery_zip`, `fulfillment_type`, `store_id` |
| Fry's Food | `frysfood_search` | `query` | `brand`, `delivery_zip`, `fulfillment_type`, `price_range`, `store_id` |
| Gerbes | `gerbes_product` | `product_id` | `delivery_zip`, `fulfillment_type`, `store_id` |
| Gerbes | `gerbes_search` | `query` | `brand`, `delivery_zip`, `fulfillment_type`, `price_range`, `store_id` |
| Harris Teeter | `harristeeter_product` | `product_id` | `delivery_zip`, `fulfillment_type`, `store_id` |
| Harris Teeter | `harristeeter_search` | `query` | `brand`, `delivery_zip`, `fulfillment_type`, `price_range`, `store_id` |
| King Soopers | `kingsoopers_product` | `product_id` | `delivery_zip`, `fulfillment_type`, `store_id` |
| King Soopers | `kingsoopers_search` | `query` | `brand`, `delivery_zip`, `fulfillment_type`, `price_range`, `store_id` |
| Mariano's | `marianos_product` | `product_id` | `delivery_zip`, `fulfillment_type`, `store_id` |
| Mariano's | `marianos_search` | `query` | `brand`, `delivery_zip`, `fulfillment_type`, `price_range`, `store_id` |
| Metro Market | `metromarket_product` | `product_id` | `delivery_zip`, `fulfillment_type`, `store_id` |
| Metro Market | `metromarket_search` | `query` | `brand`, `delivery_zip`, `fulfillment_type`, `price_range`, `store_id` |
| Pick 'n Save | `picknsave_product` | `product_id` | `delivery_zip`, `fulfillment_type`, `store_id` |
| Pick 'n Save | `picknsave_search` | `query` | `brand`, `delivery_zip`, `fulfillment_type`, `price_range`, `store_id` |
| QFC | `qfc_product` | `product_id` | `delivery_zip`, `fulfillment_type`, `store_id` |
| QFC | `qfc_search` | `query` | `brand`, `delivery_zip`, `fulfillment_type`, `price_range`, `store_id` |
| Ralphs | `ralphs_product` | `product_id` | `delivery_zip`, `fulfillment_type`, `store_id` |
| Ralphs | `ralphs_search` | `query` | `brand`, `delivery_zip`, `fulfillment_type`, `price_range`, `store_id` |
| Safeway | `safeway_product` | `product_id` | `zip_code` |
| Safeway | `safeway_search` | `query` | `zip_code` |
| Smith's Food and Drug | `smithsfoodanddrug_product` | `product_id` | `delivery_zip`, `fulfillment_type`, `store_id` |
| Smith's Food and Drug | `smithsfoodanddrug_search` | `query` | `brand`, `delivery_zip`, `fulfillment_type`, `price_range`, `store_id` |

- **Keys.**
  The 15 targets other than Safeway are Kroger stores, and their sources take the keys of `kroger_product` and `kroger_search`.
  `foodfourless_search` takes no `brand` or `price_range`, and its job fetched `myfood4less.com` instead of a Kroger site.
  The Safeway sources take `zip_code` and none of Kroger's keys.
- **Batches.**
  None of the 32 takes a batch.
  Each value returned ``Source `<source>` is not available with a batch request.`` in a 202.
- **`zip_code`.**
  Both Safeway sources require it, and their 400 lists `[zip_code]: This field is missing.` without it.
  It takes a ZIP code that Safeway serves, as the docs said on 2026-09-30.
  `98101` and `94105` passed.
  The 400 listed `[zip_code]: The value you selected is not a valid choice.` for `10001`, `33101`, `00000`, `9810`, `98101-1234` and `x`.
  An empty or `null` value added `This value should not be blank.` to the list, and the integer `98101` added `This value should be of type string.` to it.
  The fake cannot hold the list, so it checks only that the key is there.
- **Job objects.**
  Each job object held the payload alone, as for the other sources that take no batch: 7 fields, or 8 with `zip_code`.
- **Results.**
  Each results entry carried `_request`, `_response` and `session_info`.
- **Forced rendering.**
  Every `_product` source but `foodfourless_product` ran with `is_render_forced: true`, and so did `harristeeter_search` and `safeway_search`.
  No submission carried the rendered limit's headers.
- **Faults.**
  10 jobs faulted with 613 and billed nothing: both Safeway jobs, and the `_product` jobs of City Market, Dillons, Fry's Food, Mariano's, Metro Market, QFC, Ralphs and Smith's Food and Drug.
  `0001111016338` ran on 3 targets and faulted on 7, so the product ID does not explain the faults.
- **Docs.**
  Today's docs have no page for any source.
  The [llms.txt index][llms] of 2026-10-05 lists no `api-targets` page, and each old page, such as `api-targets/e-commerce/amazon.md`, returns "Page Not Found".
  The index names the API "Web Scraper API (Classic)", beside a new "Web API" at `webapi.oxylabs.io`, whose `GET /v1/scrapers` lists its scrapers.

## Usage Statistics

The run read `/v2/stats` for 2026-09-30 before its first job and at 22:03, after every job but `google_shopping_product` finished.
On this run's sources, it grew by 96 results, 26 of them rendered, which matches the jobs that ended `done`.
The 26 rendered results are the 23 forced jobs that ended `done`, `google_ai_mode`, and the two LLM jobs.
`/v2/stats` names the LLM sources `llm_chatgpt` and `llm_gemini`.
Another client on the account added 6,770 `amazon_product` results in the same window.

## Open questions

- **Google keys.**
  The three jobs that sent the keys their job objects leave out faulted, so the run could not see whether the keys take effect.

## Sources

### The live API

The run itself is the primary source.

### Oxylabs docs

Read on 2026-09-30:

- [llms.txt index][llms]
- [Google Ads][g-ads], [Local Search][g-local], [Shopping Search][g-shopping-search], [Travel Hotels][g-hotels] and [Google AI Mode][g-ai-mode]
- [YouTube Downloader][yt-download]
- [JS Rendering & Browser Control][js] and the file of domains it links
- The Grainger and Mercado Libre pages, which mark `domain` as mandatory

### Notes

- [Parameter catalog](parameter-catalog.md) lists the 123 sources and their input keys.
- [What a live test shows about parameters](live-parameters.md) found the 34-field object and the 26 sources that take a batch.

[llms]: https://developers.oxylabs.io/llms.txt
[g-ads]: https://developers.oxylabs.io/api-targets/search-engines/google/ads
[g-local]: https://developers.oxylabs.io/api-targets/search-engines/google/search/local-search
[g-shopping-search]: https://developers.oxylabs.io/api-targets/search-engines/google/shopping/shopping-search
[g-hotels]: https://developers.oxylabs.io/api-targets/search-engines/google/travel-hotels
[g-ai-mode]: https://developers.oxylabs.io/api-targets/search-engines/google/ai-mode
[yt-download]: https://developers.oxylabs.io/api-targets/video-and-social-media/youtube/youtube-downloader
[js]: https://developers.oxylabs.io/products/web-scraper-api/features/js-rendering-and-browser-control
