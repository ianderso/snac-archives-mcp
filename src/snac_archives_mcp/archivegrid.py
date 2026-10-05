"""Building ArchiveGrid search addresses for a person to open.

ArchiveGrid (OCLC Research) indexes about seven million descriptions of
archival collections, and often finds what SNAC cannot: a collection named
only by place or subject, or one described in an HTML or PDF finding aid.
But OCLC's terms of use forbid automated access to it, so this module never
fetches anything. It composes the query a researcher would type, in
ArchiveGrid's own fielded syntax, and returns the address.

The syntax, from ArchiveGrid's "How to search" page: ``AND``/``OR``/``NOT``
in capitals, ``"quoted phrases"``, and fielded indexes such as
``person.name:``, ``place.name:``, ``archive:`` and ``location:``.
"""

from __future__ import annotations

from urllib.parse import urlencode

#: ArchiveGrid's search page.
SEARCH_URL = "https://researchworks.oclc.org/archivegrid/"

#: Tool parameter -> ArchiveGrid index. Order is the order clauses are written.
FIELDS = (
    ("person", "person.name"),
    ("family", "person.name"),
    ("organization", "organization.name"),
    ("place", "place.name"),
    ("topic", "topic.name"),
    ("event", "event.name"),
    ("title", "title"),
    ("archive", "archive"),
    ("location", "location"),
)

#: Values ArchiveGrid's ``type:`` index accepts.
SOURCE_TYPES = ("marc", "ead", "html", "pdf")


def _term(value: str) -> str:
    """One search term: quoted as a phrase if it has spaces, with stray quotes dropped."""
    text = " ".join(value.replace('"', " ").split())
    return f'"{text}"' if " " in text else text


def build_query(
    *,
    keywords: str = "",
    exclude: list[str] | None = None,
    source_type: str = "",
    has_links: bool = False,
    **fields: str,
) -> str:
    """The ArchiveGrid query string for these criteria, clauses joined with AND.

    ``keywords`` is passed through as typed, so a caller may use ArchiveGrid's
    own operators in it. Every fielded value is treated as one term.
    """
    clauses = []
    if keywords.strip():
        clauses.append(" ".join(keywords.split()))
    for param, index in FIELDS:
        value = (fields.get(param) or "").strip()
        if value:
            clauses.append(f"{index}:{_term(value)}")
    if source_type:
        clauses.append(f"type:{source_type}")
    if has_links:
        clauses.append("has_links:1")
    query = " AND ".join(clauses)
    for word in exclude or []:
        if word.strip():
            query += f" NOT {_term(word.strip())}"
    return query


def search_url(query: str) -> str:
    """The address of an ArchiveGrid search for ``query``, first page."""
    return f"{SEARCH_URL}?{urlencode([('p', '1'), ('q', query)])}"
