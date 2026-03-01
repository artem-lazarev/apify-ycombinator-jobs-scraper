# Y Combinator Jobs Scraper

Scrape Y Combinator companies and job listings. 2,500+ startups, 2,400+ jobs, 3,300+ founders. Free dataset: https://www.kaggle.com/datasets/lazarun/y-combinator-jobs-enriched (scraped with this API).  

## Output Data Fields

### Company Data

| Field | Type | Description |
|-------|------|-------------|
| `name` | String | Company name |
| `slug` | String | URL-friendly identifier |
| `tagline` | String | One-line company description |
| `longDescription` | String | Full company description |
| `website` | String (URL) | Company website |
| `logoUrl` | String (URL) | Company logo image |
| `ycUrl` | String (URL) | YC profile URL |
| `ycBatch` | String | YC batch (e.g., W24, S23) |
| `foundedYear` | Integer | Year founded |
| `teamSize` | Integer | Number of employees |
| `status` | String | Company status (Active, Public, Acquired) |
| `stage` | String | Funding stage (Seed, Series A, Growth) |
| `industry` | String | Primary industry |
| `industries` | List | All industry tags |
| `tags` | List | Additional tags |
| `topCompany` | Boolean | YC top company flag |
| `allLocations` | String | Company locations |
| `regions` | List | Geographic regions |
| `socialLinks.linkedin` | String (URL) | Company LinkedIn |
| `socialLinks.twitter` | String (URL) | Company Twitter/X |
| `socialLinks.facebook` | String (URL) | Company Facebook |
| `socialLinks.github` | String (URL) | Company GitHub |
| `socialLinks.crunchbase` | String (URL) | Crunchbase profile |

### Founder Data

| Field | Type | Description |
|-------|------|-------------|
| `name` | String | Founder name |
| `role` | String | Title/role at company |
| `description` | String | Founder bio |
| `linkedin` | String (URL) | LinkedIn profile |
| `twitter` | String (URL) | Twitter/X profile |

### Job Data

| Field | Type | Description |
|-------|------|-------------|
| `jobId` | String | Unique job identifier |
| `title` | String | Job title |
| `jobUrl` | String (URL) | Job posting URL |
| `location` | String | Job location |
| `salary.min` | Integer | Minimum salary |
| `salary.max` | Integer | Maximum salary |
| `salary.currency` | String | Salary currency (USD) |
| `equity.min` | Float | Minimum equity % |
| `equity.max` | Float | Maximum equity % |
| `jobType` | String | Full-time, Part-time, Contract |
| `roleCategory` | String | Engineering, Sales, etc. |
| `experience` | String | Required experience level |
| `visa` | String | Visa sponsorship status |
| `skills` | List | Required skills |
| `description` | String | Full job description |
| `interviewProcess` | String | Interview process details |
| `applyUrl` | String (URL) | Direct application URL |

## What does Y Combinator Jobs Scraper do?

Y Combinator Jobs Scraper extracts **complete job listing data** from YC companies that are actively hiring. Unlike other YC scrapers that only provide basic company info, this actor dives deep into each job posting to extract:

- **Salary ranges** (min/max with currency)
- **Equity percentages** (min/max)
- **Required skills** and experience levels
- **Interview process details**
- **Direct apply URLs**
- **Full founder profiles** with LinkedIn and Twitter

Perfect for recruiters, job boards, market researchers, and anyone tracking the YC startup job market.

## Why scrape Y Combinator jobs?

- **Recruiting & Talent Sourcing:** Find candidates or job opportunities at top YC startups
- **Salary Benchmarking:** Analyze compensation trends across YC companies by role, location, and stage
- **Market Research:** Track hiring patterns, in-demand skills, and growth signals in the startup ecosystem
- **Lead Generation:** Identify fast-growing companies and their decision-makers (founders)
- **Investment Research:** Monitor hiring activity as a signal of company health and growth



## Input Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `maxCompanies` | Integer | Maximum number of companies to scrape | All |
| `filterByBatch` | List | Filter by YC batch (e.g., `["W24", "S24"]`) | All batches |
| `filterByIndustry` | List | Filter by industry (e.g., `["B2B", "Fintech"]`) | All industries |
| `filterByStage` | List | Filter by funding stage (e.g., `["Seed", "Series A"]`) | All stages |
| `filterByLocation` | List | Filter by location (e.g., `["Remote", "San Francisco"]`) | All locations |
| `topCompaniesOnly` | Boolean | Only scrape YC top companies | `false` |
| `includeFounderDescriptions` | Boolean | Include founder bios | `true` |
| `rateLimitDelay` | Number | Delay between requests (seconds) | `1.5` |

### Example Input

```json
{
  "maxCompanies": 50,
  "filterByBatch": ["W24", "S24"],
  "filterByIndustry": ["B2B", "AI"],
  "filterByStage": ["Seed", "Series A"],
  "topCompaniesOnly": false,
  "includeFounderDescriptions": true,
  "rateLimitDelay": 1.5
}
```

## Output Example

Each result contains complete company, founder, and job data:

```json
{
  "company": {
    "id": 271,
    "name": "Airbnb",
    "slug": "airbnb",
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
      "description": "Brian Chesky is the co-founder and CEO of Airbnb...",
      "linkedin": "https://www.linkedin.com/in/brianchesky/",
      "twitter": "https://twitter.com/bchesky"
    }
  ],
  "jobs": [
    {
      "jobId": "yaLKuLq",
      "title": "Senior Software Engineer",
      "jobUrl": "https://ycombinator.com/companies/airbnb/jobs/yaLKuLq",
      "location": "San Francisco / Remote",
      "salary": {
        "min": 180000,
        "max": 280000,
        "currency": "USD"
      },
      "equity": {
        "min": 0.01,
        "max": 0.05
      },
      "jobType": "Full-time",
      "roleCategory": "Engineering, Backend",
      "experience": "5+ years",
      "visa": "Will sponsor",
      "skills": ["Python", "Distributed Systems", "AWS"],
      "description": "Join our platform team to build scalable infrastructure...",
      "interviewProcess": "Technical phone screen, system design, onsite with team",
      "applyUrl": "https://account.ycombinator.com/authenticate?continue=..."
    }
  ],
  "scrapedAt": "2026-01-24T12:00:00Z"
}
```

## How to Use

1. **Set your filters** - Use the input parameters to target specific batches, industries, stages, or locations
2. **Run the scraper** - Click "Start" and wait for the extraction to complete
3. **Export your data** - Download results in JSON, CSV, Excel, or connect via API

## Integrations

Connect Y Combinator Jobs Scraper with your favorite tools:

- **Google Sheets** - Automatically sync job data to spreadsheets
- **Airtable / Notion** - Build your own job tracking database
- **Zapier / Make / n8n** - Trigger workflows when new jobs are found
- **Slack** - Get notifications for new job postings
- **Your own API** - Use webhooks for real-time data delivery

## Technical Details

### Data Sources

1. **YC Hiring API** - Primary source for company metadata
2. **Company Pages** (`/companies/{slug}`) - Social links, founders, founded year
3. **Job Pages** (`/companies/{slug}/jobs/{job-id}`) - Complete job details

### Features

- Smart founder data merging from multiple sources
- Automatic retries with exponential backoff
- Rate limiting to avoid blocks
- Pydantic data validation
- Handles missing optional fields gracefully

## Feedback

Found a bug or have a feature request? Please create an issue on the Actor's Issues tab in Apify Console. We're always working to improve this scraper!
