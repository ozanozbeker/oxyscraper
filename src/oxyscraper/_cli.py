"""The Typer app of `oxy run` and `oxy get`, which call `Session`.

Only `_main.main` imports it, so `import oxyscraper` loads neither typer nor rich.
Typer evaluates the commands' annotations at runtime, so the module leaves out `from __future__ import annotations`, because under it ruff moves annotation-only imports into a `TYPE_CHECKING` block.
"""

import json
import logging
import os
import signal
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from typing import Annotated, Any, Literal, NoReturn, cast

import obstore
import typer
from pydantic import ValidationError
from rich.console import Console
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text
from typer._click.exceptions import NoArgsIsHelpError, UsageError
from typer.core import TyperGroup
from typing_extensions import override

import oxyscraper as oxy
from oxyscraper._payloads import _InputKey, _UserAgentType
from oxyscraper._sessions import _counted, _ShownPath, _store

_USERNAME = "OXY_WSA_USERNAME"
_PASSWORD = "OXY_WSA_PASSWORD"  # noqa: S105
_MODELS = {model.model_fields["source"].default: model for model in oxy.SOURCES}
_PARAMETERS = "Parameters"
_UNAUTHORIZED = 401
_COLORS = {
    "done": "green",
    "faulted": "red",
    "rejected": "red",
    "unfetched": "yellow",
    "pending": "cyan",
    "unsubmitted": "dim",
}
_logger = logging.getLogger("oxyscraper")
# Off a terminal, rich prints no color, as uv does.
_console = Console(stderr=True)


class _Terminated(BaseException):
    """SIGTERM, raised where Ctrl+C raises `KeyboardInterrupt`.

    It is no `KeyboardInterrupt`, because Typer turns one into exit code 130 before `_Group.main` sees it.
    """


class _Group(TyperGroup):
    """Print usage errors as uv does, and stop on SIGTERM as on Ctrl+C."""

    @override
    def main(self, *args: Any, **kwargs: Any) -> NoReturn:
        with _attached():
            try:
                # Typer's standalone mode prints a usage error in a box, so `main` catches it instead.
                code = super().main(*args, standalone_mode=False, **kwargs)
            except _Terminated:
                code = 143
            except NoArgsIsHelpError as error:
                # Typer printed the help when it built the error.
                code = error.exit_code
            except UsageError as error:
                _print(
                    _prefixed(
                        "error", "bold red", error.format_message().removesuffix(".")
                    )
                )
                if error.ctx is not None:
                    _print(Text(f"\n{error.ctx.get_usage()}"))
                code = error.exit_code
        sys.exit(code)


app = typer.Typer(
    help=f"Run Oxylabs Web Scraper API jobs.\n\nSet {_USERNAME} and {_PASSWORD} to the credentials of your Web Scraper API user.",
    cls=_Group,
    no_args_is_help=True,
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)

_Destination = Annotated[
    str | None,
    typer.Option(
        "-d",
        "--destination",
        help="Write each done job to DESTINATION/<job ID>.json instead of stdout. A URL such as gs://bucket/path names a bucket.",
    ),
]


