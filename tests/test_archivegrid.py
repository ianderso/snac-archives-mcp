"""The ArchiveGrid link builder: ArchiveGrid's own syntax, and never a network call."""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from snac_archives_mcp.archivegrid import build_query, search_url

from .conftest import call_tool


def test_the_help_page_examples_encode_exactly():
    """ArchiveGrid's "How to search" page gives these two addresses."""
    assert search_url(build_query(person="einstein")).endswith("?p=1&q=person.name%3Aeinstein")
    assert search_url(build_query(topic="women education")).endswith(
        "?p=1&q=topic.name%3A%22women+education%22"
    )


def test_fields_are_joined_with_and_in_a_fixed_order():
    q = build_query(place="Lincoln County (N.C.)", family="Davenport family", archive="UNC")
    assert q == (
        'person.name:"Davenport family" AND place.name:"Lincoln County (N.C.)" AND archive:UNC'
    )


def test_exclusions_become_not_and_flags_are_appended():
    q = build_query(
        keywords="ledger", exclude=["Iowa", "New York"], source_type="ead", has_links=True
    )
    assert q == 'ledger AND type:ead AND has_links:1 NOT Iowa NOT "New York"'


def test_stray_quotes_cannot_break_out_of_a_phrase():
    assert build_query(person='Smith "the elder"') == 'person.name:"Smith the elder"'


def test_keywords_pass_through_so_operators_still_work():
    assert build_query(keywords='"Crothers" OR "Carothers"') == '"Crothers" OR "Carothers"'


async def test_the_tool_returns_a_url_and_makes_no_request(snac):
    result = await call_tool("archivegrid_search_link", family="Anderson family", location="Maine")
    assert snac.calls.call_count == 0
    query = parse_qs(urlsplit(result["url"]).query)
    assert query == {"p": ["1"], "q": ['person.name:"Anderson family" AND location:Maine']}
    assert "does not fetch" in result["explanation"]


async def test_an_oclc_number_gives_the_record_and_worldcat_links(snac):
    result = await call_tool("archivegrid_search_link", oclc_number="28048621")
    assert result["url"] == "https://researchworks.oclc.org/archivegrid/collection/data/28048621"
    assert result["worldcat_url"] == "https://www.worldcat.org/oclc/28048621"
    assert snac.calls.call_count == 0


async def test_a_bad_oclc_number_is_refused():
    result = await call_tool("archivegrid_search_link", oclc_number="28048621x")
    assert result["error"] == "invalid_id"


async def test_exclusions_alone_are_not_a_search():
    assert (await call_tool("archivegrid_search_link", exclude=["Iowa"]))["error"] == "no_criteria"
    assert (await call_tool("archivegrid_search_link"))["error"] == "no_criteria"
