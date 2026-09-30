# /// script
# requires-python = ">=3.11"
# dependencies = ["typer>=0.27", "rich>=15", "pydantic>=2.11", "httpx2>=2.13.1", "anyio>=4.15"]
# ///
"""PROTOTYPE, throwaway: oxy's command line and what it prints to stderr, to react to.

It answers [Prototype: the CLI's progress output](https://github.com/ozanozbeker/oxyscraper/issues/46), on the CLI of [Prototype: the CLI](https://github.com/ozanozbeker/oxyscraper/issues/19).
Each command opens the fake of `testing.py` itself, so nothing bills, and stderr copies the look of uv and ruff.
"""

# ruff: noqa: ANN401, ARG001, EM101, EM102, FBT002, PLR0913, PLR0917, PLR2004, S101, S301, SLF001, TRY003
# pyrefly: ignore-errors

import inspect
import itertools
import json
import logging
import math
import os
import pickle
import signal
import sys
import tempfile
import time
import zlib
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Any

import oxy_standin as oxy
import testing
import typer
from pydantic import ValidationError
from rich.console import Console
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text

USERNAME, PASSWORD = "OXY_WSA_USERNAME", "OXY_WSA_PASSWORD"
MODELS = {model.model_fields["source"].default: model for model in oxy.SOURCES}
# The source and input come from arguments, and `context` holds JSON, so no option sets them.
NO_OPTION = {"source", "context", *oxy.INPUT_KEYS}
PARAMETERS = "Parameters"
COLORS = {
    "done": "green",
    "faulted": "red",
    "rejected": "red",
    "unfetched": "yellow",
    "pending": "cyan",
    "unsubmitted": "dim",
}
logger = logging.getLogger("oxyscraper")

app = typer.Typer(
    help="Run Oxylabs Web Scraper API jobs.\n\nSet OXY_WSA_USERNAME and OXY_WSA_PASSWORD to the credentials of your Web Scraper API user.",
    no_args_is_help=True,
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)
Verbose = Annotated[
    bool,
    typer.Option(
        "-v", "--verbose", help="Log each job's change of state, and each retry."
    ),
]


class Terminated(KeyboardInterrupt):
    """SIGTERM, raised where Ctrl+C would be, so a stopped container still writes the run log."""


