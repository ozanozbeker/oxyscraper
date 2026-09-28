# Parameter catalog

This note answers [#3](https://github.com/ozanozbeker/oxyscraper/issues/3) for [#12](https://github.com/ozanozbeker/oxyscraper/issues/12).
The docs were read on 2026-09-24 through their `.md` pages, and the SDK was read at tag `3.0.0` (commit `0a98cff`).

## Answer

- The docs list 123 sources, and only `source` and one input key appear for all of them.
  `callback_url` appears for 121 sources, and `render` and `user_agent_type` for 111.
  63 sources take nothing else except, on 23 of them, `domain` or `start_page`.
- The input key has seven names: `query` (56 sources), `url` (33), `product_id` (28), `prompt` (3), and `video_id`, `channel_handle` and `category_id` (one each).
  The batch docs allow a list of `query` or `url` values only, and say nothing about the other five keys.
- Amazon, the main use, is uniform.
  Its six sources draw on 17 parameters beyond `source` and the input key.
  Every Amazon source takes `geo_location`, `locale`, `render`, `parse`, `callback_url` and `user_agent_type`.
  The rest are `domain`, pagination, `context:currency`, `context:autoselect_variant` and the `amazon_search` filters.
- One parameter name can change place, type and allowed values between sources.
  `store_id` is a top-level string that must start with `0` on Kroger, a top-level integer on Publix, and a `context` item on `bodegaaurrera_search`.
  `sort_by`, `min_price`, `max_price` and `category_id` are top-level keys on one source and `context` items on another.
- `context` takes 44 documented keys, with boolean, integer, string, list and object values.
  Three `youtube_search` parameters, `360`, `3d` and `4k`, are not valid Python identifiers.
- Feature parameters such as `markdown`, `xhr`, `parsing_instructions` and `storage_type` appear only on feature pages, so the docs never say which sources accept them.
  The two job objects the docs show, for `universal` and `google_ai_mode`, carry the same 32 fields.
- The docs are not a reliable schema.
  Seven source pages name the wrong source in their own parameter table, and two pages type a string parameter as Boolean.
- Oxylabs' own SDK does not match its docs.
  SDK 3.0.0 differs from the docs in parameter names or placement on 33 of the 120 sources both cover.
  It also sends `universal_ecommerce` where the docs say `universal`.
- The SDK changes its sources rarely and in large steps.
  Its source count went from 28 to 24, 29 and 129 across nine PyPI releases.
  Its unreleased main branch has since removed one source and changed 13 more.
- The API validates part of each job, and returns 400 for a missing parameter, an invalid value or a wrong type.
  Some mistakes still end in a billed result.
  Google applies no location for an unrecognised `geo_location`, and an invalid Kroger store and fulfillment pair returns a 4xx page, which Oxylabs bills.
- Neither quirk from the earlier billed runs is documented.
  [Quirks from earlier billed runs](#quirks-from-earlier-billed-runs) gives what the docs do say.

## Catalog

The tables use the docs' parameter names.
`context:sort_by` means the item `{"key": "sort_by", "value": ...}` in the job's `context` list.

### Parameters most sources share

| Parameter | Type | Default | Sources | Notes |
| --- | --- | --- | --- | --- |
| `source` | string | none | 123 | Required. |
| input key | string, or a list in a batch | none | 123 | Required. `query` 56, `url` 33, `product_id` 28, `prompt` 3, `video_id` 1, `channel_handle` 1, `category_id` 1. |
| `callback_url` | string | none | 121 | Not listed for `youtube_search` and `youtube_search_max`. |
| `render` | string | none | 111 | `html` or `png`, and `""` turns off forced rendering. Not listed for the LLM sources, the YouTube sources and `google_trends_explore`. |
| `user_agent_type` | string | `desktop` | 111 | `desktop`, `mobile`, `mobile_android`, `mobile_ios`, `tablet`, `tablet_android`, `tablet_ios`. Not listed for the LLM sources, the YouTube sources and `google_ai_mode`. |
| `parse` | boolean | `false` | 30 | Needs a dedicated parser, or `parsing_instructions` or `parser_preset`. |
| `start_page` | integer | `1` | 29 | The docs give no range. |
| `geo_location` | string | none | 25 | Accepted values depend on the source family. |
| `domain` | string | per target | 25 | Each target has its own values. |
| `store_id` | integer or string | none | 23 | Type and placement depend on the target. |
| `delivery_zip` | string | none | 16 | A postal code. |
| `locale` | string | none | 14 | Amazon takes `en_US` style values, and Google and Bing take `de-DE` style values. |
| `fulfillment_type` | string | per target | 11 | Each target has its own values. |
| `pages` | integer | `1` | 8 | The docs give no range. |
| `limit` | integer | `10`, or `20` on `youtube_channel` | 4 | Results per page, or videos per channel. |

Sources: every source page in the [llms.txt][d-llms] index, [JS Rendering][d-js], [User Agent Type][d-uat], [Dedicated Parsers][d-parsers] and [Domain and Locale][d-domain-locale].

### Feature parameters

These parameters appear on feature pages, mostly with `universal` examples.
The docs do not say which dedicated sources accept them.
[Multi-format Output][d-multi] sends `markdown`, `xhr` and `render: png` to `amazon_product`, so they are not `universal` only.

| Parameter | Type | Rule | Page |
| --- | --- | --- | --- |
| `parsing_instructions` | object | Needs `parse: true`. Each `_fn` name comes from a list of 20 functions. | [Custom Parser][d-custom-parser], [List of functions][d-functions] |
| `parser_preset` | string | Needs `parse: true`. A new preset takes about a minute to become usable. | [Custom Parser][d-custom-parser] |
| `markdown` | boolean, default `false` | Makes Markdown the default output type. | [Markdown Output][d-markdown] |
| `xhr` | boolean | Needs `render`, and makes the XHR list the default output type. | [Fetch/XHR][d-xhr] |
| `browser_instructions` | list of objects | Needs `render`, and `fetch_resource` must come last. | [JS Rendering][d-js] |
| `content_encoding` | string | `base64` for images. Job objects show `utf-8` otherwise. | [Download Images][d-images], [Push-Pull][d-push-pull] |
| `storage_type` | string | `gcs`, `s3`, `tos` or `s3_compatible`, with Push-Pull only. | [Cloud Storage][d-storage] |
| `storage_url` | string | A bucket path that accepts templates such as `{{ source }}`. | [Cloud Storage][d-storage], [File name templating][d-templating] |
| `client_notes` | string | Saved with the job. | [Client Notes][d-client-notes] |
| `aggregate_name` | string | Sends the result to a Result Aggregator. | [Result Aggregator][d-aggregator] |
| `context:session_id` | string | Reuses one proxy IP across jobs. | [Proxy Location][d-proxy-loc] |
| `context:force_headers`, `context:headers` | boolean, object | Sends custom headers. | [Headers, Cookies, Method][d-headers] |
| `context:force_cookies`, `context:cookies` | boolean, list | Sends custom cookies. | [Headers, Cookies, Method][d-headers] |
| `context:http_method`, `context:content` | string | `post`, with a Base64 body. | [Headers, Cookies, Method][d-headers] |

### Amazon

#### Amazon sources

| Source | Input key | Input value | Dedicated parser |
| --- | --- | --- | --- |
| `amazon_product` | `query` | 10-character ASIN | yes |
| `amazon_search` | `query` | search term | yes |
| `amazon_pricing` | `query` | 10-character ASIN | yes |
| `amazon_sellers` | `query` | seller ID | yes |
| `amazon_bestsellers` | `query` | browse node ID | yes |
| `amazon` | `url` | any Amazon URL, which the API sends unchanged | some page types only |

Sources: [Amazon][d-amazon], [Product][d-amz-product], [Search][d-amz-search], [Pricing][d-amz-pricing], [Sellers][d-amz-sellers], [Best Sellers][d-amz-bestsellers] and [URL][d-amz-url].

#### Amazon parameters

| Parameter | Type | Default | Allowed values | Sources |
| --- | --- | --- | --- | --- |
| `domain` | string | `com` | 23 marketplaces, listed below | all but `amazon` |
| `geo_location` | string | none | A postal code inside the marketplace's country, or an ISO 3166-1 alpha-2 code outside it. Exceptions are listed below. | all six |
| `locale` | string | the marketplace's default language | the pairs listed below | all six |
| `render` | string | none | `html`. The JS Rendering page adds `png`, and `""` to turn off forced rendering. | all six |
| `parse` | boolean | `false` | `true`, `false` | all six |
| `callback_url` | string | none | a URL | all six |
| `user_agent_type` | string | `desktop` | the seven values in the shared table | all six |
| `start_page` | integer | `1` | not stated | `amazon_search`, `amazon_pricing`, `amazon_bestsellers` |
| `pages` | integer | `1` | not stated | `amazon_search`, `amazon_pricing`, `amazon_bestsellers` |
| `context:currency` | string | the marketplace's default | the codes listed below | all but `amazon_sellers` |
| `context:autoselect_variant` | boolean | `false` | `true` appends `th=1&psc=1` to the product URL, for accurate price and buybox data. | `amazon_product` |
| `context:sort_by` | string | none | `most_recent`, `price_low_to_high`, `price_high_to_low`, `featured`, `average_review`, `bestsellers` | `amazon_search` |
| `context:refinements` | list of strings | none | Amazon refinement codes such as `p_123:256097` | `amazon_search` |
| `context:min_price`, `context:max_price` | positive integer | none | Cents, so `5000` means 50.00. Either works alone. | `amazon_search` |
| `context:category_id` | string | none | an Amazon node ID such as `16391693031` | `amazon_search` |
| `context:merchant_id` | string | none | a seller ID | `amazon_search` |

Sources: the six Amazon source pages, [Domain and Locale][d-domain-locale], [E-Commerce Localization][d-ecom-loc], [JS Rendering][d-js] and the [currency list][d-currency].

#### Amazon marketplaces

| `domain` | Marketplace | `locale` values | Default currency | Other currencies | Custom `geo_location` |
| --- | --- | --- | --- | --- | --- |
| `ae` | United Arab Emirates | `en_AE` (default), `ar_AE` | AED | 14: BHD, CAD, EGP, EUR, GBP, INR, JOD, KWD, OMR, PKR, QAR, RUB, SAR, USD | city names or alpha-2 codes |
| `ca` | Canada | `en_CA` (default), `fr_CA` | CAD | none | yes |
| `cn` | China | `zh_CN` | not listed | not listed | no |
| `co.jp` | Japan | `ja_JP` (default), `en_US`, `zh_CN` | JPY | 14: AUD, CNY, EUR, GBP, HKD, KRW, NOK, NZD, SEK, SGD, THB, TWD, USD, ZAR | yes |
| `co.uk` | United Kingdom | `en_GB` | GBP | 60, in the currency list | yes |
| `com` | United States | `en_US` (default), `es_US`, `ar_AE`, `de_US`, `he_IL`, `ko_KR`, `pt_BR`, `zh_CN`, `zh_TW` | USD | none supported | yes |
| `com.au` | Australia | `en_AU` | AUD | NZD | Australian postcodes only |
| `com.be` | Belgium | `fr_BE`, `nl_BE`, `en_GB` | EUR | none | no |
| `com.br` | Brazil | `pt_BR` | BRL | none | yes |
| `com.mx` | Mexico | `es_MX` | MXN | none | yes |
| `com.tr` | Turkey | `tr_TR` | TRY | none | no |
| `de` | Germany | `de_DE` (default), `en_GB`, `cs_CZ`, `nl_NL`, `pl_PL`, `tr_TR`, `da_DK` | EUR | 60, in the currency list | yes |
| `eg` | Egypt | `ar_AE` (default), `en_AE` | EGP | none | yes |
| `es` | Spain | `es_ES` (default), `pt_PT`, `en_GB` | EUR | none | yes |
| `fr` | France | `fr_FR` (default), `en_GB` | EUR | none | yes |
| `ie` | Ireland | `en_IE` | not listed | not listed | yes |
| `in` | India | `en_IN` (default), `hi_IN`, `ta_IN`, `te_IN`, `kn_IN`, `ml_IN`, `bn_IN`, `mr_IN` | INR | none | yes |
| `it` | Italy | `it_IT` (default), `en_GB` | EUR | none | yes |
| `nl` | Netherlands | `nl_NL` (default), `en_GB` | EUR | none | no |
| `pl` | Poland | `pl_PL` (default) | PLN | none | yes |
| `sa` | Saudi Arabia | `ar_AE` (default), `en_AE` | SAR | none | yes |
| `se` | Sweden | `sv_SE` (default), `en_GB` | SEK | none | yes |
| `sg` | Singapore | `en_SG` (default) | SGD | MYR | yes |

Sources: [Domain and Locale][d-domain-locale], [currency list][d-currency] and [E-Commerce Localization][d-ecom-loc].

#### SDK coverage of Amazon

- SDK 3.0.0 has one method per documented Amazon source.
  It adds `scrape_reviews` (`amazon_reviews`) and `scrape_questions` (`amazon_questions`), which no docs page lists ([amazon.py][s-amazon-file]).
- Every Amazon method also takes `parsing_instructions`, and merges unknown keyword arguments into the payload.
- No method names `currency`, `autoselect_variant`, `category_id`, `merchant_id`, `min_price` or `max_price`, so a caller passes them in `context`.
- `scrape_search` sends `sort_by` and `refinements` as top-level keys, and types `refinements` as `str` ([amazon.py][s-amazon]).
  The docs put both in `context`, and pass `refinements` as a list.
- 3.0.0 added `locale` to all six documented sources, `context` to `amazon`, `amazon_pricing` and `amazon_bestsellers`, `geo_location` to `amazon`, and `sort_by` and `refinements` to `amazon_search` ([2.0.0 to 3.0.0][s-compare-2-3]).

### Other sources

The base set is `callback_url`, `render` and `user_agent_type`.
The last column lists what each source's page adds to the base set, and names any base parameter the page leaves out.
The `google_search` row merges four pages: web search, image search, news search and AI Overviews.
Each row comes from the source's page under `https://developers.oxylabs.io/api-targets/`, which [llms.txt][d-llms] indexes.

| Target | Source | Input key | Beyond the base set |
| --- | --- | --- | --- |
| Airbnb | `airbnb` | `url` | none |
| Airbnb | `airbnb_product` | `product_id` | `domain` |
| Alibaba | `alibaba` | `url` | none |
| Alibaba | `alibaba_product` | `product_id` | none |
| Alibaba | `alibaba_search` | `query` | `start_page` |
| AliExpress | `aliexpress` | `url` | none |
| AliExpress | `aliexpress_product` | `product_id` | `domain`, `subdomain` |
| AliExpress | `aliexpress_search` | `query` | `start_page` |
| Allegro | `allegro_product` | `product_id` | none |
| Allegro | `allegro_search` | `query` | `start_page`, `delivery_time`, `shipping_from`, `store_city`, `store_region` |
| Any domain | `universal` | `url` | `geo_location`, `browser_instructions`, `parse`, `parsing_instructions`, `context:headers`, `context:cookies`, `context:session_id`, `context:http_method`, `context:content`, `content_encoding`, `context:follow_redirects`, `context:successful_status_codes` |
| Avnet | `avnet_search` | `query` | `start_page` |
| Bed Bath & Beyond | `bedbathandbeyond` | `url` | none |
| Bed Bath & Beyond | `bedbathandbeyond_product` | `product_id` | none |
| Bed Bath & Beyond | `bedbathandbeyond_search` | `query` | `start_page` |
| Best Buy | `bestbuy_product` | `product_id` | `parse`, `domain`, `store_id`, `delivery_zip` |
| Best Buy | `bestbuy_search` | `query` | `start_page`, `domain`, `fulfillment_type` |
| Bing | `bing` | `url` | `parse`, `geo_location` |
| Bing | `bing_search` | `query` | `parse`, `geo_location`, `domain`, `locale`, `start_page`, `pages`, `limit` |
| Bodega Aurrerá | `bodegaaurrera` | `url` | `delivery_zip`, `store_id` |
| Bodega Aurrerá | `bodegaaurrera_product` | `product_id` | `subdomain`, `delivery_zip`, `store_id` |
| Bodega Aurrerá | `bodegaaurrera_search` | `query` | `subdomain`, `delivery_zip`, `context:store_id`, `context:fulfillment_type` |
| Cdiscount | `cdiscount` | `url` | none |
| Cdiscount | `cdiscount_product` | `product_id` | none |
| Cdiscount | `cdiscount_search` | `query` | `start_page` |
| ChatGPT | `chatgpt` | `prompt` | `search`, `parse`, `geo_location`, `browser_instructions`; no `render`, `user_agent_type` |
| Costco | `costco` | `url` | none |
| Costco | `costco_product` | `product_id` | `domain` |
| Costco | `costco_search` | `query` | `domain`, `start_page` |
| Dcard | `dcard_search` | `query` | none |
| eBay | `ebay` | `url` | none |
| eBay | `ebay_product` | `product_id` | `domain` |
| eBay | `ebay_search` | `query` | `start_page`, `domain` |
| Etsy | `etsy` | `url` | none |
| Etsy | `etsy_product` | `product_id` | `parse` |
| Etsy | `etsy_search` | `query` | `start_page`, `store_id`, `geo_location` |
| Falabella | `falabella` | `url` | none |
| Falabella | `falabella_product` | `product_id` | none |
| Falabella | `falabella_search` | `query` | `start_page` |
| Flipkart | `flipkart` | `url` | none |
| Flipkart | `flipkart_product` | `product_id` | none |
| Flipkart | `flipkart_search` | `query` | `start_page` |
| Gemini | `gemini` | `prompt` | `parse`, `geo_location`, `browser_instructions`; no `render`, `user_agent_type` |
| Google | `google` | `url` | `parse`, `geo_location` |
| Google | `google_ads` | `query` | `parse`, `geo_location`, `locale`, `start_page`, `pages`, `context:udm`, `context:tbm`, `context:tbs`, `context:nfpr` |
| Google | `google_ai_mode` | `query` | `parse`, `geo_location`; no `user_agent_type` |
| Google | `google_lens` | `query` | `parse`, `geo_location`, `locale` |
| Google | `google_maps` | `query` | `geo_location`, `locale`, `start_page`, `pages`, `limit`, `context:nfpr`, `context:hotel_occupancy`, `context:hotel_dates` |
| Google | `google_scholar` | `query` | `parse` |
| Google | `google_search` | `query` | `parse`, `geo_location`, `locale`, `start_page`, `pages`, `limit`, `context:limit_per_page`, `context:filter`, `context:safe_search`, `context:udm`, `context:tbm`, `context:tbs`, `context:fpstate`, `context:nfpr`, `context:expand_aio` |
| Google | `google_travel_hotels` | `query` | `parse`, `geo_location`, `locale`, `start_page`, `context:adults`, `context:children`, `context:hotel_classes`, `context:hotel_dates` |
| Google | `google_trends_explore` | `query` | `geo_location`, `context:search_type`, `context:date_from`, `context:date_to`, `context:category_id`; no `render` |
| Google Shopping | `google_shopping_product` | `query` | `parse`, `geo_location`, `locale` |
| Google Shopping | `google_shopping_search` | `query` | `parse`, `geo_location`, `locale`, `start_page`, `pages`, `context:sort_by`, `context:min_price`, `context:max_price`, `context:nfpr` |
| Grainger | `grainger` | `url` | none |
| Grainger | `grainger_product` | `product_id` | `domain` |
| Grainger | `grainger_search` | `query` | `domain` |
| Idealo | `idealo_search` | `query` | none |
| IndiaMART | `indiamart` | `url` | none |
| IndiaMART | `indiamart_product` | `product_id` | none |
| IndiaMART | `indiamart_search` | `query` | none |
| Instacart | `instacart` | `url` | none |
| Instacart | `instacart_product` | `product_id` | `domain` |
| Instacart | `instacart_search` | `query` | none |
| Kroger | `kroger` | `url` | `store_id`, `delivery_zip`, `fulfillment_type` |
| Kroger | `kroger_product` | `product_id` | `store_id`, `delivery_zip`, `fulfillment_type` |
| Kroger | `kroger_search` | `query` | `store_id`, `delivery_zip`, `fulfillment_type`, `price_range`, `brand` |
| Lazada | `lazada` | `url` | none |
| Lazada | `lazada_product` | `product_id` | `domain` |
| Lazada | `lazada_search` | `query` | `start_page`, `domain` |
| Lowe's | `lowes` | `url` | `store_id`, `delivery_zip` |
| Lowe's | `lowes_product` | `product_id` | `store_id`, `delivery_zip` |
| Lowe's | `lowes_search` | `query` | `store_id`, `delivery_zip`, `free_delivery`, `pickup_today`, `delivery_today_tomorrow` |
| Magazine Luiza | `magazineluiza` | `url` | none |
| Magazine Luiza | `magazineluiza_product` | `product_id` | none |
| Magazine Luiza | `magazineluiza_search` | `query` | `start_page` |
| MediaMarkt | `mediamarkt` | `url` | none |
| MediaMarkt | `mediamarkt_product` | `product_id` | `domain` |
| MediaMarkt | `mediamarkt_search` | `query` | `start_page`, `domain` |
| Menards | `menards` | `url` | `store_id` |
| Menards | `menards_product` | `product_id` | `store_id` |
| Menards | `menards_search` | `query` | `start_page`, `store_id`, `pickup_at_store_eligible`, `in_stock_today`, `fulfillment_center`, `delivery_eligible` |
| Mercado Libre | `mercadolibre` | `url` | none |
| Mercado Libre | `mercadolibre_product` | `product_id` | `domain` |
| Mercado Libre | `mercadolibre_search` | `query` | none |
| Mercado Livre | `mercadolivre_product` | `product_id` | none |
| Mercado Livre | `mercadolivre_search` | `query` | none |
| Perplexity | `perplexity` | `prompt` | `parse`, `geo_location`, `browser_instructions`; no `render`, `user_agent_type` |
| Petco | `petco` | `url` | none |
| Petco | `petco_search` | `query` | `start_page`, `fulfillment_type` |
| Publix | `publix` | `url` | `store_id` |
| Publix | `publix_product` | `product_id` | `store_id` |
| Publix | `publix_search` | `query` | `store_id` |
| Rakuten | `rakuten` | `url` | none |
| Rakuten | `rakuten_search` | `query` | none |
| Staples | `staples_search` | `query` | `domain`, `start_page` |
| Target | `target` | `url` | `store_id`, `delivery_zip` |
| Target | `target_category` | `category_id` | `fulfillment_type`, `store_id`, `delivery_zip` |
| Target | `target_product` | `product_id` | `parse`, `fulfillment_type`, `store_id`, `delivery_zip` |
| Target | `target_search` | `query` | `parse`, `fulfillment_type`, `store_id`, `delivery_zip` |
| TikTok | `tiktok` | `url` | none |
| TikTok | `tiktok_shop_product` | `product_id` | none |
| TikTok | `tiktok_shop_search` | `query` | none |
| Tokopedia | `tokopedia` | `url` | none |
| Tokopedia | `tokopedia_search` | `query` | `start_page` |
| Walmart | `walmart` | `url` | `parse` |
| Walmart | `walmart_product` | `product_id` | `parse`, `domain`, `fulfillment_type`, `delivery_zip`, `store_id` |
| Walmart | `walmart_search` | `query` | `min_price`, `max_price`, `sort_by`, `parse`, `domain`, `fulfillment_speed`, `fulfillment_type`, `delivery_zip`, `store_id`, `start_page` |
| YouTube | `youtube_autocomplete` | `query` | `location`, `language`; no `render`, `user_agent_type` |
| YouTube | `youtube_channel` | `channel_handle` | `parse`, `limit`; no `render`, `user_agent_type` |
| YouTube | `youtube_download` | `query` | `storage_type`, `storage_url`, `context:download_type`, `context:video_quality`, `context:audio_language`, `context:start_at`, `context:end_at`; no `render`, `user_agent_type` |
| YouTube | `youtube_metadata` | `query` | `parse`; no `render`, `user_agent_type` |
| YouTube | `youtube_search` | `query` | `geo_location`, `upload_date`, `type`, `duration`, `sort_by`, `360`, `3d`, `4k`, `creative_commons`, `hd`, `hdr`, `live`, `location`, `purchased`, `subtitles`, `vr180`; no `callback_url`, `render`, `user_agent_type` |
| YouTube | `youtube_search_max` | `query` | `geo_location`, `upload_date`, `type`, `duration`, `sort_by`, `360`, `3d`, `4k`, `creative_commons`, `hd`, `hdr`, `live`, `location`, `purchased`, `subtitles`, `vr180`; no `callback_url`, `render`, `user_agent_type` |
| YouTube | `youtube_subtitles` | `query` | `context:language_code`, `context:subtitle_origin`; no `render`, `user_agent_type` |
| YouTube | `youtube_video_trainability` | `video_id` | none; no `render`, `user_agent_type` |
| Zillow | `zillow` | `url` | none |

The `bodegaaurrera_search` row takes its placement from that page's own sample ([Bodega Aurrerá Search][d-bodega-search]).
The Bodega Aurrerá product and URL pages do not show where `store_id` goes.

### Groups

| Group | Sources | Parameters beyond `source` and the input key |
| --- | --- | --- |
| Retail, base set only | 40 | `callback_url`, `render`, `user_agent_type` |
| Retail, base set plus `domain` or `start_page` | 23 | The base set, plus `domain` (9 sources), `start_page` (9) or both (5). |
| Retail with localization, filters or a parser | 29 | The base set, plus some of `store_id`, `delivery_zip`, `fulfillment_type`, `subdomain`, `domain`, `parse` and filters specific to the target. |
| Amazon | 6 | The base set, plus `parse`, `geo_location`, `domain`, `locale`, pagination and `context` keys. |
| Google and Bing | 13 | The base set, plus `parse`, `geo_location`, `locale`, pagination and Google `context` keys. `google_ai_mode` lacks `user_agent_type`, and `google_trends_explore` lacks `render`. |
| YouTube | 8 | No `render` or `user_agent_type`. Each source has its own set. |
| LLMs | 3 | `callback_url`, `parse`, `geo_location` and `browser_instructions`. `chatgpt` adds `search`. |
| Any domain | 1 | The base set, plus the feature parameters on the Any Domain page. |

### Same name, different rules

| Name | How it varies |
| --- | --- |
| `store_id` | The Kroger, Lowe's, Menards, Publix, Target, Best Buy, Etsy and Walmart pages list it as a top-level parameter, and the Kroger, Lowe's and Publix samples send it that way. A `context` item on `bodegaaurrera_search`, on Walmart's non-US domains and on The Home Depot through `universal`. A string that must start with `0` on Kroger, an integer on Publix, Lowe's, Best Buy and Etsy, and a string on Menards, Walmart, Bodega Aurrerá and The Home Depot. Target's pages say integer, and its E-Commerce Localization section says string. |
| `sort_by` | A top-level key on `walmart_search` (`price_low`, `price_high`, `best_seller`, `best_match`) and `youtube_search` (`rating`, `relevance`, `view_count`, `upload_date`). A `context` item on `amazon_search` (six values) and `google_shopping_search` (`r`, `rv`, `p`, `pd`). |
| `min_price`, `max_price` | Top-level keys on `walmart_search`. `context` items on `amazon_search`, in integer cents, and on `google_shopping_search`. |
| `category_id` | The input key of `target_category`, a string such as `owq2q`. A `context` item on `amazon_search`, as a node ID string, and on `google_trends_explore`, as an integer such as `3`. |
| `location` | A country code string on `youtube_autocomplete`, default `US`. A boolean filter on `youtube_search`. |
| `limit` | Results per page on `google_search`, `google_maps` and `bing_search`, default 10. Videos returned on `youtube_channel`, default 20. |
| `geo_location` | Amazon takes a postal code or an alpha-2 code. Google takes canonical location names, coordinates or Criteria IDs, and applies no location for an unrecognised value. Bing applies the country only. `google_trends_explore` takes alpha-2 codes, and `google_travel_hotels` needs a city. `universal`, the LLM sources and YouTube take a country. |
| `domain` | Each target has its own value set: 23 for Amazon, 6 for Bing, 4 for Walmart, 12 for Costco and 10 for eBay, among others. Defaults differ: `com` for most, `de` for MediaMarkt, `com.ph` for Lazada, and none for Grainger and Mercado Libre. |
| `fulfillment_type` | Kroger takes `pickup`, `delivery` and `in_store`. Walmart takes `pickup`, `delivery` and `shipping`, depending on the domain. Target takes `pickup`, `shipping`, `shop_in_store` and `same_day_delivery`. Best Buy takes `pickup` and `shipping`, Bodega Aurrerá takes `pickup` and `delivery`, and Petco takes `repeat_delivery`, `free_pickup_today` and `same_day_delivery`. |
| `subdomain` | `www` or `despensa` on Bodega Aurrerá. A two-letter country code on `aliexpress_product`. |

Sources: the source pages named in the table, [E-Commerce Localization][d-ecom-loc], [SERP Localization][d-serp-loc] and [Proxy Location][d-proxy-loc].

### Documented incompatibilities

| Scope | Rule | Page |
| --- | --- | --- |
| `chatgpt`, `gemini`, `perplexity` | Push-Pull only, because Realtime and Proxy Endpoint are not available. Rendering is on by default, and the page says not to send `render`. | [LLMs and AI][d-llm] |
| `youtube_download` | Push-Pull with Cloud Storage only, so `storage_type` and `storage_url` are required. `context:start_at` and `context:end_at` take `hh:mm:ss`, `end_at` must be later, and a bad value returns 400. | [YouTube Downloader][d-yt-download] |
| `youtube_metadata` | `render` is not supported, and `parse` must be `true`. | [YouTube Metadata][d-yt-metadata], [YouTube guide for AI][d-yt-guide] |
| `google_ai_mode` | `render: html` is required, and `query` must be under 400 characters. Google AI Mode is not available in France, Turkey, China, Iran, North Korea, Syria or Cuba. | [Google AI Mode][d-g-ai-mode] |
| `google_search`, `google_ads` | `context:udm` and `context:tbm` cannot be combined. | [Google Search][d-g-search] |
| `google_shopping_product` | `query` must be a product token, and only a rendered, parsed `google_shopping_search` job returns one. | [Shopping Product][d-g-shop-product], [Shopping Search][d-g-shop-search] |
| `google_travel_hotels` | Needs a city-level `geo_location`, and the page asks for `render: html`. | [Travel Hotels][d-g-hotels] |
| `google_trends_explore` | Always returns parsed data, and `geo_location` takes alpha-2 codes. | [Trends: Explore][d-g-trends] |
| `google_maps` | `context:hotel_occupancy` and `context:hotel_dates` apply to hotel searches only. | [Local Search][d-g-maps] |
| Amazon `geo_location` | `cn`, `com.tr`, `com.be` and `nl` take no custom delivery location. `com.au` takes Australian postcodes only, and `ae` takes city names or alpha-2 codes. | [E-Commerce Localization][d-ecom-loc] |
| Amazon `context:currency` | `com` supports USD only, and every other domain accepts its listed codes. | [currency list][d-currency] |
| Amazon `locale` | Only the listed `domain` and `locale` pairs work. | [Domain and Locale][d-domain-locale] |
| Kroger | `pickup` and `in_store` need `store_id`, and `delivery` needs `delivery_zip`. An invalid pair returns a 404 page, or 400 on search. `store_id` must start with `0`. | [Kroger Product][d-kroger-product], [Kroger Search][d-kroger-search] |
| Bodega Aurrerá | `delivery_zip`, `store_id` and `fulfillment_type` apply only with `subdomain: despensa`. | [Bodega Aurrerá Search][d-bodega-search] |
| Walmart | `com` takes `fulfillment_type` values `pickup`, `delivery` and `shipping`. `com.mx` and `ca` take `pickup` and `delivery`, and `co.cr` takes `pickup` only. | [Walmart Product][d-walmart-product] |
| `bestbuy_search` | `pickup` needs `store_id`, `shipping` needs `delivery_zip`, and `domain` takes `com` only. | [Best Buy Search][d-bestbuy-search] |
| `rakuten`, `rakuten_search` | Only the `com.tw` domain works. | [Rakuten Search][d-rakuten-search] |
| `xhr` | Needs `render`, and the API rejects the job otherwise. | [Fetch/XHR][d-xhr] |
| `browser_instructions` | Needs `render`, and `fetch_resource` must come last. A malformed instruction returns 400. | [JS Rendering][d-js] |
| `storage_type`, `storage_url` | Push-Pull only. | [Cloud Storage][d-storage] |
| Batch | Only `query` or `url` may be a list, of up to 5,000 values, and every other parameter takes one value. | [Push-Pull][d-push-pull] |
| `parse` | Needs a dedicated parser, or `parsing_instructions` or `parser_preset`. The `amazon`, `google` and `walmart` URL sources parse only some page types. | [Dedicated Parsers][d-parsers], [Amazon URL][d-amz-url], [Google URL][d-g-url], [Walmart URL][d-walmart-url] |
| `render` | Rendered jobs have a lower rate limit: 13 per second on Micro to Venture plans, against 50 jobs per second overall. | [Rate Limits][d-rate] |
| Restricted targets | A job for a restricted target returns 400 before any scraping. | [Restricted Targets][d-restricted] |

### Quirks from earlier billed runs

#### `geo_location` on `amazon_product`

- The docs support the pair.
  The Amazon overview's request sample sends `amazon_product` with `geo_location: "90210"`, and the product page advises setting the delivery location ([Amazon][d-amazon], [Product][d-amz-product]).
- The docs restrict the value, not the source.
  `geo_location` takes a postal code inside the marketplace's country and an alpha-2 code outside it.
  `cn`, `com.tr`, `com.be` and `nl` take no custom delivery location ([E-Commerce Localization][d-ecom-loc]).
- The product page's first request sample uses `domain: nl`, one of those four domains ([Product][d-amz-product]).
- Country names such as `Germany` work for `universal` and Google, but they are not among Amazon's documented values ([Proxy Location][d-proxy-loc], [SERP Localization][d-serp-loc]).
- No page says what an unsupported value does: fault the job, return 400, or apply no location.

#### `render: html` on Google search batches

- No page restricts `render` on `google_search` or on batches.
  The batch rule limits only which parameter may be a list ([Push-Pull][d-push-pull]).
- Google pages ask for rendering.
  AI Overviews need `render: html`, `google_ai_mode` requires it, and `google_shopping_search` returns product tokens only from rendered jobs ([AI Overviews][d-g-aio], [Google AI Mode][d-g-ai-mode], [Shopping Search][d-g-shop-search]).
- Rendered jobs have their own rate limit: 13 per second on Micro to Venture plans, against 50 jobs per second overall ([Rate Limits][d-rate]).
- If each query in a batch counts as a job, one batch of more than 13 rendered queries passes that limit in a single HTTP request.
  The docs do not say how the batch endpoint answers then.

### Where the docs and the SDK disagree

| Topic | Docs | SDK 3.0.0 |
| --- | --- | --- |
| Source for any URL | `universal` | Sends `universal_ecommerce` ([source.py][s-source], [universal.py][s-universal]). |
| Sources in only one of the two | `gemini`, `google_scholar`, `universal` | `amazon_reviews`, `amazon_questions`, `google_suggest`, `google_shopping`, `wayfair`, `wayfair_search`, `shein_search`, `youtube_transcript`, `universal_ecommerce` |
| `amazon_search` sorting and filters | `sort_by` and `refinements` are `context` items, and `refinements` is a list. | Both are top-level keys, and `refinements` is typed `str` ([amazon.py][s-amazon]). |
| Google `domain` | No Google page lists it. | Six Google sources and the images and news methods send it ([google.py][s-google]). Main drops it after 3.0.0 ([9823585][s-google-domain]). |
| `results_language` | One SERP Localization hint names it, and no page defines it. | Both Google Shopping sources send it ([google_shopping.py][s-gshop]). |
| LLM sources | Push-Pull only, and no `render`. | `RealtimeClient` exposes `chatgpt` and `perplexity`, and `Chatgpt.scrape` takes a `render` argument ([client.py][s-client], [chatgpt.py][s-chatgpt]). |
| Kroger `store_id` | A string that must start with `0`, such as `01100002`. | Typed `int`, which cannot keep the leading zero ([kroger.py][s-kroger]). |
| Walmart localization | Non-US domains take `delivery_zip` and `store_id` as `context` items ([E-Commerce Localization][d-ecom-loc]). | Always top-level keys ([walmart.py][s-walmart]). |
| `user_agent_type` | Seven values. | Twelve constants, adding `desktop_chrome`, `desktop_edge`, `desktop_firefox`, `desktop_opera` and `desktop_safari` ([user_agent_type.py][s-uat]). |
| `locale` | `en_US` style for Amazon, and `de-DE` style for Google and Bing. | Constants `en`, `ru`, `by`, `de`, `fr`, `id`, `kk`, `tt`, `tr` and `uk` ([locale.py][s-locale]). |
| `browser_instructions` | A list of instruction objects. | Typed `dict` ([universal.py][s-universal]). |
| Parameter names per source | See the next table. | 33 of the 120 shared sources differ. |

The next table lists every shared source whose named parameters differ.
It compares each source page with the payload keys of the matching SDK 3.0.0 method.

| Sources | Only in the docs | Only in SDK 3.0.0 |
| --- | --- | --- |
| `airbnb_product` | `domain` | none |
| `aliexpress_product` | `domain`, `subdomain` | none |
| `amazon_search` | `sort_by`, `refinements` as `context` items | `sort_by`, `refinements` as top-level keys |
| `bodegaaurrera` | `delivery_zip`, `store_id` | none |
| `bodegaaurrera_product` | `delivery_zip`, `store_id`, `subdomain` | none |
| `bodegaaurrera_search` | `delivery_zip`, `context:store_id`, `context:fulfillment_type` | `start_page` |
| `chatgpt` | `browser_instructions` | `render` |
| `perplexity` | `browser_instructions` | none |
| `google_ads`, `google_maps`, `google_search` | none | `domain` |
| `google_shopping_product`, `google_shopping_search` | none | `domain`, `results_language` |
| `google_travel_hotels` | `parse` | `domain` |
| `grainger_search`, `indiamart_search`, `mercadolibre_search`, `mercadolivre_search`, `publix_search`, `rakuten_search` | none | `start_page` |
| `instacart_search` | none | `domain`, `start_page` |
| `kroger_search` | `price_range`, `brand` | none |
| `lazada_product`, `lazada_search` | `domain` | none |
| `lowes`, `lowes_product` | `delivery_zip`, `store_id` | none |
| `mercadolibre_product` | `domain` | none |
| `petco`, `petco_search` | none | `store_id` |
| `tiktok_shop_product` | none | `domain` |
| `walmart_product` | `fulfillment_type` | none |
| `youtube_search`, `youtube_search_max` | `geo_location` | `callback_url` |

`bestbuy_search` is not in the table.
The SDK adds `store_id` and `delivery_zip` to it, and the docs name both inside the `fulfillment_type` description.

### How the SDK handles parameters

- Each target method names its parameters, and merges unknown keyword arguments into the payload ([amazon.py][s-amazon]).
- The client drops top-level keys whose value is `None`, and sends the rest unchecked ([api.py][s-api-strip]).
- The SDK checks only `parsing_instructions` before it submits ([utils.py][s-utils]).
  Each `_fn` must be one of 20 names, and they match the 20 functions in the docs ([List of functions][d-functions]).
  Each `_args` must fit its function.
- The check skips `_items`, which holds the instructions for each item of a list ([Parsing instruction examples][d-parse-examples]).
  When a level has `_fns`, the SDK checks the functions and does not descend into that level's other keys.
- The SDK renames `360`, `3d` and `4k` to `filter_360`, `filter_3d` and `filter_4k` in Python, and maps them back in the payload ([youtube.py][s-youtube]).

### Where the docs disagree with themselves

- Seven pages give a wrong default in their `source` row.
  `bestbuy_product`, `lowes_product`, `lowes`, `petco`, `rakuten` and `target_product` say `universal`, and `allegro_product` says `allegro_search` ([Allegro Product][d-allegro-product], [Target Product][d-target-product]).
  Each page's request sample uses its own source.
- [E-Commerce Localization][d-ecom-loc] says Kroger needs no `context` item for the store ID, "unlike with other sources".
  Yet the Lowe's and Publix samples send a top-level `store_id` too ([Publix Search][d-publix-search]).
- [Petco Search][d-petco-search] and the Target section of [E-Commerce Localization][d-ecom-loc] type `fulfillment_type` as Boolean, then list string values.
- Kroger's default `fulfillment_type` is `in_store` on the product page and `pickup` on the search, URL and localization pages ([Kroger Product][d-kroger-product], [Kroger Search][d-kroger-search]).
- Target's `fulfillment_type` takes `pickup`, `delivery` and `shipping` on the product page, and `pickup`, `shipping`, `shop_in_store` and `same_day_delivery` on the search page ([Target Product][d-target-product], [Target Search][d-target-search]).
- `browser_instructions` is a list on [JS Rendering][d-js] and an "object" on the [LLMs and AI][d-llm] overview.
- The [YouTube guide for AI][d-yt-guide] batches `youtube_video_trainability` with a `query` list, while the source's own page uses `video_id` ([Video Trainability][d-yt-trainability]).
- [Travel Hotels][d-g-hotels] calls wide-area `geo_location` values not supported, while [SERP Localization][d-serp-loc] says they work and return hotels from the whole area.
- A `context:session_id` session lasts up to 10 minutes on [Any Domain][d-any], and up to 25 minutes or 100 requests on [Proxy Location][d-proxy-loc].

### Client identifier header

SDK 3.0.0 sends the header `x-oxylabs-sdk` on every Realtime and Push-Pull HTTP request ([api.py][s-api]).
Its value is `oxylabs-sdk-python/<version> (<Python version>; <pointer width>)`, such as `oxylabs-sdk-python/3.0.0 (3.12.4; 64bit)`.
The SDK builds the value from `platform.python_version()` and `platform.architecture()`.
A caller can replace it with the `sdk_type` keyword argument of `RealtimeClient` or `AsyncClient`.
`ProxyClient` sends the same header, with no way to replace it ([proxy.py][s-proxy]).
The header arrived in 1.0.7 ([pull request 23][s-pr-23]), and no docs page mentions it.

### Source counts and churn

On 2026-09-24 the docs list 123 sources for 43 targets, plus `universal`.
SDK 3.0.0 has 46 target attributes on each client, and its methods send 129 distinct source values.
120 sources appear in both.

The table counts the distinct `source` values that each release's methods send.

| Release | PyPI upload | Sources | Change |
| --- | --- | --- | --- |
| 1.0.0 | 2024-03-30 | 28 | First release ([source.py at 1.0.0][s-src-100]). |
| 1.0.1 | 2024-03-30 | 28 | None. |
| 1.0.3 | 2024-06-12 | 24 | Removed `baidu`, `baidu_search`, `yandex` and `yandex_search` ([1.0.3 files][s-src-103]). |
| 1.0.4 to 1.0.7 | 2024-06-12 to 2024-11-08 | 24 | None. |
| 2.0.0 | 2025-03-28 | 29 | Added `google_lens`, `google_maps`, `kroger`, `kroger_product`, `kroger_search` and `youtube_transcript`, and removed `google_hotels` ([sources at 2.0.0][s-src-200]). |
| 3.0.0 | 2026-03-09 | 129 | Added 101 sources, removed `google_shopping_pricing`, and changed the parameters of 8 existing methods ([2.0.0 to 3.0.0][s-compare-2-3]). |
| main at `540d9a4` | not released | 128 | Removed `google_suggest`, and changed the parameters of 13 sources ([3.0.0 to main][s-compare]). |

Three of the nine PyPI releases changed the source list ([release history][s-pypi], [changelog][s-changelog]).
Counting from 1.0.0, those three changes came 2.5, 9.5 and 11.5 months apart.
After 3.0.0, a docs-sync commit on main added `country` to the TikTok sources ([fd2af40][s-docs-sync]).
Today's TikTok pages do not list `country` ([TikTok Shop Search][d-tiktok-search]).

## Open questions

- Does the API reject, ignore or accept unknown top-level keys and unknown `context` keys?
  The docs do not say, and the answer decides whether a typo in an open parameter set fails at submission or bills a result.
- Does the batch endpoint accept lists of `product_id`, `prompt`, `video_id`, `channel_handle` or `category_id`?
  The Push-Pull page names only `query` and `url`, and 34 sources use another input key.
- Which `geo_location` value and `domain` faulted on `amazon_product`?
  Does an unsupported value fault the job, return 400, or apply no location?
- How did the rendered Google search batch fail: a 429 from the rendered-jobs limit, a 400, or faulted jobs?
- Does the API still accept what SDK 3.0.0 sends and the docs omit?
  That covers `universal_ecommerce`, `domain` on Google sources, top-level `sort_by` and `refinements` on `amazon_search`, and the eight sources only the SDK lists.
- Which feature parameters does each dedicated source accept?
  The docs show `markdown` and `xhr` only on `universal` and `amazon_product`.

## Sources

Oxylabs docs, read on 2026-09-24:

- [llms.txt index][d-llms] and [Web Scraper API][d-wsa]
- [Amazon][d-amazon], [Product][d-amz-product], [Search][d-amz-search], [Pricing][d-amz-pricing], [Sellers][d-amz-sellers], [Best Sellers][d-amz-bestsellers], [URL][d-amz-url] and the [currency list][d-currency]
- [Domain and Locale][d-domain-locale], [E-Commerce Localization][d-ecom-loc], [SERP Localization][d-serp-loc], [Proxy Location][d-proxy-loc]
- [User Agent Type][d-uat], [Headers, Cookies, Method][d-headers], [Client Notes][d-client-notes], [JS Rendering][d-js]
- [Fetch/XHR][d-xhr], [Markdown Output][d-markdown], [Multi-format Output][d-multi], [Download Images][d-images], [Dedicated Parsers][d-parsers]
- [Custom Parser][d-custom-parser], [List of functions][d-functions], [Parsing instruction examples][d-parse-examples]
- [Cloud Storage][d-storage], [File name templating][d-templating], [Result Aggregator][d-aggregator]
- [Push-Pull][d-push-pull], [Response Codes][d-codes], [Traffic and Billing][d-billing], [Rate Limits][d-rate], [Restricted Targets][d-restricted]
- [Any Domain][d-any], [Google Search][d-g-search], [AI Overviews][d-g-aio], [Google AI Mode][d-g-ai-mode], [Local Search][d-g-maps], [Travel Hotels][d-g-hotels], [Trends: Explore][d-g-trends], [Shopping Search][d-g-shop-search], [Shopping Product][d-g-shop-product], [Google URL][d-g-url], [Bing Search][d-bing-search]
- [LLMs and AI][d-llm], [YouTube Search][d-yt-search], [YouTube Metadata][d-yt-metadata], [YouTube Downloader][d-yt-download], [Video Trainability][d-yt-trainability], [YouTube Autocomplete][d-yt-autocomplete], [YouTube guide for AI][d-yt-guide]
- [Kroger Product][d-kroger-product], [Kroger Search][d-kroger-search], [Bodega Aurrerá Search][d-bodega-search], [Walmart Product][d-walmart-product], [Walmart Search][d-walmart-search], [Walmart URL][d-walmart-url], [Target Product][d-target-product], [Target Search][d-target-search], [Petco Search][d-petco-search], [Best Buy Search][d-bestbuy-search], [Rakuten Search][d-rakuten-search], [Publix Search][d-publix-search], [Allegro Product][d-allegro-product], [TikTok Shop Search][d-tiktok-search]

The billing claim about 4xx results comes from [Traffic and Billing][d-billing], and the 400 description from [Response Codes][d-codes].

Official SDK, `oxylabs/oxylabs-sdk-python`:

- At tag `3.0.0`: [api.py header][s-api], [api.py payload][s-api-strip], [client.py][s-client], [source.py][s-source], [universal.py][s-universal], [amazon.py][s-amazon-file], [amazon.py scrape_search][s-amazon], [kroger.py][s-kroger], [walmart.py][s-walmart], [chatgpt.py][s-chatgpt], [google.py][s-google], [google_shopping.py][s-gshop], [youtube.py][s-youtube], [user_agent_type.py][s-uat], [locale.py][s-locale], [utils.py][s-utils], [proxy.py][s-proxy], [CHANGELOG.md][s-changelog]
- Release history: [PyPI][s-pypi], [source.py at 1.0.0][s-src-100], [1.0.3 files][s-src-103], [sources at 2.0.0][s-src-200], [pull request 23][s-pr-23], [2.0.0 to 3.0.0][s-compare-2-3]
- After 3.0.0: [3.0.0 to main at 540d9a4][s-compare], [commit 9823585][s-google-domain], [commit fd2af40][s-docs-sync]

[d-llms]: https://developers.oxylabs.io/llms.txt
[d-wsa]: https://developers.oxylabs.io/products/web-scraper-api.md
[d-amazon]: https://developers.oxylabs.io/api-targets/e-commerce/amazon.md
[d-amz-product]: https://developers.oxylabs.io/api-targets/e-commerce/amazon/product.md
[d-amz-search]: https://developers.oxylabs.io/api-targets/e-commerce/amazon/search.md
[d-amz-pricing]: https://developers.oxylabs.io/api-targets/e-commerce/amazon/pricing.md
[d-amz-sellers]: https://developers.oxylabs.io/api-targets/e-commerce/amazon/sellers.md
[d-amz-bestsellers]: https://developers.oxylabs.io/api-targets/e-commerce/amazon/best-sellers.md
[d-amz-url]: https://developers.oxylabs.io/api-targets/e-commerce/amazon/url.md
[d-currency]: https://developers.oxylabs.io/api-targets/e-commerce/amazon/product.md
[d-domain-locale]: https://developers.oxylabs.io/products/web-scraper-api/features/localization/domain-locale.md
[d-ecom-loc]: https://developers.oxylabs.io/products/web-scraper-api/features/localization/e-commerce-localization.md
[d-serp-loc]: https://developers.oxylabs.io/products/web-scraper-api/features/localization/serp-localization.md
[d-proxy-loc]: https://developers.oxylabs.io/products/web-scraper-api/features/localization/proxy-location.md
[d-uat]: https://developers.oxylabs.io/products/web-scraper-api/features/http-context-and-job-management/user-agent-type.md
[d-headers]: https://developers.oxylabs.io/products/web-scraper-api/features/http-context-and-job-management/headers-cookies-method.md
[d-client-notes]: https://developers.oxylabs.io/products/web-scraper-api/features/http-context-and-job-management/client-notes.md
[d-js]: https://developers.oxylabs.io/products/web-scraper-api/features/js-rendering-and-browser-control.md
[d-xhr]: https://developers.oxylabs.io/products/web-scraper-api/features/result-processing-and-storage/output-types/capturing-network-requests-fetch-xhr.md
[d-markdown]: https://developers.oxylabs.io/products/web-scraper-api/features/result-processing-and-storage/output-types/markdown-output.md
[d-multi]: https://developers.oxylabs.io/products/web-scraper-api/features/result-processing-and-storage/output-types/multi-format-output.md
[d-images]: https://developers.oxylabs.io/products/web-scraper-api/features/result-processing-and-storage/output-types/download-images.md
[d-parsers]: https://developers.oxylabs.io/products/web-scraper-api/features/result-processing-and-storage/dedicated-parsers.md
[d-custom-parser]: https://developers.oxylabs.io/products/web-scraper-api/features/custom-parser.md
[d-functions]: https://developers.oxylabs.io/products/web-scraper-api/features/custom-parser/writing-instructions-manually/list-of-functions.md
[d-parse-examples]: https://developers.oxylabs.io/products/web-scraper-api/features/custom-parser/writing-instructions-manually/parsing-instruction-examples.md
[d-storage]: https://developers.oxylabs.io/products/web-scraper-api/features/result-processing-and-storage/cloud-storage.md
[d-templating]: https://developers.oxylabs.io/products/web-scraper-api/features/result-processing-and-storage/cloud-storage/file-name-templating.md
[d-aggregator]: https://developers.oxylabs.io/products/web-scraper-api/features/result-processing-and-storage/result-aggregator.md
[d-push-pull]: https://developers.oxylabs.io/products/web-scraper-api/integration-methods/push-pull.md
[d-codes]: https://developers.oxylabs.io/products/web-scraper-api/response-codes.md
[d-billing]: https://developers.oxylabs.io/products/web-scraper-api/usage-and-billing/billing-information.md
[d-rate]: https://developers.oxylabs.io/products/web-scraper-api/usage-and-billing/rate-limits.md
[d-restricted]: https://developers.oxylabs.io/products/web-scraper-api/restricted-targets.md
[d-any]: https://developers.oxylabs.io/api-targets/overview.md
[d-g-search]: https://developers.oxylabs.io/api-targets/search-engines/google/search/search.md
[d-g-aio]: https://developers.oxylabs.io/api-targets/search-engines/google/ai-overviews.md
[d-g-ai-mode]: https://developers.oxylabs.io/api-targets/search-engines/google/ai-mode.md
[d-g-maps]: https://developers.oxylabs.io/api-targets/search-engines/google/search/local-search.md
[d-g-hotels]: https://developers.oxylabs.io/api-targets/search-engines/google/travel-hotels.md
[d-g-trends]: https://developers.oxylabs.io/api-targets/search-engines/google/trends-explore.md
[d-g-shop-search]: https://developers.oxylabs.io/api-targets/search-engines/google/shopping/shopping-search.md
[d-g-shop-product]: https://developers.oxylabs.io/api-targets/search-engines/google/shopping/shopping-product.md
[d-g-url]: https://developers.oxylabs.io/api-targets/search-engines/google/url.md
[d-bing-search]: https://developers.oxylabs.io/api-targets/search-engines/bing/search.md
[d-llm]: https://developers.oxylabs.io/api-targets/llms-and-ai.md
[d-yt-search]: https://developers.oxylabs.io/api-targets/video-and-social-media/youtube/youtube-search.md
[d-yt-metadata]: https://developers.oxylabs.io/api-targets/video-and-social-media/youtube/youtube-metadata.md
[d-yt-download]: https://developers.oxylabs.io/api-targets/video-and-social-media/youtube/youtube-downloader.md
[d-yt-trainability]: https://developers.oxylabs.io/api-targets/video-and-social-media/youtube/youtube-video-trainability.md
[d-yt-autocomplete]: https://developers.oxylabs.io/api-targets/video-and-social-media/youtube/autocomplete.md
[d-yt-guide]: https://developers.oxylabs.io/api-targets/video-and-social-media/youtube/youtube-scraping-guide-for-ai.md
[d-kroger-product]: https://developers.oxylabs.io/api-targets/e-commerce/kroger/product.md
[d-kroger-search]: https://developers.oxylabs.io/api-targets/e-commerce/kroger/search.md
[d-bodega-search]: https://developers.oxylabs.io/api-targets/e-commerce/bodega-aurrera/search.md
[d-walmart-product]: https://developers.oxylabs.io/api-targets/e-commerce/walmart/product.md
[d-walmart-search]: https://developers.oxylabs.io/api-targets/e-commerce/walmart/search.md
[d-walmart-url]: https://developers.oxylabs.io/api-targets/e-commerce/walmart/url.md
[d-target-product]: https://developers.oxylabs.io/api-targets/e-commerce/target/product.md
[d-target-search]: https://developers.oxylabs.io/api-targets/e-commerce/target/search.md
[d-petco-search]: https://developers.oxylabs.io/api-targets/e-commerce/petco/search.md
[d-bestbuy-search]: https://developers.oxylabs.io/api-targets/e-commerce/bestbuy/search.md
[d-rakuten-search]: https://developers.oxylabs.io/api-targets/e-commerce/rakuten/search.md
[d-publix-search]: https://developers.oxylabs.io/api-targets/e-commerce/publix/search.md
[d-allegro-product]: https://developers.oxylabs.io/api-targets/e-commerce/allegro/product.md
[d-tiktok-search]: https://developers.oxylabs.io/api-targets/e-commerce/tiktok/shop-search.md
[s-api]: https://github.com/oxylabs/oxylabs-sdk-python/blob/3.0.0/src/oxylabs/internal/api.py#L36-L44
[s-api-strip]: https://github.com/oxylabs/oxylabs-sdk-python/blob/3.0.0/src/oxylabs/internal/api.py#L67-L68
[s-client]: https://github.com/oxylabs/oxylabs-sdk-python/blob/3.0.0/src/oxylabs/internal/client.py#L54-L109
[s-source]: https://github.com/oxylabs/oxylabs-sdk-python/blob/3.0.0/src/oxylabs/utils/types/source.py#L28
[s-universal]: https://github.com/oxylabs/oxylabs-sdk-python/blob/3.0.0/src/oxylabs/sources/universal/universal.py#L22-L76
[s-amazon-file]: https://github.com/oxylabs/oxylabs-sdk-python/blob/3.0.0/src/oxylabs/sources/amazon/amazon.py
[s-amazon]: https://github.com/oxylabs/oxylabs-sdk-python/blob/3.0.0/src/oxylabs/sources/amazon/amazon.py#L22-L88
[s-kroger]: https://github.com/oxylabs/oxylabs-sdk-python/blob/3.0.0/src/oxylabs/sources/kroger/kroger.py#L25
[s-walmart]: https://github.com/oxylabs/oxylabs-sdk-python/blob/3.0.0/src/oxylabs/sources/north_american/walmart/walmart.py
[s-chatgpt]: https://github.com/oxylabs/oxylabs-sdk-python/blob/3.0.0/src/oxylabs/sources/chatgpt/chatgpt.py#L24
[s-google]: https://github.com/oxylabs/oxylabs-sdk-python/blob/3.0.0/src/oxylabs/sources/google/google.py#L69
[s-gshop]: https://github.com/oxylabs/oxylabs-sdk-python/blob/3.0.0/src/oxylabs/sources/google_shopping/google_shopping.py#L29
[s-youtube]: https://github.com/oxylabs/oxylabs-sdk-python/blob/3.0.0/src/oxylabs/sources/youtube/youtube.py#L53-L131
[s-uat]: https://github.com/oxylabs/oxylabs-sdk-python/blob/3.0.0/src/oxylabs/utils/types/user_agent_type.py
[s-locale]: https://github.com/oxylabs/oxylabs-sdk-python/blob/3.0.0/src/oxylabs/utils/types/locale.py
[s-utils]: https://github.com/oxylabs/oxylabs-sdk-python/blob/3.0.0/src/oxylabs/utils/utils.py#L143-L166
[s-proxy]: https://github.com/oxylabs/oxylabs-sdk-python/blob/3.0.0/src/oxylabs/proxy/proxy.py#L41
[s-changelog]: https://github.com/oxylabs/oxylabs-sdk-python/blob/3.0.0/CHANGELOG.md
[s-pypi]: https://pypi.org/project/oxylabs/#history
[s-src-100]: https://github.com/oxylabs/oxylabs-sdk-python/blob/1.0.0/oxylabs/utils/source.py
[s-src-103]: https://pypi.org/project/oxylabs/1.0.3/#files
[s-src-200]: https://github.com/oxylabs/oxylabs-sdk-python/tree/2.0.0/src/oxylabs/sources
[s-pr-23]: https://github.com/oxylabs/oxylabs-sdk-python/pull/23
[s-compare-2-3]: https://github.com/oxylabs/oxylabs-sdk-python/compare/2.0.0...3.0.0
[s-compare]: https://github.com/oxylabs/oxylabs-sdk-python/compare/3.0.0...540d9a4dbfffc549b33559be03210221edcc0859
[s-google-domain]: https://github.com/oxylabs/oxylabs-sdk-python/commit/9823585
[s-docs-sync]: https://github.com/oxylabs/oxylabs-sdk-python/commit/fd2af40
