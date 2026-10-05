"""Turning SNAC's records into compact, citable results.

SNAC records are verbose and uneven: every term carries an id, a URI and a
type; a repository's address is a list of ordered lines; a collection's link
may point at WorldCat, at the repository's own finding aid or at a regional
aggregator. These functions keep what a researcher acts on -- what the
collection is, who holds it, and the identifiers that find it again -- and
drop the rest.

Every function here accepts a malformed record without raising. A field that
is missing or the wrong type comes back empty.
"""

from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import urlsplit

#: SNAC's ARK prefix. Every SNAC name record has an ARK under it.
ARK_PREFIX = "ark:/99166/"

#: Characters of a collection abstract kept in a search result.
ABSTRACT_LIMIT = 400

#: Characters of a biographical note kept by default.
BIOGRAPHY_LIMIT = 2_000

#: Related names returned by ``get_name(detail="full")``.
RELATED_NAMES_LIMIT = 50

_ARK_TAIL = re.compile(r"(?:ark:/)?99166/([a-z0-9]+)/?$", re.IGNORECASE)
# SNAC mints its ARKs as "w6" plus six characters; a bare value must look like one,
# so that a plain word such as "Anderson" is never taken for an identifier.
_BARE_ARK = re.compile(r"w6[a-z0-9]{5,8}", re.IGNORECASE)
_OCLC_IN_LINK = re.compile(r"worldcat\.org/(?:oclc|title)/(\d+)", re.IGNORECASE)
_OCLC_IN_SOURCE = re.compile(r"WorldCat:\s*(\d+)")
_YEAR = re.compile(r"(?<!\d)(1[0-9]{3}|20[0-9]{2})(?!\d)")
_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


# --------------------------------------------------------------------------- #
# Identifiers
# --------------------------------------------------------------------------- #
def ark_tail(value: object) -> str | None:
    """The final segment of a SNAC ARK, or None if the value is not one.

    Accepts ``ark:/99166/w6xj0ds0``, the ``http://n2t.net/ark:/99166/...``
    form SNAC returns, the ``https://snaccooperative.org/ark:/99166/...``
    page address, or the bare ``w6xj0ds0``.
    """
    text = str(value or "").strip()
    if match := _ARK_TAIL.search(text):
        return match.group(1).lower()
    if _BARE_ARK.fullmatch(text):
        return text.lower()
    return None


def ark(value: object) -> str | None:
    """A SNAC ARK in its short, citable form: ``ark:/99166/<tail>``."""
    tail = ark_tail(value)
    return f"{ARK_PREFIX}{tail}" if tail else None


def ark_for_api(value: object) -> str | None:
    """A SNAC ARK in the ``http://n2t.net/...`` form the ``read`` command takes."""
    tail = ark_tail(value)
    return f"http://n2t.net/{ARK_PREFIX}{tail}" if tail else None


def snac_page(value: object) -> str | None:
    """The address of a name's page on the SNAC website."""
    tail = ark_tail(value)
    return f"https://snaccooperative.org/{ARK_PREFIX}{tail}" if tail else None


def oclc_number(link: object = None, source: object = None) -> str | None:
    """The WorldCat OCLC number of a collection, from its link or its MODS source.

    The link is the usual place. A record whose link points at a finding aid
    can still name its WorldCat origin inside the MODS record
    (``<recordOrigin>WorldCat:28048621</recordOrigin>``).
    """
    if isinstance(link, str) and (match := _OCLC_IN_LINK.search(link)):
        return match.group(1)
    if isinstance(source, str) and (match := _OCLC_IN_SOURCE.search(source)):
        return match.group(1)
    return None


def worldcat_url(oclc: str | None) -> str | None:
    """WorldCat's page for an OCLC number."""
    return f"https://www.worldcat.org/oclc/{oclc}" if oclc else None


