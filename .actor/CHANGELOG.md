# Changelog

All notable changes to the YC Jobs Scraper Actor will be documented in this file.

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
