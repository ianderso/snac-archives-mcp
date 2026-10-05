"""Async client for the SNAC Cooperative's REST API.

Every SNAC command is a JSON body sent with ``PUT`` to a single URL:
``{"command": "read", "constellationid": 61583061}``. The read commands need
no key and no account. Commands that edit SNAC need both, and this client
refuses to send them at all: :data:`READ_COMMANDS` is the whole of what it
will put on the wire.

Four rules keep the client a polite guest of a free service:

* **One host.** A request hook refuses any request whose host is not the
  configured API's, so nothing a model passes in can make the server fetch
  another site.
* **One request at a time, at least a second apart.** SNAC publishes no rate
  limit; this is the courtesy one.
* **Identical concurrent calls share one request.** Two tools asking the same
  question at once wait on a single answer.
* **Answers are cached on disk.** Keyed by the API URL and the canonical JSON
  body, and kept for :data:`CACHE_DAYS` days, or forever for a record that is
  addressed by version and so cannot change. A failed request is never cached.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import random
import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from . import __version__

logger = logging.getLogger("snac_archives_mcp.client")

#: Where the project lives; named in the User-Agent so SNAC can see who calls.
PROJECT_URL = "https://github.com/ianderso/snac-archives-mcp"

#: The only commands this client sends. All are read-only and need no key.
READ_COMMANDS = frozenset(
    {"search", "read", "resource_search", "read_resource", "shared_resources", "get_holdings"}
)

#: Days a cached answer is served before it is asked again.
CACHE_DAYS = 30

#: A holdings list for a large repository runs to thousands of rows and takes
#: SNAC 10 to 20 seconds to build, so it gets a longer timeout of its own.
HOLDINGS_TIMEOUT = 120.0

_DAY = 86_400.0


class SnacApiError(RuntimeError):
    """A request that SNAC refused or that could not be completed.

    ``status`` is the HTTP status, or 0 when no response arrived at all
    (a timeout or a dropped connection).
    """

    def __init__(self, status: int, detail: str, *, command: str):
        """Record the failing command and what went wrong."""
        self.status = status
        self.detail = detail
        self.command = command
        super().__init__(f"{command} -> {status or 'no response'}: {detail}")


class HostNotAllowed(RuntimeError):
    """Raised when a request is aimed at a host other than the SNAC API's."""


def user_agent(contact: str = "") -> str:
    """The User-Agent sent with every request, naming this project."""
    extra = f"; {contact}" if contact else ""
    return f"snac-archives-mcp/{__version__} (+{PROJECT_URL}{extra})"


