"""Settings from the environment and from ``.env`` in the working directory."""

from __future__ import annotations

from pathlib import Path

import pytest

from snac_archives_mcp.config import DEFAULT_API_URL, ConfigError, load_config

VARIABLES = ("SNAC_API_URL", "SNAC_CACHE_DIR", "SNAC_TIMEOUT", "SNAC_CONTACT")


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch, tmp_path):
    for name in VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)


def test_nothing_is_required():
    cfg = load_config()
    assert cfg.api_url == DEFAULT_API_URL
    assert cfg.timeout == 60.0
    assert cfg.contact == ""
    assert cfg.cache_dir == Path.home() / ".cache" / "snac-archives-mcp"


def test_every_setting_is_read(monkeypatch, tmp_path):
    monkeypatch.setenv("SNAC_API_URL", "https://test.snaccooperative.org")
    monkeypatch.setenv("SNAC_CACHE_DIR", str(tmp_path / "c"))
    monkeypatch.setenv("SNAC_TIMEOUT", "15")
    monkeypatch.setenv("SNAC_CONTACT", "me@example.org")
    cfg = load_config()
    assert cfg.api_url == "https://test.snaccooperative.org/"
    assert cfg.cache_dir == tmp_path / "c"
    assert cfg.timeout == 15.0
    assert cfg.contact == "me@example.org"


@pytest.mark.parametrize(
    "url", ["http://api.snaccooperative.org/", "api.snaccooperative.org", "https://"]
)
def test_the_api_url_must_be_https_with_a_host(monkeypatch, url):
    monkeypatch.setenv("SNAC_API_URL", url)
    with pytest.raises(ConfigError, match="SNAC_API_URL"):
        load_config()


@pytest.mark.parametrize("raw", ["sixty", "0", "-5", "nan", "inf"])
def test_an_unusable_timeout_names_the_variable(monkeypatch, raw):
    monkeypatch.setenv("SNAC_TIMEOUT", raw)
    with pytest.raises(ConfigError, match="SNAC_TIMEOUT"):
        load_config()


@pytest.mark.parametrize("raw", ["me@example.org\r\nX-Evil: 1", "me (home)"])
def test_a_contact_that_could_break_the_header_is_refused(monkeypatch, raw):
    monkeypatch.setenv("SNAC_CONTACT", raw)
    with pytest.raises(ConfigError, match="SNAC_CONTACT"):
        load_config()


def test_dot_env_in_the_working_directory_is_read(tmp_path):
    (tmp_path / ".env").write_text("SNAC_TIMEOUT=7\n")
    assert load_config().timeout == 7.0


def test_the_environment_wins_over_dot_env(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("SNAC_TIMEOUT=7\n")
    monkeypatch.setenv("SNAC_TIMEOUT", "9")
    assert load_config().timeout == 9.0
