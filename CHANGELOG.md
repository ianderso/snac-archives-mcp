# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/). The tool surface is the public
interface: renaming or removing a tool or a parameter is a major release, and
adding one is a minor release. Before 1.0, a minor release may do either.

## [Unreleased]

## [0.1.0] — 2026-10-05

First release.

### Added

- Eight read-only tools over the SNAC Cooperative's REST API:
  `search_collections`, `get_collection`, `repository_holdings`,
  `search_names`, `get_name`, `collections_in_common`, plus
  `archivegrid_search_link` (builds ArchiveGrid addresses, fetches nothing)
  and `cache_status`.
- Results carry OCLC numbers, SNAC ARKs, repository postal addresses, a
  `link_kind` saying whether a link is the repository's own finding aid, and
  `possible_duplicate_of` for the same papers catalogued more than once.
- A polite client: one host only, one request at a time at least a second
  apart, identical concurrent calls joined, answers cached for 30 days,
  retries with back-off on 429 and 5xx.
