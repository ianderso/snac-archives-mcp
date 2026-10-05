"""The client: what it sends, what it caches, how it paces and retries, and where it may go."""

from __future__ import annotations

import asyncio
import json
import time

import httpx
import pytest

from snac_archives_mcp import __version__
from snac_archives_mcp.client import (
    CACHE_DAYS,
    HOLDINGS_TIMEOUT,
    PROJECT_URL,
    HostNotAllowed,
    SnacApiError,
    user_agent,
)

from .conftest import API, body_of, fixture, make_client, route_commands


async def test_a_command_is_a_json_put_to_the_api_url(client, snac):
    route = route_commands(snac, {"read_resource": fixture("read_resource_7252207.json")})
    await client.command("read_resource", resourceid=7252207)
    request = route.calls.last.request
    assert request.method == "PUT"
    assert str(request.url) == API
    assert body_of(request) == {"command": "read_resource", "resourceid": 7252207}


async def test_none_parameters_are_dropped_from_the_body(client, snac):
    route = route_commands(snac, {"search": fixture("search_anderson_family.json")})
    await client.command("search", term="Anderson family", entity_type=None, count=5)
    assert body_of(route.calls.last.request) == {
        "command": "search",
        "term": "Anderson family",
        "count": 5,
    }


async def test_the_user_agent_names_the_project_and_version(client, snac):
    route = route_commands(snac, {"read_resource": fixture("read_resource_7252207.json")})
    await client.command("read_resource", resourceid=1)
    agent = route.calls.last.request.headers["user-agent"]
    assert agent == f"snac-archives-mcp/{__version__} (+{PROJECT_URL})"


def test_a_contact_is_appended_to_the_user_agent():
    assert user_agent("me@example.org").endswith(f"(+{PROJECT_URL}; me@example.org)")


async def test_an_edit_command_is_refused_before_anything_is_sent(client, snac):
    route = route_commands(snac, {})
    for name in ("insert_constellation", "update_resource", "publish_constellation", "merge"):
        with pytest.raises(ValueError):
            await client.command(name)
    assert route.call_count == 0


async def test_a_request_to_another_host_is_refused(client):
    with pytest.raises(HostNotAllowed):
        await client._http.get("https://researchworks.oclc.org/archivegrid/")


async def test_a_repeat_is_served_from_the_cache(client, snac):
    route = route_commands(snac, {"read_resource": fixture("read_resource_7252207.json")})
    first = await client.command("read_resource", resourceid=7252207)
    second = await client.command("read_resource", resourceid=7252207)
    assert first == second
    assert route.call_count == 1
    assert (client.live_calls, client.cache_hits) == (1, 1)


async def test_parameter_order_does_not_split_the_cache(client, snac):
    route = route_commands(snac, {"search": fixture("search_anderson_family.json")})
    await client.command("search", term="Anderson family", count=5)
    await client.command("search", count=5, term="Anderson family")
    assert route.call_count == 1


async def test_refresh_asks_again_and_replaces_the_copy(client, snac):
    answers = iter([{"total": 1, "results": []}, {"total": 2, "results": []}])
    route = route_commands(snac, {"resource_search": lambda body: next(answers)})
    await client.command("resource_search", term="x")
    fresh = await client.command("resource_search", term="x", refresh=True)
    again = await client.command("resource_search", term="x")
    assert fresh["total"] == 2 and again["total"] == 2
    assert route.call_count == 2


def _age_cache(client, days: float) -> None:
    for entry in client.cache_dir.glob("*.json"):
        data = json.loads(entry.read_text())
        data["stored"] = time.time() - days * 86_400
        entry.write_text(json.dumps(data))


async def test_a_search_expires_after_the_cache_period(client, snac):
    route = route_commands(snac, {"resource_search": {"total": 0, "results": []}})
    await client.command("resource_search", term="x")
    _age_cache(client, CACHE_DAYS + 1)
    await client.command("resource_search", term="x")
    assert route.call_count == 2


async def test_a_collection_record_never_expires(client, snac):
    route = route_commands(snac, {"read_resource": fixture("read_resource_7252207.json")})
    await client.command("read_resource", resourceid=7252207)
    _age_cache(client, CACHE_DAYS * 10)
    await client.command("read_resource", resourceid=7252207)
    assert route.call_count == 1


