import inspect
import io
import json
import logging
import math
import re
import sys
from pathlib import Path
from typing import Any

import anyio
import httpx2
import pytest
from typer.testing import CliRunner
from typing_extensions import override

import oxyscraper as oxy
from oxyscraper._cli import app, run
from oxyscraper._main import main
from oxyscraper._payloads import _INPUT_KEYS
from oxyscraper.testing import FakeOxylabs, Outcome, Rejected

SANDBOX = "https://sandbox.oxylabs.io"
# A wide terminal keeps Typer's error box from wrapping a message.
runner = CliRunner(
    env={
        "OXY_WSA_USERNAME": "USERNAME",
        "OXY_WSA_PASSWORD": "PASSWORD",
        "COLUMNS": "1000",
    }
)
NO_CREDENTIALS = {"OXY_WSA_USERNAME": None, "OXY_WSA_PASSWORD": None}
# Typer forces color when `GITHUB_ACTIONS` is set, so CI's stderr holds ANSI codes.
ANSI = re.compile(r"\x1b\[[0-9;]*m")


class Terminal(io.StringIO):
    """Stand in for a stdin that a person types into."""

    @override
    def isatty(self) -> bool:
        return True


def reject(payload: dict[str, Any]) -> Rejected:
    return Rejected("Unsupported source.")


def plain(text: str) -> str:
    return ANSI.sub("", text)


def lines(stdout: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stdout.splitlines()]


def submitted(fake: FakeOxylabs, *urls: str) -> list[str]:
    """Submit one Push-Pull job per URL, as an earlier run would, and return their IDs."""

    async def submit() -> list[str]:
        auth = ("USERNAME", "PASSWORD")
        async with httpx2.AsyncClient(transport=fake, auth=auth) as client:
            return [
                (
                    await client.post(
                        "https://data.oxylabs.io/v1/queries",
                        json={"source": "universal", "url": url},
                    )
                ).json()["id"]
                for url in urls
            ]

    return anyio.run(submit)


def test_run_prints_each_done_job(fake: FakeOxylabs) -> None:
    """`run` submits one Push-Pull job per input, and prints each done job's body as one line."""
    result = runner.invoke(app, ["run", "universal", f"{SANDBOX}/1", f"{SANDBOX}/2"])
    assert result.exit_code == 0, result.output
    printed = lines(result.stdout)
    assert [line["job"]["url"] for line in printed] == [f"{SANDBOX}/1", f"{SANDBOX}/2"]
    assert [line["job"]["id"] for line in printed] == [job["id"] for job in fake.jobs]
    assert all(line["results"][0]["content"] for line in printed)


def test_run_reads_inputs_from_stdin(fake: FakeOxylabs) -> None:
    """Without INPUT arguments, each non-empty line of stdin is one input, sent as `query` when it has no `://`."""
    result = runner.invoke(
        app,
        ["run", "amazon_product", "--realtime"],
        input="B07FZ8S74R\n\n B09B8V1LZ3 \n",
    )
    assert result.exit_code == 0, result.output
    assert [job["query"] for job in fake.jobs] == ["B07FZ8S74R", "B09B8V1LZ3"]


def test_run_input_key(fake: FakeOxylabs) -> None:
    """`-k` names the input key."""
    result = runner.invoke(
        app, ["run", "walmart_product", "436012154", "-k", "product_id", "--realtime"]
    )
    assert result.exit_code == 0, result.output
    assert fake.jobs[0]["product_id"] == "436012154"


def test_run_reads_payloads_from_stdin(fake: FakeOxylabs) -> None:
    """Without a source, each line of stdin is a payload in the API's shape, and the options apply to each."""
    payloads = [
        {"source": "universal", "url": f"{SANDBOX}/1"},
        {"source": "amazon_product", "query": "B07FZ8S74R", "domain": "de"},
    ]
    result = runner.invoke(
        app,
        ["run", "--realtime", "--user-agent-type", "mobile"],
        input="".join(json.dumps(payload) + "\n" for payload in payloads),
    )
    assert result.exit_code == 0, result.output
    assert [request.method for request in fake.requests] == ["POST", "POST"]
    assert [json.loads(request.content) for request in fake.requests] == [
        payload | {"user_agent_type": "mobile"} for payload in payloads
    ]


