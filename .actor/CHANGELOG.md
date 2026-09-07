# Changelog

All notable changes to the YC Jobs Scraper Actor will be documented in this file.

## [1.1.1] - 2026-09-08

### Fixed
- The Notion sync reads the connector proxy base URL from
  `ACTOR_MCP_CONNECTOR_BASE_URL`. It previously read `APIFY_MCP_PROXY_URL`,
  which the platform no longer sets, so a run with a connector selected
  skipped the sync with a "not set" warning instead of writing to Notion.
- Tool schemas saved to `NOTION_TOOL_SCHEMA` now hold the actual schemas. The
  dump read `tool.inputSchema`, which does not exist on the Python SDK's `Tool`
  object - the attribute is `input_schema` - so every entry was saved as null.
  The record's JSON key is unchanged.

### Changed
- Declares `httpx2` rather than `httpx`. `mcp` 2.x depends on httpx2, and its
  streamable-HTTP transport expects an `httpx2.AsyncClient`.

### Notes
- Runs without a connector are unaffected.

## [1.1.0] - 2026-08-11

### Added
- Optional Notion output through an Apify MCP connector. Select an authorized
  Notion connector and a data source, and every scraped job is created as a page
  in your Notion database. Your Notion credentials stay on Apify and never reach
  this Actor.
- The Actor reads the target data source schema first and writes only columns
  that exist, so it adapts to whatever database layout you already have.
- `notionMaxRows` caps how many pages a single run creates.
- `OUTPUT` now reports `notionPagesCreated`.

### Notes
- Runs without a connector are unchanged in every respect.

## [1.0.0] - 2026-01-24

### Added
- Initial release of Y Combinator Jobs Scraper
- Fetch company data from YC hiring.json API
- Scrape company pages for social links, founders, and founded year
- Scrape job pages for complete job details (salary, equity, skills, interview process)
- Smart founder data merging from multiple sources
- Filtering by batch, industry, stage, and location
- Support for top companies filter
- Configurable rate limiting to avoid blocks
- Pydantic data validation
- Comprehensive error handling with retries
