"""Configuration from environment variables.

===================  =========================================================
``SNAC_API_URL``     The SNAC REST API. Default ``https://api.snaccooperative.org/``.
``SNAC_CACHE_DIR``   Directory for the on-disk response cache.
``SNAC_TIMEOUT``     HTTP timeout in seconds, for every call but holdings.
``SNAC_CONTACT``     An email address or URL appended to the User-Agent, so
                     the SNAC team can reach whoever runs this server.
===================  =========================================================

None is required: the read commands this server uses need no API key and no
account. A ``.env`` file in the working directory supplies any of these that
the environment does not.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

#: The public SNAC REST API.
DEFAULT_API_URL = "https://api.snaccooperative.org/"


class ConfigError(RuntimeError):
    """Raised when a setting is present but unusable."""


@dataclass
class Config:
    """Resolved server configuration.

    Attributes
    ----------
    api_url : str
        The SNAC REST endpoint. Every request goes here and nowhere else.
    cache_dir : Path
        Directory holding cached responses.
    timeout : float
        HTTP timeout in seconds. Holdings lists get a longer one of their own.
    contact : str
        Appended to the User-Agent when set. Empty by default.
    """

    api_url: str = DEFAULT_API_URL
    cache_dir: Path = field(default_factory=lambda: Path.home() / ".cache" / "snac-archives-mcp")
    timeout: float = 60.0
    contact: str = ""


def load_config() -> Config:
    """Load configuration from the environment.

    A ``.env`` file in the working directory is read if present; real
    environment variables win. Only the working directory is consulted.
    ``load_dotenv()`` with no path searches upward from the *calling
    module's* location instead, which for an installed package is
    ``site-packages``: it would ignore the ``.env`` beside the user and could
    read an unrelated one from a parent such as the home directory.

    Returns
    -------
    Config
        Fully resolved configuration.

    Raises
    ------
    ConfigError
        If ``SNAC_API_URL`` is not an https URL, or ``SNAC_TIMEOUT`` is not a
        positive number. The server loads its configuration on the first tool
        call, so this surfaces there as a ``not_configured`` result rather
        than as a crash at launch.
    """
    load_dotenv(Path.cwd() / ".env")

    cfg = Config()
    if raw := (os.environ.get("SNAC_API_URL") or "").strip():
        cfg.api_url = _https_url("SNAC_API_URL", raw)
    if raw := os.environ.get("SNAC_CACHE_DIR"):
        cfg.cache_dir = Path(raw).expanduser()
    if raw := os.environ.get("SNAC_TIMEOUT"):
        cfg.timeout = _positive("SNAC_TIMEOUT", raw)
    if raw := os.environ.get("SNAC_CONTACT"):
        cfg.contact = _contact(raw)
    return cfg


def _https_url(name: str, raw: str) -> str:
    """Accept an https URL with a host, and give it a trailing slash.

    The host of this URL is the only one the client will talk to, so a
    plain-http or host-less value is refused rather than guessed at.
    """
    parts = urlsplit(raw)
    if parts.scheme != "https" or not parts.hostname:
        raise ConfigError(f"{name} must be an https URL with a host; got {raw!r}.")
    return raw if raw.endswith("/") else raw + "/"


def _positive(name: str, raw: str) -> float:
    """Parse one numeric setting, naming the variable if it is unusable.

    A bare ``float("sixty")`` would surface as "could not convert string to
    float", which does not say which setting is wrong.
    """
    try:
        value = float(raw.strip())
    except ValueError:
        raise ConfigError(f"{name} must be a number; got {raw!r}.") from None
    if not math.isfinite(value) or value <= 0:
        raise ConfigError(f"{name} must be greater than zero; got {raw!r}.")
    return value


def _contact(raw: str) -> str:
    """Keep a contact string safe to place inside a User-Agent header.

    A newline would let the value inject a second header, and parentheses
    would close the comment it sits in.
    """
    text = raw.strip()
    if any(ch in text for ch in "\r\n()") or not text.isprintable():
        raise ConfigError(
            "SNAC_CONTACT must be one line with no parentheses, such as an "
            f"email address or a URL; got {raw!r}."
        )
    return text
