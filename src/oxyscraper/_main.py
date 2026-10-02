"""The entry point that the `oxy` and `oxyscraper` commands run.

`[project.scripts]` installs both commands without the `cli` extra, so this module imports the CLI only inside `main`.
"""

import sys


def main() -> None:
    """Run the CLI, or print the command that installs the `cli` extra."""
    try:
        from oxyscraper._cli import app  # noqa: PLC0415
    except ImportError:
        sys.exit(
            "error: oxy's commands need the cli extra\n"
            "hint: Install it with `uv tool install 'oxyscraper[cli]'`"
        )
    app()
