# What a live test shows about Cloud Storage

This note records what a small billed run against the live Oxylabs API showed about Cloud Storage.
It answers [Does Cloud Storage work on the batch endpoint?](https://github.com/ozanozbeker/oxyscraper/issues/10).
Its questions are the Cloud Storage questions in [What the docs state about the job lifecycle](job-lifecycle.md#cloud-storage).
The run took place on 2026-09-25 from 14:26 to 14:36 UTC, on an account with the Starter plan.
It spent 9 results, 2 of them rendered.

Every job uploaded to the private GCS bucket from [Provision a test bucket Oxylabs can write to](https://github.com/ozanozbeker/oxyscraper/issues/7).
Oxylabs' service account holds only `storage.objects.create` on it.
The billed jobs used `universal` on Oxylabs' practice site, `https://sandbox.oxylabs.io/products`, and `amazon_search`.
Free jobs, called fault jobs below, used unregistered `.com` names, as [Fault jobs](live-api.md#fault-jobs) describes.
All 17 fault jobs ended `faulted`, and none billed.

The samples replace the bucket name with `BUCKET`, the run's folder in the bucket with `RUN`, the client ID with `123456` and the API username with `USERNAME`.
`"...": "..."` and `...` mark cuts.
The raw captures stay outside the repo, and the objects stay in the bucket under `research/cloud-storage/`.

## Answer

- **Batch.**
  `storage_type` and `storage_url` work on `/v1/queries/batch`.
  Each job in a batch resolves its own `storage_url` at submission and uploads its own object.
- **Results endpoint.**
  `/results` still returns an uploaded job.
  Each result's `content` matched the one in the object.
- **Statuses.**
  An upload adds one entry to `statuses`, such as `{"event": "GCS_STORAGE_UPLOAD", "code": 13000, "message": "Upload Successful"}`.
  The entry appears after the job turns `done` or `faulted`.
  13 of 25 jobs showed a final status with an empty `statuses` first.
  `updated_at` does not change when the entry appears.
  A job object of the payload alone has no `statuses`, even after a successful upload ([Probes on 2026-10-02](#probes-on-2026-10-02)).
- **Failures.**
  A bucket that does not exist gives 13102.
  An object name that already exists gives 10001 about 20 seconds after the job finishes, and the existing object stays unchanged.
  The run could not produce 13103.
- **Faulted jobs.**
  Oxylabs uploads a faulted job's result too, and records 13000.
  The object holds one result with `status_code: 613`.
- **Object names.**
  A `storage_url` that ends in `.{{ extension }}` names the object.
  Any other `storage_url` names a folder, and the API appends `/{{ job_id }}.{{ extension }}`.
  Only `{{ job_id }}`, `{{ source }}`, `{{ query }}` and `{{ extension }}` resolve.
  Other variables stay in the name as literal text, including `{{ created_at }}`, which the docs give as an example.
- **Object contents.**
  Every object is a JSON document with `results` and `job`.
  `{{ extension }}` resolves to `json` for all five output types, including `png`.
  A job with `pages: 2` uploads one object with both pages.
  The object's fields differ from `/results` in small ways, and `job.client` holds the API username.
- **Realtime.**
  Realtime rejects `storage_url` with 400.

## Runs

| Run | Time (UTC) | What it sent | Results billed |
| --- | --- | --- | --- |
| Probes | 14:26 to 14:27 | 8 fault jobs with different `storage_url` values, a 2-value fault batch with `{{ url }}` in the name, and one Realtime submission | 0 |
| Variables | 14:30 to 14:31 | 5 fault jobs: template variables, an existing object name and a missing bucket | 0 |
| Folders | 14:32 | 2 fault jobs whose `storage_url` ends in `.json` | 0 |
| Uploads | 14:33 to 14:34 | A 2-value `universal` batch, then one job each for `parse: true` with `pages: 2`, `render: png`, `markdown: true` and `xhr: true` | 7 |
| Query batch | 14:35 | A 2-value `amazon_search` batch with `{{ query }}` in the name | 2 |

After each run's submissions, the run polled every job's status and listed the bucket every second, until every job had a `statuses` entry.
It polled each job every 1.3 to 1.8 seconds, so the timings below have a resolution of about 2 seconds.
Usage Statistics at 14:36 counted 5 `universal` results, 2 of them rendered, and 4 `amazon_search` results for the day.
These are exactly the billed jobs.

## Uploads on a batch

A batch with storage parameters returned 202 with one job object per value, as a batch without them does.
Each job carries its own resolved `storage_url`.
This is the Uploads run's batch, cut to the storage fields:

```json
{
  "queries": [
    {
      "id": "7509258822901324802",
      "status": "pending",
      "source": "universal",
      "url": "https://sandbox.oxylabs.io/products",
      "storage_type": "gcs",
      "storage_url": "BUCKET/RUN/billed/batch/7509258822901324802.json",
      "statuses": [],
      "...": "..."
    },
    {
      "id": "7509258822901325825",
      "status": "pending",
      "source": "universal",
      "url": "https://sandbox.oxylabs.io/products?page=2",
      "storage_type": "gcs",
      "storage_url": "BUCKET/RUN/billed/batch/7509258822901325825.json",
      "statuses": [],
      "...": "..."
    }
  ]
}
```

Both jobs uploaded, and each object's path matched its job's `storage_url`.
The same held for all 22 uploads that recorded 13000.

## The `statuses` entry

### Success

A successful upload added this entry, for `done` and `faulted` jobs alike:

```json
"statuses": [
  {
    "event": "GCS_STORAGE_UPLOAD",
    "code": 13000,
    "message": "Upload Successful"
  }
]
```

No job got more than one entry.

### Failures

| Case | `code` | `message` | Seconds after the final status |
| --- | --- | --- | --- |
| The bucket does not exist | 13102 | `No such path` | 1.3 |
| The object name already exists | 10001 | `Unexpected Exception` | 22.0 |
| An earlier job in the same batch wrote the name | 10001 | `Unexpected Exception` | 20.4 |

The missing bucket had a random name, and the GCS JSON API returned 404 for it before the job.
The run wrote the existing object with its own credentials before the job.
After the job, the object's generation and content were unchanged.
GCS requires `storage.objects.delete` to overwrite an object ([GCS IAM permissions][gcs-iam]), and Oxylabs' role lacks it.
Oxylabs reported the failure as 10001, not as 13103 Access Denied.

The `message` values differ from the Status column of [Response Codes][response-codes], which gives `Upload Success` and `No Such Path`.
So a client matches on `code`, not on `message`.

### Timing

The entry appears after the job's final status.
In 13 of 25 jobs, the first poll that showed `done` or `faulted` still showed an empty `statuses`.
A 13000 entry followed 0.8 to 2.6 seconds later, a 13102 after 1.3 seconds, and a 10001 after about 20 seconds.
Each uploaded object's `last_modified` came before the poll that first showed its 13000, though the run's clock and GCS's clock can differ by a fraction of a second.
`updated_at` kept its value when the entry appeared.
The `markdown` job shows the order:

| Time (UTC) | What the run saw |
| --- | --- |
| 14:33:42.676 | `status: done`, empty `statuses`, `updated_at` 14:33:42 |
| 14:33:42.900 | The object's `last_modified` |
| 14:33:44.120 | `status: done`, the 13000 entry, `updated_at` 14:33:42 |

So a final status does not mean the upload has finished, and `updated_at` does not show that `statuses` changed.

## Faulted jobs

14 of the 17 fault jobs uploaded an object and recorded 13000.
The other 3 are the failures above.
Each object holds one result with `status_code: 613` and `content: null`, where `/results` returns `content: ""`.
Usage Statistics counted none of the fault jobs.
So an object in the bucket does not mean the scrape succeeded.
The object's `job.status` and each result's `status_code` tell.

## Object names

The API resolves `storage_url` at submission and returns the resolved path in the job's `storage_url`, as [File name templating][file-name-templating] says.
Each object's path matched it.
In this table, `P` stands for a fault job's folder, such as `BUCKET/RUN/probe`:

| `storage_url` sent | Object path |
| --- | --- |
| `BUCKET` | `BUCKET/<job_id>.json` |
| `P/no-slash` | `P/no-slash/<job_id>.json` |
| `P/slash/` | `P/slash/<job_id>.json` |
| `gs://P/gs-scheme/` | `gs://P/gs-scheme/<job_id>.json` |
| `P/plain/name.json` | `P/plain/name.json/<job_id>.json` |
| `P/dot/{{ job_id }}.json` | `P/dot/<job_id>.json/<job_id>.json` |
| `P/noext/{{ job_id }}` | `P/noext/<job_id>/<job_id>.json` |
| `P/tpl-dir/{{ source }}/` | `P/tpl-dir/universal/<job_id>.json` |
| `P/template/{{ source }}_{{ job_id }}.{{ extension }}` | `P/template/universal_<job_id>.json` |
| `P/created-at/{{ created_at }}.{{ extension }}` | `P/created-at/{{ created_at }}.json` |
| `P/unknown-var/{{ nope }}.{{ extension }}` | `P/unknown-var/{{ nope }}.json` |
| `P/broken/{{ source` | `P/broken/{{ source/<job_id>.json` |

Every `storage_url` that ended in `.{{ extension }}` named the object.
Every other one named a folder, even `name.json` and `{{ job_id }}`.
The `gs://` prefix is optional, and the job's `storage_url` keeps it.

### Variables

One fault job set `client_notes: notes1` and `geo_location: Germany`, and put ten variables in one name:

```text
sent:     P/vars/q={{ query }}_n={{ client_notes }}_g={{ geo_location }}_ua={{ user_agent_type }}_d={{ domain }}_s={{ status }}_id={{ id }}_u={{ url }}_p={{ pages }}_st={{ storage_type }}_src={{source}}.{{ extension }}
resolved: P/vars/q=_n={{ client_notes }}_g={{ geo_location }}_ua={{ user_agent_type }}_d={{ domain }}_s={{ status }}_id={{ id }}_u={{ url }}_p={{ pages }}_st={{ storage_type }}_src={{source}}.json
```

Only `{{ query }}` resolved, to an empty string, because a `universal` job has no query.
`{{source}}` without spaces stayed literal, while `{{ source }}` resolved in every other name.
Across the run, `{{ job_id }}`, `{{ source }}`, `{{ query }}` and `{{ extension }}` resolved, and nothing else did.
[File name templating][file-name-templating] says any input parameter or `job` field works, and names `created_at` as an example.

`{{ query }}` keeps spaces.
For `amazon_search` with `query: usb c cable`, `BUCKET/RUN/billed/parsed/{{ source }}_{{ query }}_{{ job_id }}.{{ extension }}` resolved to `BUCKET/RUN/billed/parsed/amazon_search_usb c cable_7509258823543070721.json`.

### Names in a batch

Each job in a batch resolves the template with its own values.
In the Query batch, `BUCKET/RUN/billed/query-batch/{{ query }}.{{ extension }}` resolved to `usb c cable.json` for one job and `hdmi cable.json` for the other, and both uploaded.
In the Probes run's `url` batch, `{{ url }}` stayed literal, so both jobs got the name `{{ url }}.json`.
The job that finished first uploaded.
The other recorded 10001, 20 seconds after it finished.
So a batch's name needs `{{ job_id }}`, or `{{ query }}` with distinct queries, or every job after the first fails.

## What the object holds

Every object is a JSON document with `Content-Type: application/json`.
Like `/results`, it holds `results` and `job`, and each result's `content` matched the one `/results` returned.
Other fields differ:

| Field | Object | `/results` |
| --- | --- | --- |
| `results[].id` | A numeric ID | Absent |
| `results[].type` and `is_render_forced` | Absent | Present |
| `results[].parser_type` and `parser_preset`, for `amazon_search` | Absent | Present |
| `results[]._request`, `_response` and `session_info`, for `amazon_search` | `null` | Absent |
| `results[].created_at` | When the result was created | The job's `created_at` |
| `results[].content`, for a faulted job | `null` | `""` |
| `job.parse` | `0` or `1` | `false` or `true` |
| `job.updated_at` | The same as `created_at` | The finish time |
| `job.statuses`, `_links` and `aggregate_name` | Absent | Present |
| `job.client` | Present | Absent |

`job.client` holds the client ID, the API username and one rate-limit row.
The row is the render limit for `universal`, 13 per second, and its `label` holds the UUID from the `x-ratelimit-*` header names.
So anyone who can read the bucket can read the API username.
This is the object for the first job of the Uploads run's batch:

```json
{
  "results": [
    {
      "id": 9692815808,
      "job_id": "7509258822901324802",
      "page": 1,
      "status_code": 200,
      "content": "<!DOCTYPE html><html lang=\"en\"><head>...",
      "url": "https://sandbox.oxylabs.io/products",
      "created_at": "2026-09-25 14:33:41",
      "updated_at": "2026-09-25 14:33:41",
      "_request": {"cookies": [], "headers": {"...": "..."}},
      "_response": {"cookies": [], "headers": {"...": "..."}},
      "session_info": {"expires_at": null, "id": null, "remaining": null}
    }
  ],
  "job": {
    "id": "7509258822901324802",
    "client_id": 123456,
    "status": "done",
    "source": "universal",
    "query": "",
    "url": "https://sandbox.oxylabs.io/products",
    "parse": 0,
    "storage_url": "BUCKET/RUN/billed/batch/7509258822901324802.json",
    "storage_type": "gcs",
    "created_at": "2026-09-25 14:33:38",
    "updated_at": "2026-09-25 14:33:38",
    "client": {
      "id": 123456,
      "name": "USERNAME",
      "rate_limits": [
        {
          "job_source": "universal",
          "measurement": "sec",
          "limit": 13,
          "limit_interval": 1,
          "label": "total_render_requests_00000000-0000-0000-0000-000000000000",
          "...": "..."
        }
      ]
    },
    "client_notes": null,
    "...": "..."
  }
}
```

## Output types

| Job | Output type | `{{ extension }}` | Results in the object | `content` |
| --- | --- | --- | --- | --- |
| `universal` | `raw` | `json` | 1 | HTML as a string |
| `amazon_search`, `parse: true`, `pages: 2` | `parsed` | `json` | 2 | A JSON object per page |
| `universal`, `render: png` | `png` | `json` | 1 | Base64 text |
| `universal`, `markdown: true` | `markdown` | `json` | 1 | Markdown as a string |
| `universal`, `render: html`, `xhr: true` | `xhr` | `json` | 1 | A list |

Each job uploaded one object.
The object held the job's default output only, as `/results` returns it without `?type=`.
No page of the docs says that `{{ extension }}` is always `json`.

## The results endpoint after an upload

`/results` returned 200 for every uploaded job, with the same `content` as the object.
The run fetched them within a minute of the upload, so this says nothing about retention.

## Realtime

Realtime rejects the storage parameters at submission and creates no job:

```text
HTTP/1.1 400 Bad Request
content-type: application/json
content-length: 185
```

```json
{
  "message": "Parameter `storage_url` cannot be used with realtime.",
  "instance": "/v1/queries",
  "timestamp": "2026-09-25T14:27:01.266772079Z",
  "trace_id": "6ab684b5-bf037680ebb0d349cae8ff05"
}
```

This matches [Cloud Storage][cloud-storage], which says Cloud Storage works only with Push-Pull.

## Probes on 2026-09-29

Two probes for [How does oxy use Oxylabs Cloud Storage?](https://github.com/ozanozbeker/oxyscraper/issues/17) sent only GETs and fault jobs, so they billed nothing.

### The entry after four days

At 13:39 UTC, the status endpoint returned the 13000 entry for both jobs of the Uploads run's batch, 95 hours after they finished.
Results expire 4 to 78 hours after a job finishes ([Retention](live-api.md#retention)), so a client can read the entry after the results expire.

### An endpoint that does not resolve

At 13:46 UTC, two fault jobs set `storage_type` to `s3_compatible` and `tos`.
Each sent a `storage_url` of the form `https://FAKEKEYID:FAKESECRET@<name>.com/bucket/folder`, where `<name>` is an unregistered name.

- Both submissions returned 202.
- The job's `storage_url` hid the credentials, as `https://redacted:redacted@<name>.com/bucket/folder/<job_id>.json`.
  The status endpoint returned the same value.
- The API appended `/<job_id>.json` to the folder, as it does for `gcs`.
- Both jobs ended `faulted` within 15 seconds.
  At 14:01 UTC, 15 minutes later, `statuses` was still empty for both.
  It was still empty at 14:34 UTC, 48 minutes after the jobs finished.

So an upload to an endpoint that does not resolve recorded no code within 48 minutes, and a client that waits for the entry needs a limit.

## Probes on 2026-10-01

A probe for [Redact every credential in a storage_url](https://github.com/ozanozbeker/oxyscraper/issues/107) sent 13 submissions with `storage_type` set to `s3_compatible` or `tos`, and a `storage_url` of the form `https://<userinfo>@<name>.com/bucket/folder`.
11 were `universal` fault jobs, and 2 were `walmart_product` jobs.
It billed 1 result, for the one `walmart_product` job that the API took.

### Secrets that are not URL-safe

| Userinfo sent | Status | Body, or the job's `storage_url` |
| --- | --- | --- |
| `FAKEKEYID:FAKE/SECRET`, `FAKEKEYID:FAKE?SECRET`, `FAKEKEYID:FAKE#SECRET` or `FAKEKEYID:F/A?K#E@SECRET` | 400 | ``Parameter `storage_url` must be a valid url.`` |
| `FAKEKEYID:FAKE@SECRET`, `FAKEKEYID:FAKE:SECRET` or `FAKEKEYID:F%2FA%3FK%23E%40SECRET` | 202 | `https://redacted:redacted@<name>.com/bucket/folder/<job_id>.json` |
| `FAKETOKEN`, or none | 400 | ``Parameter `storage_url` must contain a valid user info.`` |

- `tos` returned the same 400s as `s3_compatible` for `/`, for `FAKETOKEN` and for no userinfo.
- A raw `/`, `?` or `#` ends the host, so the rest of the secret reads as a port.
  A raw `@` stays in the userinfo, which runs to the last `@`.
- No upload ran, so the probe could not see whether the API decodes a percent-encoded secret before it signs the upload.

### A source that returns the payload alone

`walmart_product` returns the payload alone ([The short job object](live-job-objects.md#the-short-job-object)).
Its job object held the resolved and redacted `storage_url`, `https://redacted:redacted@<name>.com/bucket/folder/<job_id>.json`, not the value sent.
The job ended `done` within 4 seconds, and 7 minutes later its object still had no `statuses` key.
An endpoint that does not resolve also leaves `statuses` empty on a full job object, so this does not show whether a successful upload adds the key.
[Probes on 2026-10-02](#probes-on-2026-10-02) shows that a successful upload adds no key either.

## Probes on 2026-10-02

A probe for [Match the fake to the API before 0.1.0](https://github.com/ozanozbeker/oxyscraper/issues/105) sent one `walmart_product` job with `storage_type: gcs` and a folder in the run's bucket.
It billed 1 result.

The job object held the resolved `storage_url`, with `<job_id>.json` appended.
The job ended `done` within 4 seconds.
Oxylabs wrote a 632,294-byte object to the folder, with a `last_modified` 2 seconds after the job's `updated_at`.
The run polled the status endpoint every 2 seconds for 300 seconds after that.
Every job object held the same 9 keys: `_links`, `created_at`, `id`, `product_id`, `source`, `status`, `storage_type`, `storage_url` and `updated_at`.
So a job object of the payload alone has no `statuses`, and it shows no upload's outcome.

## Open questions

- **13103.**
  Access Denied needs a bucket that exists and grants Oxylabs nothing.
  Every such bucket the run could reach belongs to someone else, so the run did not try.
  A second bucket without the grant, or removing the grant from this bucket for one job, would settle it.
- **13001.**
  No case in the run produced Upload Failed.
- **Other storage types.**
  The account has no S3 bucket.
  The `event` name for S3, and whether S3 overwrites an existing name, stay open.
  So does whether a successful `s3`, `tos` or `s3_compatible` upload records an entry at all.
- **Characters in a name.**
  The run did not test a `query` with `/` or other characters that change a path.

## Sources

### The live API

The run itself is the primary source.
It sent every call from one machine over HTTP/1.1 with httpx 0.28.1, and read the bucket with obstore 0.11.1.

### Oxylabs docs

- [Cloud Storage][cloud-storage] lists the storage types and the `job_ID.json` name, and says Cloud Storage works only with Push-Pull.
- [File name templating][file-name-templating] gives the default name, the template variables and the resolved `storage_url`.
- [Response Codes][response-codes] lists the upload codes and says a failed upload leaves the job `done`.

### Google Cloud docs

- [GCS IAM permissions][gcs-iam] says `objects.insert` needs `storage.objects.delete` when it overwrites an object.

### Notes

- [What the docs state about the job lifecycle](job-lifecycle.md#cloud-storage) lists the questions this run tested.
- [What a live test shows about the job lifecycle](live-api.md#fault-jobs) describes the fault jobs.

[cloud-storage]: https://developers.oxylabs.io/products/web-scraper-api/features/result-processing-and-storage/cloud-storage
[file-name-templating]: https://developers.oxylabs.io/products/web-scraper-api/features/result-processing-and-storage/cloud-storage/file-name-templating
[response-codes]: https://developers.oxylabs.io/products/web-scraper-api/response-codes
[gcs-iam]: https://cloud.google.com/storage/docs/access-control/iam-json
