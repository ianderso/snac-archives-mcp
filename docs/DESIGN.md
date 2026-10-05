# Design

Why the server is shaped the way it is, and what is out of scope by decision.

## The question it answers

"Which archive holds the papers?" Federal records have NARA's catalogue and
indexed records have FamilySearch. But a family's letters, a church's
registers, a county's loose court papers or a store's ledgers are usually
held by one library or historical society, undigitised, and described only by
a catalogue record or a finding aid. Finding that description is the step this
server does.

## Why SNAC, and why not ArchiveGrid

ArchiveGrid (OCLC Research) is the larger union catalogue of collection
descriptions, and the one genealogists know. But its `robots.txt` disallows
every path to every agent, OCLC Research's terms of use prohibit robots and
automated copying, and it blocks non-browser clients. A server that fetched it
would have to work around all three. So it doesn't.

SNAC is free, CC0, documented for programmatic use, actively maintained, and
keyed on the same WorldCat OCLC numbers as ArchiveGrid. It holds less, and its
collection search matches titles only. So the server pairs it with
`archivegrid_search_link`, which writes the ArchiveGrid query a person would
type, in ArchiveGrid's fielded syntax, and returns the address for that person
to open.

## The evidence model

Every answer is a finding aid. The descriptions and the server instructions
say so in the words a model acts on, and a contract test fails if they stop
saying it:

- A collection hit supports a research *task* (request copies, plan a visit),
  never a citation on a fact.
- The description to cite is the holding repository's own finding aid, by its
  collection number. SNAC and ArchiveGrid are indexes to it.
- A biographical note is copied from a finding aid: secondary, a lead.
- `referencedIn` is an index term, not proof a person is in the papers.

## Shape of the results

- **Compact.** A SNAC record carries ids, URIs and type objects on every term.
  Results keep what a researcher acts on: what the collection is, who holds
  it (with a postal address), its OCLC number and its link, classified by
  `link_kind` so the model knows whether the link is the citable finding aid.
- **Identifiers first.** OCLC numbers and ARKs in their short, citable forms;
  WorldCat and ArchiveGrid record URLs built from the OCLC number, never
  fetched.
- **Duplicates flagged, not merged.** By title words and title years, because
  the repository's name varies between a collection's records.
- **Pages are 1-based**, as in the sibling servers, whatever SNAC uses.

## Courtesy

SNAC publishes no rate limit. The client allows one request in flight, at
least a second apart, joins identical concurrent calls, and caches answers for
30 days (a collection record forever, since a versioned record cannot change).
A holdings list, which SNAC builds in 10 to 20 seconds, is fetched once and
filtered locally. The User-Agent names the project, and `SNAC_CONTACT` adds the
operator's address.

## Out of scope, by decision

- **Writing to SNAC.** The client sends six read commands and refuses every
  other name before any request is made.
- **Fetching ArchiveGrid.** See above. If OCLC grants permission in writing,
  an ArchiveGrid provider could be added behind an option, with the letter
  kept in `docs/`.
- **Fetching finding aids from repository sites** (`read_finding_aid`). It
  would turn a one-host client into one that fetches thousands of hosts, with
  a parser per platform and a larger surface for injected text. Revisit once
  the core server has proved useful.

## Tests

- Everything is mocked with respx against **recorded** SNAC responses
  (`tests/fixtures/`, CC0 data, historical records only). The suite never
  touches the live API.
- Contract tests pin the tool surface as a client sees it: names and
  parameters (snapshot), descriptions present and within a size budget,
  read-only annotations, no write-sounding tool, no tool that raises when the
  API fails, unknown parameters refused.
- `tests/live_check.py` makes eight paced live calls by hand to catch drift in
  SNAC's answers.
