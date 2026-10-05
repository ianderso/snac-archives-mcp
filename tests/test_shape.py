"""Shaping SNAC records: identifiers, links, text, duplicates, names."""

from __future__ import annotations

import pytest

from snac_archives_mcp.shape import (
    ABSTRACT_LIMIT,
    ark,
    ark_for_api,
    ark_tail,
    clip,
    collection_detail,
    collection_summary,
    holding,
    link_kind,
    mark_duplicates,
    name_detail,
    name_summary,
    oclc_number,
    plain,
    repository,
    shared,
    snac_page,
    title_years,
)

from .conftest import fixture


@pytest.mark.parametrize(
    "value",
    [
        "ark:/99166/w6xj0ds0",
        "http://n2t.net/ark:/99166/w6xj0ds0",
        "https://snaccooperative.org/ark:/99166/w6xj0ds0",
        "w6xj0ds0",
        "  W6XJ0DS0 ",
    ],
)
def test_every_ark_form_reduces_to_the_same_tail(value):
    assert ark_tail(value) == "w6xj0ds0"
    assert ark(value) == "ark:/99166/w6xj0ds0"
    assert ark_for_api(value) == "http://n2t.net/ark:/99166/w6xj0ds0"
    assert snac_page(value) == "https://snaccooperative.org/ark:/99166/w6xj0ds0"


@pytest.mark.parametrize(
    "value", ["", None, "61583061", "ark:/12345/abc", "not an ark at all", "Anderson", "abcdef12"]
)
def test_a_non_ark_is_none(value):
    assert ark_tail(value) is None


def test_the_oclc_number_comes_from_the_link():
    assert oclc_number("http://www.worldcat.org/oclc/28048621") == "28048621"


def test_the_oclc_number_falls_back_to_the_mods_record_origin():
    source = "<recordInfo><recordOrigin>WorldCat:502156501</recordOrigin></recordInfo>"
    assert oclc_number("http://example.edu/ead/x.xml", source) == "502156501"


def test_no_oclc_number_is_none():
    assert oclc_number("http://example.edu/ead/x.xml", "<mods/>") is None


@pytest.mark.parametrize(
    ("link", "kind"),
    [
        ("http://www.worldcat.org/oclc/63938239", "worldcat"),
        ("http://nwda.orbiscascade.org/ark:/80444/xv88243", "aggregator"),
        ("http://rmc.library.cornell.edu/EAD/xml/dlxs/RMM00539.xml", "finding_aid"),
        (
            "http://dlib.nyu.edu/findingaids/html/bhs/arms_1977_345_davenport/x.html",
            "finding_aid",
        ),
        ("https://archives.example.edu/repositories/2/resources/88", "finding_aid"),
        ("http://finding-aids.lib.unc.edu/01255/", "finding_aid"),
        ("https://www.example.org/about", "other"),
        ("", "other"),
        (None, "other"),
    ],
)
def test_links_are_classified(link, kind):
    assert link_kind(link) == kind


@pytest.mark.parametrize(
    ("title", "years"),
    [
        ("Wilder and Anderson family papers, 1837-1938 [manuscript].", [1837, 1938]),
        ("Rankin-Davenport family papers, [ca. 1876]-1979.", [1876, 1979]),
        ("William D. Davenport. Family Papers, 1840(ca.)-1934.", [1840, 1934]),
        ("Davenport family papers Bulk, 1840-1899 1700-1915", [1700, 1915]),
        ("C.S. Lewis collection. [1939].", [1939]),
        ("Papers.", []),
        (None, []),
    ],
)
def test_title_years_are_the_outer_years(title, years):
    assert title_years(title) == years


def test_markup_and_entities_are_stripped():
    text = '<biogHist><p xmlns="urn:x">The Andersons &amp; the\n  Berrys</p></biogHist>'
    assert plain(text) == "The Andersons & the Berrys"


def test_clip_cuts_at_a_word_and_says_so():
    text, cut = clip("one two three four", 9)
    assert cut is True and text == "one two …"
    assert clip("short", 9) == ("short", False)


def test_the_repository_address_is_in_line_order():
    res = fixture("read_resource_7252207.json")["resource"]
    repo = repository(res["repository"])
    assert repo["name"] == "University of North Carolina at Chapel Hill"
    assert repo["ark"] == "ark:/99166/w6xj0ds0"
    assert repo["constellation_id"] == "76787443"
    assert repo["address_lines"][:3] == [
        "Davis Library, CB#3914, 208 Raleigh St.",
        "Chapel Hill",
        "US-NC",
    ]


