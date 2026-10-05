"""Ask the live SNAC API what the recorded fixtures cannot. Run by hand.

    uv run python -m tests.live_check

Eight calls, paced by the client itself (one at a time, a second apart), each
checking that SNAC still answers in the shape the server reads. It is not a
test module: pytest does not collect it, and CI never runs it, because the
suite must never depend on a third party's service being up.

Exit status 0 if every check passed, 1 if any failed.
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

from snac_archives_mcp import server
from snac_archives_mcp.client import SnacClient
from snac_archives_mcp.config import load_config

#: (tool, arguments, check, what the check means)
CHECKS: list[tuple[str, dict, Callable[[dict], bool], str]] = [
    (
        "search_collections",
        {"title_words": "Wilder and Anderson family papers"},
        lambda r: any(c.get("oclc_number") == "28048621" for c in r.get("collections", [])),
        "the UNC Wilder-Anderson papers, OCLC 28048621",
    ),
    (
        "search_collections",
        {"title_words": "Davenport family papers", "count": 5, "page": 2},
        lambda r: r.get("page") == 2 and r.get("total", 0) > 5 and r.get("returned", 0) > 0,
        "a second page of results (start= still pages)",
    ),
    (
        "get_collection",
        {"resource_id": "7252207"},
        lambda r: (r.get("repository") or {}).get("ark") == "ark:/99166/w6xj0ds0",
        "the collection names UNC by its ARK, with an address",
    ),
    (
        "search_names",
        {"name": "Anderson family", "entity_type": "family", "count": 3},
        lambda r: r.get("total", 0) > 100 and all(n.get("ark") for n in r.get("names", [])),
        "hundreds of Anderson family records, each with an ARK",
    ),
    (
        "get_name",
        {"name_id": "61583061", "detail": "full"},
        lambda r: any(
            c.get("role") == "creatorOf" and c.get("oclc_number") == "502156501"
            for c in r.get("collections", [])
        ),
        "the Windham, Maine Andersons created OCLC 502156501 (Maine Historical Society)",
    ),
    (
        "get_name",
        {"name_id": "ark:/99166/w61r7qfw"},
        lambda r: r.get("constellation_id") == "29260863" and r.get("same_as"),
        "a read by ARK resolves, and carries identifier links",
    ),
    (
        "collections_in_common",
        {"first": "29260863", "second": "50307952"},
        lambda r: any("Lewis" in (c.get("title") or "") for c in r.get("collections", [])),
        "the example in SNAC's own documentation: a C.S. Lewis collection",
    ),
    (
        "repository_holdings",
        {"repository": "87967572", "title_contains": "Anderson"},
        lambda r: r.get("holdings_total", 0) > 1000 and r.get("total", 0) >= 1,
        "Maine Historical Society's holdings list, filtered (slow the first time)",
    ),
]


async def main() -> int:
    cfg = load_config()
    with tempfile.TemporaryDirectory() as cache:
        server.state.config = cfg
        server.state.client = SnacClient(
            cfg.api_url, Path(cache), timeout=cfg.timeout, contact=cfg.contact
        )
        failed = 0
        for tool, args, check, meaning in CHECKS:
            result = json.loads((await server.mcp.call_tool(tool, args)).content[0].text)
            ok = "error" not in result and bool(check(result))
            failed += not ok
            print(f"{'PASS' if ok else 'FAIL'}  {tool}: {meaning}")
            if not ok:
                print(f"      got: {json.dumps(result)[:400]}")
        await server.state.client.aclose()
    print(f"\n{len(CHECKS) - failed}/{len(CHECKS)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