@app.command()
def run(  # noqa: PLR0913, PLR0917
    source: Annotated[
        str | None,
        typer.Argument(
            help="The source, such as amazon_product. Without it, each line of stdin is a payload as JSON in the API's shape."
        ),
    ] = None,
    inputs: Annotated[
        list[str] | None,
        typer.Argument(help="One job each. Without any, each line of stdin is one."),
    ] = None,
    input_key: Annotated[
        _InputKey | None,
        typer.Option(
            "-k",
            "--input-key",
            help="The parameter each INPUT goes in. Defaults to url for an INPUT with ://, and query for any other.",
        ),
    ] = None,
    render: Annotated[
        Literal["html", "png", ""] | None,
        typer.Option(
            help="Render the page in a browser, or turn off forced rendering with an empty value.",
            rich_help_panel=_PARAMETERS,
        ),
    ] = None,
    parse: Annotated[
        bool | None,
        typer.Option(
            help="Return parsed content, which needs a parser.",
            rich_help_panel=_PARAMETERS,
        ),
    ] = None,
    user_agent_type: Annotated[
        _UserAgentType | None,
        typer.Option(
            help="The device of the job's user agent.", rich_help_panel=_PARAMETERS
        ),
    ] = None,
    geo_location: Annotated[
        str | None,
        typer.Option(
            help="The location the job appears to come from.",
            rich_help_panel=_PARAMETERS,
        ),
    ] = None,
    locale: Annotated[
        str | None,
        typer.Option(help="The language of the page.", rich_help_panel=_PARAMETERS),
    ] = None,
    domain: Annotated[
        str | None,
        typer.Option(
            help="The target's domain, such as de for amazon.de.",
            rich_help_panel=_PARAMETERS,
        ),
    ] = None,
    start_page: Annotated[
        int | None,
        typer.Option(
            min=1, help="The first page to fetch.", rich_help_panel=_PARAMETERS
        ),
    ] = None,
    pages: Annotated[
        int | None,
        typer.Option(
            min=1,
            help="The number of pages to fetch, each billed as one result.",
            rich_help_panel=_PARAMETERS,
        ),
    ] = None,
    limit: Annotated[
        int | None,
        typer.Option(
            help="The number of results on each page.", rich_help_panel=_PARAMETERS
        ),
    ] = None,
    markdown: Annotated[
        bool | None,
        typer.Option(
            help="Make Markdown the default output type.", rich_help_panel=_PARAMETERS
        ),
    ] = None,
    xhr: Annotated[
        bool | None,
        typer.Option(
            help="Make the page's Fetch and XHR requests the default output type.",
            rich_help_panel=_PARAMETERS,
        ),
    ] = None,
    parser_preset: Annotated[
        str | None,
        typer.Option(
            help="The parser preset to parse with.", rich_help_panel=_PARAMETERS
        ),
    ] = None,
    content_encoding: Annotated[
        Literal["base64", "utf-8"] | None,
        typer.Option(
            help="Return an image as Base64 text with base64.",
            rich_help_panel=_PARAMETERS,
        ),
    ] = None,
    client_notes: Annotated[
        str | None,
        typer.Option(
            help="Text that the API saves with the job.", rich_help_panel=_PARAMETERS
        ),
    ] = None,
    aggregate_name: Annotated[
        str | None,
        typer.Option(
            help="The Result Aggregator that receives the result.",
            rich_help_panel=_PARAMETERS,
        ),
    ] = None,
    callback_url: Annotated[
        str | None,
        typer.Option(
            help="The URL that the API calls when the job finishes.",
            rich_help_panel=_PARAMETERS,
        ),
    ] = None,
    storage_type: Annotated[
        Literal["gcs", "s3", "tos", "s3_compatible"] | None,
        typer.Option(
            help="Upload each result to your bucket with Cloud Storage.",
            rich_help_panel=_PARAMETERS,
        ),
    ] = None,
    storage_url: Annotated[
        str | None,
        typer.Option(
            help="The bucket path that Cloud Storage uploads to.",
            rich_help_panel=_PARAMETERS,
        ),
    ] = None,
    params: Annotated[
        list[str] | None,
        typer.Option(
            "-p",
            "--param",
            metavar="KEY=VALUE",
            help="Set any other parameter as a string. KEY:=JSON sets a JSON value, such as context:='[...]'.",
            rich_help_panel=_PARAMETERS,
        ),
    ] = None,
    destination: _Destination = None,
    run_log: Annotated[
        str | None,
        typer.Option(
            metavar="DIR",
            help="Write DIR/<run start>.jsonl, with a line per payload that holds its state, job ID and payload.",
        ),
    ] = None,
    realtime: Annotated[  # noqa: FBT002
        bool, typer.Option("--realtime", help="Use Realtime instead of Push-Pull.")
    ] = False,
    check_storage: Annotated[  # noqa: FBT002
        bool,
        typer.Option(
            help="Submit one job per storage URL first, and the rest once its upload works."
        ),
    ] = True,
    dry_run: Annotated[  # noqa: FBT002
        bool,
        typer.Option(
            "--dry-run",
            help="Print each payload and the most results they can bill, and send nothing.",
        ),
    ] = False,
    verbose: Annotated[  # noqa: FBT002
        bool,
        typer.Option(
            "-v",
            "--verbose",
            help="Print each change of a job's state, and each retry.",
        ),
    ] = False,
) -> None:
    """Run jobs, and print each done job as one line of JSON, the body the API returned."""
    # Each option that `Payload` types has the field's name, so `locals()` maps them.
    shared = {
        name: value
        for name, value in locals().items()
        if name in oxy.Payload.model_fields and value is not None
    } | _params(params or [])
    payloads = (
        _from_inputs(source, inputs or _stdin(), input_key, shared)
        if source
        else _from_lines(_stdin(), shared)
    )
    if verbose:
        _logger.setLevel(logging.DEBUG)
    if dry_run:
        report = oxy.dry_run(payloads)
        for job in report.jobs:
            typer.echo(json.dumps(job))
        _logger.info(
            "Would submit %s, which bill at most %s",
            _counted(report.job_count, "job"),
            _counted(report.max_results, "result"),
        )
        return
    failed = unauthorized = False
    terminal = _console.is_terminal
    # On a terminal the live line shows the progress, so the periodic line would repeat it.
    with _session(progress_interval=None if terminal else 10.0) as session:
        try:
            jobs = session.execute(
                payloads,
                realtime=realtime,
                destination=destination,
                run_log=run_log,
                check_storage=check_storage,
            )
        except ValueError as error:
            raise typer.BadParameter(str(error)) from None
        try:
            with _live(jobs) if terminal else nullcontext():
                for job in jobs:
                    if job.status == "faulted":
                        failed = True
                    elif destination is None and job.upload is None:
                        typer.echo(_line(job))
        except oxy.IncompleteRunError as error:
            failed = True
            cause = error.__cause__
            unauthorized = (
                isinstance(cause, oxy.OxylabsError)
                and cause.status_code == _UNAUTHORIZED
            )
    _exit(failed=failed, unauthorized=unauthorized)


