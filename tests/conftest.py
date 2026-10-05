"""Shared fixtures. Every test runs against a mocked API; nothing touches SNAC.

The fixtures under ``fixtures/`` are real SNAC responses recorded on
2026-10-05 (see docs/API-NOTES.md), trimmed only where a list ran to
thousands of rows. SNAC's data is CC0. The records are historical: families
active 1790-1942, a nineteenth-century collection, and two authors who died
in 1963 and 1973.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from snac_archives_mcp import server
from snac_archives_mcp.client import SnacClient
from snac_archives_mcp.config import DEFAULT_API_URL, Config

FIXTURES = Path(__file__).parent / "fixtures"

#: Where every mocked request goes.
API = DEFAULT_API_URL


def fixture(name: str) -> dict:
    """Load one recorded SNAC response."""
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def body_of(request: httpx.Request) -> dict:
    """The JSON command a mocked request carried."""
    return json.loads(request.content)


def make_client(tmp_path: Path, **kwargs) -> SnacClient:
    """A client with no pacing and no back-off, caching under ``tmp_path``."""
    options = {"min_interval": 0.0, "backoff": 0.0}
    options.update(kwargs)
    return SnacClient(API, tmp_path / "cache", **options)


@pytest.fixture
def client(tmp_path) -> SnacClient:
    return make_client(tmp_path)


@pytest.fixture
def served(tmp_path, monkeypatch) -> SnacClient:
    """Install a fast test client as the server's client for the duration of a test."""
    c = make_client(tmp_path)
    monkeypatch.setattr(server.state, "client", c)
    monkeypatch.setattr(server.state, "config", Config(cache_dir=tmp_path / "cache"))
    return c


@pytest.fixture
def snac():
    """A respx router over the SNAC API. Any request it does not expect fails the test."""
    with respx.mock(assert_all_called=False, assert_all_mocked=True) as router:
        yield router


def route_commands(router: respx.MockRouter, answers: dict) -> respx.Route:
    """Answer each SNAC command from ``answers``, keyed by command name.

    A value is a dict (returned as JSON with 200), an ``httpx.Response``, or a
    callable taking the decoded body and returning either.
    """

    def respond(request: httpx.Request) -> httpx.Response:
        body = body_of(request)
        answer = answers.get(body.get("command"))
        if callable(answer):
            answer = answer(body)
        if answer is None:
            return httpx.Response(400, json={"error": {"message": f"unmocked {body}"}})
        if isinstance(answer, httpx.Response):
            return answer
        return httpx.Response(200, json=answer)

    return router.put(API).mock(side_effect=respond)


async def call_tool(tool_name: str, /, **arguments) -> dict:
    """Invoke a tool the way a client does, so Field defaults are resolved.

    The tool name is positional-only so a tool parameter called ``name`` cannot
    collide with it.
    """
    result = await server.mcp.call_tool(tool_name, arguments)
    return json.loads(result.content[0].text)


# --------------------------------------------------------------------------- #
# Argument building for whole-surface sweeps
# --------------------------------------------------------------------------- #
#: Errors a tool returns from its own input checks, before any work. A sweep
#: that gets one of these has not tested what it thinks it has.
LOCAL_VALIDATION_ERRORS = frozenset({"no_criteria", "invalid_id"})

#: Arguments that carry each tool past its own checks.
VALID_ARGS = {
    "search_collections": {"title_words": "Davenport family papers"},
    "get_collection": {"resource_id": "7252207"},
    "search_names": {"name": "Anderson family"},
    "get_name": {"name_id": "61583061"},
    "collections_in_common": {"first": "29260863", "second": "50307952"},
    "repository_holdings": {"repository": "87967572"},
    "archivegrid_search_link": {"family": "Anderson family"},
    "cache_status": {},
}


def assert_reached_body(tool_name: str, result) -> None:
    """Fail if a sweep stopped at input validation instead of the tool's body."""
    if isinstance(result, dict) and result.get("error") in LOCAL_VALIDATION_ERRORS:
        raise AssertionError(
            f"{tool_name} rejected the sweep's arguments with {result['error']!r}; "
            f"update VALID_ARGS in tests/conftest.py. Message: {result.get('message')!r}"
        )