def test_run_options(fake: FakeOxylabs) -> None:
    """Each typed parameter has its own option, and `-p` sets any other as a string, or as JSON with `:=`."""
    result = runner.invoke(
        app,
        [
            "run",
            "google_search",
            "shoes",
            "--render",
            "html",
            "--parse",
            "--user-agent-type",
            "mobile",
            "--geo-location",
            "Germany",
            "--locale",
            "de-de",
            "--domain",
            "de",
            "--start-page",
            "2",
            "--pages",
            "3",
            "--limit",
            "10",
            "--no-markdown",
            "--xhr",
            "--parser-preset",
            "preset",
            "--content-encoding",
            "base64",
            "--client-notes",
            "notes",
            "--aggregate-name",
            "aggregate",
            "--callback-url",
            "https://example.com/callback",
            "-p",
            "tbm=isch",
            "-p",
            "nfpr:=true",
            "-p",
            'context:=[{"key": "results_language", "value": "de"}]',
            "--dry-run",
        ],
        env=NO_CREDENTIALS,
    )
    assert result.exit_code == 0, result.output
    assert lines(result.stdout) == [
        {
            "source": "google_search",
            "query": "shoes",
            "render": "html",
            "user_agent_type": "mobile",
            "callback_url": "https://example.com/callback",
            "parse": True,
            "start_page": 2,
            "pages": 3,
            "limit": 10,
            "markdown": False,
            "xhr": True,
            "parser_preset": "preset",
            "content_encoding": "base64",
            "client_notes": "notes",
            "aggregate_name": "aggregate",
            "geo_location": "Germany",
            "locale": "de-de",
            "domain": "de",
            "context": [{"key": "results_language", "value": "de"}],
            "tbm": "isch",
            "nfpr": True,
        }
    ]
    assert fake.requests == []


def test_dry_run(fake: FakeOxylabs) -> None:
    """`--dry-run` prints each payload with its secrets redacted, and the totals to stderr, with no credentials and no request."""
    result = runner.invoke(
        app,
        [
            "run",
            "universal",
            f"{SANDBOX}/1",
            f"{SANDBOX}/2",
            "--storage-type",
            "gcs",
            "--storage-url",
            "gs://key:secret@bucket/path",
            "--dry-run",
        ],
        env=NO_CREDENTIALS,
    )
    assert result.exit_code == 0, result.output
    assert [line["storage_url"] for line in lines(result.stdout)] == [
        "gs://redacted:redacted@bucket/path"
    ] * 2
    assert result.stderr == "Would submit 2 jobs, which bill at most 2 results\n"
    assert "secret" not in result.output
    assert fake.requests == []