def archivegrid_record_url(oclc: str | None) -> str | None:
    """ArchiveGrid's record page for an OCLC number. Built, never fetched."""
    return f"https://researchworks.oclc.org/archivegrid/collection/data/{oclc}" if oclc else None


def link_kind(link: object) -> str:
    """Classify a collection link: ``worldcat``, ``finding_aid``, ``aggregator`` or ``other``.

    A WorldCat link is a catalogue record. A regional aggregator (Archives
    West and its predecessor NWDA, OAC, ArchiveGrid) indexes many
    repositories' finding aids. A link to an EAD file, an ArchivesSpace or
    ArcLight page, or a path naming a finding aid is the repository's own
    description, which is the one to cite.
    """
    if not isinstance(link, str) or not link.strip():
        return "other"
    parts = urlsplit(link.strip())
    host = (parts.hostname or "").lower()
    path = parts.path.lower()
    if host.endswith("worldcat.org"):
        return "worldcat"
    if (
        host.endswith("orbiscascade.org")
        or host.endswith("archiveswest.orbiscascade.org")
        or host == "oac.cdlib.org"
        or host == "researchworks.oclc.org"
    ):
        return "aggregator"
    if (
        path.endswith(".xml")
        or "/ead/" in path
        or "findingaid" in path.replace("-", "").replace("_", "")
        or "/repositories/" in path
        or "/catalog/" in path
        or "finding" in host
    ):
        return "finding_aid"
    return "other"


# --------------------------------------------------------------------------- #
# Text
# --------------------------------------------------------------------------- #
def plain(text: object) -> str:
    """Strip markup and entities from catalogue text and collapse whitespace."""
    if not isinstance(text, str):
        return ""
    return _SPACE.sub(" ", html.unescape(_TAG.sub(" ", text))).strip()


def clip(text: str, limit: int) -> tuple[str, bool]:
    """Cut text to ``limit`` characters at a word boundary. Returns (text, truncated)."""
    if len(text) <= limit:
        return text, False
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",;:")
    return cut + " …", True


def title_years(title: object) -> list[int]:
    """The earliest and latest year named in a collection title, or [] if none.

    Titles carry the collection's span ("papers, 1837-1938"), sometimes
    hedged ("[ca. 1876]-1979", "1840(ca.)-1934") or with a bulk range. This
    reads the outer years only. It is the span the cataloguer gave, not a
    statement about any document.
    """
    years = [int(y) for y in _YEAR.findall(title)] if isinstance(title, str) else []
    if not years:
        return []
    return [min(years), max(years)] if min(years) != max(years) else [years[0]]


def _term(value: object) -> str | None:
    """The ``term`` of a SNAC vocabulary object, e.g. ``creatorOf``."""
    if isinstance(value, dict) and isinstance(value.get("term"), str):
        return value["term"]
    return None


