# SNAC API notes

What the SNAC REST API actually does, observed against the live service. The
published command list is `src/snac/client/rest/commands.json` in
[snac-cooperative/snac](https://github.com/snac-cooperative/snac); its help
page (`snaccooperative.org/api_help`) renders that file but sits behind a
JavaScript bot check, so read the file instead.

Observed 2026-10-04 and 2026-10-05, about 25 calls in all, paced 2 seconds
apart.

## Transport

- One URL, `https://api.snaccooperative.org/`. Every command is a JSON body
  sent with **PUT**: `{"command": "read", "constellationid": 61583061}`.
- No key and no account for the read commands. The API host has no
  `robots.txt` (404) and no bot check; the website does.
- Responses are JSON. Each carries a `timing` field (milliseconds).

## Commands this server uses

| Command | Parameters used | Notes |
| --- | --- | --- |
| `resource_search` | `term`, `count`, `start` | Matches collection **titles**, every word required. `start` is not in `commands.json` but works. `total` is the true match count, `page` is 0-based, `pagination` is the number of pages. "Anderson family papers": total 28; count 5 start 5 gave the next five. |
| `read_resource` | `resourceid` | `{resource, related_constellations, timing}`. Resource ids are not sparse at the low end: id 1 exists. |
| `search` | `term`, `start`, `count`, `entity_type`, `biog_hist` | `entity_type` is `person`, `family` or `corporateBody`. Hits carry `id`, `ark`, `nameEntries`, `entityType` and `resource_count` (a string). |
| `read` | `constellationid` or `arkid`, `type: "summary"` | `arkid` must be the `http://n2t.net/ark:/99166/...` form. `constellation` is an **array** when the record was split. A missing id is HTTP **404** with `{"error": {"type": "Input Error", "message": "...does not have a published version."}}`. |
| `shared_resources` | `icid1`, `icid2` | Constellation ids only, not ARKs. Rows carry `arcrole_1` and `arcrole_2`: each name's role in the collection. |
| `get_holdings` | `constellationid` | Unpaged. UNC-Chapel Hill: 8,579 rows, 17 s. Maine Historical Society: 6,115 rows, 1.35 MB, 11 s. Includes printed and microform items. |

## Shapes worth knowing

- **ARKs.** Name records carry `ark` as `http://n2t.net/ark:/99166/<tail>`.
  Every tail seen begins `w6` and has eight characters.
- **Resource links.** `link` is a WorldCat record (`worldcat.org/oclc/<n>`),
  the repository's EAD or HTML finding aid, or an aggregator ARK
  (`nwda.orbiscascade.org/ark:/80444/...`). The OCLC number is also in the
  MODS record in `source`: `<recordOrigin>WorldCat:28048621</recordOrigin>`.
- **Repository addresses** are `repository.places[].address[]` lines, each
  with an `order`. The last lines are a region code (`US-NC`) and postcode.
- **Duplicates.** "Davenport family papers" returns Cornell's papers three
  times: one WorldCat record (repository "Cornell University Library") and two
  EAD files (repository "Division of Rare and Manuscript Collections, Cornell
  University Library."). Repository names differ, so duplicates cannot be
  keyed on the repository.
- **Biographical notes** are EAD fragments: `<biogHist><p xmlns="...">`.
- **Vocabulary terms** are objects: `{"id", "term", "uri", "type"}`. The
  string is `term`.

## The help-page example

`shared_resources` with `icid1: 29260863` (Tolkien) and `icid2: 50307952`
(C.S. Lewis) returns one collection, "C.S. Lewis collection. [1939].", OCLC
667850821, Tolkien `referencedIn`, Lewis `creatorOf`.
