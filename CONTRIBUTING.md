# Contributing

Issues and pull requests are welcome. This file says how the project is put
together and what a change is expected to carry.

## Setting up

```bash
git clone https://github.com/ianderso/snac-archives-mcp
cd snac-archives-mcp
uv sync --extra dev
```

Before sending a change, run what CI runs:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

The suite is mocked with [respx](https://lundberg.github.io/respx/) against
recorded SNAC responses. It must never touch the live API: SNAC is a free
service run by a small cooperative, and CI should not depend on it being up.

## Where things live

| Path | What it holds |
| --- | --- |
| `src/snac_archives_mcp/server.py` | The tools. Their docstrings and `Field` descriptions *are* the published tool descriptions and schema. |
| `src/snac_archives_mcp/client.py` | The cached, paced HTTP client, the host allowlist and the read-command allowlist. |
| `src/snac_archives_mcp/shape.py` | Turning SNAC records into compact results: identifiers, link classes, duplicates. |
| `src/snac_archives_mcp/archivegrid.py` | The ArchiveGrid query builder. Makes no request. |
| `src/snac_archives_mcp/config.py` | Settings from the environment and `.env`. |
| `docs/API-NOTES.md` | What the API was observed to do, and when. |
| `docs/DESIGN.md` | Why the server is shaped the way it is, and what is out of scope by decision. |
| `tests/fixtures/` | Recorded SNAC responses (CC0) and the tool-schema snapshot. |
| `tests/test_tool_contract.py` | Tests over the tool surface as a client sees it. |
| `tests/live_check.py` | The one script that talks to the live API, run by hand. Not collected. |

## What a change carries

**A test that fails without it.** Bug fixes especially: reproduce the bug as a
test first.

**Descriptions written for the model.** A tool's docstring is what a model
reads when choosing and calling it. The combined descriptions have a ceiling
(`DESCRIPTION_BUDGET` in `tests/test_tool_contract.py`), because they are sent
on every session. Raise it deliberately, in a pull request of its own.

**The evidence distinction, kept.** A collection description or a biographical
note is a finding aid, not evidence of what a document says. Tools that return
them say so; a contract test enforces it.

**A structured result, never an exception.** Every tool catches its failures
and returns an `error` envelope. A sweep test calls every tool with the API
failing and fails if one raises.

**Nothing that writes, and nothing that fetches ArchiveGrid.** See
[docs/DESIGN.md](docs/DESIGN.md#out-of-scope-by-decision).

**A new fixture recorded, not invented,** when a change depends on how SNAC
answers, with what was observed and when added to `docs/API-NOTES.md`. Keep
fixtures to historical records.

**The snapshot, when the surface changes.** Renaming or adding a tool or a
parameter fails the snapshot test on purpose. Regenerate it with
`uv run python -m tests.regen_tool_snapshot`, update the README tables, and add
a `CHANGELOG.md` entry.

## Releasing

A maintainer bumps `__version__` in `src/snac_archives_mcp/__init__.py` and
both versions in `server.json`, moves the changelog's Unreleased entries under
the new version, and publishes a GitHub release tagged `v<version>`. The
release workflow builds the tag, publishes to PyPI by Trusted Publishing, and
lists the version in the MCP Registry.
