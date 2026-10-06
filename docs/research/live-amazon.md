# What a live test shows about the Amazon models

This note records what a billed run against the live Oxylabs API showed about the six Amazon sources.
It answers [What does a live test show about the Amazon models?](https://github.com/ozanozbeker/oxyscraper/issues/40), for the models that [How are parameters typed?](https://github.com/ozanozbeker/oxyscraper/issues/12) decided.
The run took place on 2026-09-29, from 17:46 to 18:35 UTC, on the account with the Starter plan.
It spent 146 results, 21 of them rendered, against a plan of up to 182.
Usage Statistics agrees for every Amazon source except `amazon_product`, which another client used during the run.
The docs were read on 2026-09-29 through their `.md` pages.

Free probes used submissions with an empty input, which return 400 and create no job.
Of the run's 472 submissions, 320 returned 400, 152 created jobs, and 8 of those jobs faulted, so none of those billed.

The samples replace the account's client ID with `123456`, its username with `USERNAME`, and the UUID inside rate-limit header names with the nil UUID.
Every other value is what the API returned, except where `"...": "..."` marks a cut.
The raw captures stay outside the repo.

## Answer

- **Free checks.**
  On `amazon_search`, the API checks `domain`, `locale`, `context:currency`, `geo_location`, `user_agent_type`, pagination, `context:sort_by`, the price filters and `context:refinements` before it checks `query`.
  So a submission with an empty `query` maps those checks for free, and each 400 lists the values the domain allows.
  The other five sources return the same 400s for the same values.
- **Context keys.**
  `amazon_product` lists 9, `amazon_search` 14, `amazon_pricing` 9, `amazon_sellers` 8, `amazon_bestsellers` 9 and `amazon` 10, and `parse: true` adds `successful_parse_status_codes` to each.
  No page names `check_empty_geo`, `parse_json_schema`, `parse_json_prompt`, or the `condition` key of `amazon_pricing`.
  `amazon_sellers` lists `currency`, `amazon_bestsellers` lists `category_id`, and `amazon` lists `cookies` and `headers`, which their pages leave out.
- **The `amazon` source.**
  A product URL becomes an `amazon_product` job and a search URL an `amazon_search` job, with `query` and `domain` read from the URL.
  Every `amazon` job appends `language=<locale>` to the URL, although the URL page says the API never alters it.
  Its checks use the URL's host as the domain, and it drops a `domain` sent beside the URL.
- **Top-level parameters.**
  `domain`, `geo_location`, `locale`, `render`, `parse`, `callback_url`, `user_agent_type`, `start_page` and `pages` each took effect on every source that documents them, with one exception.
  `user_agent_type` has no effect on a rendered job, so it has none on `amazon_bestsellers`.
  On the three sources without pagination, `pages: 2` resets to 1, and `start_page: 2` fetches the first page again and labels it page 2.
- **Value sets.**
  The API takes the 23 documented domains and `co.za`, the 58 documented `domain` and `locale` pairs and `en_ZA` on `co.za`, and the six `sort_by` values.
  It takes the 7 documented user agent types and the 5 `desktop_*` values that SDK 3.0.0 adds.
  Its currency lists match the file that the Search page links, which allows 67 codes on `com`, and not the file that the other pages link, which allows only USD there.
  Without `locale`, `ae` returns its Arabic page, although the docs mark English as its default.
- **Rules that return a free 400.**
  A `geo_location`, `locale` or `context:currency` that does not fit the `domain` returns 400 on all six sources.
  So do an ASIN shorter than 10 characters or with lowercase letters, `min_price` above `max_price`, `pages` above 20, `start_page` or `pages` below 1, and `render` other than `html` or `png`.
  On `amazon`, a URL outside Amazon and `parse: true` on a page without a dedicated parser return 400 too.
  The Pricing page's own example, `AUD` on `nl`, returns this 400.
- **Rules that bill.**
  An empty or unknown node on `amazon_bestsellers` bills a rendered "Best undefined" page.
  An 11-character ASIN, an ASIN that does not exist, and an unknown seller ID each bill a 404 page.
  `EUR` on `com` without a `geo_location` outside the US, `XYZ` on `ie`, and `GBP` on `amazon_pricing` bill with no effect.
  So does the Best Sellers page's own example, `AUD` on `com`.
  No `geo_location` check runs on `ae`, `com.be`, `eg`, `ie`, `pl`, `sa`, `se` and `sg`, and `90210` on `ae` billed a location named "90210".
  `XX` on `com` billed with Amazon's default location.
  `parse: "yes"` becomes `false`, `min_price: 0` applies no filter, and a page past the last bills on `amazon_search` and `amazon_pricing`.
  `start_page` on a source without pagination bills the first page under another number, and `amazon` drops `domain`.
- **Rules that fault.**
  `render: ""` on `amazon_bestsellers` faulted both times, and so did a page past the last on `amazon_bestsellers`.
  `check_empty_geo: true` without a location, `90210` on `pl`, `2000` on `com.au` and both `cn` jobs faulted too.
  None of them billed.
- **Forced rendering.**
  `amazon_bestsellers` renders every job, but its submission carries no rendered-limit header, so forced rendering takes nothing from the rendered limit.
  Usage Statistics still counts each of its results as rendered.
  `render: ""` turns forced rendering off, and the job then faults, so every billed `amazon_bestsellers` result is rendered.
- **Spend.**
  The plan and its two addenda allowed up to 182 results, 28 of them rendered.
  The run spent 146 results, 21 of them rendered.

## Runs

| Run | Time (UTC) | What it sent | Results billed |
| --- | --- | --- | --- |
| Free probes | 17:46 to 17:54 | 296 submissions with an empty input: 49 to find the check order, then 247 to map domains, locales, currencies, locations, user agent types and sort values | 0 |
| Baselines | 17:57 | One job per source with only its input | 6 |
| Forced rendering | 17:58 to 18:00 | `amazon_bestsellers` with `render: ""`, `render: html` and `query: ""` | 2 |
| Top-level parameters | 18:00 to 18:02 | 52 jobs, one per documented parameter and source, plus pagination on the sources without it and `domain` on `amazon` | 55 |
| Domains | 18:03 to 18:09 | `amazon_search` with `parse: true` on 24 domains | 23 |
| Locales and currencies | 18:10 to 18:15 | 6 locales on `amazon_search`, and 13 currency cases on all six sources | 17 |
| Sorting and filters | 18:16 to 18:18 | 16 `amazon_search` submissions, 2 `amazon_product` jobs and 1 `amazon_bestsellers` job | 16 |
| Location rules | 18:27 to 18:29 | 12 `amazon_search` jobs with values that pass the check | 10 |
| Rules on other sources | 18:27 | 16 submissions with a real input and a value that breaks a rule | 1 |
| Input and page rules | 18:30 to 18:31 | 16 submissions with a malformed input, a page past the last, or a bad `render` or `parse` | 8 |
| Follow-ups | 18:32 to 18:34 | 8 jobs on results that left a question open | 7 |
| `amazon` context | 18:34 | One `amazon` job for an Amazon help page | 1 |

The run posted its [plan](https://github.com/ozanozbeker/oxyscraper/issues/40#issuecomment-5895709964) before the first job, after the free probes, and two addenda before the follow-ups.

## Free checks

A submission with an empty input creates no job, so it bills nothing, whatever else it carries.
On `amazon_product`, only the `domain`, `user_agent_type` and `callback_url` checks among those probed run before `query`.
On `amazon_search`, `query` comes after nearly every other check, so the 400 names the first value that fails:

| Check | Before `query` on `amazon_search` | Message |
| --- | --- | --- |
| `domain` | yes | ``Parameter `domain` with value `xx` is not available.`` |
| `user_agent_type` | yes | ``Unsupported `user_agent_type` type.`` |
| `callback_url` | yes | ``Invalid `callback_url`.`` |
| `start_page`, `pages` | yes | ``Parameter `start_page` should be a positive integer.``, ``Parameter `pages` should be a positive integer.`` and ``Parameter `pages` should not exceed 20.`` |
| `context:sort_by` | yes | ``Parameter `context:sort_by` must be one of: most_recent, price_low_to_high, price_high_to_low, featured, average_review, bestsellers.`` |
| `context:min_price`, `context:max_price` | yes | ``Parameter `context:min_price` must be a positive integer.`` |
| `context:refinements` | yes | ``Parameter `context:refinements` must be an array of strings.`` |
| `locale` | yes | ``Unsupported `locale` value for `domain` `com`. Supported locales are: ...`` |
| `context:currency` | yes | ``Context parameter with key `currency` for domain `com` is not valid. Available values: ...`` |
| `geo_location` | yes | Four messages, in [Locations](#locations) |
| `min_price` above `max_price` | no | ``Parameter `context:min_price` must not be larger than `context:max_price`.`` |
| `render` | no | ``Invalid `render` parameter value, possible values: html, png.`` |

`min_price: 0`, `context:refinements: []`, an integer `category_id`, `start_page: "2"` and `start_page: 1000` pass these checks.
`parse: "yes"` passes every check.
The empty-`query` message on `amazon_search` is ``Either `query` or `context:merchant_id` parameters must be set``.
This is the 400 for an unknown locale:

```text
HTTP/1.1 400 Bad Request
content-type: application/json
content-length: 264
x-oxylabs-client-id: 123456
x-oxylabs-client-name: USERNAME
x-oxyserps-client-id: 123456
x-oxyserps-client-name: USERNAME

{"message":"Unsupported `locale` value for `domain` `com`. Supported locales are: en_US, es_US, ar_AE, de_US, he_IL, ko_KR, pt_BR, zh_CN, zh_TW.","instance":"/v1/queries","timestamp":"2026-09-29T17:49:45.628822585Z","trace_id":"6abbfa39-caed2171b6a5f4100cd9f063"}
```

### Domains

All 23 documented domains passed, and so did `co.za`, the South African marketplace, which no page lists.
`COM`, `amazon.com`, `.com`, `de` with a trailing space, and an empty string returned ``Parameter `domain` with value `<value>` is not available``.
`uk`, `jp`, `au` and `com.sg` returned a second message, ``Unsupported `domain` value``.

### Locales

One probe per domain with `locale: xx_XX` returned that domain's locales.
They match the [Domain and Locale][domain-locale] table for all 23 domains: 58 pairs.
`co.za` adds `en_ZA`.

### Currencies

One probe per domain with `currency: XYZ` returned that domain's currencies.
They match the file that the [Search][amz-search] page links, [`Amazon_search_currency_values.json`][currency-search], for all 21 domains it lists.
The Product, Pricing, Best Sellers and URL pages link a second file, [`currency_new.json`][currency-new], which differs only on `com`.
There it lists USD alone, with the note "for now, we only support the default currency, USD".
The API allows 67 codes on `com`, as the Search file does.
Neither file lists `cn`, `ie` or `co.za`.
The API takes `CNY` on `cn` and `ZAR` on `co.za`, and runs no currency check on `ie`: `XYZ`, `USD` and `eur` all passed.

### Locations

One probe per domain sent a local postal code, another country's code, the domain's own country code, `90210` and a lowercase code:

| Domains | Local postal code | Another country's code | Own country's code | `90210` |
| --- | --- | --- | --- | --- |
| `com`, `com.mx`, `de`, `es`, `fr`, `it` | passes | passes | 400 | passes |
| `ca`, `co.jp`, `com.br`, `in` | passes | passes | 400 | 400 |
| `co.uk` | passes | passes | passes | 400 |
| `com.au` | passes | 400 | 400 | 400 |
| `nl` | 400 | 400 | passes | 400 |
| `co.za` | 400 | passes | passes | 400 |
| `cn`, `com.tr` | 400 | 400 | 400 | 400 |
| `ae`, `com.be`, `eg`, `ie`, `pl`, `sa`, `se`, `sg` | passes | passes | passes | passes |

Each domain got a real local code, such as `M5V 3L9` on `ca`, `W105LT` on `co.uk`, `1012 AB` on `nl` and `2000` on `co.za`, and `ae` got `Abu Dhabi`.
A lowercase code returned 400 wherever a check runs.
On `com`, `XX`, `99999`, `00000` and `90210-1234` passed, and `9021`, `902100`, `90210` with a leading space, `Lithuania` and `New York` returned 400.
On `co.uk`, `W10 5LT` and `SW1A 1AA` passed, and `w105lt` and `London` returned 400.
On `ae`, `Dubai`, `Sharjah`, `abu dhabi` and `Paris` passed.

The checks return four messages:

| Case | Message |
| --- | --- |
| A value in the wrong form | ``Parameter `geo_location` with value `90210` is not valid.`` |
| The domain's own country code | ``Parameter `geo_location` with value `US` with domain `com` is not valid. Parameter `geo_location` should be in zip/postal codes inside the native country.`` |
| Any code on `com.au` | ``Parameter `geo_location` in foreign countries with domain `com.au` is not supported.`` |
| Any value on `cn` or `com.tr` | ``Parameter `geo_location` with domain `cn` is not supported.`` |

### Other checks

The 7 documented user agent types and SDK 3.0.0's `desktop_chrome`, `desktop_edge`, `desktop_firefox`, `desktop_opera` and `desktop_safari` passed.
`Desktop`, `mobile` with a trailing space, and an empty string returned 400.
The six documented `sort_by` values passed, and `""` and `Featured` returned 400.
A `context` object instead of a list returned ``Invalid type for parameter `context`, supported types: `array`.``

## Context keys by source

A job object lists every `context` key its source takes, with its default.
In this table, "the first five" means `force_headers`, `force_cookies`, `hc_policy`, `parse_json_schema` and `parse_json_prompt`.

| Source | `context` keys in the job object | Keys the source's page documents |
| --- | --- | --- |
| `amazon_product` | the first five, `autoselect_variant`, `check_empty_geo`, `safe_search`, `currency` | `autoselect_variant`, `currency` |
| `amazon_search` | the first five, `category_id`, `merchant_id`, `check_empty_geo`, `safe_search`, `currency`, `sort_by`, `refinements`, `min_price`, `max_price` | `currency`, `sort_by`, `refinements`, `min_price`, `max_price`, `category_id`, `merchant_id` |
| `amazon_pricing` | the first five, `condition`, `check_empty_geo`, `safe_search`, `currency` | `currency` |
| `amazon_sellers` | the first five, `check_empty_geo`, `safe_search`, `currency` | none |
| `amazon_bestsellers` | the first five, `category_id`, `check_empty_geo`, `safe_search`, `currency` | `currency` |
| `amazon` | the first five, `check_empty_geo`, `safe_search`, `cookies`, `headers`, `currency` | `currency` |

`parse: true` adds `successful_parse_status_codes`, with the value `[]`, to every source's list.
`hc_policy` and `safe_search` default to `true`, `force_headers`, `force_cookies` and `autoselect_variant` to `false`, `cookies` and `headers` to `[]`, and the rest to `null`.
The `amazon` row comes from a help page URL, because the API turns a product or search URL into another source, as [The `amazon` source](#the-amazon-source) shows.

No page names `check_empty_geo`, `parse_json_schema`, `parse_json_prompt` or `condition` as a parameter.
`hc_policy` and `successful_parse_status_codes` appear only in the sample job object on the [Google AI Mode][g-ai-mode] page.
[Headers, Cookies, Method][headers-cookies] documents `force_headers`, `force_cookies`, `cookies` and `headers` with `universal`, and the Google pages document `safe_search`.
The run tried four of these keys:

| Payload adds | Result |
| --- | --- |
| `condition: "new"` on `amazon_pricing` | The URL gained `&condition=new`. |
| `check_empty_geo: true` on `amazon_product`, without `geo_location` | The job faulted after 128 seconds. |
| `safe_search: false` on `amazon_search` | The URL did not change, and nothing on the page showed an effect. |
| `category_id: "electronics"` on `amazon_bestsellers` | The job stayed `pending`, as [Faulted and stuck jobs](#faulted-and-stuck-jobs) describes. |

## The `amazon` source

The API reads an `amazon` URL, and turns a page type that has a dedicated source into a job of that source:

| URL sent to `amazon` | Job `source` | `query` | `domain` | Result URL |
| --- | --- | --- | --- | --- |
| `https://www.amazon.com/dp/1492056359` | `amazon_product` | `1492056359` | `com` | `https://www.amazon.com/dp/1492056359?language=en_US` |
| `https://www.amazon.de/dp/1492056359` | `amazon_product` | `1492056359` | `de` | `https://www.amazon.de/dp/1492056359?language=de_DE` |
| `https://www.amazon.com/dp/1492056359?th=1&foo=bar` | `amazon_product` | `1492056359` | `com` | `https://www.amazon.com/dp/1492056359?lv=shuf&th=1&foo=bar&language=en_US&channelId=500&plpRedirect=mhFallback` |
| `https://www.amazon.com/s?k=usb+c+cable` | `amazon_search` | `usb c cable` | `com` | `https://www.amazon.com/s?k=usb+c+cable&language=en_US` |
| `https://www.amazon.com/gp/help/customer/display.html?nodeId=508510` | `amazon` | `""` | `com` | `https://www.amazon.com/gp/help/customer/display.html?nodeId=508510&language=en_US` |

Every `amazon` job fetched its URL with `language=<locale>` appended, and `locale: es_US` made it `language=es_US`.
The [URL][amz-url] page says: "We do not strip any parameters or alter your URLs in any other way."
Amazon's redirect adds `lv=shuf`, `channelId` and `plpRedirect`, which the docs' own product sample shows too.
The job object of a product URL also lists `autoselect_variant`, the `amazon_product` key.
Usage Statistics counted these jobs under `amazon_product` and `amazon_search`, and counted only the help page under `amazon`.
This is the submission of the first URL:

```text
HTTP/1.1 202 Accepted
content-type: application/json
x-oxylabs-job-id: 7510759714129461249
x-ratelimit-total-requests-00000000-0000-0000-0000-000000000000-limit: 50
x-ratelimit-total-requests-00000000-0000-0000-0000-000000000000-remaining: 49
```

```json
{
  "id": "7510759714129461249",
  "source": "amazon_product",
  "url": "https://www.amazon.com/dp/1492056359",
  "query": "1492056359",
  "domain": "com",
  "status": "pending",
  "context": [
    {"key": "autoselect_variant", "value": false},
    "..."
  ],
  "...": "..."
}
```

The URL's host is the domain for every check.
`90210` with an `amazon.co.uk` URL and `locale: de_DE` with an `amazon.com` URL returned 400, and `de_DE` with an `amazon.de` URL passed.
A `domain: de` sent with an `amazon.com` URL became `com` in the job object.
`https://sandbox.oxylabs.io/products/1` returned ``Parameter `url` hostname: oxylabs is invalid``.
`parse: true` with the help page returned ``Parsing with `url` parameter is not allowed for `amazon` source``.
The [Amazon][amazon] overview says parsing is "Limited to URLs of specific Amazon page types", and links to [Domain and Locale][domain-locale], which lists no page types.

A batch rewrites each URL the same way.
On 2026-10-05, a batch held `https://sandbox.oxylabs.io/products/1` and two product URLs.
It returned two `amazon_product` jobs, each with its sent `url` and its ASIN as `query`.
Its one `errors` entry held the rejected `url`, and the batch billed 2 results.

## Top-level parameters

Each job added one parameter to its source's baseline:

| Parameter | Value | What the result showed |
| --- | --- | --- |
| `domain` | `de` | The host `amazon.de`, `language=de_DE` and a German page |
| `geo_location` | `10001` | "Deliver to" and "New York 10001" |
| `locale` | `es_US` | `language=es_US`, `<html lang="es-us">` and a Spanish page |
| `render` | `html` | `<html class="a-ws a-js ...">` in place of `a-no-js`, and a rendered-limit header on the submission |
| `parse` | `true` | `type: parsed` and `parse_status_code: 12000` |
| `callback_url` | `https://example.com/` | The job object kept the value |
| `user_agent_type` | `mobile` | `<html class="a-no-js a-touch a-mobile">` and Amazon's mobile header |
| `start_page` | `2` | `page=2`, `pageno=2` or `pg=2` in the URL |
| `pages` | `2` | Two results, for pages 1 and 2 |

| Source | Parameters that took effect | Exceptions |
| --- | --- | --- |
| `amazon_product` | all its documented ones | none |
| `amazon_search` | all its documented ones, with `domain` in [Domains and defaults](#domains-and-defaults) | none |
| `amazon_pricing` | all its documented ones | `10001` showed nothing, because the offers fragment has no "Deliver to" line. `geo_location: DE` showed `EUR 12.41 delivery` in the parsed offers. The fragment has no `<html>` element, so only the header shows `render`, and `mobile` shows as `a-touch` classes. |
| `amazon_sellers` | all its documented ones | none |
| `amazon_bestsellers` | all its documented ones except `user_agent_type` | `mobile` returned the desktop page, with the same markers as the baseline |
| `amazon` | all its documented ones | none |

A rendered `amazon_product` job with `user_agent_type: mobile` returned the desktop page too.
So rendering ignores `user_agent_type`, and `amazon_bestsellers` renders every job.

`amazon_product`, `amazon_sellers` and `amazon` document no pagination:

| Payload adds | Job object | Result |
| --- | --- | --- |
| `pages: 2` | `pages: 1` | One result, billed |
| `start_page: 2` | `start_page: 2` | One result with `page: 2` and the first page's URL, billed |

## Domains and defaults

One `amazon_search` job with `parse: true` went to each domain:

| `domain` | `language` the API sent | Docs default | Currency of the prices |
| --- | --- | --- | --- |
| `ae` | `ar_AE` | `en_AE` | AED |
| `ca` | `en_CA` | `en_CA` | CAD |
| `cn` | none: the job faulted | none marked | none |
| `co.jp` | `ja_JP` | `ja_JP` | JPY |
| `co.uk` | `en_GB` | none marked | GBP |
| `com` | `en_US` | `en_US` | USD |
| `com.au` | `en_AU` | none marked | AUD |
| `com.be` | none | none marked | EUR |
| `com.br` | `pt_BR` | none marked | BRL |
| `com.mx` | `es_MX` | none marked | MXN |
| `com.tr` | `tr_TR` | none marked | TRY |
| `de` | `de_DE` | `de_DE` | EUR |
| `eg` | `ar_AE` | `ar_AE` | EGP |
| `es` | `es_ES` | `es_ES` | EUR |
| `fr` | `fr_FR` | `fr_FR` | EUR |
| `ie` | `en_IE` | none marked | EUR |
| `in` | `en_IN` | `en_IN` | INR |
| `it` | `it_IT` | `it_IT` | EUR |
| `nl` | `nl_NL` | `nl_NL` | EUR |
| `pl` | `pl_PL` | `pl_PL` | PLN |
| `sa` | `ar_AE` | `ar_AE` | SAR |
| `se` | `sv_SE` | `sv_SE` | SEK |
| `sg` | none | `en_SG` | SGD |
| `co.za` | `en_ZA` | not listed | ZAR |

Each currency matches the default in both currency files.
The `ae` page came back in Arabic, with `<html lang="ar-ae">`, and `locale: en_AE` returned it in English.
For `com.be` and `sg`, the URL carried no `language` and encoded the spaces in `query` as `%20`, and both pages came back in English.

Without `geo_location`, the delivery location changes from job to job.
61 `com` results without one showed 22 different locations, such as "Delivering to New York 10118", "Wilmington 19801" and "Chicago 60608", each with "Update location" below it.
A location set by `geo_location` reads "Deliver to" instead, with the location below it.

## Locales and currencies

Six non-default locales went to `amazon_search`, and each set the page's language:

| `domain` | `locale` | `<html lang>` | Delivery line |
| --- | --- | --- | --- |
| `de` | `en_GB` | `en-gb` | Delivering to Berlin 12623 |
| `co.jp` | `en_US` | `en-us` | Delivering to 横浜市 224-0051 |
| `in` | `hi_IN` | `hi-in` | New Delhi 110002 में डिलीवर किया जा रहा है |
| `ca` | `fr_CA` | `fr-ca` | Livraison à Toronto M5A |
| `com.be` | `nl_BE` | `nl-be` | Wordt bezorgd aan Brussels 1050 |
| `ae` | `en_AE` | `en-ae` | Deliver to Dubai, Al B... |

Currencies that pass the check did not always take effect.
Each job set `parse: true`, and the table gives the currency of the parsed prices:

| Source | `domain` | `currency` | Prices | Outcome |
| --- | --- | --- | --- | --- |
| `amazon_search` | `com` | `EUR` | USD | billed, no effect |
| `amazon_search` | `com`, with `geo_location: DE` | `EUR` | EUR | billed |
| `amazon_search` | `de` | `GBP` | GBP | billed |
| `amazon_search` | `co.uk` | `USD` | USD | billed |
| `amazon_search` | `cn` | `CNY` | none | faulted after 5 minutes |
| `amazon_search` | `ie` | `XYZ` | EUR | billed, no effect |
| `amazon_product`, the Product page's example | `de` | `AUD` | AUD | billed |
| `amazon_pricing`, the Pricing page's example | `nl` | `AUD` | none | 400: ``Context parameter with key `currency` for domain `nl` is not valid. Available values: `EUR`.`` |
| `amazon_bestsellers`, the Best Sellers page's example | `com` | `AUD` | USD | billed, no effect |
| `amazon_pricing` | `de` | `GBP` | `€` | billed, no effect |
| `amazon_sellers` | `de` | `GBP` | none on the page | billed |
| `amazon_bestsellers` | `de` | `GBP` | GBP | billed |
| `amazon`, with an `amazon.de` URL | `de` | `GBP` | GBP | billed |

The Search file's note explains the two `com` rows: "When selecting a currency other than USD for the "com" domain, you must also select a geographical location outside of the US."
The Pricing parser gives `currency: "€"` on `de`, and `USD` on `com`.
`geo_location: US` on `de` also showed prices in USD, without `currency`.

## Sorting and filters

Each `amazon_search` job added one `context` item:

| `context` item | Result URL adds |
| --- | --- |
| `sort_by: most_recent` | `s=date-desc-rank` |
| `sort_by: price_low_to_high` | `s=price-asc-rank` |
| `sort_by: price_high_to_low` | `s=price-desc-rank` |
| `sort_by: featured` | `s=featured-rank` |
| `sort_by: average_review` | `s=review-rank` |
| `sort_by: bestsellers` | `s=exact-aware-popularity-rank` |
| `refinements: ["p_123:256097"]` | `rh=p_123:256097&dc=` |
| `min_price: 5000` | `rh=p_36:5000-&dc=` |
| `max_price: 1000` | `rh=p_36:-1000&dc=` |
| `min_price: 1000`, `max_price: 2000` | `rh=p_36:1000-2000&dc=` |
| `min_price: 0` | nothing |
| `category_id: "16391693031"` | `rh=n:16391693031&dc=` |
| `merchant_id: "A2OL0VKAHK1LYK"` | `me=A2OL0VKAHK1LYK` |

`min_price: 9000` with `max_price: 100` returned 400, from a check that runs after `query`.
`merchant_id` without `query` fetched `https://www.amazon.com/s?page=1&me=A2OL0VKAHK1LYK&language=en_US`, which held Amazon's "No results for your search query." and billed.
With `query`, the same seller's search held 16 results.
`autoselect_variant: true` on `amazon_product` fetched `https://www.amazon.com/dp/1492056359?th=1&psc=1&language=en_US`.

## Location rules

These `amazon_search` jobs used values that pass the check:

| `domain` | `geo_location` | Result | Delivery line |
| --- | --- | --- | --- |
| `com.be` | `DE` | done | Deliver to Germany |
| `nl` | `NL` | done | Bestemming: 1079 Amsterdam |
| `ae` | `Abu Dhabi` | done | التوصيل إلى Ab...، Al R... |
| `ae` | `90210` | done | التوصيل إلى 90210 |
| `pl` | `90210` | faulted at once, with `status_code: 400` | none |
| `pl` | `00-001` | done | Adres dostawy: 00001 Warszawa |
| `co.za` | `ZA` | done | Delivering to Johannesburg 2196, the default |
| `co.uk` | `GB` | done | Deliver to DN3 3JP |
| `com` | `XX` | done | Delivering to Nashville 37217, a default |
| `com.au` | `2000` | faulted after 141 seconds | none |
| `com.au` | `3000` | done | Deliver to Melbourne 3000 |
| `de` | `US` | done | Liefern nach Vereinigte Staate... |
| `co.uk` | `W105LT` | done | Deliver to London W105LT |
| `com` | `LT` | done | Deliver to Lithuania |

[E-Commerce Localization][ecom-loc] says that `cn`, `com.tr`, `com.be` and `nl` take no custom delivery location.
The API rejects every value on `cn` and `com.tr`, but it applied `DE` on `com.be` and `NL` on `nl`.
The default `nl` page reads "Wordt bezorgd aan Amsterdam 1014", so `NL` set a location of its own.
The page also says that `ae` takes city names or country codes, yet `ae` runs no check, and `90210` set a delivery location named "90210".
The last three rows are the page's own example pairs.

The other five sources run the same checks with a real input.
`90210` on `co.uk`, `locale: de_DE` on `com` and `currency: XYZ` on `com` returned the same 400s on `amazon_product`, `amazon_pricing`, `amazon_sellers`, `amazon_bestsellers` and `amazon`.

## Input and page rules

| Source | Payload adds | Status | Result |
| --- | --- | --- | --- |
| `amazon_product` | `query: "abc"` | 400 | ``ASIN length is not valid.`` |
| `amazon_product` | `query: "149205635"`, 9 characters | 400 | ``ASIN length is not valid.`` |
| `amazon_product` | `query: "14920563599"`, 11 characters | 202 | A 404 "Page Not Found" result, billed |
| `amazon_product` | `query: "b0cw1qc1v1"` | 400 | ``ASIN should only contain alphanumeric values.`` |
| `amazon_product` | `query: "B0ZZZZZZZZ"` | 202 | A 404 result, billed |
| `amazon_pricing` | `query: "abc"` | 400 | ``ASIN length is not valid.`` |
| `amazon_pricing` | `query: "B0ZZZZZZZZ"` | 202 | A 404 result, billed |
| `amazon_sellers` | `query: "abc"` | 202 | A 404 result from `https://www.amazon.com/gp/errors/404.html`, billed |
| `amazon_bestsellers` | `query: "abc"` | 202 | "Amazon Best Sellers: Best undefined", rendered and billed |
| `amazon_bestsellers` | `query: ""` | 202 | The same page, rendered and billed |
| `amazon_search` | `start_page: 21` | 202 | "No results for your search query.", billed |
| `amazon_pricing` | `start_page: 10` | 202 | An offers fragment for page 10, billed |
| `amazon_bestsellers` | `start_page: 3` | 202 | Faulted after 94 seconds |
| `amazon_product` | `render: "foo"` | 400 | ``Invalid `render` parameter value, possible values: html, png.`` |
| `amazon_product` | `parse: "yes"` | 202 | `parse: false` in the job object, and a raw result, billed |

The `query: ""` job is a single submission, so an empty `query` bills outside a batch as well.
The [Traffic and Billing][billing] page bills 4xx results.
Usage Statistics counted the 404 pages on `amazon_pricing` and `amazon_sellers`, where no other client ran.

## Forced rendering

Each `amazon_bestsellers` job below went alone, so its response headers belong to it:

| Payload adds | Rendered-limit header | `is_render_forced` | Result | Seconds |
| --- | --- | --- | --- | --- |
| nothing | none | `true` | done, billed | 24 |
| `render: ""` | none | `false` | faulted, 613 | 97 |
| `render: ""`, again | none | `false` | faulted, 613 | 77 |
| `render: html` | `limit: 13`, `remaining: 12` | `false` | done, billed | 23 |
| `query: ""` | none | `true` | done, billed | 21 |
| `parse: true` | none | `false` on the parsed entry, `true` on the raw one | done, billed | 21 |

The [Best Sellers][amz-bestsellers] page marks `render` as required, and the [forced-rendering list][forced-render] names `amazon_bestsellers`.
[JS Rendering][js] says that `render: ""` disables forced rendering.
It does, and the job then faults, so no `amazon_bestsellers` job returns an unrendered result.
Usage Statistics counted all 15 of the run's `amazon_bestsellers` results as rendered, and 14 of them came from submissions without a rendered-limit header.
The parsed entry of a forced job reads `is_render_forced: false`, and `?type=raw` returns the same job's raw entry with `true`.

This is the submission without `render`:

```text
HTTP/1.1 202 Accepted
content-type: application/json
content-length: 1583
x-oxylabs-client-id: 123456
x-oxylabs-client-name: USERNAME
x-oxylabs-job-id: 7510759708051919873
x-oxyserps-client-id: 123456
x-oxyserps-client-name: USERNAME
x-oxyserps-job-id: 7510759708051919873
x-ratelimit-total-requests-00000000-0000-0000-0000-000000000000-limit: 50
x-ratelimit-total-requests-00000000-0000-0000-0000-000000000000-remaining: 49
```

This is the submission with `render: html`:

```text
HTTP/1.1 202 Accepted
content-type: application/json
content-length: 1585
x-oxylabs-client-id: 123456
x-oxylabs-client-name: USERNAME
x-oxylabs-job-id: 7510759970460142593
x-oxyserps-client-id: 123456
x-oxyserps-client-name: USERNAME
x-oxyserps-job-id: 7510759970460142593
x-ratelimit-total-render-requests-00000000-0000-0000-0000-000000000000-limit: 13
x-ratelimit-total-render-requests-00000000-0000-0000-0000-000000000000-remaining: 12
x-ratelimit-total-requests-00000000-0000-0000-0000-000000000000-limit: 50
x-ratelimit-total-requests-00000000-0000-0000-0000-000000000000-remaining: 49
```

This is the `render: ""` job on the results endpoint:

```json
{
  "results": [
    {
      "content": "",
      "created_at": "2026-09-29 17:58:37",
      "updated_at": "2026-09-29 18:00:14",
      "page": 1,
      "url": "https://www.amazon.com/Best-Sellers/zgbs/x/172541/?pg=1&language=en_US",
      "job_id": "7510759961429840897",
      "is_render_forced": false,
      "status_code": 613,
      "type": "raw"
    }
  ],
  "job": {
    "id": "7510759961429840897",
    "status": "faulted",
    "source": "amazon_bestsellers",
    "query": "172541",
    "render": "",
    "statuses": [],
    "...": "..."
  }
}
```

## Faulted and stuck jobs

| Job | Seconds to `faulted` | Results endpoint |
| --- | --- | --- |
| `amazon_bestsellers`, `render: ""`, twice | 97 and 77 | 200, one entry with `status_code: 613` |
| `amazon_bestsellers`, `start_page: 3` | 94 | 200, one entry with `status_code: 613` |
| `amazon_product`, `check_empty_geo: true` | 128 | 200, one entry with `status_code: 613` |
| `amazon_search`, `com.au`, `2000` | 141 | 200, one entry with `status_code: 613` |
| `amazon_search`, `pl`, `90210` | 0 | 200, one entry with `status_code: 400` |
| `amazon_search`, `cn`, twice | 360 and 297 | 204 with `x-oxylabs-job-status: faulted`, and still 204 22 and 28 minutes later |

Two of these differ from [A faulted job](live-api.md#a-faulted-job), where every faulted job had one entry with 613.
The `pl` job faulted in the second it was created, and its entry carried 400:

```json
{
  "content": "",
  "created_at": "2026-09-29 18:27:13",
  "updated_at": "2026-09-29 18:27:13",
  "page": 1,
  "url": "https://www.amazon.pl/s?k=usb%20c%20cable&page=1",
  "job_id": "7510767156754136065",
  "is_render_forced": false,
  "status_code": 400,
  "type": "raw"
}
```

The `cn` jobs have no entry at all:

```text
HTTP/1.1 204 No Content
content-type: application/json
x-oxylabs-client-id: 123456
x-oxylabs-client-name: USERNAME
x-oxylabs-job-id: 7510761206756456449
x-oxylabs-job-status: faulted
x-oxyserps-client-id: 123456
x-oxyserps-client-name: USERNAME
x-oxyserps-job-id: 7510761206756456449
x-oxyserps-job-status: faulted
```

The `amazon_bestsellers` job with `category_id: "electronics"`, created at 18:16:25, was still `pending` at 19:00, 44 minutes later.

## Usage Statistics

The run read `/v2/stats` for 2026-09-29 before its first submission, at 17:46, and at 18:36, after its last job.

| Source title in `/v2/stats` | `all_count` | `render_count` | This run's billed results |
| --- | --- | --- | --- |
| `amazon_bestsellers` | +15 | +15 | 15, all forced |
| `amazon_search` | +73 | +1 | 73, one of them from an `amazon` search URL |
| `amazon_pricing` | +16 | +1 | 16 |
| `amazon_sellers` | +12 | +1 | 12 |
| `amazon` | +1 | 0 | 1, the help page |
| `amazon_product` | +59 | +3 | 29, 13 of them from `amazon` product URLs |

`all_count` matched the run's own count on every source except `amazon_product`.
That source had 525 results before the run, and it rose by 30 more than the run's 29, so another client used it during the run.
Its `render_count` rose by exactly the run's 3.
The faulted jobs and the 400s never appeared.
`universal` rose by 80, and this run sent no `universal` job.

## Open questions

- **The `category_id` job.**
  The `amazon_bestsellers` job with `category_id: "electronics"` stayed `pending` for at least 44 minutes, and the run cannot say what the key does.
- **`cn`.**
  Both `cn` jobs faulted after 5 to 6 minutes, with no results entry.
  The run cannot say whether `cn` works at all.
- **`com.au` postcodes.**
  `2000` faulted and `3000` set Melbourne, one job each, and the `com.au` default page already delivers to Sydney 2000.
- **Unchecked domains.**
  `geo_location` took effect on `ae`, `com.be` and `pl`, and the run did not send a billed location to `eg`, `ie`, `sa`, `se` or `sg`.
- **Other `amazon` page types.**
  The run mapped product, search and help URLs only.
  A Best Sellers, offers or seller URL may become its own source, and a Best Sellers job then renders.
- **`check_empty_geo` and `safe_search`.**
  `check_empty_geo: true` without a location faulted the job, and `safe_search: false` changed nothing the run could see.
- **`render: png`.**
  The 400 for `render: foo` lists `png`, and the run did not send it to an Amazon source.

## Sources

### The live API

The run itself is the primary source.
It sent every call from one machine over HTTP/1.1.

### Oxylabs docs

The run read these pages on 2026-09-29:

- [Amazon][amazon] says `parse` on `amazon` is "Limited to URLs of specific Amazon page types".
- [Product][amz-product], [Search][amz-search], [Pricing][amz-pricing], [Sellers][amz-sellers], [Best Sellers][amz-bestsellers] and [URL][amz-url] document each source's parameters and examples.
- [Domain and Locale][domain-locale] gives the 23 domains and 58 `domain` and `locale` pairs, with their defaults.
- [E-Commerce Localization][ecom-loc] gives Amazon's `geo_location` rules and exceptions.
- [`Amazon_search_currency_values.json`][currency-search], linked from the Search page, and [`currency_new.json`][currency-new], linked from the other five pages, give the currencies.
- [JS Rendering][js] says that `render: ""` disables forced rendering, and links the [forced-rendering list][forced-render].
- [User Agent Type][uat] gives the 7 user agent types.
- [Headers, Cookies, Method][headers-cookies] documents `force_headers`, `force_cookies`, `cookies` and `headers`.
- [Google AI Mode][g-ai-mode] shows a sample job object with `hc_policy` and `successful_parse_status_codes`.
- [Traffic and Billing][billing] bills `2xx` and `4xx` results, and neither faulted jobs nor 429s.

### Notes

- [What a live test shows about parameters](live-parameters.md) found the first `context` lists and the `geo_location` check on `amazon_product`.
- [What a live test shows about the job lifecycle](live-api.md) describes faulted jobs and the rate-limit headers.
- [Parameter catalog](parameter-catalog.md) lists the documented Amazon parameters.

[amazon]: https://developers.oxylabs.io/api-targets/e-commerce/amazon
[amz-product]: https://developers.oxylabs.io/api-targets/e-commerce/amazon/product
[amz-search]: https://developers.oxylabs.io/api-targets/e-commerce/amazon/search
[amz-pricing]: https://developers.oxylabs.io/api-targets/e-commerce/amazon/pricing
[amz-sellers]: https://developers.oxylabs.io/api-targets/e-commerce/amazon/sellers
[amz-bestsellers]: https://developers.oxylabs.io/api-targets/e-commerce/amazon/best-sellers
[amz-url]: https://developers.oxylabs.io/api-targets/e-commerce/amazon/url
[domain-locale]: https://developers.oxylabs.io/products/web-scraper-api/features/localization/domain-locale
[ecom-loc]: https://developers.oxylabs.io/products/web-scraper-api/features/localization/e-commerce-localization
[currency-search]: https://files.gitbook.com/v0/b/gitbook-x-prod.appspot.com/o/spaces%2FzrXw45naRpCZ0Ku9AjY1%2Fuploads%2FIAHLazcDOwZSiZ6s8IJt%2FAmazon_search_currency_values.json?alt=media
[currency-new]: https://files.gitbook.com/v0/b/gitbook-x-prod.appspot.com/o/spaces%2FzrXw45naRpCZ0Ku9AjY1%2Fuploads%2FNNybEQaVnTrc9ymR1NGE%2Fcurrency_new.json?alt=media
[js]: https://developers.oxylabs.io/products/web-scraper-api/features/js-rendering-and-browser-control
[forced-render]: https://3826932121-files.gitbook.io/~/files/v0/b/gitbook-x-prod.appspot.com/o/spaces%2FBQ7Zf9paoN3FTeGcyfY1%2Fuploads%2Fgit-blob-ce36c9c3a1ffbdf6abf6f8ada7b7e56dd6e2c760%2Fforced-render-domains.csv?alt=media
[uat]: https://developers.oxylabs.io/products/web-scraper-api/features/http-context-and-job-management/user-agent-type
[headers-cookies]: https://developers.oxylabs.io/products/web-scraper-api/features/http-context-and-job-management/headers-cookies-method
[g-ai-mode]: https://developers.oxylabs.io/api-targets/search-engines/google/ai-mode
[billing]: https://developers.oxylabs.io/products/web-scraper-api/usage-and-billing/billing-information
