"""`Payload`, `SOURCES` and the instruction types, which validate, serialize and redact one job's body and send nothing.

`_sessions` builds the dry run from them.
A model validator on a subclass runs outside `Payload`'s scrubbing wrap validator, so a subclass checks fields together in `model_post_init` instead.
"""

from __future__ import annotations

import re
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    Literal,
    NotRequired,
    Required,
    Self,
    TypeVar,
)

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    PlainValidator,
    PositiveInt,
    StrictInt,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_serializer,
    model_validator,
    with_config,
)
from typing_extensions import TypeAliasType, TypedDict, override

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pydantic import ModelWrapValidatorHandler
    from pydantic_core import InitErrorDetails

_INPUT_KEYS = (
    "query",
    "url",
    "product_id",
    "prompt",
    "video_id",
    "channel_handle",
    "category_id",
)
_CREDENTIALS = re.compile(r"(?<=://)[^/?#@\s\"']+(?=@)")

_UserAgentType = Literal[
    "desktop",
    "mobile",
    "mobile_android",
    "mobile_ios",
    "tablet",
    "tablet_android",
    "tablet_ios",
    "desktop_chrome",
    "desktop_edge",
    "desktop_firefox",
    "desktop_opera",
    "desktop_safari",
]


_T = TypeVar("_T")


# Without it, a TypedDict keeps an undeclared key unchecked inside `Payload`, and drops it through a `TypeAdapter`.
_closed = with_config(ConfigDict(extra="forbid"))


def _compiled(pattern: str) -> str:
    """Raise for a regex that Python's `re` cannot compile, because the API bills it or returns 500."""
    try:
        re.compile(pattern)
    except re.error as error:
        msg = f"{pattern!r} is not a valid regex: {error}"
        raise ValueError(msg) from None
    return pattern


_Regex = Annotated[str, AfterValidator(_compiled)]


@_closed
class _Selector(TypedDict):
    type: Literal["xpath", "css", "text"]
    value: str


@_closed
class _BrowserInstructionBase(TypedDict, total=False):
    timeout_s: Annotated[int, Field(ge=1, le=60)]
    wait_time_s: Annotated[int, Field(ge=0, le=60)]
    on_error: Literal["error", "skip"]


@_closed
class _Click(_BrowserInstructionBase):
    type: Required[Literal["click", "wait_for_element"]]
    selector: Required[_Selector]


@_closed
class _Input(_BrowserInstructionBase):
    type: Required[Literal["input"]]
    selector: Required[_Selector]
    value: Required[str]


@_closed
class _Scroll(_BrowserInstructionBase):
    type: Required[Literal["scroll"]]
    x: Required[int]
    y: Required[int]


@_closed
class _Wait(_BrowserInstructionBase):
    type: Required[Literal["scroll_to_bottom", "wait"]]


@_closed
class _FetchResource(_BrowserInstructionBase):
    type: Required[Literal["fetch_resource"]]
    filter: Required[_Regex]


BrowserInstruction = Annotated[
    _Click | _Input | _Scroll | _Wait | _FetchResource, Field(discriminator="type")
]
"""One item of `browser_instructions`, whose `type` names one of the 7 documented instructions.

[JS Rendering & Browser Control](https://developers.oxylabs.io/products/web-scraper-api/features/js-rendering-and-browser-control) gives each instruction's keys.
"""


def _regex_search(args: list[str | int]) -> list[str | int]:
    """Raise unless `args` holds a regex and, optionally, the number of the group to return."""
    match args:
        case [str(pattern)] | [str(pattern), int()]:
            _compiled(pattern)
            return args
    msg = (
        "regex_search takes a regex and, optionally, the number of the group to return"
    )
    raise ValueError(msg)


def _regex_substring(args: list[str]) -> list[str]:
    """Raise unless the first of `args` compiles, because the second is the replacement."""
    _compiled(args[0])
    return args


@_closed
class _NoArgs(TypedDict):
    _fn: Literal[
        "element_text",
        "amount_from_string",
        "amount_range_from_string",
        "length",
        "convert_to_float",
        "convert_to_int",
        "convert_to_str",
        "max",
        "min",
        "product",
    ]