@app.command()
def run(
    source: Annotated[
        str | None,
        typer.Argument(
            help="The source, such as amazon_product. Without it, each line of stdin is a payload as JSON."
        ),
    ] = None,
    inputs: Annotated[
        list[str] | None,
        typer.Argument(help="One job each. Without any, each line of stdin is one."),
    ] = None,
    input_key: Annotated[
        oxy.InputKey | None,
        typer.Option(
            "-k",
            "--input-key",
            help="The parameter each INPUT goes in. Defaults to `url` for an INPUT with `://`, and `query` for any other.",
        ),
    ] = None,
    render: Annotated[
        oxy.Render | None,
        typer.Option(
            help="Render JavaScript, and return HTML or a screenshot.",
            rich_help_panel=PARAMETERS,
        ),
    ] = None,
    parse: Annotated[
        bool | None,
        typer.Option(
            help="Return parsed JSON, for a source with a parser.",
            rich_help_panel=PARAMETERS,
        ),
    ] = None,
    user_agent_type: Annotated[
        oxy.UserAgentType | None, typer.Option(rich_help_panel=PARAMETERS)
    ] = None,
    geo_location: Annotated[
        str | None, typer.Option(rich_help_panel=PARAMETERS)
    ] = None,
    locale: Annotated[str | None, typer.Option(rich_help_panel=PARAMETERS)] = None,
    domain: Annotated[
        str | None,
        typer.Option(
            help="The target's top-level domain, such as `de`.",
            rich_help_panel=PARAMETERS,
        ),
    ] = None,
    start_page: Annotated[
        int | None, typer.Option(min=1, rich_help_panel=PARAMETERS)
    ] = None,
    pages: Annotated[
        int | None,
        typer.Option(
            min=1, help="Pages per job. Each page bills.", rich_help_panel=PARAMETERS
        ),
    ] = None,
    storage_type: Annotated[
        oxy.StorageType | None,
        typer.Option(
            help="Upload each result to your bucket with Cloud Storage.",
            rich_help_panel=PARAMETERS,
        ),
    ] = None,
    storage_url: Annotated[
        str | None,
        typer.Option(
            help="The bucket and path that Cloud Storage uploads to.",
            rich_help_panel=PARAMETERS,
        ),
    ] = None,
    callback_url: Annotated[
        str | None, typer.Option(rich_help_panel=PARAMETERS)
    ] = None,
    params: Annotated[
        list[str] | None,
        typer.Option(
            "-p",
            "--param",
            metavar="KEY=VALUE",
            help="Set any other parameter. KEY:=JSON sets a value that is not a string.",
            rich_help_panel=PARAMETERS,
        ),
    ] = None,
    destination: Annotated[
        str | None,
        typer.Option(
            "-d",
            "--destination",
            help="Write each done job to DESTINATION/<job id>.json, instead of stdout.",
        ),
    ] = None,
    run_log: Annotated[
        str | None,
        typer.Option(
            metavar="DIR",
            help="Write DIR/<run start>.jsonl, with a line per payload that holds its state, job ID and payload.",
        ),
    ] = None,
    realtime: Annotated[
        bool, typer.Option("--realtime", help="Use Realtime instead of Push-Pull.")
    ] = False,
    check_storage: Annotated[
        bool,
        typer.Option(
            help="Submit one job per storage URL first, and the rest only if its upload works."
        ),
    ] = True,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Print each job's payload and the most results they can bill, and send nothing.",
        ),
    ] = False,
    verbose: Verbose = False,
) -> None:
    """Run jobs, and print or write each one as it finishes.

    Each done job prints to stdout as one line of JSON, the body the API returned.
    oxy's log lines go to stderr, above a live display of the run's progress on a terminal.
    """
    fields = {
        name: value
        for name, value in locals().items()
        if name in oxy.Payload.model_fields
    }
    shared = {
        name: value for name, value in fields.items() if value is not None
    } | _params(params or [])
    payloads = (
        _from_inputs(source, inputs or [], input_key, shared)
        if source
        else _from_json_lines(shared)
    )

    console = _logging(verbose=verbose)
    if dry_run:
        report = oxy.dry_run(payloads)
        for job in report.jobs:
            typer.echo(json.dumps(job))
        logger.info(
            "Would submit %s, which bill at most %s",
            oxy.plural(report.job_count, "job"),
            oxy.plural(report.max_results, "result"),
        )
        return

    signal.signal(signal.SIGTERM, _terminate)
    faulted = False
    incomplete: oxy.IncompleteRunError | None = None
    try:
        # On a terminal the live display shows progress, so oxy's periodic line would repeat it.
        with _session(
            progress_interval=None if console.is_terminal else 10.0
        ) as session:
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
            with _live(jobs, console):
                try:
                    for job in jobs:
                        if job.status == "faulted":
                            faulted = True
                        elif destination is None and job.upload is None:
                            typer.echo(json.dumps(_body(job), separators=(",", ":")))
                except oxy.IncompleteRunError as error:
                    incomplete = error
    except KeyboardInterrupt as stop:
        raise typer.Exit(143 if isinstance(stop, Terminated) else 130) from None
    cause = incomplete.__cause__ if incomplete else None
    if isinstance(cause, oxy.OxylabsError) and cause.status_code == 401:
        console.print(
            Text.assemble(
                ("hint", "bold cyan"),
                (":", "bold"),
                " Check ",
                (USERNAME, "green"),
                " and ",
                (PASSWORD, "green"),
                ", because the API returned 401",
            ),
            soft_wrap=True,
        )
    raise typer.Exit(1 if faulted or incomplete else 0)


# The parameter options are written out, so each keeps its Literal type, and this check stops them drifting from `Payload`.
assert (
    set(inspect.signature(run).parameters) >= set(oxy.Payload.model_fields) - NO_OPTION
)


@app.command()
def get(
    job_ids: Annotated[
        list[str] | None,
        typer.Argument(
            help="The IDs of the jobs. Without any, each line of stdin is one."
        ),
    ] = None,
    destination: Annotated[
        str | None,
        typer.Option(
            "-d",
            "--destination",
            help="Write each done job to DESTINATION/<job id>.json, instead of stdout.",
        ),
    ] = None,
    verbose: Verbose = False,
) -> None:
    """Print each done job as one line of JSON, the body the API returned."""
    _logging(verbose=verbose)
    folder = Path(destination) if destination else None
    if folder:
        folder.mkdir(parents=True, exist_ok=True)
    failed = False
    with _session(progress_interval=None) as session:
        for job_id in job_ids or _stdin():
            try:
                job = session.get(job_id)
            except oxy.OxylabsError as error:
                logger.warning("Job %s: %s", job_id, error)
                failed = True
                continue
            line = json.dumps(_body(job), separators=(",", ":"))
            if job.status != "done":
                status = "is still pending" if job.status == "pending" else "faulted"
                logger.warning(
                    "Job %s %s: %s", job.id, status, f"{job.source} {job.input}"
                )
                failed = True
            elif folder:
                (folder / f"{job.id}.json").write_text(line + "\n")
            else:
                typer.echo(line)
    raise typer.Exit(1 if failed else 0)


def _terminate(signum: int, frame: object) -> None:
    raise Terminated


