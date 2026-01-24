# YC Jobs Scraper Apify Actor

An Apify actor that scrapes Y Combinator company pages and job listings, extracting comprehensive company information, founder details, and complete job postings with salary, equity, and interview process information.

## Overview

This actor fetches company data from the YC hiring.json API and scrapes individual company and job pages to extract:

- **Company Information**: Name, description, logo, website, locations, industry, batch, stage, social links, and more
- **Founder Details**: Names, roles, descriptions, LinkedIn, and Twitter profiles
- **Job Listings**: Complete job details including salary ranges, equity, location, job type, skills, descriptions, interview process, and apply URLs

## Architecture

The actor follows this workflow:

1. Fetches company list from `https://yc-oss.github.io/api/companies/hiring.json`
2. Filters companies based on input criteria
3. For each company:
   - Scrapes the company page to extract social links, founders, and founded year
   - Extracts job listing URLs from the company page
   - Scrapes each job page to extract complete job details
   - Merges founder data from company and job pages (using the most complete information)
4. Outputs structured data to Apify dataset

## Input Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `maxCompanies` | integer | Maximum number of companies to scrape | null (all) |
| `filterByBatch` | array | Filter by YC batch (e.g., ['W24', 'S24']) | [] |
| `filterByIndustry` | array | Filter by industry (e.g., ['B2B', 'Fintech']) | [] |
| `filterByStage` | array | Filter by stage (e.g., ['Seed', 'Series A']) | [] |
| `filterByLocation` | array | Filter by location keywords (e.g., ['Remote', 'San Francisco']) | [] |
| `topCompaniesOnly` | boolean | Only scrape top YC companies | false |
| `includeFounderDescriptions` | boolean | Include founder bio descriptions | true |
| `rateLimitDelay` | number | Delay between requests in seconds | 1.5 |

## Output Data Structure

Each record in the dataset contains:

```json
{
  "company": {
    "id": 271,
    "name": "Airbnb",
    "slug": "airbnb",
    "formerNames": [],
    "tagline": "Book accommodations around the world.",
    "longDescription": "Founded in August of 2008...",
    "website": "http://airbnb.com",
    "logoUrl": "https://bookface-images.s3.amazonaws.com/...",
    "ycUrl": "https://www.ycombinator.com/companies/airbnb",
    "ycBatch": "W09",
    "foundedYear": 2008,
    "teamSize": 6132,
    "status": "Public",
    "stage": "Growth",
    "industry": "Consumer",
    "subindustry": "Consumer -> Travel, Leisure and Tourism",
    "industries": ["Consumer", "Travel, Leisure and Tourism"],
    "tags": ["Marketplace", "Travel"],
    "topCompany": true,
    "allLocations": "San Francisco, CA, USA",
    "regions": ["United States of America", "America / Canada"],
    "socialLinks": {
      "linkedin": "https://www.linkedin.com/company/airbnb/",
      "twitter": "https://twitter.com/Airbnb",
      "facebook": "https://www.facebook.com/airbnb/",
      "crunchbase": "https://www.crunchbase.com/organization/airbnb",
      "github": null
    }
  },
  "founders": [
    {
      "name": "Brian Chesky",
      "role": "Founder/CEO",
      "description": "Brian Chesky is the co-founder, Head of Community, and CEO of Airbnb...",
      "linkedin": "https://www.linkedin.com/in/brianchesky/",
      "twitter": "https://twitter.com/bchesky"
    }
  ],
  "jobs": [
    {
      "jobId": "yaLKuLq",
      "title": "Head of Engineering, Identity Graph",
      "jobUrl": "https://ycombinator.com/companies/stripe/jobs/yaLKuLq",
      "location": "San Francisco / Remote",
      "salary": {
        "min": 140000,
        "max": 250000,
        "currency": "USD"
      },
      "equity": {
        "min": 0.10,
        "max": 0.40
      },
      "jobType": "Full-time",
      "roleCategory": "Engineering, Backend",
      "experience": "11+ years",
      "visa": "Will sponsor",
      "skills": ["Java"],
      "description": "Before Stripe, every growing internet platform had a payments team...",
      "interviewProcess": "Show and describe to us something you have built.",
      "applyUrl": "https://account.ycombinator.com/authenticate?continue=..."
    }
  ],
  "scrapedAt": "2026-01-24T12:00:00Z"
}
```

## Data Sources

### 1. hiring.json API
Primary source for company metadata (no scraping needed):
- Company ID, name, slug, former names
- Logo, website, locations, description
- Industry, batch, stage, status
- Tags, team size, regions

### 2. Company Page (`/companies/{slug}`)
Scraped for additional data:
- Social links (LinkedIn, Twitter, GitHub, Facebook, Crunchbase)
- Founder information (name, role, description, social links)
- Founded year

### 3. Job Page (`/companies/{slug}/jobs/{job-id}`)
Scraped for complete job details:
- Job title, location, type
- Salary and equity ranges
- Skills, experience requirements
- Full job description
- Interview process
- Apply URL
- Backup founder data (if not available on company page)

## Founder Data Merging

Founder information may appear on both company pages and job pages. The actor uses a smart merging strategy:

1. Uses company page founders as the primary source (usually more complete)
2. Fills in missing data from job page founders
3. Prefers longer descriptions when available
4. Merges social links from both sources

## Error Handling

- Retries failed requests with exponential backoff (3 retries)
- Skips companies with no job listings gracefully
- Logs and continues on individual page failures
- Validates data with Pydantic models before output
- Handles missing optional fields (equity, interview process, some social links)
- Rate limiting to avoid being blocked (configurable delay between requests)

## Dependencies

- `apify>=2.0.0` - Apify SDK
- `crawl4ai>=0.7.4` - Web scraping framework
- `pydantic>=2.0.0` - Data validation
- `aiohttp>=3.9.0` - Async HTTP client
- `beautifulsoup4>=4.12.0` - HTML parsing
- `lxml>=5.0.0` - XML/HTML parser

## Local Development

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set up Apify credentials (if testing locally):
```bash
export APIFY_TOKEN=your_token_here
```

3. Run the actor:
```bash
python -m src
```

## Notes

- Not all jobs have equity information
- "About the interview" section is optional and may not be present for all jobs
- Social links vary by company (some have all, others have only a few)
- Founder descriptions are typically more complete on company pages
- The actor respects rate limits to avoid being blocked