@_closed
class _Expressions(TypedDict):
    # `docs/research/live-universal.md` found that the API runs a bare string for these three only.
    _fn: Literal["xpath", "xpath_one", "css"]
    _args: Annotated[list[str], Field(min_length=1)] | str


@_closed
class _CssOne(TypedDict):
    _fn: Literal["css_one"]
    _args: Annotated[list[str], Field(min_length=1)]


@_closed
class _Join(TypedDict):
    _fn: Literal["join"]
    _args: NotRequired[str]


@_closed
class _RegexFindAll(TypedDict):
    _fn: Literal["regex_find_all"]
    _args: Annotated[list[_Regex], Field(min_length=1)]


@_closed
class _RegexSearch(TypedDict):
    _fn: Literal["regex_search"]
    _args: Annotated[list[str | StrictInt], AfterValidator(_regex_search)]


@_closed
class _RegexSubstring(TypedDict):
    _fn: Literal["regex_substring"]
    _args: Annotated[
        list[str], Field(min_length=2, max_length=2), AfterValidator(_regex_substring)
    ]


@_closed
class _SelectNth(TypedDict):
    _fn: Literal["select_nth"]
    _args: StrictInt


@_closed
class _Average(TypedDict):
    _fn: Literal["average"]
    _args: NotRequired[StrictInt]


ParsingFunction = (
    _NoArgs
    | _Expressions
    | _CssOne
    | _Join
    | _RegexFindAll
    | _RegexSearch
    | _RegexSubstring
    | _SelectNth
    | _Average
)
"""One item of a `_fns` pipeline, whose `_fn` names one of the 20 documented functions.

[List of parsing functions](https://developers.oxylabs.io/products/web-scraper-api/features/custom-parser/writing-instructions-manually/list-of-functions) gives each function's `_args`.
"""

_OnError = Literal["suppress", "warn", "error"]

ParsingInstructions = TypeAliasType(
    "ParsingInstructions",
    "dict[str, ParsingInstructions | list[ParsingFunction] | _OnError]",
)
"""One scope of parsing instructions, which holds a `_fns` pipeline, `_on_error`, and `_items` and fields that are scopes of their own.

[Parsing instruction examples](https://developers.oxylabs.io/products/web-scraper-api/features/custom-parser/writing-instructions-manually/parsing-instruction-examples) shows each part.
"""

_PIPELINE = TypeAdapter(list[Annotated[ParsingFunction, Field(discriminator="_fn")]])
_ON_ERROR = TypeAdapter(_OnError)
_SCOPE = TypeAdapter(dict[str, Any])


def _parsing_instructions(scope: object, *, path: tuple[str, ...] = ()) -> object:
    """Check the pipeline, `_on_error` and fields of the scope at `path`, and return it as it is."""
    # pydantic before 2.8 passes `ValidationInfo` to a second positional parameter, so `path` is keyword-only.
    # A union over a scope's values reports an error for every branch, so the key names the type to validate.
    for key, value in _checked(_SCOPE, scope, path).items():
        if key == "_fns":
            _checked(_PIPELINE, value, (*path, key))
        elif key == "_on_error":
            _checked(_ON_ERROR, value, (*path, key))
        else:
            _parsing_instructions(value, path=(*path, key))
    return scope


def _checked(adapter: TypeAdapter[_T], value: object, path: tuple[str, ...]) -> _T:
    """Validate `value`, and raise with `path` before each error's location."""
    try:
        return adapter.validate_python(value)
    except ValidationError as error:
        raise _scrubbed(error, "python", path) from None


class _ContextItem(TypedDict):
    key: str
    value: Any


class _ExtraContext(TypedDict):
    context: NotRequired[list[_ContextItem]]


_EXTRA_CONTEXT = TypeAdapter(_ExtraContext)


