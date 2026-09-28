# How obstore and fsspec compare for oxy's cloud writer

This note compares obstore and fsspec as the library behind oxy's cloud writer, for S3, GCS and Azure.
It answers [#5](https://github.com/ozanozbeker/oxyscraper/issues/5), and [#16](https://github.com/ozanozbeker/oxyscraper/issues/16) makes the decision.
It reads obstore 0.11.1, fsspec 2026.9.0, s3fs 2026.9.0, gcsfs 2026.8.1, adlfs 2026.8.0 and Polars 1.44.2, as published on 2026-09-24.
The measurements ran that day on Python 3.11.15 and macOS 26.6 (arm64), in throwaway uv environments outside the repo.

## Answer

obstore is one binary package with one API for S3, GCS, Azure and local disk.
Every obstore `put` is atomic, local disk included, and obstore takes the same config keys and environment variables as Polars' native cloud I/O.
The fsspec stack needs a package per cloud, writes local files in place, and ships no type information.
Its cloud backends get credentials from each cloud's SDK, as Polars does when those SDKs are installed, but their option names differ from Polars'.

- **Packages and weight.**
  Each obstore wheel is 4.6 to 5.8 MB and covers S3, GCS, Azure, HTTP, local disk and memory ([PyPI][pypi-obstore]).
  Its only dependency is `typing-extensions`, below Python 3.13 ([`pyproject.toml`][obs-pyproject]).
  For the three clouds, fsspec needs s3fs, gcsfs and adlfs.
  Installed together, those add 55 distributions and 103.2 MB, where obstore adds 2 distributions and 12.2 MB (measured).
- **Async.**
  Both libraries run natively on asyncio, and neither runs its async API under trio (measured).
  In obstore, sync calls release the GIL and block on a tokio runtime ([performance][obs-perf], [`put.rs`][obs-put-rs-sync]).
  In fsspec's cloud backends, sync calls all run on one `fsspecIO` thread ([`asyn.py`][fs-asyn-loop]).
  Async use of fsspec needs `asynchronous=True`, an explicit session and the underscore-prefixed methods, and its local filesystem has no async methods ([async docs][fs-async-doc]).
- **Atomic writes.**
  On S3, GCS and Azure, a reader never gets a partly written object ([S3][aws-consistency], [GCS][gcs-consistency], [Azure][az-concurrency]).
  In obstore, `put` is atomic on every store ([`_put.pyi`][obs-put-pyi]).
  Its `LocalStore` writes a staging file beside the target, then renames it ([`local.rs`][os-local-put]).
  In fsspec, the local filesystem writes the target file in place ([`local.py`][fs-local-open]).
  Its transaction mode stages in the system temp directory and then calls `shutil.move`, which copies when that directory is on another filesystem ([`local.py`][fs-local-commit]).
- **Create-only writes.**
  In obstore, `mode="create"` sends a create-only precondition to S3, GCS and Azure, and hard-links on local disk ([S3][os-s3-put], [GCS][os-gcs-put], [Azure][os-azure-put], [local][os-local-put]).
  In fsspec, `mode="create"` differs by backend.
  The s3fs backend sends `If-None-Match: *`, and its docstring says this is known to work only on AWS S3 ([`core.py`][s3-pipe]).
  The gcsfs backend sends `ifGenerationMatch=0`, and its docstring marks the mode as experimental ([`core.py`][gcs-class]).
  The adlfs backend turns it into `overwrite=False` ([`spec.py`][adl-pipe]).
  The local filesystem checks `exists` and then writes, and fsspec's own comment calls that non-atomic ([`spec.py`][fs-pipe]).
- **Uploads and retries at oxy's file sizes.**
  Each library sends one request for a file of tens to hundreds of KB.
  Multipart starts above 5 MiB in obstore and above 64 MiB in adlfs, and at 100 MiB in s3fs and 50 MiB in gcsfs.
  By default, obstore retries up to 10 times within 3 minutes ([`_retry.pyi`][obs-retry-pyi]).
  The s3fs backend makes up to 5 attempts, and botocore makes up to 5 attempts inside each of them ([`core.py`][s3-wrapper], [botocore][bc-retry]).
  The gcsfs backend makes up to 6 attempts ([`retry.py`][gcs-retry]).
  The adlfs backend uses the Azure SDK's policy of 3 retries, starting at 15 seconds ([azure-storage-blob][az-retry]).
- **Settings shared with Polars.**
  Both obstore and Polars build stores with the Rust `object_store` crate, on its 0.14 line ([obstore `Cargo.lock`][obs-lock], [Polars `Cargo.toml`][pl-cargo]).
  Both read `AWS_*`, `GOOGLE_*` and `AZURE_*` variables through that crate's `from_env` builders ([obstore][obs-env-aws], [Polars][pl-build-aws]).
  Both parse config keys with that crate's key enums, so one dict of credential, region and endpoint keys serves as obstore's `config` and as Polars' `storage_options` ([obstore][obs-key-parse], [Polars][pl-parse]).
  Polars' retry keys, such as `max_retries`, make obstore raise `UnknownConfigurationKeyError` (measured).
- **Where the shared settings stop.**
  When boto3, google-auth or azure-identity is installed and `storage_options` holds no credential keys, Polars' default `credential_provider` gets credentials from that SDK's default chain ([`_builder.py`][pl-auto]).
  The native obstore chain reads no `~/.aws` files or profiles, uses the Azure CLI only with `use_azure_cli=True`, and needs the region of any S3 bucket outside `us-east-1` ([auth docs][obs-auth-doc], [troubleshooting][obs-region-doc]).
  Optional obstore credential providers wrap the same three SDKs ([auth docs][obs-auth-providers]).
  The fsspec backends use those SDK chains directly, but take different option names from Polars' `storage_options` ([Polars `read_csv`][pl-csv]).
- **Typing and maintenance.**
  The obstore wheel ships `py.typed` and 21 stub files, and pyrefly's strict preset resolves its calls to concrete types (measured).
  None of fsspec, s3fs, gcsfs and adlfs ships `py.typed` or has a stub package, so pyrefly types their values as `Unknown`, and mypy's strict mode reports `import-untyped` (measured).
  Seven of obstore's nine minor releases from 0.3.0 to 0.11.0 list breaking changes ([changelog][obs-changelog]).
  One maintainer wrote 80 of obstore's 101 non-bot commits in the last 12 months ([commits][gh-obstore]).

| | obstore 0.11.1 | fsspec 2026.9.0 with s3fs, gcsfs and adlfs |
| --- | --- | --- |
| Packages for S3, GCS, Azure and local | `obstore` | `fsspec`, `s3fs`, `gcsfs`, `adlfs` |
| Installed, all three clouds | 2 distributions, 12.2 MB | 55 distributions, 103.2 MB |
| Wheels | Binary, no Windows ARM64 | Pure Python, with compiled dependencies |
| Async | Native, asyncio only | Native in the cloud backends, asyncio only; local is sync |
| Sync calls | Release the GIL | Cloud backends run them on one `fsspecIO` thread |
| Local write | Staging file, then rename | In place |
| `mode="create"` | Precondition on every cloud, hard link locally | Differs per backend, check-then-write locally |
| Single-request limit | 5 MiB | 100 MiB (s3fs), 50 MiB (gcsfs), 64 MiB (adlfs) |
| Default retries | 10 within 3 minutes | 5 × botocore's 5 (s3fs), 6 (gcsfs), 3 (adlfs) |
| Default connection limit | None | 10 (s3fs), 100 (gcsfs) |
| Default credential sources | `object_store` chain, no `~/.aws` files | botocore, google-auth, azure-identity |
| Keys shared with Polars `storage_options` | Yes | No |
| Type information | `py.typed`, 21 stub files | None |
| Releases in the last 12 months | 10, on a 0.x line | 9 for fsspec, on calendar versions |

## Backends and packages

obstore has six stores: `S3Store`, `GCSStore`, `AzureStore`, `HTTPStore`, `LocalStore` and `MemoryStore`.
`obstore.store.from_url` returns the store that matches the URL scheme: `s3://`, `gs://`, `az://` or `abfs://`, `file://`, `memory://` and `https://` ([`__init__.pyi`][obs-store-pyi]).
The optional credential providers in `obstore.auth` import boto3, google-auth or azure-identity, and nothing else in obstore needs those packages ([auth docs][obs-auth-providers]).

fsspec holds the local, memory and HTTP filesystems itself.
Its registry maps `s3://` and `s3a://` to s3fs, `gs://` and `gcs://` to gcsfs, and `abfs://` and `az://` to adlfs ([`registry.py`][fs-registry]).
It imports a backend on first use and raises `ImportError` with an install hint when the package is missing.

The measured installs, each into an empty Python 3.11 environment:

| Install | Distributions | Size on disk | Largest package |
| --- | --- | --- | --- |
| `obstore` | 2 | 12.2 MB | obstore's extension module, 11.4 MB |
| `s3fs` | 20 | 32.0 MB | botocore, 24.8 MB |
| `gcsfs` | 39 | 71.0 MB | grpcio, 38.8 MB |
| `adlfs` | 26 | 25.9 MB | cryptography, 12.0 MB |
| `s3fs`, `gcsfs` and `adlfs` | 55 | 103.2 MB | grpcio, 38.8 MB |
| `obstore` and `boto3` | 9 | 39.7 MB | botocore, 24.6 MB |
| `obstore`, `google-auth` and `requests` | 13 | 30.4 MB | cryptography, 12.0 MB |
| `obstore` and `azure-identity` | 15 | 30.2 MB | cryptography, 12.0 MB |

gcsfs gets grpcio through `google-cloud-storage-control`, which gcsfs 2026.8.1 requires ([PyPI][pypi-gcsfs]).

obstore 0.11.1 publishes 51 wheels and an sdist ([PyPI][pypi-obstore]).
The wheels cover CPython 3.10, an abi3 build for CPython 3.11 and later, free-threaded CPython 3.14 and PyPy 3.11.
The platforms are macOS on x86_64 and arm64, manylinux and musllinux on x86_64, aarch64, armv7l and i686, manylinux on ppc64le and s390x, and Windows on x86_64.
No Windows ARM64 wheel exists, and the sdist builds with maturin, which needs a Rust toolchain ([`pyproject.toml`][obs-pyproject]).

fsspec, s3fs, gcsfs and adlfs each publish one pure-Python wheel ([fsspec][pypi-fsspec], [s3fs][pypi-s3fs], [gcsfs][pypi-gcsfs], [adlfs][pypi-adlfs]).
Their compiled code comes from dependencies such as aiohttp, grpcio and cryptography.

Two version constraints in the s3fs chain are narrow.
The s3fs 2026.9.0 release requires `fsspec>=2026.9.0,<2026.9.1`, so each s3fs release needs the fsspec release with the same version ([PyPI][pypi-s3fs]).
Its dependency aiobotocore 3.9.1 requires `botocore>=1.43.66,<1.43.76`, while botocore itself is at 1.43.101 ([aiobotocore][pypi-aiobotocore], [botocore][pypi-botocore]).
Resolving `boto3==1.43.101` with `s3fs==2026.9.0` fails in uv, and an unpinned `boto3` beside s3fs resolves to 1.43.75 (measured; [boto3][pypi-boto3]).
By contrast, gcsfs requires `fsspec>=2026.7.0` and adlfs requires `fsspec>=2023.12.0`, with no upper bound ([gcsfs][pypi-gcsfs], [adlfs][pypi-adlfs]).

## Async

### Async in obstore

Every obstore operation has an async form, such as `put_async` beside `put` ([`_put.pyi`][obs-put-pyi]).
The async forms return asyncio awaitables through pyo3-async-runtimes, and the requests run on a tokio runtime ([`Cargo.toml`][obs-cargo]).
`obstore.put_async` under `trio.run` raised `RuntimeError: no running event loop` (measured).
Async credential providers also need a running event loop ([auth docs][obs-auth-providers]).
The sync forms release the GIL and block the calling thread on the same runtime ([`put.rs`][obs-put-rs-sync]).
The obstore docs say the sync API may perform better in a thread pool than other Python request libraries, and that its authors have not benchmarked it ([performance][obs-perf]).

### Async in fsspec

s3fs, gcsfs and adlfs subclass `AsyncFileSystem`, whose coroutine methods carry a leading underscore, such as `_pipe_file` ([async docs][fs-async-doc]).
By default, the sync methods submit those coroutines to one event loop on a daemon thread named `fsspecIO`, which every instance in the process shares ([`asyn.py`][fs-asyn-loop]).
A sync call made from inside that loop raises `NotImplementedError` ([`asyn.py`][fs-asyn-sync]).
In async code, an instance needs `asynchronous=True`, an awaited `set_session()`, and an explicit close of that session ([s3fs docs][s3-docs-async], [async docs][fs-async-doc]).
An instance used in a forked child process raises `RuntimeError("This class is not fork-safe")` ([`asyn.py`][fs-asyn-fork]).

fsspec's `LocalFileSystem` is sync only.
`AsyncFileSystemWrapper` gives it async methods by running each sync method through `asyncio.to_thread` ([`asyn_wrapper.py`][fs-wrapper]).
Under `trio.run`, the wrapper's `_pipe_file` raised `RuntimeError: no running event loop` (measured).
The cloud backends' coroutines run on asyncio, through aiohttp in s3fs and gcsfs and through `azure-storage-blob[aio]` in adlfs ([s3fs][pypi-s3fs], [gcsfs][pypi-gcsfs], [adlfs][pypi-adlfs]).

## Atomic writes

### What the services guarantee

S3 updates a single key atomically, and a concurrent reader gets the old data or the new data, never partial data ([S3 consistency][aws-consistency]).
Concurrent PUTs to one key follow last-writer-wins semantics, and S3 has no object locking for concurrent writers.
With `If-None-Match: *`, `PutObject` and `CompleteMultipartUpload` fail with `412 Precondition Failed` when the key exists ([conditional writes][aws-conditional]).
A concurrent delete can produce `409 Conflict` instead, and a `PutObject` may be retried after it.

GCS uploads are atomic: an interrupted upload leaves no partial data, and the object appears only when the upload completes ([GCS consistency][gcs-consistency]).
A request with `ifGenerationMatch=0` proceeds only if no live object has that name, and a failed precondition returns `412` ([preconditions][gcs-preconditions]).
The GCS docs say this precondition stops a retried upload from writing the object twice.

Azure Put Blob replaces the whole blob, and blocks from Put Block join a blob only when Put Block List commits them ([Put Blob][az-put-blob], [Put Block List][az-put-block-list]).
Reads use snapshot isolation, so a read during a write returns a consistent snapshot ([concurrency][az-concurrency]).
`If-None-Match: *` makes a write fail when the blob exists, and a failed write condition returns `412` ([conditional headers][az-conditional]).

Under `create`, a retry sent after a lost success response gets `412`, because the first attempt already wrote the object.
This follows from the documented `412` behaviour above.
On S3 and GCS, obstore raises `AlreadyExistsError` in that case, the same error as for an object from another writer ([`mod.rs`][os-s3-put], [`client.rs`][os-gcs-put]).

### Writes in obstore

`put` documents that the write is atomic, and that no client should be able to observe a partly written object ([`_put.pyi`][obs-put-pyi]).
`PutMode` is `"overwrite"`, the default, `"create"`, or an `UpdateVersion` dict with `e_tag` and `version`.
`create` raises `AlreadyExistsError` when the object exists, and `UpdateVersion` raises `PreconditionError` when the version differs.
Any mode other than `overwrite` forces a single-request upload, which holds the whole payload in memory ([`put.rs`][obs-put-rs-sync]).

- On S3, `create` sends `If-None-Match: *`, because the `conditional_put` setting defaults to `etag` ([`precondition.rs`][os-s3-cp], [`_aws.pyi`][obs-aws-cp]).
  A `412` or `304` response becomes `AlreadyExistsError` ([`mod.rs`][os-s3-put]).
- On GCS, `create` sends `x-goog-if-generation-match: 0`, and a failed precondition becomes `AlreadyExistsError` ([`client.rs`][os-gcs-put]).
- On Azure, `create` sends `If-None-Match: *` ([`client.rs`][os-azure-put]).
  In `object_store` 0.14.1, which obstore 0.11.1 locks, a failed Azure `create` raises `PreconditionError`, not `AlreadyExistsError`.
  `object_store` 0.14.2 maps it to `AlreadyExists` ([changelog][os-changelog]).
- `object_store` marks an overwrite PUT as idempotent, so it retries one after a timeout ([`mod.rs`][os-s3-put]).
  It retries a `create` PUT only after a 5xx, 429 or 408 response, or after a connection error that stopped the request from being sent ([retry rules][os-retry-rules]).

`LocalStore` writes each `put` to a staging file named `{target}#{n}` in the target's directory ([`local.rs`][os-local-staging]).
For `overwrite`, it renames the staging file over the target.
For `create`, it hard-links the staging file to the target, which fails if the target exists ([`local.rs`][os-local-put]).
On an error, it removes the staging file, but a process killed mid-write leaves the file behind.
`LocalStore.list` skips names that end in `#` and digits ([`local.rs`][os-local-list]).
`object_store` can fsync written files and their directories through `with_fsync`, which is off by default, and obstore's `LocalStore` has no option for it ([`local.rs`][os-local-fsync], [`__init__.pyi`][obs-store-pyi]).
`LocalStore` does not support `UpdateVersion`.
A second `create` of `jobs/123.json` raised `AlreadyExistsError`, and the directory held only `123.json` afterwards (measured).

### Writes in fsspec

fsspec writes bytes with `pipe_file(path, value, mode="overwrite")`.
`LocalFileSystem` inherits the base `pipe_file`, which opens the target with `"wb"` and writes to it in place ([`spec.py`][fs-pipe], [`local.py`][fs-local-open]).
For `mode="create"`, the base method calls `exists` first, and its comment calls this "non-atomic".
Inside `fs.transaction`, a local file opens with `autocommit=False` and writes to a file from `tempfile.mkstemp()`, in the system temp directory ([`local.py`][fs-local-open]).
On commit, `shutil.move` moves that file to the target ([`local.py`][fs-local-commit]).
`shutil.move` renames within one filesystem and copies across filesystems.
The transaction's temp file was in `tempfile.gettempdir()`, not in the target directory (measured).

- s3fs sends one `put_object` below 100 MiB, twice its 50 MiB chunk size, and a multipart upload from 100 MiB up ([`core.py`][s3-pipe]).
  `mode="create"` adds `IfNoneMatch="*"` to `put_object` and to `complete_multipart_upload`, and the docstring says this "is only known to work on AWS S3".
  A failed multipart upload is aborted.
- gcsfs sends a single-request upload below 50 MiB and a resumable upload from 50 MiB up ([`core.py`][gcs-pipe]).
  `mode="create"` adds `ifGenerationMatch=0`, and the class docstring says the mode is supported "on an experimental basis" ([`core.py`][gcs-simple], [`core.py`][gcs-class]).
- adlfs calls the Azure SDK's `upload_blob(overwrite=...)`, and `mode="create"` sets `overwrite=False` ([`spec.py`][adl-pipe]).
  A `ResourceExistsError` becomes `FileExistsError`.
- obstore's fsspec adapter, `obstore.fsspec.FsspecStore`, accepts `mode` in `_pipe_file` but does not use it, so `create` through the adapter overwrites ([`fsspec.py`][obs-fsspec-pipe]).
  The obstore docs describe the adapter as best effort ([`fsspec.py`][obs-fsspec-doc]).

## Multipart uploads, concurrency and retries

### Multipart uploads

| Library | Single-request limit | Part size | Parts in flight | After a failure |
| --- | --- | --- | --- | --- |
| obstore | 5 MiB, or any size when `mode` is not `overwrite` | 5 MiB | 12 | Aborts the upload |
| s3fs | 100 MiB | 50 MiB | 10 | Aborts the upload |
| gcsfs | 50 MiB | 50 MiB | 1, in sequence | Deletes the upload session |
| adlfs | 64 MiB | 4 MiB | adlfs `max_concurrency` | Uncommitted blocks expire after a week |

obstore uses multipart for a buffer larger than `chunk_size` and always for an iterator ([`put.rs`][obs-put-rs-choice]), and it aborts the upload on an error ([`put.rs`][obs-put-rs-abort]).
The s3fs figures come from `_pipe_file` and the `max_concurrency` default ([`core.py`][s3-pipe], [`core.py`][s3-class]).
The gcsfs figures come from `_pipe_file`, which uploads chunks in a loop ([`core.py`][gcs-pipe]).
The adlfs figures come from the Azure SDK defaults and adlfs's `_pipe_file` ([azure-storage-blob][az-sizes], [`spec.py`][adl-pipe], [Put Block List][az-put-block-list]).

An incomplete S3 multipart upload keeps its parts, and their storage charges, until it is completed or aborted ([multipart upload][aws-mpu]).
AWS recommends a lifecycle rule that aborts incomplete uploads, and obstore's `put` docstring repeats that advice ([`_put.pyi`][obs-put-pyi]).
A GCS resumable session URI expires after one week, and only a completed upload appears in the bucket ([resumable uploads][gcs-resumable]).
At tens to hundreds of KB, oxy's usual results stay below every threshold in the table, so each write is one request.

### Concurrency across files

obstore sets no limit on concurrent requests.
Its `ClientConfig` caps idle connections per host through `pool_max_idle_per_host`, not open connections ([`_client.pyi`][obs-client-pyi]).
A writer that runs many `put_async` calls at once bounds them itself.

s3fs clients use aiobotocore's connection pool, and botocore sets its size to 10 connections by default ([botocore][bc-pool], [aiobotocore][abc-pool]).
A request beyond 10 waits for a free connection.
Passing botocore's `max_pool_connections` through s3fs's `config_kwargs` changes the size ([`core.py`][s3-session]).
The gcsfs backend opens an aiohttp `ClientSession` with aiohttp's default connector, which allows 100 connections ([`core.py`][gcs-session], [fsspec `get_client`][fs-get-client], [aiohttp][aiohttp-limit]).
The fsspec bulk `pipe`, which takes a dict of paths and values, runs `_pipe_file` coroutines in batches of 1,280 by default ([`asyn.py`][fs-pipe-bulk], [`asyn.py`][fs-batch]).

### Retries

obstore uses `object_store`'s retry policy, and obstore lists no changes to the upstream defaults ([overridden defaults][obs-overrides]).

- It retries up to 10 times within 3 minutes of the first request ([`_retry.pyi`][obs-retry-pyi], [`retry.rs`][os-retry-config]).
- The backoff is exponential with jitter, from 100 ms to 15 s, with base 2 ([`backoff.rs`][os-backoff]).
- It retries 5xx, 429 and 408 responses and connection errors, and it retries timeouts only for idempotent requests ([`retry.rs`][os-retry-rules]).
- Each store's `retry_config` changes these values.
- `object_store` 0.14.2 adds retries for failed multipart parts, which obstore 0.11.1 lacks because it locks 0.14.1 ([changelog][os-changelog]).

s3fs retries in its own loop and again inside botocore.

- `_error_wrapper` makes up to 5 attempts and waits `min(1.7**i * 0.1, 15)` seconds between them ([`core.py`][s3-wrapper]).
- It retries socket timeouts, HTTP client errors, incomplete reads and response parser errors ([`core.py`][s3-retryable]).
- It retries a botocore `ClientError` only when the message contains `SlowDown`, `reduce your request rate` or `XAmzContentSHA256Mismatch`.
- Inside each attempt, botocore 1.43.75 uses its default `legacy` retry mode, with up to 5 attempts ([`configprovider.py`][bc-mode], [`_retry.json`][bc-retry]).
  `botocore.configprovider._DEFAULT_RETRY_MODE` was `legacy` in the s3fs environment (measured).

gcsfs retries in `retry_request`.

- It makes up to 6 attempts and sleeps `min(random() + 2**(n - 1), 32)` seconds before attempt `n` ([`retry.py`][gcs-retry]).
- It retries 500 to 504, 408 and 429, a 401 whose message contains "Invalid Credentials", and connection, timeout and SSL errors, but never a 404.
- Single-request uploads go through the same wrapper ([`core.py`][gcs-simple]).

adlfs adds no retry loop.
The Azure SDK's default `ExponentialRetry` makes 3 retries, with an initial backoff of 15 s and an increment base of 3 ([policies][az-retry], [base client][az-default]).

## Credentials, and settings shared with Polars

### How Polars resolves credentials

- `storage_options` takes `object_store` config keys for AWS, GCP and Azure ([`ndjson.py`][pl-ndjson]).
  Polars lower-cases each key and parses it with the crate's key enums, and it drops unknown keys without an error ([`options.rs`][pl-parse]).
  It adds its own keys: `max_retries`, `retry_timeout_ms`, `retry_init_backoff_ms`, `retry_max_backoff_ms`, `retry_base_multiplier` and `file_cache_ttl` ([`_utils.py`][pl-retry-keys]).
- `credential_provider` defaults to `"auto"` ([`_builder.py`][pl-auto]).
  For an S3 path, `"auto"` builds `CredentialProviderAWS`, which calls `boto3.Session().get_credentials()`, so profiles, `AWS_PROFILE` and the rest of boto3's chain apply ([`_providers.py`][pl-cp-aws]).
  For GCS, it builds `CredentialProviderGCP`, which calls `google.auth.default()` ([`_providers.py`][pl-cp-gcp]).
  For Azure, it builds `CredentialProviderAzure`, which uses `DefaultAzureCredential` ([`_providers.py`][pl-cp-azure]).
  With explicit credential keys in `storage_options`, Polars uses its Rust side instead.
- When the SDK is missing, the provider raises `ImportError`, and `"auto"` falls back to the Rust side ([`_builder.py`][pl-autoinit]).
- The Rust side starts from `AmazonS3Builder::from_env()`, reads a `region` from `~/.aws/config` and keys from `~/.aws/credentials` with regular expressions, then applies `storage_options` ([`options.rs`][pl-build-aws]).
  With no region set, it sends a HEAD request to the bucket and reads `x-amz-bucket-region`.
- A custom `credential_provider` returns a tuple: a dict of `object_store` keys, such as `aws_access_key_id`, and an expiry in epoch seconds or `None` ([`_providers.py`][pl-cp-return], [cloud storage docs][pl-docs]).
  Polars marks the parameter and its provider classes unstable ([`ndjson.py`][pl-ndjson]).
- `pl.Config.set_default_credential_provider` sets one provider for every call ([cloud storage docs][pl-docs]).
- Eager `read_csv` and `read_ipc` still open cloud paths through fsspec when they receive `storage_options`, and they raise `ImportError` without it ([`_utils.py`][pl-utils]).
  A Polars comment notes that the `storage_options` keys differ between fsspec and `object_store` ([`functions.py`][pl-csv]).
  The cloud storage page tells Python users to install `fsspec s3fs adlfs gcsfs` ([cloud storage docs][pl-docs]).

### Credentials in obstore

- Each store constructor starts from `object_store`'s `from_env` builder, then applies `config` and keyword arguments over it ([S3][obs-env-aws], [GCS][obs-env-gcp], [Azure][obs-env-azure], [auth docs][obs-auth-doc]).
  No argument turns the environment off.
  With `AWS_ENDPOINT=http://127.0.0.1:9` set, `S3Store("some-bucket")` sent its PUT to that address (measured).
- The `from_env` builders read every `AWS_*`, `GOOGLE_*` or `AZURE_*` variable that names a config key ([S3][os-aws-env], [GCS][os-gcp-env], [Azure][os-azure-env]).
- AWS: static keys, web identity, ECS container credentials, EKS pod identity and EC2 instance metadata ([auth docs][obs-auth-doc], [changelog][obs-changelog]).
  `object_store`'s S3 builder and credential code contain no reference to profiles or to the shared `~/.aws` files (searched; [`builder.rs`][os-aws-env]).
  Without a region, S3 requests go to `us-east-1`, and a request to a bucket in another region fails ([`builder.rs`][os-aws-region], [troubleshooting][obs-region-doc]).
- GCS: a service account key or path, then an application default credentials file of type `service_account` or `authorized_user`, then instance metadata ([`builder.rs`][os-gcp-chain], [`credential.rs`][os-gcp-adc]).
- Azure: in `auto` mode, Fabric tokens, a bearer token, an access key, workload identity, a client secret, a SAS, the Azure CLI when `use_azure_cli` is set, and then managed identity ([`builder.rs`][os-azure-chain]).
- A credential provider is a sync or async Python callable that returns a TypedDict with an `expires_at` datetime ([`_aws.pyi`][obs-aws-cred], [auth docs][obs-auth-providers]).
  When less than 300 seconds remain before `expires_at`, obstore calls the provider again ([`credentials.rs`][obs-token-cache]).
  `Boto3CredentialProvider` returns boto3's frozen credentials with a 30-minute expiry, and it passes the session's region to the store ([`boto3.py`][obs-boto3]).
  The native obstore providers refresh credentials before expiry without calling Python ([README][obs-readme], [auth docs][obs-auth-doc]).

Sharing settings with Polars:

- A dict of `aws_access_key_id`, `aws_secret_access_key` and `aws_region` built an `S3Store` through `config=`, and obstore stored the keys without the `aws_` prefix (measured).
  Polars documents the same dict for `storage_options` ([cloud storage docs][pl-docs]).
- `max_retries` in that dict raised `UnknownConfigurationKeyError` in obstore (measured).
  In obstore, retry settings go in a separate `retry_config` argument ([`_retry.pyi`][obs-retry-pyi]).
- A Polars provider returns `({"aws_access_key_id": ...}, epoch_seconds)`, and an obstore provider returns `{"access_key_id": ..., "expires_at": datetime}`, so one callable fits only one of them ([Polars][pl-cp-return], [obstore][obs-aws-cred]).

### Credentials in the fsspec backends

- s3fs takes `key`, `secret`, `token`, `profile`, `anon` or an aiobotocore `session` ([`core.py`][s3-class]).
  Without them, botocore's resolver reads environment variables, config files such as `~/.aws/credentials`, and EC2 instance metadata ([s3fs docs][s3-docs-creds]).
- gcsfs with `token=None` tries `google_default`, which calls `google.auth.default()`, then its token cache, then the metadata server, then anonymous access ([`credentials.py`][gcs-creds], [`core.py`][gcs-class]).
  Anonymous access always connects, so missing credentials cause an error at the first request, not at construction.
- adlfs reads `AZURE_STORAGE_ACCOUNT_NAME`, `AZURE_STORAGE_ACCOUNT_KEY`, `AZURE_STORAGE_CONNECTION_STRING`, `AZURE_STORAGE_SAS_TOKEN`, `AZURE_STORAGE_CLIENT_ID`, `AZURE_STORAGE_CLIENT_SECRET` and `AZURE_STORAGE_TENANT_ID` for any argument it does not receive ([`spec.py`][adl-env]).
  With none of them and `anon` false, it uses `DefaultAzureCredential` ([`spec.py`][adl-class]).
- fsspec applies default keyword arguments to every instance from `~/.config/fsspec/*.json` and `*.ini` files and from `FSSPEC_{protocol}` variables ([configuration][fs-config-doc]).
- These option names differ from Polars' `storage_options`, so a Polars dict does not pass to s3fs, gcsfs or adlfs unchanged ([`functions.py`][pl-csv]).

## Local paths

- obstore's `LocalStore` has the same `put`, `put_async` and `mode` API as the cloud stores, and `from_url("file:///...")` returns one ([`__init__.pyi`][obs-store-pyi]).
  `mkdir=True` creates the prefix directory.
  `LocalStore` raised `NotImplementedError` when `put` received `attributes` such as `Content-Type`, while `MemoryStore` accepted them (measured; [`local.rs`][os-local-put]).
- fsspec's `LocalFileSystem` has the same `pipe_file` API as the cloud backends, and `fsspec.filesystem("file")` or a `file://` URL returns one ([`registry.py`][fs-registry]).
  Its writes are sync and in place, as the atomic writes section describes.
  `fsspec.filesystem("file") is fsspec.filesystem("file")` returned `True`, because fsspec caches instances by their constructor arguments (measured; [instance caching][fs-cache-doc]).
- universal-pathlib 0.3.10 puts a `pathlib` API over fsspec and ships `py.typed` ([PyPI][pypi-upath]).
  It writes through `fs.open(path, "wb")` and has no async methods, so it changes none of the async or atomic-write facts above ([`core.py`][upath-writer]).

## Typing and maintenance

### Typing

- obstore's installed wheel holds `py.typed` and 21 `.pyi` files (measured).
  With pyrefly 1.3.1 and `preset = "strict"`, `S3Store(...)` revealed `S3Store`, `obstore.put(...)` revealed `PutResult`, and `LocalStore.put` revealed its full signature, with 0 errors (measured).
  Under mypy 2.3.1 with `--strict`, the same file had no issues (measured).
- `PutMode`, `PutResult`, `S3Config`, `RetryConfig` and `S3Credential` exist only in the stubs, and obstore's docs say to import them under `TYPE_CHECKING` ([`_put.pyi`][obs-put-pyi], [`_aws.pyi`][obs-aws-cred]).
  Importing `RetryConfig` from `obstore.store` at runtime raised `ImportError` (measured).
- fsspec, s3fs, gcsfs and adlfs ship no `py.typed`, and neither typeshed nor PyPI holds stubs for them (measured).
  The strict pyrefly preset revealed `fsspec.filesystem("s3")` and its `pipe_file` as `Unknown`, with 0 errors (measured).
  In strict mode, mypy reported `Skipping analyzing "fsspec": module is installed, but missing library stubs or py.typed marker [import-untyped]` (measured).

### Releases and maintainers

| Package | Latest | Released | Releases, last 12 months | License | Commits, last 12 months | Top author |
| --- | --- | --- | --- | --- | --- | --- |
| obstore | 0.11.1 | 2026-08-21 | 10 | MIT | 132 | `kylebarron`, 80 |
| object_store | 0.14.2 | 2026-09-15 | 7 | MIT or Apache-2.0 | 156 | `alamb`, 25 |
| fsspec | 2026.9.0 | 2026-09-18 | 9 | BSD-3-Clause | 168 | `martindurant`, 27 |
| s3fs | 2026.9.0 | 2026-09-18 | 9 | BSD | 35 | `martindurant`, 18 |
| gcsfs | 2026.8.1 | 2026-09-11 | 11 | BSD-3-Clause | 300 | `zhixiangli`, 94 |
| adlfs | 2026.8.0 | 2026-08-11 | 4 | BSD | 23 | `anjaliratnam-msft`, 9 |

Release counts come from PyPI and crates.io, and commit counts from the GitHub commits API on each default branch since 2025-09-24 ([sources](#sources)).
Dependabot wrote 31 of obstore's 132 commits, so `kylebarron` wrote 80 of the 101 others.

- obstore's PyPI classifier is "Development Status :: 4 - Beta" ([`pyproject.toml`][obs-pyproject]).
- The changelog lists breaking changes in 0.3.0, 0.4.0, 0.5.0, 0.6.0, 0.7.0, 0.8.0 and 0.9.0, and none in 0.10.0 or 0.11.0 ([changelog][obs-changelog]).
  Version 0.8.0 changed how paths are percent-encoded, and 0.9.0 dropped Python 3.9.
- obstore moves to a new `object_store` line in a minor release: 0.9.0 moved to 0.13, and 0.11.0 moved to 0.14 ([changelog][obs-changelog]).
- fsspec, s3fs, gcsfs and adlfs use calendar versions, and s3fs releases alongside fsspec ([PyPI][pypi-s3fs]).

## Awkward in a library

For obstore:

- The store constructors read the process environment, and no argument turns that off, so ambient `AWS_*`, `GOOGLE_*` or `AZURE_*` variables change a store built from explicit settings.
- The async API needs asyncio.
- The stub-only types cannot appear in annotations that run at runtime, such as pydantic fields.
- Minor releases have broken APIs, so a library pin such as `obstore>=0.11,<0.12` also constrains users who call obstore directly.
- Windows ARM64 has no wheel, so installing there builds from source with Rust.
- An S3 bucket outside `us-east-1` needs its region set, because obstore does not look it up.
- `LocalStore` has no fsync option and rejects `attributes`.

For fsspec:

- Its packages carry no type information.
- It keeps process-wide state: the instance cache, config defaults from `~/.config/fsspec` and `FSSPEC_*` variables, and one IO thread.
- Its async instances raise after `fork`.
- s3fs needs the fsspec release with its own version, and aiobotocore pins botocore to a narrow range, which conflicts with a user's current boto3.
- `mode="create"` behaves differently in each backend, and on local disk it checks and then writes.
- gcsfs falls back to anonymous access when it finds no credentials.
- gcsfs installs grpcio among 39 distributions.

## Open questions

- **Which event loops does oxy's async API support?**
  The httpx2 2.13.1 package declares AnyIO, asyncio and Trio support ([PyPI][pypi-httpx2]).
  Neither obstore's nor fsspec's async API runs under trio, so a trio caller would need the sync API in a worker thread.
  No ticket settles the event loops yet, and [#11](https://github.com/ozanozbeker/oxyscraper/issues/11) covers sync and async only.
- **How fast is each library at thousands of small PUTs?**
  The obstore README's figure of 9 times fsspec's throughput comes from a benchmark of concurrent small GETs ([README][obs-readme]).
  Neither project publishes a PUT benchmark, and measuring one needs a real bucket, such as the one [#7](https://github.com/ozanozbeker/oxyscraper/issues/7) provisions.
- **How does the writer treat a retried `create`?**
  With job-ID keys, a retry after a lost success response gets `412`, and obstore raises `AlreadyExistsError` for it.
  Ticket [#16](https://github.com/ozanozbeker/oxyscraper/issues/16) chooses between `overwrite` and `create`, and `create` also needs a rule for that error.
- **Is Windows ARM64 in scope?**
  No obstore wheel exists for it.

## Sources

obstore at tag `py-v0.11.1` (commit `51e204c`):

- [README][obs-readme], [`obstore/pyproject.toml`][obs-pyproject], [workspace `Cargo.toml`][obs-cargo] and [`Cargo.lock`][obs-lock].
- `put`: [`_put.pyi`][obs-put-pyi], and `put.rs` for [the multipart choice][obs-put-rs-choice], [the mode and GIL release][obs-put-rs-sync] and [the abort][obs-put-rs-abort].
- Stores: [`_store/__init__.pyi`][obs-store-pyi], [`_retry.pyi`][obs-retry-pyi], [`_client.pyi`][obs-client-pyi], and `_aws.pyi` for [`conditional_put`][obs-aws-cp], [`region`][obs-aws-region] and [`S3Credential`][obs-aws-cred].
- `pyo3-object_store` constructors for [S3][obs-env-aws], [GCS][obs-env-gcp] and [Azure][obs-env-azure], [S3 key parsing][obs-key-parse] and [the token cache][obs-token-cache].
- [`auth/boto3.py`][obs-boto3], and [`fsspec.py`][obs-fsspec-doc] with [its `_pipe_file`][obs-fsspec-pipe].
- Docs: [native authentication][obs-auth-doc], [credential providers][obs-auth-providers], [S3 troubleshooting][obs-region-doc], [performance][obs-perf], [overridden defaults][obs-overrides] and [`CHANGELOG.md`][obs-changelog].

`object_store` at tag `v0.14.1` (commit `c7316d2`), the version obstore 0.11.1 locks:

- S3: [`precondition.rs`][os-s3-cp], [`mod.rs`][os-s3-put], [`from_env`][os-aws-env] and [the default region][os-aws-region].
- GCS: [`client.rs`][os-gcs-put], [`from_env`][os-gcp-env], [the credential chain][os-gcp-chain] and [application default credentials][os-gcp-adc].
- Azure: [`client.rs`][os-azure-put], [`from_env`][os-azure-env] and [the `auto` credential chain][os-azure-chain].
- `local.rs`: [`put_opts`][os-local-put], [the listing filter][os-local-list], [the staging path][os-local-staging] and [`with_fsync`][os-local-fsync].
- [`RetryConfig`][os-retry-config], [the retry rules][os-retry-rules] and [`BackoffConfig`][os-backoff].
- [The 0.14.2 changelog][os-changelog], at tag `v0.14.2` (commit `279572e`).

Polars at tag `py-1.44.2` (commit `1bd8ec1`):

- [`Cargo.toml`][pl-cargo] and [its `object_store` patch][pl-cargo-patch], and [`Cargo.toml` on `main`][pl-cargo-main] at commit `c4e21dc`, which pins 0.14.2.
- [Cloud storage user guide][pl-docs] and [its examples][pl-docs-examples].
- `_builder.py`: [`AutoInit`][pl-autoinit] and [the `"auto"` resolution][pl-auto].
- `_providers.py`: [the return type][pl-cp-return], [`CredentialProviderAWS`][pl-cp-aws], [`CredentialProviderAzure`][pl-cp-azure] and [`CredentialProviderGCP`][pl-cp-gcp].
- `options.rs`: [key parsing][pl-parse] and [`build_aws`][pl-build-aws].
- [`io/cloud/_utils.py`][pl-retry-keys], [`ndjson.py`][pl-ndjson], [`csv/functions.py`][pl-csv] and [`io/_utils.py`][pl-utils].

fsspec at tag `2026.9.0` (commit `0f76baa`):

- [`spec.py`][fs-pipe], `local.py` for [opening][fs-local-open] and [committing][fs-local-commit], and [`registry.py`][fs-registry].
- `asyn.py`: [`sync`][fs-asyn-sync], [the IO loop][fs-asyn-loop], [fork safety][fs-asyn-fork], [batch sizes][fs-batch] and [bulk `_pipe`][fs-pipe-bulk].
- [`asyn_wrapper.py`][fs-wrapper] and [`http.py`][fs-get-client].
- Docs: [async][fs-async-doc], [instance caching][fs-cache-doc] and [configuration][fs-config-doc].

Backends:

- s3fs at tag `2026.9.0` (commit `62f45e6`): `core.py` for [the class][s3-class], [`set_session`][s3-session], [retryable errors][s3-retryable], [`_error_wrapper`][s3-wrapper] and [`_pipe_file`][s3-pipe], and the docs on [async][s3-docs-async] and [credentials][s3-docs-creds].
- gcsfs at tag `2026.8.1` (commit `73929a1`): `core.py` for [the class][gcs-class], [the session][gcs-session], [`_pipe_file`][gcs-pipe] and [`simple_upload`][gcs-simple], plus [`retry.py`][gcs-retry] and [`credentials.py`][gcs-creds].
- adlfs at tag `2026.8.0` (commit `6362b4f`): `spec.py` for [the class][adl-class], [environment variables][adl-env] and [`_pipe_file`][adl-pipe].
- botocore at tag `1.43.75`: [`endpoint.py`][bc-pool], [`configprovider.py`][bc-mode] and [`_retry.json`][bc-retry].
- aiobotocore at tag `3.9.1`: [`httpsession.py`][abc-pool].
- azure-storage-blob at tag `azure-storage-blob_12.30.3`: [`policies.py`][az-retry], [`base_client.py`][az-default] and [`models.py`][az-sizes].
- aiohttp at tag `v3.14.3`: [`connector.py`][aiohttp-limit].
- universal-pathlib at tag `v0.3.10`: [`core.py`][upath-writer].

Service docs:

- AWS: [data consistency model][aws-consistency], [conditional writes][aws-conditional] and [multipart upload][aws-mpu].
- Google Cloud: [consistency][gcs-consistency], [request preconditions][gcs-preconditions] and [resumable uploads][gcs-resumable].
- Azure: [managing concurrency][az-concurrency], [conditional headers][az-conditional], [Put Blob][az-put-blob] and [Put Block List][az-put-block-list].

Package indexes and GitHub:

- PyPI JSON: [obstore][pypi-obstore], [fsspec][pypi-fsspec], [s3fs][pypi-s3fs], [gcsfs][pypi-gcsfs], [adlfs][pypi-adlfs], [aiobotocore][pypi-aiobotocore], [botocore][pypi-botocore], [boto3][pypi-boto3], [universal-pathlib][pypi-upath] and [httpx2][pypi-httpx2].
- [`object_store` versions on crates.io][crates-object-store].
- GitHub commits since 2025-09-24: [obstore][gh-obstore], [object_store][gh-object-store], [fsspec][gh-fsspec], [s3fs][gh-s3fs], [gcsfs][gh-gcsfs] and [adlfs][gh-adlfs].

[obs-readme]: https://github.com/developmentseed/obstore/blob/py-v0.11.1/README.md#L19-L34
[obs-pyproject]: https://github.com/developmentseed/obstore/blob/py-v0.11.1/obstore/pyproject.toml#L1-L31
[obs-cargo]: https://github.com/developmentseed/obstore/blob/py-v0.11.1/Cargo.toml#L29-L39
[obs-lock]: https://github.com/developmentseed/obstore/blob/py-v0.11.1/Cargo.lock#L1423-L1424
[obs-put-pyi]: https://github.com/developmentseed/obstore/blob/py-v0.11.1/obstore/python/obstore/_put.pyi#L19-L201
[obs-put-rs-choice]: https://github.com/developmentseed/obstore/blob/py-v0.11.1/obstore/src/put.rs#L213-L222
[obs-put-rs-sync]: https://github.com/developmentseed/obstore/blob/py-v0.11.1/obstore/src/put.rs#L302-L357
[obs-put-rs-abort]: https://github.com/developmentseed/obstore/blob/py-v0.11.1/obstore/src/put.rs#L439-L467
[obs-store-pyi]: https://github.com/developmentseed/obstore/blob/py-v0.11.1/obstore/python/obstore/_store/__init__.pyi#L77-L201
[obs-retry-pyi]: https://github.com/developmentseed/obstore/blob/py-v0.11.1/obstore/python/obstore/_store/_retry.pyi#L1-L97
[obs-client-pyi]: https://github.com/developmentseed/obstore/blob/py-v0.11.1/obstore/python/obstore/_store/_client.pyi#L94-L95
[obs-aws-cp]: https://github.com/developmentseed/obstore/blob/py-v0.11.1/obstore/python/obstore/_store/_aws.pyi#L124-L135
[obs-aws-region]: https://github.com/developmentseed/obstore/blob/py-v0.11.1/obstore/python/obstore/_store/_aws.pyi#L287-L288
[obs-aws-cred]: https://github.com/developmentseed/obstore/blob/py-v0.11.1/obstore/python/obstore/_store/_aws.pyi#L431-L458
[obs-env-aws]: https://github.com/developmentseed/obstore/blob/py-v0.11.1/pyo3-object_store/src/aws/store.rs#L84-L139
[obs-key-parse]: https://github.com/developmentseed/obstore/blob/py-v0.11.1/pyo3-object_store/src/aws/store.rs#L225-L237
[obs-env-gcp]: https://github.com/developmentseed/obstore/blob/py-v0.11.1/pyo3-object_store/src/gcp/store.rs#L96
[obs-env-azure]: https://github.com/developmentseed/obstore/blob/py-v0.11.1/pyo3-object_store/src/azure/store.rs#L104
[obs-token-cache]: https://github.com/developmentseed/obstore/blob/py-v0.11.1/pyo3-object_store/src/credentials.rs#L22-L90
[obs-boto3]: https://github.com/developmentseed/obstore/blob/py-v0.11.1/obstore/python/obstore/auth/boto3.py#L57-L104
[obs-fsspec-doc]: https://github.com/developmentseed/obstore/blob/py-v0.11.1/obstore/python/obstore/fsspec.py#L1-L28
[obs-fsspec-pipe]: https://github.com/developmentseed/obstore/blob/py-v0.11.1/obstore/python/obstore/fsspec.py#L367-L376
[obs-auth-doc]: https://github.com/developmentseed/obstore/blob/py-v0.11.1/docs/authentication.md#L5-L50
[obs-auth-providers]: https://github.com/developmentseed/obstore/blob/py-v0.11.1/docs/authentication.md#L52-L202
[obs-region-doc]: https://github.com/developmentseed/obstore/blob/py-v0.11.1/docs/troubleshooting/aws.md#L3-L21
[obs-perf]: https://github.com/developmentseed/obstore/blob/py-v0.11.1/docs/performance.md#L41
[obs-overrides]: https://github.com/developmentseed/obstore/blob/py-v0.11.1/docs/dev/overridden-defaults.md
[obs-changelog]: https://github.com/developmentseed/obstore/blob/py-v0.11.1/CHANGELOG.md
[os-s3-cp]: https://github.com/apache/arrow-rs-object-store/blob/v0.14.1/src/aws/precondition.rs#L114-L131
[os-s3-put]: https://github.com/apache/arrow-rs-object-store/blob/v0.14.1/src/aws/mod.rs#L164-L243
[os-aws-env]: https://github.com/apache/arrow-rs-object-store/blob/v0.14.1/src/aws/builder.rs#L606-L618
[os-aws-region]: https://github.com/apache/arrow-rs-object-store/blob/v0.14.1/src/aws/builder.rs#L1152
[os-gcs-put]: https://github.com/apache/arrow-rs-object-store/blob/v0.14.1/src/gcp/client.rs#L403-L417
[os-gcp-env]: https://github.com/apache/arrow-rs-object-store/blob/v0.14.1/src/gcp/builder.rs#L293-L311
[os-gcp-chain]: https://github.com/apache/arrow-rs-object-store/blob/v0.14.1/src/gcp/builder.rs#L565-L640
[os-gcp-adc]: https://github.com/apache/arrow-rs-object-store/blob/v0.14.1/src/gcp/credential.rs#L537-L557
[os-azure-put]: https://github.com/apache/arrow-rs-object-store/blob/v0.14.1/src/azure/client.rs#L758-L767
[os-azure-env]: https://github.com/apache/arrow-rs-object-store/blob/v0.14.1/src/azure/builder.rs#L567-L584
[os-azure-chain]: https://github.com/apache/arrow-rs-object-store/blob/v0.14.1/src/azure/builder.rs#L1046-L1094
[os-local-put]: https://github.com/apache/arrow-rs-object-store/blob/v0.14.1/src/local.rs#L393-L455
[os-local-list]: https://github.com/apache/arrow-rs-object-store/blob/v0.14.1/src/local.rs#L378-L389
[os-local-staging]: https://github.com/apache/arrow-rs-object-store/blob/v0.14.1/src/local.rs#L1081-L1086
[os-local-fsync]: https://github.com/apache/arrow-rs-object-store/blob/v0.14.1/src/local.rs#L305-L325
[os-retry-config]: https://github.com/apache/arrow-rs-object-store/blob/v0.14.1/src/client/retry.rs#L227-L260
[os-retry-rules]: https://github.com/apache/arrow-rs-object-store/blob/v0.14.1/src/client/retry.rs#L405-L445
[os-backoff]: https://github.com/apache/arrow-rs-object-store/blob/v0.14.1/src/client/backoff.rs#L40-L48
[os-changelog]: https://github.com/apache/arrow-rs-object-store/blob/v0.14.2/CHANGELOG.md#L22-L67
[pl-cargo]: https://github.com/pola-rs/polars/blob/py-1.44.2/Cargo.toml#L77
[pl-cargo-patch]: https://github.com/pola-rs/polars/blob/py-1.44.2/Cargo.toml#L172-L175
[pl-cargo-main]: https://github.com/pola-rs/polars/blob/c4e21dcfa1bb7ab067e4a0af69e6d92693c4e8a9/Cargo.toml#L77
[pl-docs]: https://docs.pola.rs/user-guide/io/cloud-storage/
[pl-docs-examples]: https://github.com/pola-rs/polars/blob/py-1.44.2/docs/source/src/python/user-guide/io/cloud-storage.py
[pl-autoinit]: https://github.com/pola-rs/polars/blob/py-1.44.2/py-polars/src/polars/io/cloud/credential_provider/_builder.py#L293-L311
[pl-auto]: https://github.com/pola-rs/polars/blob/py-1.44.2/py-polars/src/polars/io/cloud/credential_provider/_builder.py#L340-L540
[pl-cp-return]: https://github.com/pola-rs/polars/blob/py-1.44.2/py-polars/src/polars/io/cloud/credential_provider/_providers.py#L33-L37
[pl-cp-aws]: https://github.com/pola-rs/polars/blob/py-1.44.2/py-polars/src/polars/io/cloud/credential_provider/_providers.py#L147-L320
[pl-cp-azure]: https://github.com/pola-rs/polars/blob/py-1.44.2/py-polars/src/polars/io/cloud/credential_provider/_providers.py#L321-L460
[pl-cp-gcp]: https://github.com/pola-rs/polars/blob/py-1.44.2/py-polars/src/polars/io/cloud/credential_provider/_providers.py#L518-L590
[pl-parse]: https://github.com/pola-rs/polars/blob/py-1.44.2/crates/polars-io/src/cloud/options.rs#L256-L271
[pl-build-aws]: https://github.com/pola-rs/polars/blob/py-1.44.2/crates/polars-io/src/cloud/options.rs#L410-L530
[pl-retry-keys]: https://github.com/pola-rs/polars/blob/py-1.44.2/py-polars/src/polars/io/cloud/_utils.py#L10-L19
[pl-ndjson]: https://github.com/pola-rs/polars/blob/py-1.44.2/py-polars/src/polars/io/ndjson.py#L99-L121
[pl-csv]: https://github.com/pola-rs/polars/blob/py-1.44.2/py-polars/src/polars/io/csv/functions.py#L526-L530
[pl-utils]: https://github.com/pola-rs/polars/blob/py-1.44.2/py-polars/src/polars/io/_utils.py#L135-L168
[fs-pipe]: https://github.com/fsspec/filesystem_spec/blob/2026.9.0/fsspec/spec.py#L870-L877
[fs-local-open]: https://github.com/fsspec/filesystem_spec/blob/2026.9.0/fsspec/implementations/local.py#L381-L409
[fs-local-commit]: https://github.com/fsspec/filesystem_spec/blob/2026.9.0/fsspec/implementations/local.py#L440-L463
[fs-registry]: https://github.com/fsspec/filesystem_spec/blob/2026.9.0/fsspec/registry.py#L63-L211
[fs-asyn-sync]: https://github.com/fsspec/filesystem_spec/blob/2026.9.0/fsspec/asyn.py#L66-L84
[fs-asyn-loop]: https://github.com/fsspec/filesystem_spec/blob/2026.9.0/fsspec/asyn.py#L238-L265
[fs-asyn-fork]: https://github.com/fsspec/filesystem_spec/blob/2026.9.0/fsspec/asyn.py#L442-L455
[fs-batch]: https://github.com/fsspec/filesystem_spec/blob/2026.9.0/fsspec/asyn.py#L281-L307
[fs-pipe-bulk]: https://github.com/fsspec/filesystem_spec/blob/2026.9.0/fsspec/asyn.py#L548-L556
[fs-wrapper]: https://github.com/fsspec/filesystem_spec/blob/2026.9.0/fsspec/implementations/asyn_wrapper.py#L11-L35
[fs-get-client]: https://github.com/fsspec/filesystem_spec/blob/2026.9.0/fsspec/implementations/http.py#L32-L33
[fs-async-doc]: https://github.com/fsspec/filesystem_spec/blob/2026.9.0/docs/source/async.rst#L1-L100
[fs-cache-doc]: https://github.com/fsspec/filesystem_spec/blob/2026.9.0/docs/source/features.rst#L161-L178
[fs-config-doc]: https://github.com/fsspec/filesystem_spec/blob/2026.9.0/docs/source/features.rst#L360-L404
[s3-class]: https://github.com/fsspec/s3fs/blob/2026.9.0/s3fs/core.py#L259-L394
[s3-session]: https://github.com/fsspec/s3fs/blob/2026.9.0/s3fs/core.py#L578-L670
[s3-retryable]: https://github.com/fsspec/s3fs/blob/2026.9.0/s3fs/core.py#L60-L76
[s3-wrapper]: https://github.com/fsspec/s3fs/blob/2026.9.0/s3fs/core.py#L161-L200
[s3-pipe]: https://github.com/fsspec/s3fs/blob/2026.9.0/s3fs/core.py#L1403-L1470
[s3-docs-async]: https://github.com/fsspec/s3fs/blob/2026.9.0/docs/source/index.rst#L90-L117
[s3-docs-creds]: https://github.com/fsspec/s3fs/blob/2026.9.0/docs/source/index.rst#L218-L247
[gcs-class]: https://github.com/fsspec/gcsfs/blob/2026.8.1/gcsfs/core.py#L197-L315
[gcs-session]: https://github.com/fsspec/gcsfs/blob/2026.8.1/gcsfs/core.py#L440
[gcs-pipe]: https://github.com/fsspec/gcsfs/blob/2026.8.1/gcsfs/core.py#L1674-L1731
[gcs-simple]: https://github.com/fsspec/gcsfs/blob/2026.8.1/gcsfs/core.py#L2815-L2887
[gcs-retry]: https://github.com/fsspec/gcsfs/blob/2026.8.1/gcsfs/retry.py#L61-L190
[gcs-creds]: https://github.com/fsspec/gcsfs/blob/2026.8.1/gcsfs/credentials.py#L304-L352
[adl-class]: https://github.com/fsspec/adlfs/blob/2026.8.0/adlfs/spec.py#L180-L260
[adl-env]: https://github.com/fsspec/adlfs/blob/2026.8.0/adlfs/spec.py#L335-L350
[adl-pipe]: https://github.com/fsspec/adlfs/blob/2026.8.0/adlfs/spec.py#L1509-L1533
[bc-pool]: https://github.com/boto/botocore/blob/1.43.75/botocore/endpoint.py#L40
[bc-mode]: https://github.com/boto/botocore/blob/1.43.75/botocore/configprovider.py#L33-L41
[bc-retry]: https://github.com/boto/botocore/blob/1.43.75/botocore/data/_retry.json#L91-L93
[abc-pool]: https://github.com/aio-libs/aiobotocore/blob/3.9.1/aiobotocore/httpsession.py#L219
[az-retry]: https://github.com/Azure/azure-sdk-for-python/blob/azure-storage-blob_12.30.3/sdk/storage/azure-storage-blob/azure/storage/blob/_shared/policies.py#L611-L626
[az-default]: https://github.com/Azure/azure-sdk-for-python/blob/azure-storage-blob_12.30.3/sdk/storage/azure-storage-blob/azure/storage/blob/_shared/base_client.py#L504
[az-sizes]: https://github.com/Azure/azure-sdk-for-python/blob/azure-storage-blob_12.30.3/sdk/storage/azure-storage-blob/azure/storage/blob/_shared/models.py#L590-L592
[aiohttp-limit]: https://github.com/aio-libs/aiohttp/blob/v3.14.3/aiohttp/connector.py#L978
[upath-writer]: https://github.com/fsspec/universal_pathlib/blob/v0.3.10/upath/core.py#L1420-L1421
[aws-consistency]: https://docs.aws.amazon.com/AmazonS3/latest/userguide/Welcome.html#ConsistencyModel
[aws-conditional]: https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html
[aws-mpu]: https://docs.aws.amazon.com/AmazonS3/latest/userguide/mpuoverview.html
[gcs-consistency]: https://docs.cloud.google.com/storage/docs/consistency
[gcs-preconditions]: https://docs.cloud.google.com/storage/docs/request-preconditions
[gcs-resumable]: https://docs.cloud.google.com/storage/docs/resumable-uploads
[az-concurrency]: https://learn.microsoft.com/en-us/azure/storage/blobs/concurrency-manage
[az-conditional]: https://learn.microsoft.com/en-us/rest/api/storageservices/specifying-conditional-headers-for-blob-service-operations
[az-put-blob]: https://learn.microsoft.com/en-us/rest/api/storageservices/put-blob
[az-put-block-list]: https://learn.microsoft.com/en-us/rest/api/storageservices/put-block-list
[pypi-obstore]: https://pypi.org/pypi/obstore/json
[pypi-fsspec]: https://pypi.org/pypi/fsspec/json
[pypi-s3fs]: https://pypi.org/pypi/s3fs/json
[pypi-gcsfs]: https://pypi.org/pypi/gcsfs/json
[pypi-adlfs]: https://pypi.org/pypi/adlfs/json
[pypi-aiobotocore]: https://pypi.org/pypi/aiobotocore/json
[pypi-botocore]: https://pypi.org/pypi/botocore/json
[pypi-boto3]: https://pypi.org/pypi/boto3/json
[pypi-upath]: https://pypi.org/pypi/universal-pathlib/json
[pypi-httpx2]: https://pypi.org/pypi/httpx2/json
[crates-object-store]: https://crates.io/api/v1/crates/object_store/versions
[gh-obstore]: https://api.github.com/repos/developmentseed/obstore/commits?since=2025-09-24T00:00:00Z
[gh-object-store]: https://api.github.com/repos/apache/arrow-rs-object-store/commits?since=2025-09-24T00:00:00Z
[gh-fsspec]: https://api.github.com/repos/fsspec/filesystem_spec/commits?since=2025-09-24T00:00:00Z
[gh-s3fs]: https://api.github.com/repos/fsspec/s3fs/commits?since=2025-09-24T00:00:00Z
[gh-gcsfs]: https://api.github.com/repos/fsspec/gcsfs/commits?since=2025-09-24T00:00:00Z
[gh-adlfs]: https://api.github.com/repos/fsspec/adlfs/commits?since=2025-09-24T00:00:00Z
