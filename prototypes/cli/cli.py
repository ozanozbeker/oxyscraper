# /// script
# requires-python = ">=3.11"
# dependencies = ["typer>=0.27", "pydantic>=2.11"]
# ///
"""PROTOTYPE, throwaway: oxy's command line, to react to.

It answers [Prototype: the CLI](https://github.com/ozanozbeker/oxyscraper/issues/19).
`fake_oxy` stands in for `oxyscraper`, so no command bills, and `tour.py` runs every scenario.
"""

# ruff: noqa: C901, EM101, EM102, FBT002, PLR0913, PLR0917, PLR2004, S101, TRY003
# pyrefly: ignore-errors

import inspect
import json
import os
import sys
import threading
import time
from typing import Annotated, Any

import fake_oxy as oxy
import typer
from pydantic import ValidationError

USERNAME, PASSWORD = "OXY_WSA_USERNAME", "OXY_WSA_PASSWORD"
MODELS = {model.model_fields["source"].default: model for model in oxy.SOURCES}
# The source and input come from arguments, and `context` holds JSON, so no option sets them.
NO_OPTION = {"source", "context", *oxy.INPUT_KEYS}
PARAMETERS = "Parameters"
SHOWN = 5

app = typer.Typer(
    help="Run Oxylabs Web Scraper API jobs.\n\nSet OXY_WSA_USERNAME and OXY_WSA_PASSWORD to the credentials of your Web Scraper API user.",
    no_args_is_help=True,
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)


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
            help="Write each done job to DESTINATION/<job id>.json, instead of stdout. A path, or a URL such as gs://bucket/prefix.",
        ),
    ] = None,
    checkpoint: Annotated[
        str | None,
        typer.Option(
            help="Where the run keeps its accepted jobs. Defaults to DESTINATION/_checkpoint."
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
) -> None:
    """Run jobs, and print or write each one as it finishes.

    Each done job prints to stdout as one line of JSON, the body the API returned.
    Progress and the summary go to stderr.
    Running the same command again resumes a run that did not finish, when it has a checkpoint.
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

    if dry_run:
        report = oxy.dry_run(payloads)
        for job in report.jobs:
            typer.echo(json.dumps(job))
        typer.echo(
            f"{report.job_count} jobs, {report.max_results} billed results at most. Sent nothing.",
            err=True,
        )
        return

    if checkpoint is None and destination is not None and not realtime:
        checkpoint = destination.rstrip("/") + "/_checkpoint"
    with _session() as session:
        try:
            jobs = session.execute(
                payloads,
                realtime=realtime,
                destination=destination,
                checkpoint=checkpoint,
                check_storage=check_storage,
            )
        except ValueError as error:
            raise typer.BadParameter(str(error)) from None
        status = _Status(jobs.progress) if sys.stderr.isatty() else None
        faulted: list[oxy.Job] = []
        incomplete: oxy.IncompleteRunError | None = None
        try:
            for job in jobs:
                if job.status == "faulted":
                    faulted.append(job)
                elif destination is None and job.upload is None:
                    typer.echo(json.dumps(_body(job), separators=(",", ":")))
        except oxy.IncompleteRunError as error:
            incomplete = error
        except KeyboardInterrupt:
            if status:
                status.stop()
            typer.echo("Stopped.", err=True)
            if checkpoint:
                typer.echo(
                    f"The checkpoint at {checkpoint} keeps the accepted jobs, so the same command resumes.",
                    err=True,
                )
            raise typer.Exit(130) from None
        if status:
            status.stop()
    _summary(jobs.progress, faulted, incomplete, destination, checkpoint)
    raise typer.Exit(1 if faulted or incomplete else 0)


# The parameter options are written out, so each keeps its Literal type, and this check stops them drifting from `Payload`.
assert (
    set(inspect.signature(run).parameters) >= set(oxy.Payload.model_fields) - NO_OPTION
)


@app.command()
def get(
    job_ids: Annotated[list[str], typer.Argument(help="The IDs of the jobs.")],
) -> None:
    """Print each job as one line of JSON, with its results once it has finished."""
    failed = False
    with _session() as session:
        for job_id in job_ids:
            try:
                job = session.get(job_id)
            except oxy.OxylabsError as error:
                typer.echo(f"{job_id}: {error}", err=True)
                failed = True
                continue
            typer.echo(json.dumps(_body(job), separators=(",", ":")))
            if job.status != "done":
                typer.echo(f"{job_id}: {job.status}", err=True)
                failed = True
    raise typer.Exit(1 if failed else 0)


class _Status:
    """Redraw one line on stderr from the run's counts, twice a second."""

    def __init__(self, progress: oxy.Progress) -> None:
        self.progress = progress
        self.stopped = threading.Event()
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self) -> None:
        while not self.stopped.wait(0.5):
            p = self.progress
            seconds = time.monotonic() - p.started
            line = f"{p.done} of {p.payloads} done, {p.faulted} faulted, {p.pending} pending, {seconds:.0f} s"
            typer.echo(f"\r\x1b[K{line}", err=True, nl=False)

    def stop(self) -> None:
        self.stopped.set()
        typer.echo("\r\x1b[K", err=True, nl=False)


