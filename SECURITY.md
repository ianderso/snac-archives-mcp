# Security policy

## Reporting a vulnerability

Please report vulnerabilities privately, through GitHub's
[private vulnerability reporting](https://github.com/ianderso/snac-archives-mcp/security/advisories/new)
(the **Report a vulnerability** button on the repository's Security tab), not
in a public issue. Include what an attacker controls, what they gain, and the
steps to reproduce it.

You should hear back within a week. Fixes are released for the latest version
only.

## Scope

In scope: this server — the requests it makes, the files it writes (its
cache), and anything a tool argument or an API response can make it do.

Out of scope: the SNAC API and website, which this project does not operate.
Report problems with those to the SNAC Cooperative.

## The security model, briefly

- **No credentials.** The server uses only SNAC's public read commands. It
  holds no key and sends none.
- **One host.** A request hook refuses any request whose host is not the
  configured API's. `SNAC_API_URL` must be https. Nothing a model passes in can
  make the server fetch another site, ArchiveGrid included.
- **Read commands only.** The client sends six named read commands and refuses
  any other before a request is made.
- **Identifiers are validated** — numeric ids as ASCII digits, ARKs against
  SNAC's pattern — before they are placed in a request.
- **The only local writes are the cache,** under `SNAC_CACHE_DIR`, in files
  named by a hash of the request, written atomically.
- **API responses carry untrusted text.** Collection abstracts and
  biographical notes are written by cataloguers and contributors and reach the
  model verbatim, which makes them a channel for prompt injection. The server's
  instructions tell the model to treat that text as material, not as
  instructions, but the model still decides what to do next. An injection that
  leads the model to misuse this server's own tools is in scope; one that leads
  it to misuse other tools the client has connected is a client concern.
- **`SNAC_CONTACT` is checked** for newlines and parentheses before it is
  placed in the User-Agent header.
