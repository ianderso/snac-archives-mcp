# snac-archives-mcp

[![CI](https://github.com/ianderso/snac-archives-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/ianderso/snac-archives-mcp/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/snac-archives-mcp)](https://pypi.org/project/snac-archives-mcp/)

<!-- mcp-name: io.github.ianderso/snac-archives-mcp -->

An [MCP](https://modelcontextprotocol.io) server for finding **which archive
holds the papers**: a family's letters, a church's registers, a store's
ledgers, a county office's loose papers. Most of that material has never
been digitised. It exists online only as a catalogue record or a finding aid
in some library, and the hard part of the research is knowing which one.

The server searches the **[SNAC Cooperative](https://snaccooperative.org)**'s
index of people, families and organisations and the archival collections
that hold their papers, across thousands of repositories. The data is CC0,
and the API needs no key and no account. It also builds
**[ArchiveGrid](https://researchworks.oclc.org/archivegrid/)** searches for
you to open, because ArchiveGrid often finds what SNAC cannot, and OCLC does
not permit automated access to it.

It works the way a careful genealogist does. Everything it returns is a
finding aid: evidence of where to look and roughly what is there, never of
what a document says. The tools say so, and they point you at the holding
repository's own finding aid, which is the description to cite.

Nothing here writes anywhere, and nothing here keeps a family tree. The
server finds collections; what you conclude from the papers belongs in your
genealogy software, or in a family-tree MCP server running alongside this
one. It sits well beside
[nara-catalog-mcp](https://github.com/ianderso/nara-catalog-mcp) (federal
records) and [familysearch-mcp](https://github.com/ianderso/familysearch-mcp)
(indexed records and images).

This is an independent project. It is not affiliated with, endorsed by, or
supported by the SNAC Cooperative, the University of Virginia, or OCLC.

## Tools

The server publishes eight tools, all read-only and annotated so for the
client. Two make no network call at all.

**Finding collections**

| Tool | Purpose |
| --- | --- |
| `search_collections` | Find collections by words in their title. Each hit names its holding repository with a postal address, its OCLC number and its link, and flags the likely duplicates (the same papers catalogued two or three times). |
| `get_collection` | One collection in full: the whole abstract, extent, repository, links, and the names SNAC connects to it. |
| `repository_holdings` | What SNAC links to one repository, filtered by title and paged. |

**Finding people, families and organisations**

| Tool | Purpose |
| --- | --- |
| `search_names` | Find SNAC name records by name, optionally by kind: person, family, or corporate body (churches, businesses, societies, offices). |
| `get_name` | One name record: headings, dates, places, biographical note and identifier links (VIAF, Library of Congress and others). With `detail="full"`, every collection linked to it, with its role, and the related names. |
| `collections_in_common` | Collections linked to both of two names: where to look for letters between intermarried families or an ancestor's associates. |

**Where SNAC stops**

| Tool | Purpose |
| --- | --- |
| `archivegrid_search_link` | Build an ArchiveGrid search, in its fielded syntax, for you to open; or a record link, given an OCLC number. Makes no request. |
| `cache_status` | This session's live calls and cache hits. Makes no request. |

## Setup

You need Python 3.11 or later and [uv](https://docs.astral.sh/uv/). There is
no key to request.

**Without cloning.** `uvx` fetches it from PyPI and runs it in one step:

```bash
uvx snac-archives-mcp
```

**From a clone**, which is what you want if you will change it:

```bash
git clone https://github.com/ianderso/snac-archives-mcp
cd snac-archives-mcp
uv sync
uv run snac-archives-mcp   # stdio server, usually launched by the client
```

Either way the server speaks MCP over stdio, so you will normally let an MCP
client start it rather than run it by hand.

### Claude Desktop

```json
{
  "mcpServers": {
    "snac": {
      "command": "uvx",
      "args": ["snac-archives-mcp"]
    }
  }
}
```

A desktop app does not always inherit your shell's `PATH`. If the server fails
to start because `uvx` cannot be found, give the full path that `which uvx`
prints as the `command`.

### Claude Code

```bash
claude mcp add snac -- uvx snac-archives-mcp
```

## Configuration

Nothing is required. A `.env` file in the directory the server starts in
supplies anything the environment does not; only that directory is read.

| Variable | Meaning |
| --- | --- |
| `SNAC_API_URL` | The SNAC REST endpoint. Default `https://api.snaccooperative.org/`. Must be https; its host is the only one the server will contact. |
| `SNAC_CACHE_DIR` | Response cache directory. Default `~/.cache/snac-archives-mcp`. |
| `SNAC_TIMEOUT` | HTTP timeout in seconds. Default 60. Holdings lists get 120. |
| `SNAC_CONTACT` | An email address or URL added to the User-Agent, so the SNAC team can reach you if your use causes trouble. Optional, and courteous. |

An unusable value is reported on the first tool call as a `not_configured`
result naming the variable.

## Being a good guest

SNAC is a free service run by a small cooperative, and it publishes no rate
limit. The server sends one request at a time, at least a second apart; two
identical calls in flight share one request; and every answer is cached on
disk for 30 days (a collection record for good). A 429 or a 5xx is retried
three times with back-off, then reported as `rate_limited` or
`upstream_error`, which is never the same as "nothing found". Pass
`refresh=true` to ask again, and refresh a cached empty result before
concluding anything is absent.

## How to read what comes back

- **A finding aid is not the record.** A collection description says the
  papers exist and roughly what is in them. Do not attach a citation to a fact
  on its strength; record a research task (request copies, plan a visit)
  instead.
- **Cite the repository's own finding aid,** by the repository and its
  collection number, for example "Wilder and Anderson Family Papers #01255,
  Southern Historical Collection, Wilson Library, UNC-Chapel Hill". Not SNAC,
  and not ArchiveGrid: they are indexes to it. When `link_kind` is
  `finding_aid`, the link goes there; otherwise look the collection up in the
  repository's own catalogue.
- **Record the identifiers.** The OCLC number ties a collection together
  across WorldCat, ArchiveGrid and SNAC; the SNAC ARK (`ark:/99166/...`) is
  the stable id of a name record. Record the repository's collection number
  too: WorldCat merges records, and a number can come to redirect to another.
- **Description depth varies enormously,** from a one-line catalogue record
  ("Papers, 1881-1958", 4 boxes) to a folder-level container list. A terse
  description does not mean a person is absent from the papers.
- **Title search is title search.** `search_collections` needs every word in
  the collection's *title*. "Davenport family papers" finds ten collections;
  "Davenport family papers Lincoln County" finds none, because the county is
  only in the abstract. Use `search_names`, or an ArchiveGrid link with
  `place`.
- **Duplicates are normal.** One collection often appears as a WorldCat record
  and as one or two harvested finding aids, sometimes under different forms of
  the repository's name. `possible_duplicate_of` groups them by title words
  and years; it is a hint, not a merge.
- **A name record is not an identification.** SNAC holds hundreds of records
  headed "Anderson family." with nothing to tell them apart but the
  collections they link to. In a name's collections, `creatorOf` means these
  are the name's own papers; `referencedIn` means the name is an index term on
  the collection, not that any document concerns the person.
  `maybe_same_count` above 0 means SNAC suspects a conflation.
- **The papers of slaveholding families are a primary route to enslaved
  ancestors.** Many descriptions name enslaved people only as a category.
  Search the papers of the family that held them, not only the ancestor's
  name.
- **The catalogue ages.** SNAC's collection index was largely built from
  2010s extracts. Collections get reprocessed, renumbered and transferred, and
  survey "repositories" such as a state historical documents inventory record
  what a town clerk or church held when surveyed decades ago. Confirm the
  current call number before writing to a repository.
- **ArchiveGrid's indexes have edges.** `location` is where the *repository*
  is; `place` is a place the papers are *about*. Its name, place and subject
  indexes cover catalogue records and EAD finding aids only; HTML and PDF
  finding aids match keywords alone. It leaves out records held by more than
  one library, so microfilm of county or church records is usually missing:
  use WorldCat or the FamilySearch Catalog for that.

## Deliberately not here

- **Writing to SNAC.** Its edit commands need an account and an API key. The
  client refuses to send any command but its six read ones, so no argument can
  make it edit anything.
- **Fetching ArchiveGrid.** OCLC's terms of use forbid robots and automated
  copying, and the site blocks automated clients. The server builds addresses;
  a person opens them.
- **Fetching finding aids from repositories' own sites.** That would widen the
  server from one API to thousands of hosts, with a parser for each and a much
  larger surface for injected text. It may come later, behind an option.

## Security

- **One host.** A request hook refuses any request not for the configured API
  host, so a value a model passes in cannot make the server fetch another
  site. `SNAC_API_URL` must be https.
- **Identifiers are validated** (numeric ids as ASCII digits, ARKs against
  SNAC's pattern) before they reach a request.
- **Catalogue text is untrusted.** Abstracts and biographical notes are
  written by cataloguers and contributors and reach the model verbatim. The
  server's instructions tell the model to treat that text as material to
  weigh, never as instructions; the model still decides, so review what it
  proposes to do.

To report a vulnerability, see [SECURITY.md](SECURITY.md).

## Development

```bash
uv sync --extra dev
uv run pytest                      # mocked with respx; never touches SNAC
uv run ruff check .
uv run ruff format --check .
uv run python -m tests.live_check  # eight paced calls to the live API
```

The live check asks SNAC what the recorded fixtures cannot: whether its
answers still have the shape the server reads. See
[CONTRIBUTING.md](CONTRIBUTING.md) for how the suite is organised,
[docs/API-NOTES.md](docs/API-NOTES.md) for what was observed of the API and
when, and [docs/DESIGN.md](docs/DESIGN.md) for why the server is shaped this
way.

## Credits

The data is the [SNAC Cooperative](https://snaccooperative.org)'s, released
under CC0, with collection records contributed by its member institutions and
drawn from WorldCat and finding aids. ArchiveGrid is a project of
[OCLC Research](https://www.oclc.org/research/).

## License

[MIT](LICENSE).