def _list(value: object) -> list[dict]:
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def _str(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


# --------------------------------------------------------------------------- #
# Repositories
# --------------------------------------------------------------------------- #
def heading(constellation: object) -> str | None:
    """The preferred name of a SNAC record: the name entry with the highest score."""
    entries = _list(constellation.get("nameEntries")) if isinstance(constellation, dict) else []
    if not entries:
        return None

    def score(entry: dict) -> float:
        try:
            return float(entry.get("preferenceScore") or 0)
        except (TypeError, ValueError):
            return 0.0

    return _str(max(entries, key=score).get("original"))


def repository(rec: object) -> dict | None:
    """The holding repository of a collection: name, SNAC ids and postal address."""
    if not isinstance(rec, dict):
        return None
    lines: list[tuple[int, str]] = []
    for place in _list(rec.get("places")):
        for line in _list(place.get("address")):
            text = _str(line.get("text"))
            if text is None:
                continue
            try:
                order = int(line.get("order") or 0)
            except (TypeError, ValueError):
                order = 0
            lines.append((order, text))
    return {
        "name": heading(rec),
        "constellation_id": _str(rec.get("id")),
        "ark": ark(rec.get("ark")),
        "address_lines": [text for _, text in sorted(lines, key=lambda pair: pair[0])],
    }


# --------------------------------------------------------------------------- #
# Collections
# --------------------------------------------------------------------------- #
def collection_summary(res: object) -> dict:
    """A compact description of one archival collection (a SNAC "resource")."""
    if not isinstance(res, dict):
        return {}
    link = _str(res.get("link"))
    oclc = oclc_number(link, res.get("source"))
    abstract, truncated = clip(plain(res.get("abstract")), ABSTRACT_LIMIT)
    title = plain(res.get("title")) or plain(res.get("displayEntry"))
    return {
        "resource_id": _str(res.get("id")),
        "title": title or None,
        "title_years": title_years(title),
        "extent": plain(res.get("extent")) or None,
        "abstract": abstract or None,
        "abstract_truncated": truncated,
        "origination_names": [
            name for o in _list(res.get("originationNames")) if (name := _str(o.get("name")))
        ],
        "repository": repository(res.get("repository")),
        "link": link,
        "link_kind": link_kind(link),
        "oclc_number": oclc,
        "worldcat_url": worldcat_url(oclc),
        "archivegrid_url": archivegrid_record_url(oclc),
    }


def collection_detail(res: object, related: object = None) -> dict:
    """One collection in full: the summary plus the whole abstract and the names linked to it."""
    out = collection_summary(res)
    if not out:
        return out
    out["abstract"] = plain(res.get("abstract")) or None
    out["abstract_truncated"] = False
    out["document_type"] = _term(res.get("documentType"))
    out["version"] = _str(res.get("version"))
    out["linked_names"] = [name_summary(c) for c in _list(related)]
    return out


def _dedup_key(summary: dict) -> tuple[str, tuple[int, ...]] | None:
    """Title words, without dates and punctuation, plus the title's years."""
    title = summary.get("title")
    if not title:
        return None
    words = _YEAR.sub(" ", title.lower())
    words = re.sub(r"\[[^\]]*\]|\bbulk\b|\bca\b|\bundated\b|[^a-z ]", " ", words)
    return " ".join(words.split()), tuple(summary.get("title_years") or ())


def mark_duplicates(summaries: list[dict]) -> list[dict]:
    """Flag collections in one result set that look like the same papers.

    SNAC often holds a collection two or three times: a WorldCat MARC record
    and one or more harvested finding aids, sometimes under different forms of
    the repository's name. Matching is on title words and title years only,
    so this is a hint ("possible"), not a merge. Each summary gains
    ``possible_duplicate_of``: the resource ids of the others in its group.
    """
    groups: dict[tuple, list[str]] = {}
    for s in summaries:
        key = _dedup_key(s)
        if key and s.get("resource_id"):
            groups.setdefault(key, []).append(s["resource_id"])
    for s in summaries:
        key = _dedup_key(s)
        ids = groups.get(key, []) if key else []
        s["possible_duplicate_of"] = [i for i in ids if i != s.get("resource_id")]
    return summaries


# --------------------------------------------------------------------------- #
# Names (SNAC "constellations")
# --------------------------------------------------------------------------- #
def name_summary(c: object) -> dict:
    """One name record as a search hit: ids, heading, kind, and how many collections link to it."""
    if not isinstance(c, dict):
        return {}
    count = c.get("resource_count")
    try:
        resources = int(count) if count is not None else None
    except (TypeError, ValueError):
        resources = None
    return {
        "constellation_id": _str(c.get("id")),
        "ark": ark(c.get("ark")),
        "heading": heading(c),
        "entity_type": _term(c.get("entityType")),
        "collection_count": resources,
    }


def _dates(c: dict) -> list[dict]:
    out = []
    for d in _list(c.get("dates")):
        out.append(
            {
                "from": _str(d.get("fromDate")),
                "from_type": _term(d.get("fromType")),
                "to": _str(d.get("toDate")),
                "to_type": _term(d.get("toType")),
                "as_written": " – ".join(
                    t for t in (_str(d.get("fromDateOriginal")), _str(d.get("toDateOriginal"))) if t
                )
                or None,
            }
        )
    return out


def _biography(c: dict, limit: int) -> tuple[str | None, bool]:
    text = " ".join(plain(b.get("text")) for b in _list(c.get("biogHists"))).strip()
    if not text:
        return None, False
    return clip(text, limit)


def name_detail(
    c: object,
    *,
    maybe_same_count: object = 0,
    full: bool = False,
    biography_limit: int = BIOGRAPHY_LIMIT,
) -> dict:
    """One name record in detail: headings, dates, places, biography, collections and links."""
    if not isinstance(c, dict):
        return {}
    bio, truncated = _biography(c, biography_limit)
    try:
        maybe_same = int(maybe_same_count or 0)
    except (TypeError, ValueError):
        maybe_same = 0
    entries = _list(c.get("nameEntries"))
    out = {
        **name_summary(c),
        "snac_url": snac_page(c.get("ark")),
        "other_headings": [
            h for e in entries if (h := _str(e.get("original"))) and h != heading(c)
        ],
        "dates": _dates(c),
        "places": [
            {"place": p, "type": _term(pl.get("type"))}
            for pl in _list(c.get("places"))
            if (p := _str(pl.get("original")))
        ],
        "occupations": [t for o in _list(c.get("occupations")) if (t := _term(o.get("term")))],
        "subjects": [t for s in _list(c.get("subjects")) if (t := _term(s.get("term")))],
        "biography": bio,
        "biography_truncated": truncated,
        "same_as": [u for s in _list(c.get("sameAsRelations")) if (u := _str(s.get("uri")))],
        "maybe_same_count": maybe_same,
    }
    out.pop("collection_count", None)
    if full:
        collections = []
        for rr in _list(c.get("resourceRelations")):
            summary = collection_summary(rr.get("resource"))
            if summary:
                collections.append({"role": _term(rr.get("role")), **summary})
        out["collections"] = mark_duplicates(collections)
        related = _list(c.get("relations"))
        out["related_names"] = [
            {
                "name": _str(r.get("content")),
                "relation": _term(r.get("type")),
                "constellation_id": _str(r.get("targetConstellation")),
                "ark": ark(r.get("targetArkID")),
                "entity_type": _term(r.get("targetEntityType")),
            }
            for r in related[:RELATED_NAMES_LIMIT]
        ]
        out["related_names_total"] = len(related)
    return out


# --------------------------------------------------------------------------- #
# Holdings and shared collections
# --------------------------------------------------------------------------- #
def holding(entry: object) -> dict:
    """One row of a repository's holdings list."""
    if not isinstance(entry, dict):
        return {}
    link = _str(entry.get("href"))
    oclc = oclc_number(link)
    try:
        count = (
            int(entry.get("relation_count")) if entry.get("relation_count") is not None else None
        )
    except (TypeError, ValueError):
        count = None
    return {
        "resource_id": _str(entry.get("id")),
        "title": plain(entry.get("title")) or None,
        "link": link,
        "link_kind": link_kind(link),
        "oclc_number": oclc,
        "linked_name_count": count,
    }


def shared(entry: object) -> dict:
    """One collection linked to both of two names, with each name's role in it."""
    if not isinstance(entry, dict):
        return {}
    link = _str(entry.get("href"))
    oclc = oclc_number(link)
    return {
        "resource_id": _str(entry.get("id")),
        "title": plain(entry.get("title")) or None,
        "link": link,
        "link_kind": link_kind(link),
        "oclc_number": oclc,
        "role_of_first": _str(entry.get("arcrole_1")),
        "role_of_second": _str(entry.get("arcrole_2")),
    }


def as_dict(value: Any) -> dict:
    """``value`` if it is a dict, else an empty one."""
    return value if isinstance(value, dict) else {}