class Payload(BaseModel):
    """One job's body, for any source.

    `Payload` types each parameter that keeps one name, placement, type and value set on every source that takes it.
    Any other keyword goes into the body as it is, so a source without a model of its own still runs.
    An unset field stays out of the body, so the API applies its own default.
    A payload sets exactly one input key, to a non-empty string.
    Otherwise it raises only for a mistake that the API would bill, and leaves each free check to the API.

    Attributes
    ----------
    source
        The source that runs the job.
        It takes any string, because the API rejects an unknown source for free.
    query
        The input of most search and product sources.
    url
        The input of `universal` and of the sources that take a page's URL.
    product_id
        The input of product sources such as `walmart_product`.
    prompt
        The input of `chatgpt`, `gemini` and `perplexity`.
    video_id
        The input of `youtube_video_trainability`.
    channel_handle
        The input of `youtube_channel`.
    category_id
        The input of `target_category`.
    render
        `html` or `png` renders the page in a browser, and `""` turns off forced rendering.
    user_agent_type
        The device of the job's user agent.
        A `desktop_*` value draws from the same agents as `desktop`.
    callback_url
        The URL that the API calls when the job finishes.
    parse
        Returns parsed content, which needs a dedicated parser, `parsing_instructions` or `parser_preset`.
    start_page
        The first page to fetch.
    pages
        The number of pages to fetch, each billed as one result.
    limit
        The number of results on each page, or of videos on `youtube_channel`.
    markdown
        Makes Markdown the default output type.
    xhr
        Makes the page's Fetch and XHR requests the default output type, and needs `render`.
    parser_preset
        The parser preset to parse with, which needs `parse`.
    content_encoding
        `base64` returns an image as Base64 text.
    client_notes
        Text that the API saves with the job.
    aggregate_name
        The Result Aggregator that receives the result.
    geo_location
        The location that the job appears to come from, in a format that depends on the source.
    locale
        The language of the page, such as `en_US` on Amazon or `de-DE` on Google.
    domain
        The target's domain, such as `de` for amazon.de.
    context
        `key` and `value` items that the API reads from the `context` list.
    storage_type
        The Cloud Storage type that uploads the result, with Push-Pull only.
        Only `gcs` has a live upload test.
    storage_url
        The bucket path that Cloud Storage uploads to.
        A path that ends in `.{{ extension }}` names each job's object, so it raises without `{{ job_id }}`: jobs that share a name lose their uploads and still bill.
        `repr`, validation errors and `dry_run` show its credentials as `redacted:redacted`, as the API does.
    parsing_instructions
        The instructions of a custom parser, which need `parse`.
        A wrong `_args` shape, or a regex that Python's `re` cannot compile, raises, because the API bills it with a null field.
    browser_instructions
        The browser actions to run on the page, which need `render`.
        An instruction after `fetch_resource`, or a `filter` that Python's `re` cannot compile, raises, because the API returns 500 for it on every attempt.
    extra
        Keys in the API's shape, which oxy merges into the body.
        Its `context` items follow the typed ones, and a key set both here and as a field raises.
        It also carries a value that an out-of-date `Literal` rejects.
    """

    model_config = ConfigDict(extra="allow", frozen=True)

    source: str
    query: str | None = None
    url: str | None = None
    product_id: str | None = None
    prompt: str | None = None
    video_id: str | None = None
    channel_handle: str | None = None
    category_id: str | None = None
    render: Literal["html", "png", ""] | None = None
    user_agent_type: _UserAgentType | None = None
    callback_url: str | None = None
    parse: bool | None = None
    start_page: PositiveInt | None = None
    pages: PositiveInt | None = None
    limit: int | None = None
    markdown: bool | None = None
    xhr: bool | None = None
    parser_preset: str | None = None
    content_encoding: Literal["base64", "utf-8"] | None = None
    client_notes: str | None = None
    aggregate_name: str | None = None
    geo_location: str | None = None
    locale: str | None = None
    domain: str | None = None
    context: list[_ContextItem] | None = None
    storage_type: Literal["gcs", "s3", "tos", "s3_compatible"] | None = None
    storage_url: str | None = None
    parsing_instructions: (
        Annotated[ParsingInstructions, PlainValidator(_parsing_instructions)] | None
    ) = None
    browser_instructions: list[BrowserInstruction] | None = None
    extra: dict[str, Any] = {}

    @field_validator("extra")
    @classmethod
    def _extra_context(cls, extra: dict[str, Any]) -> dict[str, Any]:
        _EXTRA_CONTEXT.validate_python(extra)
        return extra

    @field_validator("browser_instructions")
    @classmethod
    def _fetch_resource_last(
        cls, instructions: list[BrowserInstruction] | None
    ) -> list[BrowserInstruction] | None:
        if any(item["type"] == "fetch_resource" for item in (instructions or ())[:-1]):
            msg = "fetch_resource must be the last browser instruction, because the API returns 500 for any instruction after it"
            raise ValueError(msg)
        return instructions

    @model_validator(mode="wrap")
    @classmethod
    def _scrub_errors(
        cls, data: object, handler: ModelWrapValidatorHandler[Self]
    ) -> Self:
        # The call that receives this error renders it with its own input type.
        try:
            return handler(data)
        except ValidationError as error:
            raise _scrubbed(error, "python") from None

    @override
    def model_post_init(self, context: Any, /) -> None:
        # pydantic raises a `ValueError` from here inside `_scrub_errors`, as a `ValidationError`.
        if twice := sorted(
            {name for name, value in self if value is not None}
            & (self.extra.keys() - {"context"})
        ):
            msg = f"{twice[0]} is set both as a field and in extra"
            raise ValueError(msg)
        body = self.model_dump()
        context_keys = [item["key"] for item in body.get("context", ())]
        for key in context_keys:
            if context_keys.count(key) > 1:
                msg = f"context key {key} is set twice"
                raise ValueError(msg)
        input_keys = [key for key in _INPUT_KEYS if key in body]
        if not input_keys:
            msg = f"payload has no input key, so set one of {', '.join(_INPUT_KEYS[:-1])} or {_INPUT_KEYS[-1]}"
            raise ValueError(msg)
        if len(input_keys) > 1:
            msg = f"payload sets {' and '.join(input_keys)}, but takes one input key"
            raise ValueError(msg)
        value = body[input_keys[0]]
        if not isinstance(value, str) or not value:
            msg = f"{input_keys[0]} must be a non-empty string"
            raise ValueError(msg)
        storage_url = body.get("storage_url")
        if (
            isinstance(storage_url, str)
            and storage_url.endswith(".{{ extension }}")
            and "{{ job_id }}" not in storage_url
        ):
            msg = "a storage_url that ends in .{{ extension }} needs {{ job_id }}, because jobs that share an object name lose their uploads and still bill"
            raise ValueError(msg)

    @model_serializer
    def _body(self) -> dict[str, Any]:
        body = {
            name: value
            for name, value in self
            if value is not None and name not in {"context", "extra"}
        }
        extra = dict(self.extra)
        if context := [*(self.context or ()), *extra.pop("context", ())]:
            body["context"] = context
        return body | extra

    @override
    def __repr_args__(self) -> Iterator[tuple[str, Any]]:
        for name, value in self:
            if value is not None and (value or name != "extra"):
                yield name, _scrub(value)

    @classmethod
    @override
    def model_validate_json(
        cls, json_data: str | bytes | bytearray, **kwargs: Any
    ) -> Self:
        # An invalid document fails before `_scrub_errors` runs.
        try:
            return super().model_validate_json(json_data, **kwargs)
        except ValidationError as error:
            raise _scrubbed(error, "json") from None