class SnacClient:
    """Cached, paced async client for the SNAC REST API.

    Usable as an async context manager, which closes the transport on exit.

    Parameters
    ----------
    api_url : str
        The REST endpoint. Its host is the only one requests may reach.
    cache_dir : Path
        Directory for cached responses. Created on first write.
    timeout : float, optional
        Per-request timeout in seconds, for everything but holdings.
    contact : str, optional
        Appended to the User-Agent.
    min_interval : float, optional
        Least time between the start of one live request and the next.
    retries : int, optional
        Further attempts after a 429, a 5xx or no response at all.
    backoff : float, optional
        Base of the exponential wait between attempts, in seconds.
    transport : httpx.AsyncBaseTransport, optional
        For tests.
    """

    def __init__(
        self,
        api_url: str,
        cache_dir: Path,
        *,
        timeout: float = 60.0,
        contact: str = "",
        min_interval: float = 1.0,
        retries: int = 3,
        backoff: float = 1.0,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self._url = api_url
        self._host = urlsplit(api_url).hostname
        self._cache_dir = cache_dir
        self._timeout = timeout
        self._min_interval = min_interval
        self._retries = retries
        self._backoff = backoff
        self._clock = clock
        self._sleep = sleep
        self._http = httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": user_agent(contact), "Accept": "application/json"},
            event_hooks={"request": [self._only_the_api_host]},
            follow_redirects=False,
            transport=transport,
        )
        self._lock = asyncio.Lock()
        self._inflight: dict[str, asyncio.Future] = {}
        self._last_start: float | None = None
        self._live_calls = 0
        self._cache_hits = 0
        self._shared_waits = 0

    # ------------------------------------------------------------------ #
    # Counters
    # ------------------------------------------------------------------ #
    @property
    def live_calls(self) -> int:
        """int: Requests sent to SNAC this session, retries included."""
        return self._live_calls

    @property
    def cache_hits(self) -> int:
        """int: Answers served from the disk cache this session."""
        return self._cache_hits

    @property
    def shared_waits(self) -> int:
        """int: Calls answered by joining an identical request already in flight."""
        return self._shared_waits

    @property
    def cache_dir(self) -> Path:
        """Path: Where answers are cached."""
        return self._cache_dir

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    async def aclose(self) -> None:
        """Close the underlying HTTP transport."""
        await self._http.aclose()

    async def __aenter__(self) -> SnacClient:
        """Return the client."""
        return self

    async def __aexit__(self, *exc: object) -> None:
        """Close the transport."""
        await self.aclose()

    async def _only_the_api_host(self, request: httpx.Request) -> None:
        """Refuse any request that is not for the configured API host."""
        if request.url.host != self._host:
            raise HostNotAllowed(
                f"refusing a request to {request.url.host!r}: this server only talks to "
                f"{self._host!r}"
            )

    # ------------------------------------------------------------------ #
    # Commands
    # ------------------------------------------------------------------ #
    async def command(self, name: str, *, refresh: bool = False, **params: Any) -> Any:
        """Send one read command, serving it from the cache when possible.

        Parameters
        ----------
        name : str
            A command in :data:`READ_COMMANDS`.
        refresh : bool, optional
            Skip the cached copy and ask SNAC again; the fresh answer
            replaces the cached one.
        **params
            The command's parameters. ``None`` values are dropped.

        Returns
        -------
        Any
            The decoded response body.

        Raises
        ------
        ValueError
            If ``name`` is not a read command. Nothing is sent.
        SnacApiError
            If SNAC refuses the command, or no answer arrives after the
            retries. Nothing is cached.
        """
        if name not in READ_COMMANDS:
            raise ValueError(f"{name!r} is not a read command this client sends")
        body = {"command": name, **{k: v for k, v in params.items() if v is not None}}
        key = self._key(body)
        # A record read by version cannot change, so it never expires.
        ttl = (
            None
            if (name == "read_resource" or (name == "read" and "version" in body))
            else (CACHE_DAYS * _DAY)
        )

        if not refresh:
            cached = self._cache_get(key, ttl)
            if cached is not None:
                self._cache_hits += 1
                return cached

        if (pending := self._inflight.get(key)) is not None:
            self._shared_waits += 1
            return await asyncio.shield(pending)

        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._inflight[key] = future
        try:
            data = await self._fetch(name, body)
        except asyncio.CancelledError:
            future.cancel()
            raise
        except Exception as exc:
            future.set_exception(exc)
            # Mark it retrieved: a failure nobody else was waiting on must
            # not be logged as "exception was never retrieved".
            future.exception()
            raise
        else:
            future.set_result(data)
            self._cache_put(key, data)
            return data
        finally:
            self._inflight.pop(key, None)

    async def _fetch(self, name: str, body: dict) -> Any:
        """Send one command, paced and retried; return the decoded body."""
        timeout = HOLDINGS_TIMEOUT if name == "get_holdings" else self._timeout
        attempt = 0
        while True:
            response: httpx.Response | None = None
            async with self._lock:
                await self._pace()
                self._last_start = self._clock()
                self._live_calls += 1
                try:
                    response = await self._http.put(self._url, json=body, timeout=timeout)
                except httpx.TransportError as exc:
                    detail = f"{type(exc).__name__}: {exc}".rstrip(": ")
            if response is not None:
                if response.status_code < 400:
                    return _decode(response, name)
                detail = _detail(response)
            status = response.status_code if response is not None else 0
            retryable = status == 0 or status == 429 or status >= 500
            if not retryable or attempt >= self._retries:
                raise SnacApiError(status, detail, command=name)
            attempt += 1
            wait = self._backoff * 2 ** (attempt - 1) + random.uniform(0, self._backoff / 2)
            logger.info("%s -> %s; retry %d in %.1fs", name, status or "no response", attempt, wait)
            await self._sleep(wait)

    async def _pace(self) -> None:
        """Wait until at least ``min_interval`` has passed since the last request."""
        if self._last_start is None:
            return
        wait = self._min_interval - (self._clock() - self._last_start)
        if wait > 0:
            await self._sleep(wait)

    # ------------------------------------------------------------------ #
    # Cache
    # ------------------------------------------------------------------ #
    def _key(self, body: dict) -> str:
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(f"{self._url}\n{canonical}".encode()).hexdigest()[:24]

    def _cache_path(self, key: str) -> Path:
        return self._cache_dir / f"{key}.json"

    def _cache_get(self, key: str, ttl: float | None) -> Any:
        """Return a cached answer, or None if absent, expired or unreadable."""
        path = self._cache_path(key)
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, UnicodeDecodeError, ValueError):
            # A truncated or hand-edited entry is a re-fetch, not a crash.
            logger.warning("discarding unreadable cache entry %s", path.name)
            return None
        if not isinstance(entry, dict) or "data" not in entry:
            return None
        stored = entry.get("stored")
        if ttl is not None and (not isinstance(stored, int | float) or time.time() - stored > ttl):
            return None
        return entry["data"]

    def _cache_put(self, key: str, data: Any) -> None:
        try:
            _write_atomically(
                self._cache_path(key), json.dumps({"stored": time.time(), "data": data})
            )
        except OSError:
            # A cache that cannot be written costs speed, not correctness.
            logger.warning("could not write the response cache in %s", self._cache_dir)


def _decode(response: httpx.Response, command: str) -> Any:
    """Decode a 2xx body, turning SNAC's in-band errors into exceptions.

    SNAC usually signals an error with a 4xx status, but a body carrying an
    ``error`` object or ``"result": "failure"`` is treated as a refusal
    whatever the status, so it is never cached as an answer.
    """
    try:
        data = response.json()
    except ValueError:
        raise SnacApiError(
            502, "SNAC answered with something that is not JSON", command=command
        ) from None
    if isinstance(data, dict) and (data.get("error") or data.get("result") == "failure"):
        raise SnacApiError(400, _error_text(data) or "SNAC reported a failure", command=command)
    return data


def _detail(response: httpx.Response) -> str:
    """The server's explanation of a failed request, as plain text."""
    try:
        data = response.json()
    except ValueError:
        text = response.text.strip()
        return text[:300] or response.reason_phrase
    return _error_text(data) or response.reason_phrase


def _error_text(data: Any) -> str:
    """Pull the human-readable message out of a SNAC error body."""
    if not isinstance(data, dict):
        return ""
    err = data.get("error")
    if isinstance(err, dict):
        return str(err.get("message") or err.get("type") or "")
    if isinstance(err, str):
        return err
    message = data.get("message")
    if isinstance(message, dict):
        return str(message.get("text") or "")
    return str(message or "")


def _write_atomically(path: Path, text: str) -> None:
    """Write a file so a reader never sees it half-written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