class _Handler(logging.Handler):
    """Print each line as uv does: `warning:` before a warning, and info lines dim with their values in bold."""

    def __init__(self, console: Console) -> None:
        super().__init__()
        self.console = console

    def emit(self, record: logging.LogRecord) -> None:
        text = _values(record)
        if record.levelno >= logging.WARNING:
            text.stylize("bold")
            name, style = (
                ("error", "bold red")
                if record.levelno >= logging.ERROR
                else ("warning", "bold yellow")
            )
            text = Text.assemble((name, style), (":", "bold"), " ", text)
        elif record.levelno < logging.INFO:
            text = Text.assemble("debug: ", text)
            text.stylize("dim")
        else:
            text.stylize("dim")
        # The terminal wraps a long line, as it does for uv, and a file gets it whole.
        self.console.print(text, soft_wrap=True, highlight=False)


def _values(record: logging.LogRecord) -> Text:
    """Build the message with each `%s` value in bold, and each path in cyan."""
    pieces = str(record.msg).split("%s")
    if not isinstance(record.args, tuple) or len(pieces) != len(record.args) + 1:
        return Text(record.getMessage())
    text = Text(pieces[0])
    for value, piece in zip(record.args, pieces[1:], strict=True):
        text.append(str(value), style="cyan" if isinstance(value, Path) else "bold")
        text.append(piece)
    return text


def _logging(*, verbose: bool) -> Console:
    """Attach one stderr handler to the `oxyscraper` logger, and return its console."""
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logging.getLogger("httpx2").setLevel(logging.WARNING)
    # Off a terminal, rich drops the colors, as uv does.
    console = Console(stderr=True)
    logger.addHandler(_Handler(console))
    return console


@contextmanager
def _live(run: oxy.Run, console: Console) -> Iterator[None]:
    if not console.is_terminal:
        yield
        return
    # rich prints a redirected stdout through the stderr console, so JSON meant for a pipe would reach stderr.
    with Live(
        _Status(run),
        console=console,
        refresh_per_second=12.5,
        transient=True,
        redirect_stdout=sys.stdout.isatty(),
    ):
        yield


class _Status:
    """Draw uv's spinner and bar, then the counts, on one line that never wraps."""

    def __init__(self, run: oxy.Run) -> None:
        self.run = run
        self.spinner = Spinner("dots", style="cyan")

    def __rich__(self) -> Text:
        progress = self.run.progress
        text = Text.assemble(
            self.spinner.render(time.monotonic()),
            (" Running jobs ", "dim"),
            _bar(progress),
            " ",
            (f"{progress.done:,}/{progress.payloads:,}", "bold"),
            (" done", "dim"),
            no_wrap=True,
            overflow="ellipsis",
        )
        for state in ("faulted", "rejected", "unfetched", "pending", "unsubmitted"):
            if count := getattr(progress, state):
                text.append(", ", style="dim")
                text.append(f"{count:,}", style=f"bold {COLORS[state]}")
                text.append(f" {state}", style="dim")
        for count, label, style in (
            (progress.uploaded, "uploaded", "bold green"),
            (progress.unuploaded, "failed uploads", "bold red"),
            (progress.retries, "retries", "bold yellow"),
        ):
            if count:
                text.append(", ", style="dim")
                text.append(f"{count:,}", style=style)
                text.append(f" {label}", style="dim")
        text.append(f", {oxy.elapsed(progress.elapsed)}", style="dim")
        return text


def _bar(progress: oxy.Progress, width: int = 30) -> Text:
    """Draw uv's bar of dashes, in one color per state."""
    bar, position, total = Text(), 0, 0
    for state, color in COLORS.items():
        # Rounding the running total keeps the bar at `width`.
        total += getattr(progress, state)
        end = round(width * total / max(progress.payloads, 1))
        bar.append("-" * (end - position), style=color)
        position = end
    return bar


def _session(*, progress_interval: float | None) -> oxy.Session:
    username, password = os.environ.get(USERNAME, ""), os.environ.get(PASSWORD, "")
    if not username or not password:
        raise typer.BadParameter(
            f"set {USERNAME} and {PASSWORD} to the credentials of your Web Scraper API user"
        )
    return oxy.Session(
        username=username,
        password=password,
        progress_interval=progress_interval,
        # PROTOTYPE: a demo shortens the 10-minute pending limit.
        pending_limit=float(os.environ.get("OXY_DEMO_PENDING_LIMIT", "600")),
    )


def _from_inputs(
    source: str, inputs: list[str], input_key: str | None, shared: dict[str, Any]
) -> list[oxy.Payload]:
    model = MODELS.get(source, oxy.Payload)
    return [
        _build(
            model,
            value,
            {
                **shared,
                "source": source,
                input_key or ("url" if "://" in value else "query"): value,
            },
        )
        for value in inputs or _stdin()
    ]


