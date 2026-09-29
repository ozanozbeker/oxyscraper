# What a live test shows about `universal` and the instruction parameters

This note records what a billed run against the live Oxylabs API showed about the `universal` source, `parsing_instructions` and `browser_instructions`.
It answers [What does a live test show about `universal` and the instruction parameters?](https://github.com/ozanozbeker/oxyscraper/issues/41), which collects the evidence that [How are parameters typed?](https://github.com/ozanozbeker/oxyscraper/issues/12) asks for.
The run took place on 2026-09-29, from 17:45 to 18:19 UTC, on the account with the Starter plan.
It spent 81 results, 20 of them rendered, and Usage Statistics agrees.
The plan expected about 55 and 14, and the follow-ups that the first results raised spent the rest.

Free probes used `universal` fault jobs for unregistered `.com` names, as [Fault jobs](live-api.md#fault-jobs) describes.
Of 98 fault jobs, 97 ended `faulted`, and one ended `done` with the 488-byte router page that section describes, and billed.
Another 63 submissions returned 400, and 9 returned 500.

The billed jobs used pages that show a parameter's effect.
`httpbin.org` echoes the request it receives, and `httpbin.org/base64/<value>` serves any HTML the URL encodes.
`quotes.toscrape.com` loads its quotes with JavaScript, on scroll or after a delay.
`www.cloudflare.com/cdn-cgi/trace` reports the country that Cloudflare places the exit IP in.

The samples replace the account's client ID with `123456` and its username with `USERNAME`.
Every other value is what the API returned, except where `"...": "..."` marks a cut.
The raw captures stay outside the repo.

## Answer

- **Context keys.**
  The job object lists 16 `context` keys for `universal`.
  Ten appear on a docs page for `universal`, and `fulfillment_type` appears only for other sources.
  `hc_policy`, `parse_json_schema`, `parse_json_prompt`, `proxy_location` and `delivery_location` appear on no page the [Parameter catalog](parameter-catalog.md) read.
- **Headers and cookies.**
  `context:headers` and `context:cookies` take effect only with `force_headers` or `force_cookies` set to `true`.
  Without it, the job runs and bills, and the site receives neither.
  A custom `User-Agent` never replaced Oxylabs' own, even with `force_headers`.
- **HTTP method.**
  `http_method: post` with a Base64 `content` sent a POST with that body.
  The API also accepts `options`, and returns 400 for `put` and for a `content` that is not Base64.
- **Redirects and status codes.**
  A job follows redirects by default.
  With `follow_redirects: false`, a redirect faults the job, and `successful_status_codes` cannot list a 3xx code.
  A chain of 11 redirects faults the job.
  A 503 page faults the job unless `successful_status_codes` lists 503, and then it bills.
  A 404 page bills, as [Traffic and Billing][billing] says.
  A page with an empty body faults the job, whatever its status.
- **Sessions.**
  Two jobs with one `session_id` used one exit IP.
  The result's `session_info` expires 25 minutes after the first job and counts 100 jobs, as [Proxy Location][proxy-loc] says, not the 10 minutes on [Any Domain][any-domain].
- **Location.**
  The API accepts any `geo_location` string at submission.
  `France`, `FR`, `United Kingdom` and `Japan` gave exit IPs in those countries, as Cloudflare saw them.
  `Germany` and `DE` gave one exit IP, which Cloudflare places in Lithuania.
  Lowercase `de` and `Atlantis` had no effect, and both jobs billed.
- **Rendering and output types.**
  `render: html` ran the page's JavaScript, and `xhr` and `markdown` work as documented.
  `xhr` without `render` returns 400.
  Without `content_encoding: base64`, a PNG came back as unusable text.
  The job object defaults `content_encoding` to `utf-8`, not the `base64` that [Any Domain][any-domain] gives.
- **User agent types.**
  The API accepts the 7 documented values and the 5 `desktop_*` values that SDK 3.0.0 adds, and returns 400 for any other.
  Each documented value produced an agent for its device.
  The `desktop_*` values produced desktop agents of any browser: 4 of 20 jobs named the browser the value names.
- **Parsing functions.**
  All 20 functions returned the documented output in their documented `_args` shapes, with `parse_status_code: 12000`.
  `_items`, nested scopes and arrays of arrays work as the examples show.
- **Parsing mistakes.**
  At submission, the API checks the structure of the instructions and returns 400 for a mistake in it.
  It does not check `_args`, XPath or regex, so those mistakes bill with `parse_status_code: 12005`, and the field comes back `null`.
  `xpath`, `xpath_one` and `css` accept a bare string in place of the array the docs require.
- **`_on_error`.**
  It takes `suppress`, `warn` or `error`, and the docs name only `suppress`.
  `error` moves the failure to `_errors` and sets `parse_status_code: 12004`, and the result still bills.
- **`parse` without instructions.**
  `parse: true` without instructions returns 400, so it never bills.
  The message names `parser_type`, which no page documents.
  `parser_type: custom` without instructions bills with `parse_status_code: 12003`.
- **Browser instruction checks.**
  The API checks each instruction with pydantic 2.7 and returns 400 with its errors.
  `timeout_s` takes an integer from 1 to 60, and `wait_time_s` an integer from 0 to 60.
  Browser instructions without `render` return 400.
- **After `fetch_resource`.**
  An instruction after `fetch_resource`, or a `filter` that is not a valid regex, returns 500 with an HTML page.
  All 9 such submissions did.
  The docs promise a 400 for a malformed instruction, and say that instructions after `fetch_resource` do not run.
- **Browser instruction effects.**
  `click`, `scroll`, `scroll_to_bottom`, `wait`, `wait_for_element` and `fetch_resource` each changed the result.
  `input` worked in the docs' Etsy example, and showed no effect on a page built for the test.
  `on_error` changed nothing: the next instruction ran after an error with either value.
  Five 60-second waits faulted the job after 325 seconds.
- **Spend.**
  The run spent 81 results, 20 of them rendered.
  Usage Statistics counted 81 and 20 for `universal`.

## Runs

| Run | Time (UTC) | What it sent | Results billed |
| --- | --- | --- | --- |
| Billing checks | 17:45 to 17:51 | `parse: true` without instructions, then a job of wrong `_args` shapes, with Usage Statistics read every 30 seconds | 1 |
| Free probes | 17:53 to 17:56 | 163 submissions, 98 of them fault jobs, with each `user_agent_type` value, malformed instructions and odd values for the other parameters | 1 |
| Parsing functions | 17:54 | One job with all 20 functions | 1 |
| Parsing mistakes | 17:57 to 18:06 | Three jobs: the malformed instructions that the probes accepted, `_on_error: error`, and `parser_type: custom` | 3 |
| Parameter effects | 18:07 | 22 submissions for headers, cookies, method, redirects, status codes, rendering and output types | 12 |
| User agents | 18:07 | One job for each of the 12 values | 12 |
| Sessions and location | 18:07 | Two jobs with one `session_id`, two without, and three with `geo_location` | 7 |
| Browser instructions | 18:07 to 18:12 | 13 rendered jobs | 12 |
| Follow-ups | 18:09 to 18:13 | Cloudflare's view of 9 locations, 3 more jobs for each `desktop_*` value, status pages with a body, `on_error`, `input`, and the docs' Etsy example | 32 |
| Checks | 18:14 to 18:19 | Usage Statistics every 30 seconds, and the "All parameters" example from [Any Domain][any-domain] | 0 |

## Context keys

A `universal` job object lists these `context` keys with their defaults.

| Key | Default | Page that names it for `universal` |
| --- | --- | --- |
| `force_headers` | `false` | [Headers, Cookies, Method][headers] |
| `force_cookies` | `false` | [Headers, Cookies, Method][headers] |
| `hc_policy` | `true` | none |
| `parse_json_schema` | `null` | none |
| `parse_json_prompt` | `null` | none |
| `successful_status_codes` | `[]` | [Any Domain][any-domain] |
| `follow_redirects` | `null` | [Any Domain][any-domain], which gives `true` as the default |
| `cookies` | `[]` | [Any Domain][any-domain] |
| `headers` | `[]` | [Any Domain][any-domain], as an object |
| `session_id` | `null` | [Any Domain][any-domain] |
| `http_method` | `get` | [Any Domain][any-domain] |
| `content` | `null` | [Any Domain][any-domain] |
| `store_id` | `null` | The Home Depot section of [E-Commerce Localization][ecom-loc] |
| `proxy_location` | `null` | none |
| `delivery_location` | `null` | none |
| `fulfillment_type` | `null` | none, and Walmart's section for its non-US domains |

The job object shows `headers` as `[]` by default, and as the object sent otherwise.
Two items with the same key kept only the last.
A `context` object instead of a list, and an item without `value`, returned 400.

Every job object held the same 34 top-level fields, as [Unknown keys](live-parameters.md#unknown-keys) found.
They include `domain`, `limit`, `locale`, `pages`, `start_page` and `subdomain`, which [Any Domain][any-domain] does not list, and the run did not test them.

## Headers, cookies and method

Each job sent a header or cookie that `httpbin.org` echoes.
The result's `_request` holds the headers and cookies that Oxylabs sent, and it agreed with the echo every time.

| Job | `context` | What `httpbin.org` received |
| --- | --- | --- |
| e01 | `headers` with `X-Oxy-Test` and a `User-Agent` | Neither header |
| e02 | the same, with `force_headers: true` | `X-Oxy-Test`, and Oxylabs' own Safari `User-Agent` |
| e03 | `cookies` with `oxy_test` | No cookie |
| e04 | the same, with `force_cookies: true` | `oxy_test` |
| e05 | `http_method: post`, `content: aGVsbG89d29ybGQ=` | A POST with the body `hello=world` |

[Headers, Cookies, Method][headers] names the `force_*` keys.
[Any Domain][any-domain] lists `headers` and `cookies` without them, and its "All parameters" example sends both without them.
That example also sends `parse: true` for `https://example.com` with no instructions, so as written it returns 400:

```json
{"message": "Parsing `https://example.com` url is allowed only with `parser_type` or `parsing_instructions` parameter.", "instance": "/v1/queries", "...": "..."}
```

## Redirects and status codes

| URL | `context` | Job | Result `status_code` | Seconds |
| --- | --- | --- | --- | --- |
| `httpbin.org/redirect/2` | none | `done`, at `httpbin.org/get` | 200 | 1 |
| `httpbin.org/redirect/2` | `follow_redirects: false` | `faulted` | 302 | 2 |
| `httpbin.org/redirect/2` | `follow_redirects: false`, `successful_status_codes: [302]` | 400 | | |
| `httpbin.org/redirect/11` | none | `faulted` | 400 | 2 |
| `mock.httpstatus.io/503`, with a body | none | `faulted` | 613 | 52 |
| `mock.httpstatus.io/503`, with a body | `successful_status_codes: [503]` | `done`, with the body | 503 | 2 |
| `httpbin.org/status/503`, empty | none | `faulted` | 613 | 21 |
| `httpbin.org/status/503`, empty | `successful_status_codes: [503]` | `faulted` | 503 | 2 |
| A `quotes.toscrape.com` 404 page, with a body | none | `done`, with the body | 404 | 1 |
| `httpbin.org/status/404`, empty | none | `faulted` | 404 | 1 |
| `httpbin.org/status/200`, empty | none | `faulted` | 200 | 1 |
| `httpbin.org/anything`, empty | `http_method: options` | `faulted` | 200 | 3 |

Each faulted job's results entry had empty `content`, and none billed.
So an empty body faults a job whatever its status, and `successful_status_codes` returns a page only when it has a body.
The 400 for a 3xx code reads:

```json
{"message": "Context `successful_status_codes` value 302 is not supported (nor other status codes from the same family).", "instance": "/v1/queries", "...": "..."}
```

[Any Domain][any-domain] says redirects are followed "up to a limit of 10 links", and no page says what an 11th does.

## Sessions

Four jobs fetched `httpbin.org/ip`, one after another.

| Job | `session_id` | Exit IP's country, by ipinfo.io | `session_info` in the result |
| --- | --- | --- | --- |
| s1 | `oxy41s1` | US | `{"expires_at": "2026-09-29 18:32:29", "id": "oxy41s1", "remaining": "99"}` |
| s2 | `oxy41s1` | US, the same IP | `{"expires_at": "2026-09-29 18:32:29", "id": "oxy41s1", "remaining": "98"}` |
| s3 | none | US, another IP | `{"expires_at": null, "id": null, "remaining": null}` |
| s4 | none | SG | `{"expires_at": null, "id": null, "remaining": null}` |

s1 was created at 18:07:30, so the session expires 25 minutes after its first job.
`remaining` is a string, and it counts down from 100.
The run did not wait out a session.

## Location

Each job fetched `www.cloudflare.com/cdn-cgi/trace`, whose `loc` line gives the country Cloudflare places the exit IP in.

| `geo_location` | `loc` |
| --- | --- |
| none | `SE` |
| `Germany` | `LT` |
| `DE` | `LT`, from the same IP as `Germany` |
| `de` | `US` |
| `Atlantis` | `US` |
| `France` | `FR` |
| `FR` | `FR`, from the same IP as `France` |
| `United Kingdom` | `GB` |
| `Japan` | `JP` |

Three earlier jobs fetched `httpbin.org/ip`.
With `Germany` and `DE`, the exit IPs came from one block that ipinfo.io and ip-api.com place in Vilnius.
With `Atlantis`, the exit IP was in the US.
Every value above returned 202, and so did `90210`, `Berlin,Germany` and `Bonaire Sint Eustatius and Saba`.
The Home Depot section of [E-Commerce Localization][ecom-loc] gives `universal` a ZIP code, which the country list does not hold.
`ipinfo.io` itself returned 400 with ``Provided `url` is not supported.``, for free.

## Rendering and output types

| Job | Page | Parameters | Result |
| --- | --- | --- | --- |
| e19 | `quotes.toscrape.com/js/` | `render: html` | 10 quotes, in 8 seconds |
| e20 | `quotes.toscrape.com/js/` | none | No quotes: the page builds them with JavaScript |
| e21 | `quotes.toscrape.com/scroll` | `render: html`, `xhr: true` | Type `xhr`, with the two `/api/quotes` requests |
| e22 | `quotes.toscrape.com/` | `markdown: true` | Type `markdown`, and `?type=raw,markdown` returned both |
| e23 | `httpbin.org/image/png` | `content_encoding: base64` | Base64 that decodes to the 8,090-byte PNG |
| e24 | `httpbin.org/image/png` | none | 18,184 characters of text with escaped bytes, which do not decode |

`xhr: true` without `render` returned ``` Parameter `render` with value `` is unsupported when `xhr` is set to `true` ```.
`content_encoding` takes `base64` and `utf-8`, and `gzip` returned 400.

## Values the API checks

These submissions returned 400, so none billed.

| Parameter | Value sent | Message |
| --- | --- | --- |
| `user_agent_type` | `desktop_brave`, `DESKTOP` or `""` | ``Unsupported `user_agent_type` type.`` |
| `content_encoding` | `gzip` | ``Parameter `content_encoding` with `gzip` value is unsupported.`` |
| `render` | `jpeg` | ``Invalid `render` parameter value, possible values: html, png.`` |
| `render` | `true` | ``Invalid type for parameter `render`, supported types: `string`.`` |
| `markdown` | `"yes"` | ``Invalid type for parameter `markdown`, supported types: `boolean`.`` |
| `context` | an object | ``Invalid type for parameter `context`, supported types: `array`.`` |
| `context:http_method` | `put` | `HTTP method put is not supported. Supported methods are: GET, POST, OPTIONS.` |
| `context:content` | `hello world!` | ``Context `content` parameter invalid, should be base64 encoded string.`` |
| `context:successful_status_codes` | `"503"` or `503` | ``Context `successful_status_codes` should be provided as an integer array.`` |
| `context:follow_redirects` | `"false"` | ``Context `follow_redirects` should be provided as a boolean.`` |
| `context:force_headers` | `"true"` | ``Invalid value for `context:force_headers`, supported values: [true, false, null].`` |
| `context:session_id` | `123` | ``Context `session_id` should be provided as string.`` |
| `context:headers` | a list of `key` and `value` objects | ``Context parameter `headers` should be provided as an object with headers names and values, ...`` |
| `context:cookies` | an object | ``Context parameter `cookies` should be provided as an array of objects with `key` and `value` keys, ...`` |

These returned 202: `user_agent_type: null`, which the job object stores as `desktop`, `http_method` of `POST` or `options`, `successful_status_codes` of `[]` or `[808, 909]`, `follow_redirects: null`, a `session_id` of `""` or `abc-123_!@#`, `render: ""`, and a URL of 2,339 characters.

## User agent types

Each job fetched `httpbin.org/headers`, and the table gives the `User-Agent` it received.
The `desktop_*` values ran 3 more times each.

| Value | `User-Agent` received |
| --- | --- |
| `desktop` | Firefox 120 on Linux |
| `mobile` | Edge on an iPhone |
| `mobile_android` | Opera Mobile on a Pixel 6 Pro |
| `mobile_ios` | Edge on an iPhone |
| `tablet` | Firefox on Android 11, marked `Mobile` |
| `tablet_android` | Opera on a Galaxy Tab A |
| `tablet_ios` | Safari on an iPad |
| `desktop_chrome` | Safari 16.6, Safari 16.6, Safari 15.3, Firefox 124 |
| `desktop_edge` | Firefox 124, Safari 17.3.1, Firefox 124, Opera 114 |
| `desktop_firefox` | Firefox 133, Chrome 121, Edge 122, Edge 123 |
| `desktop_opera` | Firefox 123, Edge 122, Edge 122, Edge 126 |
| `desktop_safari` | Safari 17.4, Safari 17.4, Firefox 123, Safari 17.4 |

Jobs without `user_agent_type` received Chrome, Safari, Firefox and Edge agents.
So a `desktop_*` value draws from the same desktop agents as `desktop`.
The `Sec-Ch-Ua` headers often named another browser than the `User-Agent` in the same request.

## Parsing instructions

### All 20 functions

One job sent 33 fields, which cover every function in its documented shape, to the docs' sample HTML.
The result had `parse_status_code: 12000` and no warnings.

| Function | `_args` | Output |
| --- | --- | --- |
| `element_text` | none | `"12  3"` |
| `xpath` | `["//div[@id='socks']//li[@class='description-item']/text()"]` | `["Very", "Nice", "Socks"]` |
| `xpath` | `["boolean(//div[@class='description'])"]` | `true` |
| `xpath` | `["number(//div[@id='socks']/div[@class='price'])"]` | `123.12` |
| `xpath` | two expressions, the first matching nothing | `["123.12"]` |
| `xpath_one` | `["//div[@id='socks']//li/text()"]` | `"Very"` |
| `css` | `["#socks .description-item"]` | three `<li>` elements as strings |
| `css_one` | `["#socks .title"]` | `"<div class=\"title\">Socks</div>"` |
| `amount_from_string` | none | `123.12` |
| `amount_range_from_string` | none | `[123.12, 345.12, 678.12]` |
| `join` | `" \| "` | `"Very \| Nice \| Socks"` |
| `join` | none | `"VeryNiceSocks"` |
| `regex_find_all` | `["\\[(.*)\\]"]` | `["one description", "two description", "three description"]` |
| `regex_search` | `["{(.*)}", 1]` | `"the one i need"` |
| `regex_search` | `["{(.*)}"]` | `"{the one i need}"` |
| `regex_substring` | `["\\{(.*)\\}", "<\\1>"]` | the text with `<the one i need>` |
| `length` | none | `5`, and `[3, 4]` for nested lists |
| `select_nth` | `-1` | `"Socks"` |
| `convert_to_float` | none | `123` |
| `convert_to_int` | none | `124`, and `123` from `123.12` |
| `convert_to_str` | none | `"123.12"` |
| `average` | none | `244.8` |
| `average` | `0` | `245` |
| `max` | none | `456` |
| `min` | none | `100` |
| `product` | none | `12` |

`css` followed by `element_text` returned the text of each element.
`_items` returned a list of three objects, and the same scope without `_items` returned an object of lists, as [Parsing instruction examples][parse-examples] shows.
A scope with its own `_fns` passed its output to the fields inside it.
Two `xpath` calls and `convert_to_int` turned the rows and columns into a 3 by 3 list of integers.
Where the docs show `456.0`, the JSON holds `456`.

### Mistakes the API returns 400 for

| Payload | `errors` or `message` |
| --- | --- |
| An unknown `_fn`, or `XPATH` | ``Function `<name>` is not defined.`` |
| A function entry without `_fn` | `` `_fn` is required` `` |
| `_fns` as an object | `Functions pipeline must be a list.` |
| `_on_error: ignore` | ``Invalid `_on_error` value `ignore`, must be one of suppress, warn, error.`` |
| `_items` as a list, or a field whose value is a string | `Parsing instructions must be an object.` |
| An unknown key in a function entry | `Extra field in pipeline function definition is not allowed: foo.` |
| `{}` | `Empty parsing instructions are not allowed.` |
| A list or a string | ``Parameter `parsing_instructions` should be an object.`` |
| No `parse`, or `parse: false` | ``Parameter `parsing_instructions` can be used just with `parse` parameter set to `true`.`` |
| `parse: true` and no instructions | ``Parsing `<url>` url is allowed only with `parser_type` or `parsing_instructions` parameter.`` |
| `parser_type: bogus` or `universal` | ``Parameter `parser_type` with value `<value>` is not supported for `universal` source.`` |
| An unknown `parser_preset` | ``Provided `parser_preset` does not exist.`` |

A mistake inside the instructions returns an `errors` list with the function, its index and its path:

```json
{
  "instance": "/v1/queries",
  "timestamp": "2026-09-29T17:53:10.417786181Z",
  "trace_id": "6abbfb06-30ca0fb056bad2ee9005873d",
  "errors": [
    {"_fn": "not_a_real_fn", "_fn_idx": 0, "_msg": "Function `not_a_real_fn` is not defined.", "_path": ".t._fns"}
  ]
}
```

### Mistakes the API accepts

Each mistake below returned 202, and two billed jobs ran them on the sample HTML, next to a field that worked.
Both results had `parse_status_code: 12005`, and Usage Statistics counted the first within 30 seconds.

| Field | Output | Warning `_msg` |
| --- | --- | --- |
| `xpath` with a bare string | `["Socks"]` | none |
| `xpath_one` with a bare string | `"Socks"` | none |
| `css` with a bare string | `["<div class=\"title\">Socks</div>"]` | none |
| `regex_search` or `regex_find_all` with a bare string | `null` | ``received arguments of invalid type `str`.`` |
| `select_nth` with `[0]` | `null` | ``received arguments of invalid type `array`.`` |
| `select_nth` with `"1"` | `null` | ``received arguments of invalid type `str`.`` |
| `xpath` with `[1]` | `null` | ``received arguments of invalid type `array`.`` |
| `xpath` with `null` | `null` | ``received arguments of invalid type `not_provided`.`` |
| `xpath` with `[]` | `null` | `XPath expressions did not match any data.` |
| `join` with `[" "]` or `1` | `null` | `Failed to process function.` |
| `average` with `[1]` | `null` | `Failed to process function.` |
| `average` with `1` | `244.8` | none |
| `regex_search` with the group as `"1"` | `null` | `Failed to process function.` |
| `select_nth` with `10`, past the end | `null` | `Failed to process function.` |
| `xpath` with `//[` | `null` | `Failed to process function.` |
| `regex_find_all` with `(` | `null` | `Failed to process function.` |
| `length` or `element_text` with `[1]` | the usual output | none |
| An unknown key, `_foo`, beside `_fns` | the usual output | none |
| `_fns: []` | the whole page | none |
| An XPath that matches nothing | `null` | `XPath expressions did not match any data.` |

`average` takes its `round_precision` as a single value, and [List of parsing functions][functions] gives it no shape.
Each warning also carries `_fn`, `_fn_idx` and `_path`.

### `_on_error`

| `_on_error` on a field whose `convert_to_float` fails | Output | Where the failure appears | `parse_status_code` |
| --- | --- | --- | --- |
| none | `null` | `_warnings` | 12005 |
| `warn` | `null` | `_warnings` | 12005 |
| `suppress` | `null` | nowhere | 12005 |
| `error` | `null` | `_errors` | 12004 |

The `error` job parsed its other field normally, and Usage Statistics counted it:

```json
{
  "_errors": [
    {"_fn": "convert_to_float", "_fn_idx": 1, "_msg": "Failed to process function.", "_path": ".fails_with_error"}
  ],
  "fails_with_error": null,
  "ok": "Socks",
  "parse_status_code": 12004
}
```

### `parse` without instructions

`parse: true` without instructions returned 400 for a page with no dedicated parser, as the table above shows.
The message names `parser_type`, which the Custom Parser pages show only as a result field.
`parser_type: custom` and `parser_type: preset` returned 202 without instructions.
A billed `custom` job returned only `{"parse_status_code": 12003}`, and Usage Statistics counted it.
A job with `parsing_instructions` shows `parser_type: custom` in its job object.

## Browser instructions

### Checks at submission

The API checks each instruction with pydantic 2.7, in lax mode, so `"5"` passes as `5`.
A failed check returns the instruction and pydantic's errors:

```json
{
  "instance": "/v1/queries",
  "timestamp": "2026-09-29T17:53:30.940720451Z",
  "trace_id": "6abbfb1a-9ea545b4f468091d5c31a4b8",
  "errors": {
    "message": "Validation failed.",
    "instruction": {"type": "wait", "wait_time_s": 1, "timeout_s": 0},
    "validation_errors": [
      {"type": "greater_than", "loc": ["timeout_s"], "msg": "Input should be greater than 0", "input": 0, "ctx": {"gt": 0}, "url": "https://errors.pydantic.dev/2.7/v/greater_than"}
    ]
  }
}
```

| Instruction | Status | Error |
| --- | --- | --- |
| Each of the 7 types, as the docs show it | 202 | |
| `type: unsupported-wait`, or `Click` | 400 | ``Unsupported action type `Click`.`` |
| `timeout_s` of `0` or `-1` | 400 | `greater_than`: greater than 0 |
| `timeout_s` of `61` | 400 | `less_than_equal`: 60 or less |
| `timeout_s` of `2.5` | 400 | `int_from_float` |
| `timeout_s` of `1`, `60` or `"5"` | 202 | |
| `wait_time_s` of `-1` | 400 | `greater_than_equal`: 0 or more |
| `wait_time_s` of `61` | 400 | `less_than_equal`: 60 or less |
| `wait_time_s` of `2.5` | 400 | `int_from_float` |
| `wait_time_s` of `0` or `60`, or `wait` without it | 202 | |
| `on_error: bogus` | 400 | `enum`: `'skip'` or `'error'` |
| `selector.type: bogus` | 400 | `enum`: `'xpath'`, `'css'` or `'text'` |
| `click` without `selector`, or with a string | 400 | `missing`, or `model_type` for `SelectorSchema` |
| `input` without `value`, or with `123` | 400 | `missing`, or `string_type` |
| `fetch_resource` without `filter` | 400 | `missing` |
| An unknown key | 400 | `extra_forbidden` |
| `scroll` without `x` and `y`, or with `"0"` and `"100"` | 202 | |
| An object instead of a list | 400 | `Payload is not a list of instructions.` |
| `[]`, 100 waits, or five 60-second waits | 202 | |
| No `render`, or `render: ""` | 400 | ``Parameter `browser_instructions` can only be used with `render` parameters set to `html, png`.`` |
| `render: png` | 202 | |
| `fetch_resource` after another instruction | 202 | |
| Any instruction after `fetch_resource` | 500 | an HTML page |
| `filter` of `(` or `[` | 500 | an HTML page |

The job object stores the instructions as sent, with no defaults filled in.

### A 500 at submission

Four submissions put a `wait` or a `click` after `fetch_resource`, and two sent two `fetch_resource` instructions.
Three sent a `filter` that is not a valid regex.
All 9 returned 500, with no job and no `x-oxylabs-*` headers:

```text
HTTP/1.1 500 Internal Server Error
content-length: 469
content-type: text/html; charset=utf-8

<!DOCTYPE html>
<html lang="en">
   <head>
       <meta charset="utf-8" />
       <title>500 Internal server error</title>
   </head>
   <body>
       <main>
           <h1>500 Ooops something went wrong :( </h1>
           <p>Something went very very wrong with your request</p>
           <p>When reporting this error, please include the following</p>
           <p>+</p>
           <p>trace_id: 6abbfb26-03b147d242295c975eca810a</p>
       </main>
   </body>
</html>
```

### Effects

| Job | Page | Instructions | Result |
| --- | --- | --- | --- |
| b01 | `quotes.toscrape.com/js/` | `click` on `li.next > a` | Page 2 |
| b03 | `quotes.toscrape.com/scroll` | `scroll` by `y: 100000`, waiting 3 seconds | 30 quotes, against 10 on load |
| b04 | `quotes.toscrape.com/scroll` | `scroll_to_bottom` for 10 seconds | 20 quotes |
| b16 | `quotes.toscrape.com/scroll` | `scroll` without `x` or `y`, then `wait` 3 seconds | 10 quotes |
| b06 | `quotes.toscrape.com/js-delayed/`, which adds its quotes after 10 seconds | none | No quotes |
| b05 | the same | `wait` 12 seconds | 10 quotes |
| b07 | the same | `wait_for_element` `div.quote`, up to 15 seconds | 10 quotes |
| b13 | the same | `wait_for_element` `div.quote`, up to 2 seconds | No quotes, and an error |
| b08 | `quotes.toscrape.com/scroll` | `fetch_resource` with `filter: /api/quotes` | The JSON of `/api/quotes?page=1`, with that URL as the result's `url` |
| Etsy | `www.etsy.com` | The docs' example: `input`, `click` and `wait` | The search page for "pizza boxes", with `status_code: 403` |
| b20 | a built page | `input` into a field whose `oninput` handler copies it to the page | The handler's output stayed empty |
| b21 | a built page | `input`, then `click` on a GET form's button | The page did not change |
| b22 | a built page | `input`, then `click` on a POST form's button | The page did not change |
| b02 | `httpbin.org/forms/post` | `input`, then `click` on the form's button | The page did not change |
| b17 | `quotes.toscrape.com/js/` | five `wait` of 60 seconds | `faulted` after 325 seconds, with 613 |

A missing selector gives a warning, and a failed `wait_for_element` gives an error:

| Job | Instructions | Result |
| --- | --- | --- |
| b10 | `click` on `#nope` with `on_error: skip`, then `click` on the next page | Page 2, with a warning |
| b11 | `click` on `#nope`, then `click` on the next page | Page 2, with a warning |
| b18 | `wait_for_element` on `#nope` for 2 seconds, then `click` on the next page | Page 2, with an error |
| b19 | the same, with `on_error: skip` | Page 2, with an error |

The warning reads ``Unable to find selector type `css` with value `#nope` on the page.``, under `browser_instructions_warnings`.
The error reads ``Unexpected error happened while executing `wait_for_element` browser instructions.``, under `browser_instructions_errors`.
So `on_error: error`, the default, did not stop the instructions after an error.

## Result fields

Every `universal` result carried `_request`, `_response` and `session_info` beside the documented fields, as [What the object holds](cloud-storage.md#what-the-object-holds) found.
`_request` holds the headers and cookies Oxylabs sent, and `_response` the headers and cookies the site returned.
None of the 81 results carried `is_render_forced: true`.

## Usage Statistics

The run read `/v2/stats` for 2026-09-29 before its first job, around each billing check, and every 30 seconds from 18:14 to 18:18.
`universal` had no results that day before the run.

| Read | `all_count` | `render_count` |
| --- | --- | --- |
| 17:45, before the run | 0 | 0 |
| 17:46, after the wrong-shape job | 1 | 0 |
| 18:14 to 18:18, eight reads | 81 | 20 |

The reads around the `_on_error: error` and `parser_type` jobs were stale, as [Timing and stale reads](live-api.md#timing-and-stale-reads) found.
Each count rose by one within 2 minutes, and fell back to an older count on some later reads.
The final count matches the 81 jobs that ended `done`, and the 20 of them with `render`.
`geo_location_count` stayed at 0, although 11 billed jobs set `geo_location`.

## Open questions

- **`input`.**
  It worked on Etsy and showed no effect on the built page, and the run cannot say why.
- **Germany.**
  The run cannot say whether Oxylabs places its German exits in Lithuania, or whether Cloudflare and both IP databases misplace them.
- **Undocumented keys.**
  No page explains `hc_policy`, `parse_json_schema`, `parse_json_prompt`, `proxy_location`, `delivery_location`, or the values `parser_type` takes besides `custom` and `preset`.
- **Top-level fields.**
  The run did not test `pages`, `start_page`, `limit`, `domain`, `locale` or `subdomain` on `universal`.
- **Sessions.**
  The run read the 25-minute expiry from `session_info`, and did not test an IP after 10 minutes.

## Sources

### The live API

The run itself is the primary source.
It sent every call from one machine over HTTP/1.1, and it looked up exit IPs with ipinfo.io and ip-api.com from the same machine.

### Oxylabs docs

Read on 2026-09-29:

- [Any Domain][any-domain] lists the `universal` parameters, and its "All parameters" example.
- [JS Rendering & Browser Control][js] gives the 7 instruction types, their ranges, `on_error`, and the validation and error keys.
- [Headers, Cookies, Method][headers] names `force_headers` and `force_cookies`.
- [User Agent Type][uat] lists the 7 values.
- [Proxy Location][proxy-loc] lists the countries and gives a session 25 minutes or 100 requests.
- [E-Commerce Localization][ecom-loc] gives The Home Depot a ZIP code and `context:store_id` through `universal`.
- [List of parsing functions][functions], [Parsing function examples][function-examples] and [Parsing instruction examples][parse-examples] give the functions, their `_args` shapes and `_on_error`.
- [Custom Parser: Getting started][parser-start] says a wrong function name returns 400 and a 12005 result bills.
- [Capturing Network Requests][xhr], [Markdown Output][markdown] and [Download Images][images] describe `xhr`, `markdown` and `content_encoding`.
- [Traffic and Billing][billing] bills `2xx` and `4xx` results.

### Notes

- [Parameter catalog](parameter-catalog.md) lists what the docs say about each parameter.
- [What a live test shows about parameters](live-parameters.md) found the 16 `context` keys and the handling of unknown keys.
- [What a live test shows about the job lifecycle](live-api.md) describes fault jobs and Usage Statistics.

[any-domain]: https://developers.oxylabs.io/api-targets/overview
[js]: https://developers.oxylabs.io/products/web-scraper-api/features/js-rendering-and-browser-control
[headers]: https://developers.oxylabs.io/products/web-scraper-api/features/http-context-and-job-management/headers-cookies-method
[uat]: https://developers.oxylabs.io/products/web-scraper-api/features/http-context-and-job-management/user-agent-type
[proxy-loc]: https://developers.oxylabs.io/products/web-scraper-api/features/localization/proxy-location
[ecom-loc]: https://developers.oxylabs.io/products/web-scraper-api/features/localization/e-commerce-localization
[functions]: https://developers.oxylabs.io/products/web-scraper-api/features/custom-parser/writing-instructions-manually/list-of-functions
[function-examples]: https://developers.oxylabs.io/products/web-scraper-api/features/custom-parser/writing-instructions-manually/list-of-functions/function-examples
[parse-examples]: https://developers.oxylabs.io/products/web-scraper-api/features/custom-parser/writing-instructions-manually/parsing-instruction-examples
[parser-start]: https://developers.oxylabs.io/products/web-scraper-api/features/custom-parser/getting-started
[xhr]: https://developers.oxylabs.io/products/web-scraper-api/features/result-processing-and-storage/output-types/capturing-network-requests-fetch-xhr
[markdown]: https://developers.oxylabs.io/products/web-scraper-api/features/result-processing-and-storage/output-types/markdown-output
[images]: https://developers.oxylabs.io/products/web-scraper-api/features/result-processing-and-storage/output-types/download-images
[billing]: https://developers.oxylabs.io/products/web-scraper-api/usage-and-billing/billing-information