def test_run_writes_to_a_destination(fake: FakeOxylabs, tmp_path: Path) -> None:
    """`-d` writes each done job to the destination instead of stdout, and `--run-log` writes the run log."""
    result = runner.invoke(
        app,
        [
            "run",
            "universal",
            f"{SANDBOX}/1",
            "--realtime",
            "-d",
            str(tmp_path / "results"),
            "--run-log",
            str(tmp_path / "logs"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    [job] = fake.jobs
    assert [path.name for path in (tmp_path / "results").iterdir()] == [
        f"{job['id']}.json"
    ]
    [log] = (tmp_path / "logs").iterdir()
    assert [line["state"] for line in lines(log.read_text())] == ["done"]


@pytest.mark.parametrize(
    ("check", "submissions"), [([], 2), (["--no-check-storage"], 1)]
)
def test_run_uploads(fake: FakeOxylabs, check: list[str], submissions: int) -> None:
    """An uploaded job prints nothing, and `--no-check-storage` submits every payload at once."""
    result = runner.invoke(
        app,
        [
            "run",
            "universal",
            f"{SANDBOX}/1",
            f"{SANDBOX}/2",
            "--storage-type",
            "gcs",
            "--storage-url",
            "gs://bucket/path",
            *check,
        ],
    )
    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    assert [request.method for request in fake.requests].count("POST") == submissions


@pytest.mark.parametrize("outcome", [Outcome(status="faulted"), reject])
def test_run_exits_1_when_a_payload_ends_without_a_done_job(outcome: Any) -> None:
    """A faulted job prints nothing, and it or a rejection makes the exit code 1."""
    with FakeOxylabs(outcome):
        result = runner.invoke(app, ["run", "universal", f"{SANDBOX}/1", "--realtime"])
    assert (result.exit_code, result.stdout) == (1, "")


@pytest.mark.parametrize(
    ("args", "stdin", "message"),
    [
        (["amazon_product", "B07FZ8S74R", "--domain", "xx"], None, "domain"),
        (["amazon_product", "B07FZ8S74R", "-p", "sort_bi=1"], None, "sort_bi"),
        (["universal", "-p", "nothing"], f"{SANDBOX}/1", "KEY=VALUE or KEY:=JSON"),
        (["universal", "-p", "pages:=two"], f"{SANDBOX}/1", "-p pages is not JSON"),
        (
            ["universal", f"{SANDBOX}/1", "--storage-type", "gcs", "-d", "results"],
            None,
            "storage_type",
        ),
        ([], "{nope", "line 1 is not JSON: Expecting property name"),
        ([], "[1]", "line 1 is not a JSON object"),
        ([], '{"source": ["universal"], "url": "x"}', "source"),
        (
            ["--parse"],
            json.dumps({"source": "universal", "url": f"{SANDBOX}/1", "parse": False}),
            "line 1 sets parse, and so does an option",
        ),
    ],
)
def test_run_exits_2_before_any_request(
    fake: FakeOxylabs, args: list[str], stdin: str | None, message: str
) -> None:
    """A mistake in an option, an input or a stdin line exits with code 2 and sends nothing."""
    result = runner.invoke(app, ["run", *args], input=stdin)
    assert result.exit_code == 2
    assert message in plain(result.stderr)
    assert fake.requests == []


@pytest.mark.parametrize(
    "args",
    [
        ["-p", "storage_url:=gs://key:secret@bucket/path"],
        ["-p", "storage_url=gs://key:secret@bucket/path", "-p", "oops"],
    ],
)
def test_run_errors_hold_no_credentials(args: list[str]) -> None:
    """An error from `-p` never prints the value it read."""
    result = runner.invoke(app, ["run", "universal", f"{SANDBOX}/1", *args])
    assert result.exit_code == 2
    assert "secret" not in result.output


def test_line_errors_hold_no_credentials() -> None:
    """An error from a stdin line that is not JSON never prints the line."""
    line = '{"source": "universal", "storage_url": "gs://key:secret@bucket/path",}'
    # Python 3.13 changed this error's message and column.
    with pytest.raises(json.JSONDecodeError) as caught:
        json.loads(line)
    error = caught.value
    result = runner.invoke(app, ["run"], input=line)
    assert result.exit_code == 2
    assert (
        f"line 1 is not JSON: {error.msg} at line {error.lineno} column {error.colno}"
        in plain(result.stderr)
    )
    assert "secret" not in result.output


def test_run_exits_2_with_storage_and_realtime(fake: FakeOxylabs) -> None:
    """A payload with `storage_type` and `--realtime` exits with code 2 and sends nothing."""
    result = runner.invoke(
        app,
        ["run", "universal", f"{SANDBOX}/1", "--storage-type", "gcs", "--realtime"],
    )
    assert result.exit_code == 2
    assert "realtime=True" in plain(result.stderr)
    assert fake.requests == []


@pytest.mark.parametrize(
    "command", [["run", "universal", f"{SANDBOX}/1"], ["get", "1"]]
)
def test_missing_credentials(fake: FakeOxylabs, command: list[str]) -> None:
    """A missing credential exits with code 2 and sends nothing."""
    result = runner.invoke(app, command, env={"OXY_WSA_PASSWORD": None})
    assert result.exit_code == 2
    assert "OXY_WSA_USERNAME and OXY_WSA_PASSWORD" in plain(result.stderr)
    assert fake.requests == []


@pytest.mark.parametrize("command", [["run", "universal"], ["run"], ["get"]])
def test_stdin_on_a_terminal(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: list[str],
) -> None:
    """A command with nothing to read on a terminal's stdin exits with code 2 instead of waiting for typed lines."""
    # `CliRunner` takes stdin only as text, which is never a terminal.
    monkeypatch.setattr(sys, "argv", ["oxy", *command])
    monkeypatch.setattr(sys, "stdin", Terminal())
    monkeypatch.setenv("COLUMNS", "1000")
    with pytest.raises(SystemExit) as exited:
        main()
    assert exited.value.code == 2
    assert "one per line of stdin" in plain(capsys.readouterr().err)


def test_run_with_empty_stdin(fake: FakeOxylabs) -> None:
    """Empty stdin runs no job and exits with code 0, so a pipe with nothing to resubmit succeeds."""
    result = runner.invoke(app, ["run"], input="")
    assert (result.exit_code, result.stdout, fake.requests) == (0, "", [])


@pytest.mark.parametrize("from_stdin", [False, True])
def test_get_prints_done_jobs(fake: FakeOxylabs, from_stdin: bool) -> None:
    """`get` prints each done job's body as one line, for IDs from arguments or stdin."""
    ids = submitted(fake, f"{SANDBOX}/1", f"{SANDBOX}/2")
    if from_stdin:
        result = runner.invoke(app, ["get"], input="\n".join(ids))
    else:
        result = runner.invoke(app, ["get", *ids])
    assert result.exit_code == 0, result.output
    assert [line["job"]["id"] for line in lines(result.stdout)] == ids


def test_get_warns_for_each_job_without_results(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A pending, faulted or expired job, or an error, prints a WARNING line with its ID, and the command goes on and exits with code 1."""
    outcomes = {
        "pending": Outcome(after=math.inf),
        "faulted": Outcome(status="faulted"),
        "expired": Outcome(expires_after=0),
        "done": Outcome(),
    }
    with FakeOxylabs(
        lambda payload: outcomes[payload["url"].rsplit("/", 1)[1]]
    ) as fake:
        ids = submitted(fake, *(f"{SANDBOX}/{name}" for name in outcomes))
        result = runner.invoke(app, ["get", *ids[:3], "404", ids[3]])
    assert result.exit_code == 1
    assert [line["job"]["id"] for line in lines(result.stdout)] == [ids[3]]
    assert [
        record.getMessage()
        for record in caplog.records
        if record.name == "oxyscraper" and record.levelno == logging.WARNING
    ] == [
        f"Job {ids[0]} is still pending: universal {SANDBOX}/pending",
        f"Job {ids[1]} faulted: universal {SANDBOX}/faulted",
        f"Job {ids[2]}'s results expired: universal {SANDBOX}/expired",
        "Fetching job 404 failed: 404 Query not found.",
    ]


def test_get_writes_to_a_destination(fake: FakeOxylabs, tmp_path: Path) -> None:
    """`get -d` writes each done job's body to the destination instead of stdout."""
    [job_id] = submitted(fake, f"{SANDBOX}/1")
    result = runner.invoke(app, ["get", job_id, "-d", str(tmp_path)])
    assert (result.exit_code, result.stdout) == (0, "")
    assert json.loads((tmp_path / f"{job_id}.json").read_text())["job"]["id"] == job_id


def test_run_has_an_option_for_each_payload_field() -> None:
    """`run` has an option for every `Payload` field but the source, the input keys and the JSON ones that `-p` sets."""
    json_fields = {"context", "parsing_instructions", "browser_instructions", "extra"}
    assert set(inspect.signature(run).parameters) >= (
        oxy.Payload.model_fields.keys() - {"source", *_INPUT_KEYS, *json_fields}
    )


def test_main_runs_the_app(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The entry point runs the commands when the `cli` extra is installed."""
    monkeypatch.setattr(sys, "argv", ["oxy", "--help"])
    with pytest.raises(SystemExit) as exited:
        main()
    assert exited.value.code == 0
    assert "Run Oxylabs Web Scraper API jobs" in capsys.readouterr().out


def test_main_without_the_cli_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without the `cli` extra, the entry point prints the command that installs it."""
    monkeypatch.setitem(sys.modules, "typer", None)
    monkeypatch.delitem(sys.modules, "oxyscraper._cli")
    with pytest.raises(
        SystemExit, match=re.escape("uv tool install 'oxyscraper[cli]'")
    ):
        main()