SOURCES: tuple[type[Payload], ...] = ()
"""The source models that a billed run has checked; every other source runs through `Payload`."""


def _redacted(body: dict[str, Any]) -> dict[str, Any]:
    """Return `body` with the credentials in its `storage_url` replaced, as the API replaces them."""
    if "storage_url" in body:
        return body | {"storage_url": _scrub(body["storage_url"])}
    return body


def _scrub(value: object) -> object:
    """Return `value` with the credentials of each URL in it replaced by `redacted:redacted`."""
    if isinstance(value, str):
        return _CREDENTIALS.sub("redacted:redacted", value)
    if isinstance(value, dict):
        return {key: _scrub(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    return value


def _scrubbed(
    error: ValidationError,
    input_type: Literal["python", "json"],
    path: tuple[str, ...] = (),
) -> ValidationError:
    """Return `error` rebuilt with each input scrubbed and `path` before each location."""
    lines: list[InitErrorDetails] = []
    for line in error.errors():
        scrubbed: InitErrorDetails = {
            "type": line["type"],
            "loc": (*path, *line["loc"]),
            "input": _scrub(line["input"]),
        }
        if "ctx" in line:
            scrubbed["ctx"] = line["ctx"]
        lines.append(scrubbed)
    return ValidationError.from_exception_data(
        error.title, lines, input_type=input_type
    )
