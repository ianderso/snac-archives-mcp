"""The tools, called as a client calls them, against recorded SNAC answers."""

from __future__ import annotations

import httpx
import pytest

from snac_archives_mcp import server
from snac_archives_mcp.config import ConfigError

from .conftest import body_of, call_tool, fixture, route_commands


async def test_search_collections_pages_with_start_and_counts_pages(served, snac):
    route = route_commands(snac, {"resource_search": fixture("resource_search_davenport.json")})
    result = await call_tool(
        "search_collections", title_words="  Davenport   family papers ", count=4, page=2
    )
    assert body_of(route.calls.last.request) == {
        "command": "resource_search",
        "term": "Davenport family papers",
        "count": 4,
        "start": 4,
    }
    assert (result["total"], result["page"], result["pages"], result["next_page"]) == (10, 2, 3, 3)
    assert result["returned"] == len(result["collections"]) == 10
    assert result["collections"][0]["possible_duplicate_of"]


async def test_search_collections_needs_words(served, snac):
    route = route_commands(snac, {})
    assert (await call_tool("search_collections", title_words="  "))["error"] == "no_criteria"
    assert route.call_count == 0


async def test_count_is_clamped(served, snac):
    route = route_commands(snac, {"resource_search": fixture("resource_search_wilder.json")})
    await call_tool("search_collections", title_words="x", count=500, page=-3)
    body = body_of(route.calls.last.request)
    assert (body["count"], body["start"]) == (50, 0)


async def test_get_collection(served, snac):
    route_commands(snac, {"read_resource": fixture("read_resource_7252207.json")})
    result = await call_tool("get_collection", resource_id=" 7252207 ")
    assert result["oclc_number"] == "28048621"
    assert result["repository"]["ark"] == "ark:/99166/w6xj0ds0"


@pytest.mark.parametrize("bad", ["abc", "72522O7", "-1", "7252207; drop", "²"])
async def test_get_collection_refuses_a_non_numeric_id(served, snac, bad):
    route = route_commands(snac, {})
    assert (await call_tool("get_collection", resource_id=bad))["error"] == "invalid_id"
    assert route.call_count == 0


async def test_search_names_passes_type_and_biography_flag(served, snac):
    route = route_commands(snac, {"search": fixture("search_anderson_family.json")})
    result = await call_tool(
        "search_names",
        name="Anderson family",
        entity_type="family",
        search_biographies=True,
        count=5,
    )
    assert body_of(route.calls.last.request) == {
        "command": "search",
        "term": "Anderson family",
        "entity_type": "family",
        "biog_hist": True,
        "start": 0,
        "count": 5,
    }
    assert result["total"] == 468 and result["pages"] == 94
    assert result["names"][0]["ark"] == "ark:/99166/w65z1cbf"


async def test_search_names_omits_unset_filters(served, snac):
    route = route_commands(snac, {"search": fixture("search_anderson_family.json")})
    await call_tool("search_names", name="Anderson family")
    body = body_of(route.calls.last.request)
    assert "entity_type" not in body and "biog_hist" not in body


async def test_an_entity_type_outside_the_list_is_refused(served, snac):
    from mcp.server.mcpserver.exceptions import ToolError

    route = route_commands(snac, {})
    with pytest.raises(ToolError):
        await server.mcp.call_tool("search_names", {"name": "x", "entity_type": "organisation"})
    assert route.call_count == 0


async def test_get_name_by_id_asks_for_a_summary(served, snac):
    route = route_commands(snac, {"read": fixture("read_61583061_summary.json")})
    result = await call_tool("get_name", name_id="61583061")
    assert body_of(route.calls.last.request) == {
        "command": "read",
        "constellationid": 61583061,
        "type": "summary",
    }
    assert result["heading"] == "Anderson family." and "collections" not in result


