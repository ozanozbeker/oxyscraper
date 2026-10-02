import subprocess
import sys

import oxyscraper


def test_import() -> None:
    """The package imports."""
    assert oxyscraper.__name__ == "oxyscraper"


def test_import_loads_no_cli_packages() -> None:
    """`import oxyscraper` loads neither typer nor rich."""
    code = (
        "import sys, oxyscraper; print(sorted({'rich', 'typer'} & sys.modules.keys()))"
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert result.stdout == "[]\n"
