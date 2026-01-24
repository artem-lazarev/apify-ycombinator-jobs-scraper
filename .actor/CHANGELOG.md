# Changelog

All notable changes to the YC Jobs Scraper Actor will be documented in this file.

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