async def test_get_name_by_ark_full(served, snac):
    route = route_commands(snac, {"read": fixture("read_61583061_full.json")})
    result = await call_tool("get_name", name_id="ark:/99166/w6wn08wd", detail="full")
    assert body_of(route.calls.last.request) == {
        "command": "read",
        "arkid": "http://n2t.net/ark:/99166/w6wn08wd",
    }
    assert result["collections"][0]["role"] == "creatorOf"


async def test_get_name_reports_a_split_record(served, snac):
    split = fixture("read_61583061_summary.json")
    split["constellation"] = [split["constellation"], split["constellation"]]
    route_commands(snac, {"read": split})
    result = await call_tool("get_name", name_id="61583061")
    assert result["split"] is True and len(result["records"]) == 2


async def test_get_name_not_found(served, snac):
    route_commands(snac, {"read": httpx.Response(404, json=fixture("read_missing_404.json"))})
    result = await call_tool("get_name", name_id="1")
    assert result["error"] == "not_found"


@pytest.mark.parametrize("bad", ["", "ark:/12345/x", "Anderson family", "../../etc"])
async def test_get_name_refuses_what_is_not_an_identifier(served, snac, bad):
    route = route_commands(snac, {})
    assert (await call_tool("get_name", name_id=bad))["error"] == "invalid_id"
    assert route.call_count == 0


async def test_collections_in_common_resolves_arks_first(served, snac):
    route = route_commands(
        snac,
        {
            "read": fixture("read_29260863_summary.json"),
            "shared_resources": fixture("shared_resources.json"),
        },
    )
    result = await call_tool(
        "collections_in_common", first="ark:/99166/w61r7qfw", second="50307952"
    )
    commands = [body_of(c.request)["command"] for c in route.calls]
    assert commands == ["read", "shared_resources"]
    assert body_of(route.calls.last.request) == {
        "command": "shared_resources",
        "icid1": 29260863,
        "icid2": 50307952,
    }
    assert result["collections"][0]["title"] == "C.S. Lewis collection. [1939]."


async def test_repository_holdings_filters_and_pages_locally(served, snac):
    route = route_commands(snac, {"get_holdings": fixture("get_holdings_mhs_first40.json")})
    everything = await call_tool("repository_holdings", repository="87967572", count=10, page=2)
    assert everything["holdings_total"] == 40
    assert (everything["total"], everything["pages"], everything["next_page"]) == (40, 4, 3)
    assert len(everything["collections"]) == 10
    filtered = await call_tool(
        "repository_holdings", repository="87967572", title_contains="DRAFTS"
    )
    assert filtered["total"] >= 1
    assert all("drafts" in c["title"].lower() for c in filtered["collections"])
    assert route.call_count == 1, "the holdings list is fetched once and filtered from the cache"


async def test_rate_limiting_is_reported_as_such_not_as_empty(served, snac):
    route_commands(snac, {"search": httpx.Response(429)})
    result = await call_tool("search_names", name="x")
    assert result["error"] == "rate_limited"
    assert "says nothing about whether" in result["message"]


async def test_an_outage_is_reported_as_such(served, snac):
    route_commands(snac, {"resource_search": httpx.Response(502, text="bad gateway")})
    result = await call_tool("search_collections", title_words="x")
    assert result["error"] == "upstream_error"


async def test_a_bad_setting_surfaces_on_the_first_call(monkeypatch):
    monkeypatch.setattr(server.state, "client", None)

    def broken():
        raise ConfigError("SNAC_TIMEOUT must be a number; got 'sixty'.")

    monkeypatch.setattr(server, "load_config", broken)
    result = await call_tool("search_names", name="x")
    assert result == {
        "error": "not_configured",
        "message": "SNAC_TIMEOUT must be a number; got 'sixty'.",
    }


async def test_cache_status_counts(served, snac):
    route_commands(snac, {"read_resource": fixture("read_resource_7252207.json")})
    await call_tool("get_collection", resource_id="7252207")
    await call_tool("get_collection", resource_id="7252207")
    status = await call_tool("cache_status")
    assert (status["live_calls_this_session"], status["cache_hits_this_session"]) == (1, 1)
