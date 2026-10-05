# oxyscraper

[![CI](https://github.com/ozanozbeker/oxyscraper/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/ozanozbeker/oxyscraper/actions/workflows/ci.yml) [![Codecov](https://codecov.io/gh/ozanozbeker/oxyscraper/graph/badge.svg)](https://codecov.io/gh/ozanozbeker/oxyscraper) [![PyPI](https://img.shields.io/pypi/v/oxyscraper)](https://pypi.org/project/oxyscraper/) [![Python](https://img.shields.io/pypi/pyversions/oxyscraper)](https://pypi.org/project/oxyscraper/) [![Typed](https://img.shields.io/pypi/types/oxyscraper)](https://pypi.org/project/oxyscraper/) [![License](https://img.shields.io/pypi/l/oxyscraper)](https://github.com/ozanozbeker/oxyscraper/blob/main/LICENSE) [![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff) [![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv) [![prek](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/j178/prek/master/docs/assets/badge-v0.json)](https://github.com/j178/prek) [![pyrefly](https://img.shields.io/badge/types-pyrefly-blue)](https://github.com/facebook/pyrefly) [![Built with Claude Code](https://img.shields.io/badge/Built_with-Claude_Code-D97757?logo=claude&logoColor=white)](https://claude.com/claude-code)

Unofficial Python library and CLI for the Oxylabs Web Scraper API.

## Install

Install the library:

```sh
uv add oxyscraper
```

Install the `oxy` command:

```sh
uv tool install 'oxyscraper[cli]'
```

## Credentials

The library and the CLI call the Web Scraper API (Classic), which takes the username and password of an API user.
The Oxylabs docs lead with their newer Web API, and a new account may hold only a Web API key.
The Classic API returns 401 for that key.

---

oxyscraper is not affiliated with or endorsed by Oxylabs.
Oxylabs and Oxy are trademarks of Oxylabs.
