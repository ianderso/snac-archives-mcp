"""Contract tests over the registered MCP tool surface.

These assert properties of the tools *as a client sees them*: their names,
their JSON schema, their annotations, and the size of the description block
shipped on every session. The rest of the suite exercises the client and the
shaping, which means a ``Field`` typo or a dropped docstring could change the
published contract without failing a single test.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import httpx
import respx
from mcp.server.mcpserver.exceptions import ToolError

from snac_archives_mcp import __version__, server
from snac_archives_mcp.server import mcp

from .conftest import API, VALID_ARGS, assert_reached_body, call_tool

SNAPSHOT = Path(__file__).parent / "fixtures" / "tool_schema.json"
README = Path(__file__).parent.parent / "README.md"

#: Ceiling on the combined tool descriptions, which are sent to the model on
#: every session before any work happens. Raise it deliberately, not by accident.
DESCRIPTION_BUDGET = 4_000

#: Tools that touch no network at all.
LOCAL_TOOLS = {"archivegrid_search_link", "cache_status"}

#: Words that would mean a tool changes something somewhere.
WRITE_WORDS = re.compile(r"(^|_)(insert|update|edit|publish|delete|merge|add|create|write)(_|$)")


async def _tools() -> list:
    return sorted(await mcp.list_tools(), key=lambda t: t.name)


def _params(tool) -> dict:
    return (tool.input_schema or {}).get("properties", {}) or {}


async def test_every_tool_has_a_description():
    assert [t.name for t in await _tools() if not (t.description or "").strip()] == []


async def test_every_parameter_has_a_description():
    undocumented = [
        f"{t.name}.{name}"
        for t in await _tools()
        for name, spec in _params(t).items()
        if not (spec.get("description") or "").strip()
    ]
    assert undocumented == []


async def test_no_parameter_leaks_a_python_repr():
    leaked = [
        t.name
        for t in await _tools()
        if "FieldInfo" in json.dumps(t.input_schema)
        or "PydanticUndefined" in json.dumps(t.input_schema)
    ]
    assert leaked == []


async def test_tool_names_and_parameters_match_the_snapshot():
    """Renaming a tool or a parameter breaks callers; make it a visible diff.

    Regenerate deliberately with ``uv run python -m tests.regen_tool_snapshot``.
    """
    current = {t.name: sorted(_params(t)) for t in await _tools()}
    assert current == json.loads(SNAPSHOT.read_text())


async def test_every_tool_appears_in_the_readme_and_the_count_is_right():
    doc = README.read_text()
    names = {t.name for t in await _tools()}
    documented = set(re.findall(r"\| `([a-z_]+)`", doc))
    assert names <= documented, f"not in the README: {sorted(names - documented)}"
    assert documented - names == set(), (
        f"README documents removed tools: {sorted(documented - names)}"
    )
    words = {8: "eight"}
    assert f"publishes {words.get(len(names), len(names))} tools" in doc


async def test_description_block_stays_within_budget():
    total = sum(len(t.description or "") for t in await _tools())
    assert total <= DESCRIPTION_BUDGET, f"descriptions total {total}, over {DESCRIPTION_BUDGET}"


async def test_required_parameters_have_no_default():
    wrong = [
        f"{t.name}.{name}"
        for t in await _tools()
        for name in (t.input_schema or {}).get("required", [])
        if "default" in _params(t)[name]
    ]
    assert wrong == []


async def test_finding_aid_tools_say_a_hit_is_not_the_evidence():
    """The evidence distinction must be in the description the model acts on."""
    for name in ("search_collections", "get_collection"):
        [tool] = [t for t in await _tools() if t.name == name]
        text = tool.description.lower()
        assert "finding aid" in text and "cite" in text, name
    [get_name] = [t for t in await _tools() if t.name == "get_name"]
    assert "not to cite" in get_name.description
    assert "never" in mcp.instructions and "instructions" in mcp.instructions


async def test_the_archivegrid_tool_says_not_to_fetch():
    [tool] = [t for t in await _tools() if t.name == "archivegrid_search_link"]
    assert "never fetch" in tool.description.lower()
    assert "never fetch archivegrid" in mcp.instructions.lower()


async def test_no_tool_offers_to_write():
    assert [t.name for t in await _tools() if WRITE_WORDS.search(t.name)] == []


async def test_every_tool_is_annotated_read_only():
    for tool in await _tools():
        assert tool.annotations is not None, tool.name
        assert tool.annotations.read_only_hint is True, tool.name
        assert tool.annotations.open_world_hint is (tool.name not in LOCAL_TOOLS), tool.name


async def test_no_tool_raises_when_the_api_fails(served):
    """Every failure must come back as an envelope; a tool that raises kills the call."""
    with respx.mock(assert_all_mocked=True) as router:
        router.put(API).mock(return_value=httpx.Response(500, json={"error": "boom"}))
        for tool in await _tools():
            out = await call_tool(tool.name, **VALID_ARGS[tool.name])
            assert isinstance(out, dict), tool.name
            assert_reached_body(tool.name, out)
            if tool.name not in LOCAL_TOOLS:
                assert out.get("error") == "upstream_error", f"{tool.name} returned {out}"


async def test_every_tool_refuses_a_parameter_it_does_not_define(served):
    accepted = []
    # Should the refusal regress, the tools run for real; keep them offline.
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        router.put(API).mock(return_value=httpx.Response(200, json={}))
        for tool in await _tools():
            try:
                await mcp.call_tool(tool.name, {**VALID_ARGS[tool.name], "not_a_parameter": "x"})
            except ToolError as exc:
                assert "not_a_parameter" in str(exc), tool.name
                continue
            accepted.append(tool.name)
    assert accepted == []


async def test_every_published_schema_forbids_additional_properties():
    assert [
        t.name for t in await _tools() if t.input_schema.get("additionalProperties") is not False
    ] == []


async def test_no_schema_carries_an_auto_generated_title():
    def titles(node, path=""):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "title" and isinstance(value, str) and not path.endswith("properties"):
                    yield path
                yield from titles(value, f"{path}/{key}")
        elif isinstance(node, list):
            for i, value in enumerate(node):
                yield from titles(value, f"{path}/{i}")

    found = [f"{t.name}{p}" for t in await _tools() for p in titles(t.input_schema)]
    assert found == []


async def test_a_parameter_named_title_survives_compaction():
    [tool] = [t for t in await _tools() if t.name == "archivegrid_search_link"]
    assert "title" in _params(tool)


def test_compaction_and_refusal_are_idempotent():
    assert server.compact_schemas() == 0
    assert server.refuse_unknown_arguments() == 0


def test_the_server_reports_its_own_version():
    assert mcp.version == __version__