@app.command()
def get(
    job_ids: Annotated[
        list[str] | None,
        typer.Argument(help="The jobs' IDs. Without any, each line of stdin is one."),
    ] = None,
    destination: _Destination = None,
) -> None:
    """Print each done job as one line of JSON, the body the API returned."""
    job_ids = job_ids or _stdin()
    store = None if destination is None else _store(destination)
    failed = unauthorized = False
    with _session() as session:
        for job_id in job_ids:
            try:
                job = session.get(job_id)
            except oxy.OxylabsError as error:
                _logger.warning("Fetching job %s failed: %s", job_id, error)
                failed = True
                unauthorized = unauthorized or error.status_code == _UNAUTHORIZED
                continue
            if warning := _unprinted(job):
                _logger.warning(warning, job.id, job.source, job.input)
                failed = True
            elif store is None:
                typer.echo(_line(job))
            else:
                obstore.put(store, f"{job.id}.json", _line(job).encode())
    _exit(failed=failed, unauthorized=unauthorized)


def _exit(*, failed: bool, unauthorized: bool) -> None:
    if unauthorized:
        _print(
            _prefixed(
                "hint",
                "bold cyan",
                f"Check {_USERNAME} and {_PASSWORD}, because the API returned 401",
            )
        )
    if failed:
        raise typer.Exit(1)