async def test_an_unreadable_cache_entry_is_fetched_again(client, snac):
    route = route_commands(snac, {"read_resource": fixture("read_resource_7252207.json")})
    await client.command("read_resource", resourceid=7252207)
    for entry in client.cache_dir.glob("*.json"):
        entry.write_text("{truncated")
    await client.command("read_resource", resourceid=7252207)
    assert route.call_count == 2


async def test_a_404_is_an_error_carrying_snacs_message(client, snac):
    route_commands(snac, {"read": httpx.Response(404, json=fixture("read_missing_404.json"))})
    with pytest.raises(SnacApiError) as caught:
        await client.command("read", constellationid=1)
    assert caught.value.status == 404
    assert "does not have a published version" in caught.value.detail


async def test_a_failure_is_not_cached(client, snac):
    answers = iter(
        [
            httpx.Response(404, json=fixture("read_missing_404.json")),
            fixture("read_61583061_summary.json"),
        ]
    )
    route_commands(snac, {"read": lambda body: next(answers)})
    with pytest.raises(SnacApiError):
        await client.command("read", constellationid=61583061)
    assert (await client.command("read", constellationid=61583061))["result"] == "success"


async def test_an_error_inside_a_200_is_still_an_error(client, snac):
    route_commands(snac, {"search": {"result": "failure", "error": {"message": "bad facet"}}})
    with pytest.raises(SnacApiError) as caught:
        await client.command("search", term="x")
    assert caught.value.status == 400 and caught.value.detail == "bad facet"
    assert list(client.cache_dir.glob("*.json")) == []


async def test_a_429_is_retried(client, snac):
    answers = iter([httpx.Response(429), httpx.Response(429), {"total": 0, "results": []}])
    route = route_commands(snac, {"resource_search": lambda body: next(answers)})
    assert (await client.command("resource_search", term="x"))["total"] == 0
    assert route.call_count == 3


async def test_a_5xx_that_persists_gives_up_after_the_retries(tmp_path, snac):
    client = make_client(tmp_path, retries=2)
    route = route_commands(snac, {"search": httpx.Response(503, text="down")})
    with pytest.raises(SnacApiError) as caught:
        await client.command("search", term="x")
    assert caught.value.status == 503
    assert route.call_count == 3


async def test_a_4xx_other_than_429_is_not_retried(client, snac):
    route = route_commands(snac, {"search": httpx.Response(400, json={"error": {"message": "no"}})})
    with pytest.raises(SnacApiError):
        await client.command("search", term="x")
    assert route.call_count == 1


async def test_no_response_at_all_is_status_zero(tmp_path, snac):
    client = make_client(tmp_path, retries=1)
    snac.put(API).mock(side_effect=httpx.ConnectTimeout("timed out"))
    with pytest.raises(SnacApiError) as caught:
        await client.command("search", term="x")
    assert caught.value.status == 0
    assert "ConnectTimeout" in caught.value.detail


async def test_requests_are_spaced_by_the_minimum_interval(tmp_path, snac):
    now = [100.0]
    waits: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        waits.append(seconds)
        now[0] += seconds

    client = make_client(tmp_path, min_interval=1.0, clock=lambda: now[0], sleep=fake_sleep)
    route_commands(snac, {"search": {"total": 0, "results": []}})
    await client.command("search", term="a")
    now[0] += 0.25
    await client.command("search", term="b")
    assert waits == [pytest.approx(0.75)]


async def test_identical_concurrent_calls_share_one_request(client, snac):
    gate = asyncio.Event()

    async def slow(request):
        await gate.wait()
        return httpx.Response(200, json=fixture("read_resource_7252207.json"))

    route = snac.put(API).mock(side_effect=slow)
    first = asyncio.create_task(client.command("read_resource", resourceid=7252207))
    second = asyncio.create_task(client.command("read_resource", resourceid=7252207))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    gate.set()
    assert await first == await second
    assert route.call_count == 1
    assert client.shared_waits == 1


async def test_holdings_get_the_longer_timeout(client, snac):
    route = route_commands(snac, {"get_holdings": fixture("get_holdings_mhs_first40.json")})
    await client.command("get_holdings", constellationid=87967572)
    timeouts = route.calls.last.request.extensions["timeout"]
    assert timeouts["read"] == HOLDINGS_TIMEOUT


async def test_the_cache_key_includes_the_api_url(tmp_path, snac):
    a = make_client(tmp_path)
    b = make_client(tmp_path)
    b._url = "https://test.snaccooperative.org/"
    assert a._key({"command": "search"}) != b._key({"command": "search"})