def _from_json_lines(shared: dict[str, Any]) -> list[oxy.Payload]:
    payloads = []
    for number, line in enumerate(_stdin(), 1):
        body = json.loads(line)
        if clash := sorted(shared.keys() & body.keys()):
            raise typer.BadParameter(
                f"line {number} sets {', '.join(clash)}, and so does an option"
            )
        payloads.append(
            _build(
                MODELS.get(body.get("source"), oxy.Payload),
                f"line {number}",
                {**body, **shared},
            )
        )
    return payloads


def _build(model: type[oxy.Payload], label: str, data: dict[str, Any]) -> oxy.Payload:
    try:
        return model.model_validate(data)
    except ValidationError as error:
        problems = "; ".join(
            f"{'.'.join(map(str, e['loc'])) or 'payload'}: {e['msg']}"
            for e in error.errors()
        )
        raise typer.BadParameter(f"{label}: {problems}") from None


def _params(pairs: list[str]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep or not key:
            raise typer.BadParameter(
                f"{pair!r} is not KEY=VALUE or KEY:=JSON", param_hint="'-p'"
            )
        params[key.removesuffix(":")] = (
            json.loads(value) if key.endswith(":") else value
        )
    return params


def _stdin() -> list[str]:
    if sys.stdin.isatty():
        raise typer.BadParameter(
            "give each INPUT as an argument, or one per line on stdin"
        )
    return [line.strip() for line in sys.stdin if line.strip()]


def _body(job: oxy.Job) -> dict[str, Any]:
    return {"results": [result.data for result in job.results], "job": job.data}


# PROTOTYPE: everything below sets up the fake for a demo, and the real CLI has none of it.
STATE = Path(tempfile.gettempdir()) / "oxy-cli-progress-prototype"
DOMAIN_THROTTLE = (
    "Access to www.amazon.com has been limited to 1 req/s due to a low success rate."
)


class _DemoFake(testing.FakeOxylabs):
    """Decide each job from words in its input, keep jobs between commands, and fail requests for a while.

    `FAULT` faults, `FLAKY` faults on its first submission only, `SLOW` takes 8 seconds and `STUCK` never finishes.
    A `storage_url` with `wrong` fails its upload.
    `OXY_DEMO_FAIL` names a failure: `outage`, `throttle` or `domain-throttle`.
    """

    def __init__(self) -> None:
        super().__init__(self._outcome_of)
        self._opened = time.monotonic()
        self._mode = os.environ.get("OXY_DEMO_FAIL")
        self._tail = os.environ.get("OXY_DEMO_TAIL") == "1"
        if os.environ.get(PASSWORD) == "wrong":
            self.fail(401, times=None)

    def _outcome_of(self, payload: dict[str, Any]) -> testing.Outcome:
        value = next(str(payload[key]) for key in oxy.INPUT_KEYS if key in payload)
        spread = zlib.crc32(value.encode()) % 1000 / 1000
        # The sandbox and amazon_product jobs took 2 to 4 seconds live.
        after = 2 + 2 * spread
        if self._tail and spread < 0.05:
            after = 10 + 600 * spread
        if "SLOW" in value:
            after = 8.0
        if "STUCK" in value:
            after = math.inf
        again = any(
            record.payload.get("url") == value for record in self._records.values()
        )
        faulted = "FAULT" in value or ("FLAKY" in value and not again)
        return testing.Outcome(
            status="faulted" if faulted else "done",
            after=after,
            upload=13001 if "wrong" in payload.get("storage_url", "") else 13000,
            upload_after=3 + 8 * spread,
        )

    def _next_failure(self, endpoint: testing.Endpoint | None) -> Any:
        seconds = time.monotonic() - self._opened
        if self._mode == "outage" and 3 <= seconds < 23:
            return testing._Failure(503, None, None, None)
        if self._mode == "throttle" and endpoint == "submit" and 2 <= seconds < 12:
            return testing._Failure(429, "submit", None, None)
        if self._mode == "domain-throttle" and endpoint == "submit" and seconds >= 2:
            return testing._Failure(429, "submit", None, DOMAIN_THROTTLE)
        return super()._next_failure(endpoint)

    def load(self, path: Path) -> None:
        if path.exists():
            saved = pickle.loads(path.read_bytes())
            self._records, self._zero = saved["records"], saved["zero"]
            self._ids = itertools.count(saved["next_id"])

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        saved = {
            "records": self._records,
            "zero": self._zero,
            "next_id": next(self._ids),
        }
        path.write_bytes(pickle.dumps(saved))


if __name__ == "__main__":
    fake = _DemoFake()
    fake.load(STATE / "fake.pickle")
    try:
        with fake:
            app(prog_name="oxy")
    finally:
        fake.save(STATE / "fake.pickle")