def _session(*, progress_interval: float | None = 10.0) -> oxy.Session:
    username, password = os.environ.get(_USERNAME), os.environ.get(_PASSWORD)
    if not username or not password:
        msg = f"set {_USERNAME} and {_PASSWORD} to the credentials of your Web Scraper API user"
        raise typer.BadParameter(msg)
    return oxy.Session(
        username=username, password=password, progress_interval=progress_interval
    )


@contextmanager
def _attached() -> Iterator[None]:
    """Attach the stderr handler and the SIGTERM handler, and undo both on exit, because `CliRunner` runs the app many times in one process."""
    httpx2_logger = logging.getLogger("httpx2")
    levels = _logger.level, httpx2_logger.level
    handler = _Handler()
    _logger.addHandler(handler)
    _logger.setLevel(logging.INFO)
    httpx2_logger.setLevel(logging.WARNING)
    sigterm = signal.signal(signal.SIGTERM, _terminate)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, sigterm)
        _logger.removeHandler(handler)
        _logger.setLevel(levels[0])
        httpx2_logger.setLevel(levels[1])


def _terminate(_signum: int, _frame: object) -> NoReturn:
    raise _Terminated


class _Handler(logging.Handler):
    """Print each line as uv does: a warning bold after `warning:`, an info line dim, and a debug line dim after `debug:`."""

    @override
    def emit(self, record: logging.LogRecord) -> None:
        text = _values(record)
        if record.levelno >= logging.WARNING:
            text.stylize("bold")
            text = _prefixed("warning", "bold yellow", text)
        elif record.levelno >= logging.INFO:
            text.stylize("dim")
        else:
            text = Text.assemble("debug: ", text, style="dim")
        _print(text)


def _values(record: logging.LogRecord) -> Text:
    """Build the message with each `%s` value in bold, and each path in cyan."""
    pieces = str(record.msg).split("%s")
    args = record.args if isinstance(record.args, tuple) else ()
    if len(pieces) != len(args) + 1:
        return Text(record.getMessage())
    text = Text(pieces[0])
    for value, piece in zip(args, pieces[1:], strict=True):
        text.append(
            str(value), style="cyan" if isinstance(value, _ShownPath) else "bold"
        )
        text.append(piece)
    return text


def _prefixed(name: str, style: str, text: str | Text) -> Text:
    return Text.assemble((name, style), (":", "bold"), " ", text)


def _print(text: Text) -> None:
    # The terminal wraps a long line, as it does for uv, and a file gets it whole.
    _console.print(text, soft_wrap=True, highlight=False)


@contextmanager
def _live(run: oxy.Run) -> Iterator[None]:
    """Draw the live line, and redraw it 12.5 times a second until the block exits."""
    spinner = Spinner("dots", style="cyan")
    stopped = threading.Event()
    # rich prints a redirected stdout through the stderr console, so it redirects only a terminal's stdout, never a pipe's.
    with Live(
        _status(run.progress, spinner),
        console=_console,
        auto_refresh=False,
        transient=True,
        redirect_stdout=sys.stdout.isatty(),
    ) as live:
        # Live's own thread renders under its lock, and `run.progress` waits for the portal's thread, which may wait for that lock to print a log line.
        def redraw() -> None:
            while not stopped.wait(0.08):
                live.update(_status(run.progress, spinner), refresh=True)

        thread = threading.Thread(target=redraw, daemon=True)
        thread.start()
        try:
            yield
        finally:
            stopped.set()
            thread.join()


def _status(progress: oxy.Progress, spinner: Spinner) -> Text:
    """Draw the spinner, `Running jobs`, the bar and the counts on one line, cut off at the terminal's width."""
    # A spinner without text renders as `Text`.
    frame = cast("Text", spinner.render(time.monotonic()))
    text = Text.assemble(
        frame,
        (" Running jobs ", "dim"),
        _bar(progress),
        " ",
        no_wrap=True,
        overflow="ellipsis",
    )
    *counts, elapsed = str(progress).split(", ")
    for count in counts:
        number, name = count.split(" ", 1)
        text.append(number, style="bold")
        text.append(f" {name}, ", style="dim")
    text.append(elapsed, style="dim")
    return text