def test_a_collection_summary_carries_its_identifiers():
    s = collection_summary(fixture("read_resource_7252207.json")["resource"])
    assert s["resource_id"] == "7252207"
    assert s["oclc_number"] == "28048621"
    assert s["link_kind"] == "worldcat"
    assert s["worldcat_url"] == "https://www.worldcat.org/oclc/28048621"
    assert s["archivegrid_url"].endswith("/archivegrid/collection/data/28048621")
    assert s["title_years"] == [1837, 1938]
    assert s["origination_names"] == ["Anderson family."]
    assert s["abstract_truncated"] is True
    assert len(s["abstract"]) <= ABSTRACT_LIMIT + 2


def test_a_collection_detail_keeps_the_whole_abstract():
    payload = fixture("read_resource_7252207.json")
    d = collection_detail(payload["resource"], payload["related_constellations"])
    assert d["abstract_truncated"] is False
    assert d["abstract"].endswith("Ga.") or len(d["abstract"]) > ABSTRACT_LIMIT
    assert d["document_type"] == "ArchivalResource"
    assert d["linked_names"] == []


def test_the_same_papers_catalogued_three_ways_are_flagged():
    results = fixture("resource_search_davenport.json")["results"]
    by_id = {s["resource_id"]: s for s in mark_duplicates([collection_summary(r) for r in results])}
    # Cornell: one WorldCat record and two harvested EAD files, under two names.
    assert sorted(by_id["7906246"]["possible_duplicate_of"]) == ["6400485", "6400535"]
    assert sorted(by_id["6400485"]["possible_duplicate_of"]) == ["6400535", "7906246"]
    # Oregon: the aggregator copy and the WorldCat record.
    assert by_id["6380320"]["possible_duplicate_of"] == ["7590908"]
    # Different papers that share a surname are left alone.
    assert by_id["7079513"]["possible_duplicate_of"] == []
    assert by_id["7003163"]["possible_duplicate_of"] == []


def test_a_name_search_hit():
    hit = name_summary(fixture("search_anderson_family.json")["results"][0])
    assert hit == {
        "constellation_id": "226833",
        "ark": "ark:/99166/w65z1cbf",
        "heading": "Anderson family.",
        "entity_type": "family",
        "collection_count": 1,
    }


def test_a_full_name_record_lists_collections_with_roles_and_related_names():
    payload = fixture("read_61583061_full.json")
    d = name_detail(payload["constellation"], maybe_same_count=0, full=True)
    assert d["heading"] == "Anderson family."
    assert d["places"] == [{"place": "Maine--Windham", "type": "AssociatedPlace"}]
    assert d["dates"][0]["from"] == "1790" and d["dates"][0]["to"] == "1942"
    [collection] = d["collections"]
    assert collection["role"] == "creatorOf"
    assert collection["oclc_number"] == "502156501"
    assert collection["repository"]["name"] == "Maine Historical Society Library"
    assert d["related_names_total"] == 14
    assert d["related_names"][0]["relation"] == "correspondedWith"
    assert d["biography"].startswith("The Andersons")


def test_a_summary_name_record_has_no_collection_lists():
    payload = fixture("read_61583061_summary.json")
    d = name_detail(payload["constellation"])
    assert "collections" not in d and "related_names" not in d


def test_identifier_links_come_through():
    d = name_detail(fixture("read_29260863_summary.json")["constellation"])
    assert "https://viaf.org/viaf/95218067" in d["same_as"]
    assert "Authors" in d["occupations"]


def test_the_biography_is_clipped_when_asked():
    d = name_detail(fixture("read_61583061_full.json")["constellation"], biography_limit=80)
    assert d["biography_truncated"] is True and len(d["biography"]) <= 82


def test_holdings_and_shared_rows():
    row = holding(fixture("get_holdings_mhs_first40.json")["resources"][0])
    assert row["oclc_number"] == "70973129" and row["linked_name_count"] == 1
    [both] = fixture("shared_resources.json")["resources"]
    s = shared(both)
    assert (s["role_of_first"], s["role_of_second"]) == ("referencedIn", "creatorOf")


@pytest.mark.parametrize(
    "func", [collection_summary, name_summary, holding, shared, repository, name_detail]
)
@pytest.mark.parametrize("junk", [None, "text", 7, [], {"id": 5, "nameEntries": "x", "places": 3}])
def test_malformed_input_never_raises(func, junk):
    func(junk)