def _summary(
    progress: oxy.Progress,
    faulted: list[oxy.Job],
    incomplete: oxy.IncompleteRunError | None,
    destination: str | None,
    checkpoint: str | None,
) -> None:
    def say(text: str) -> None:
        typer.echo(text, err=True)

    def listed(label: str, items: list[str]) -> None:
        if items:
            more = f", and {len(items) - SHOWN} more" if len(items) > SHOWN else ""
            say(f"{label}: {', '.join(items[:SHOWN])}{more}".rstrip(".") + ".")

    if progress.matched:
        say(
            f"Resumed from {checkpoint}: {progress.matched} payloads matched accepted jobs. "
            f"{progress.skipped} were already delivered, and {progress.resubmitted} went again because they faulted or failed."
        )
    seconds = time.monotonic() - progress.started
    counts = [f"{progress.done} done", f"{progress.faulted} faulted"]
    if incomplete:
        counts += [
            f"{len(incomplete.unuploaded)} with a failed upload",
            f"{len(incomplete.unfetched)} still pending",
            f"{len(incomplete.rejections)} rejected",
            f"{len(incomplete.unsubmitted)} not submitted",
        ]
    counted = ", ".join(count for count in counts if not count.startswith("0 "))
    say(f"{_n(progress.payloads, 'payload')} in {seconds:.1f} s: {counted}.")
    if progress.written:
        say(f"Wrote {_n(progress.written, 'file')} to {destination}.")
    if progress.uploaded:
        say(f"Cloud Storage uploaded {progress.uploaded} results.")
    listed("Faulted, so nothing billed", [f"{job.input} ({job.id})" for job in faulted])
    if incomplete:
        cause = incomplete.__cause__
        if isinstance(cause, oxy.OxylabsError) and cause.status_code == 401:
            say(
                f"Stopped, because the API returned 401. Check {USERNAME} and {PASSWORD}."
            )
        elif cause:
            say(f"Stopped, because of {cause}.")
        listed(
            "Still pending after 10 minutes",
            [f"{job.input} ({job.id})" for job in incomplete.unfetched],
        )
        listed(
            "Rejected",
            [
                f"{_input(rejection.payload)}: {rejection.status_code} {rejection.message}"
                for rejection in incomplete.rejections
            ],
        )
        listed(
            "Upload failed",
            [
                f"{job.input} ({job.id}): {job.upload.code} {job.upload.message}"
                for job in incomplete.unuploaded
            ],
        )
        listed("Not submitted", [_input(payload) for payload in incomplete.unsubmitted])
        if checkpoint:
            say(
                f"Kept the checkpoint at {checkpoint}, so the same command resumes this run."
            )


def _n(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"


def _session() -> oxy.Session:
    username, password = os.environ.get(USERNAME, ""), os.environ.get(PASSWORD, "")
    if not username or not password:
        raise typer.BadParameter(
            f"set {USERNAME} and {PASSWORD} to the credentials of your Web Scraper API user"
        )
    return oxy.Session(username=username, password=password)


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


def _input(payload: oxy.Payload) -> str:
    body = payload.to_api()
    return f"{body['source']} " + next(
        str(body[key]) for key in oxy.INPUT_KEYS if key in body
    )


if __name__ == "__main__":
    app(prog_name="oxy")