def _bar(progress: oxy.Progress, width: int = 30) -> Text:
    """Draw a bar of `width` dashes, with one color per state."""
    bar, end, total = Text(), 0, 0
    for state, color in _COLORS.items():
        total += getattr(progress, state)
        # Rounding the running total keeps the bar at `width`.
        start, end = end, round(width * total / max(progress.payloads, 1))
        bar.append("-" * (end - start), style=color)
    return bar


def _stdin() -> list[str]:
    """Return the non-empty lines of stdin, or raise on a terminal, where reading would wait for typed lines."""
    if sys.stdin.isatty():
        msg = "pass arguments, or pipe them in one per line of stdin"
        raise typer.BadParameter(msg)
    return [stripped for line in sys.stdin if (stripped := line.strip())]


def _from_inputs(
    source: str, inputs: list[str], input_key: str | None, shared: dict[str, Any]
) -> list[oxy.Payload]:
    model = _MODELS.get(source, oxy.Payload)
    return [
        _build(
            model,
            f"input {value}",
            {
                **shared,
                "source": source,
                input_key or ("url" if "://" in value else "query"): value,
            },
        )
        for value in inputs
    ]


def _from_lines(lines: list[str], shared: dict[str, Any]) -> list[oxy.Payload]:
    payloads = []
    for number, line in enumerate(lines, 1):
        label = f"line {number}"
        body = _json(line, label)
        if not isinstance(body, dict):
            msg = f"{label} is not a JSON object"
            raise typer.BadParameter(msg)
        if clash := sorted(shared.keys() & body.keys()):
            msg = f"{label} sets {', '.join(clash)}, and so does an option"
            raise typer.BadParameter(msg)
        source = body.get("source")
        model = (
            _MODELS.get(source, oxy.Payload) if isinstance(source, str) else oxy.Payload
        )
        payloads.append(_build(model, label, body | shared))
    return payloads


def _build(model: type[oxy.Payload], label: str, data: dict[str, Any]) -> oxy.Payload:
    try:
        return model.model_validate(data)
    except ValidationError as error:
        problems = "; ".join(
            f"{'.'.join(map(str, problem['loc'])) or 'payload'}: {problem['msg']}"
            for problem in error.errors()
        )
        msg = f"{label}: {problems}"
        raise typer.BadParameter(msg) from None


def _params(pairs: list[str]) -> dict[str, Any]:
    """Read each `-p KEY=VALUE` as a string, and each `-p KEY:=JSON` as JSON."""
    params: dict[str, Any] = {}
    for pair in pairs:
        key, equals, value = pair.partition("=")
        name = key.removesuffix(":")
        if not equals or not name:
            # The pair can hold a storage_url's credentials, so the message leaves it out.
            msg = "each -p takes KEY=VALUE or KEY:=JSON"
            raise typer.BadParameter(msg)
        params[name] = _json(value, f"-p {name}") if key.endswith(":") else value
    return params


def _json(text: str, label: str) -> object:
    """Read `text` as JSON, with an error that leaves out the text, which can hold a storage_url's credentials."""
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        msg = f"{label} is not JSON: {error.msg} at line {error.lineno} column {error.colno}"
        raise typer.BadParameter(msg) from None


def _unprinted(job: oxy.Job) -> str | None:
    """Return the warning for a job that has no results to print, or `None` if it has them."""
    if job.status == "pending":
        return "Job %s is still pending: %s %s"
    if job.status == "faulted":
        return "Job %s faulted: %s %s"
    return None if job.results else "Job %s's results expired: %s %s"


def _line(job: oxy.Job) -> str:
    """Return the body that held the job's results, as one line of JSON."""
    return json.dumps(
        {"results": [result.data for result in job.results], "job": job.data},
        separators=(",", ":"),
    )
