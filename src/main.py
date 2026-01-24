"""Main actor logic for YC Jobs Scraper."""
import asyncio
import logging
import re
from typing import List, Dict, Optional, Any
from datetime import datetime
import aiohttp
from apify import Actor

from .models import Company, CompanyOutput, Founder, Job, SocialLinks, Salary, Equity
from .scraper import scrape_company_page, scrape_job_page
from .parsers import parse_company_page, parse_job_page, merge_founders

logger = logging.getLogger(__name__)

HIRING_JSON_URL = "https://yc-oss.github.io/api/companies/hiring.json"


async def fetch_hiring_json() -> List[Dict[str, Any]]:
    """Fetch the hiring.json API."""
    async with aiohttp.ClientSession() as session:
        async with session.get(HIRING_JSON_URL) as response:
            if response.status == 200:
                data = await response.json()
                logger.info(f"Fetched {len(data)} companies from hiring.json")
                return data
            else:
                logger.error(f"Failed to fetch hiring.json: {response.status}")
                raise Exception(f"Failed to fetch hiring.json: {response.status}")


def filter_companies(
    companies: List[Dict[str, Any]],
    max_companies: Optional[int] = None,
    filter_by_batch: List[str] = None,
    filter_by_industry: List[str] = None,
    filter_by_stage: List[str] = None,
    filter_by_location: List[str] = None,
    top_companies_only: bool = False
) -> List[Dict[str, Any]]:
    """Filter companies based on input criteria."""
    filtered = companies
    
    # Filter by batch
    if filter_by_batch:
        filtered = [c for c in filtered if c.get('batch') in filter_by_batch]
    
    # Filter by industry
    if filter_by_industry:
        filtered = [c for c in filtered if any(
            ind in (c.get('industry', '') or '') or ind in (c.get('subindustry', '') or '')
            for ind in filter_by_industry
        )]
    
    # Filter by stage
    if filter_by_stage:
        filtered = [c for c in filtered if c.get('stage') in filter_by_stage]
    
    # Filter by location
    if filter_by_location:
        locations_str = (c.get('all_locations', '') or '').lower()
        filtered = [c for c in filtered if any(
            loc.lower() in locations_str for loc in filter_by_location
        )]
    
    # Filter top companies only
    if top_companies_only:
        filtered = [c for c in filtered if c.get('top_company', False)]
    
    # Limit by max_companies
    if max_companies:
        filtered = filtered[:max_companies]
    
    logger.info(f"Filtered to {len(filtered)} companies")
    return filtered


def extract_job_ids_from_company_page(html: str) -> List[str]:
    """Extract job IDs from company page HTML."""
    # Look for job links like /companies/slug/jobs/job-id
    import re
    pattern = r'/companies/[^/]+/jobs/([a-zA-Z0-9_-]+)'
    job_ids = re.findall(pattern, html)
    # Remove duplicates while preserving order
    seen = set()
    unique_job_ids = []
    for job_id in job_ids:
        if job_id not in seen:
            seen.add(job_id)
            unique_job_ids.append(job_id)
    return unique_job_ids


def build_company_from_hiring_json(company_data: Dict[str, Any], scraped_data: Dict) -> Company:
    """Build Company model from hiring.json data and scraped data."""
    # Build social links
    social_links = SocialLinks(
        linkedin=scraped_data.get('socialLinks', {}).get('linkedin'),
        twitter=scraped_data.get('socialLinks', {}).get('twitter'),
        github=scraped_data.get('socialLinks', {}).get('github'),
        facebook=scraped_data.get('socialLinks', {}).get('facebook'),
        crunchbase=scraped_data.get('socialLinks', {}).get('crunchbase')
    )
    
    # Parse locations
    all_locations = company_data.get('all_locations') or ''
    
    # Parse industries
    industries = company_data.get('industries', [])
    if not industries and company_data.get('industry'):
        industries = [company_data['industry']]
    
    # Parse tags
    tags = company_data.get('tags', [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(',') if t.strip()]
    
    # Parse regions
    regions = company_data.get('regions', [])
    if isinstance(regions, str):
        regions = [r.strip() for r in regions.split(',') if r.strip()]
    
    return Company(
        id=company_data.get('id', 0),
        name=company_data.get('name', ''),
        slug=company_data.get('slug', ''),
        formerNames=company_data.get('former_names', []),
        tagline=company_data.get('one_liner'),
        longDescription=company_data.get('long_description'),
        website=company_data.get('website'),
        logoUrl=company_data.get('small_logo_thumb_url'),
        ycUrl=company_data.get('url'),
        ycBatch=company_data.get('batch'),
        foundedYear=scraped_data.get('foundedYear'),
        teamSize=company_data.get('team_size'),
        status=company_data.get('status'),
        stage=company_data.get('stage'),
        industry=company_data.get('industry'),
        subindustry=company_data.get('subindustry'),
        industries=industries,
        tags=tags,
        topCompany=company_data.get('top_company', False),
        allLocations=all_locations if all_locations else None,
        regions=regions,
        socialLinks=social_links
    )


def build_founders_from_parsed(parsed_founders: List[Dict]) -> List[Founder]:
    """Build Founder models from parsed data."""
    founders = []
    for f_data in parsed_founders:
        founder = Founder(
            name=f_data.get('name', ''),
            role=f_data.get('role'),
            description=f_data.get('description'),
            linkedin=f_data.get('linkedin'),
            twitter=f_data.get('twitter')
        )
        if founder.name:  # Only add if we have a name
            founders.append(founder)
    return founders


def build_job_from_parsed(job_data: Dict, slug: str, job_id: str) -> Job:
    """Build Job model from parsed data."""
    # Build salary
    salary = None
    if job_data.get('salary'):
        salary = Salary(
            min=job_data['salary'].get('min'),
            max=job_data['salary'].get('max'),
            currency=job_data['salary'].get('currency', 'USD')
        )
    
    # Build equity
    equity = None
    if job_data.get('equity'):
        equity = Equity(
            min=job_data['equity'].get('min'),
            max=job_data['equity'].get('max')
        )
    
    # Build job URL
    job_url = f"https://www.ycombinator.com/companies/{slug}/jobs/{job_id}"
    
    return Job(
        jobId=job_id,
        title=job_data.get('title', ''),
        jobUrl=job_url,
        location=job_data.get('location'),
        salary=salary,
        equity=equity,
        jobType=job_data.get('jobType'),
        roleCategory=job_data.get('roleCategory'),
        experience=job_data.get('experience'),
        visa=job_data.get('visa'),
        skills=job_data.get('skills', []),
        description=job_data.get('description'),
        interviewProcess=job_data.get('interviewProcess'),
        applyUrl=job_data.get('applyUrl')
    )


async def process_company(
    company_data: Dict[str, Any],
    include_founder_descriptions: bool = True,
    rate_limit_delay: float = 1.5
) -> Optional[CompanyOutput]:
    """
    Process a single company: scrape company page and job pages, extract data.
    
    Args:
        company_data: Company data from hiring.json
        include_founder_descriptions: Whether to scrape company page for founder descriptions
        rate_limit_delay: Delay between requests in seconds
    
    Returns:
        CompanyOutput or None if processing failed
    """
    slug = company_data.get('slug')
    if not slug:
        logger.warning(f"Company {company_data.get('name')} has no slug, skipping")
        return None
    
    logger.info(f"Processing company: {company_data.get('name')} ({slug})")
    
    try:
        # Scrape company page
        company_html = None
        company_parsed = {'socialLinks': {}, 'founders': [], 'foundedYear': None}
        
        if include_founder_descriptions or True:  # Always scrape for social links and founded year
            company_html = await scrape_company_page(slug)
            await asyncio.sleep(rate_limit_delay)  # Rate limiting
            
            if company_html:
                company_parsed = parse_company_page(company_html)
            else:
                logger.warning(f"Failed to scrape company page for {slug}")
        
        # Extract job IDs from company page
        job_ids = []
        if company_html:
            job_ids = extract_job_ids_from_parsed_page(company_html)
        
        # Scrape each job page
        jobs = []
        job_founders = []
        
        for job_id in job_ids:
            job_html = await scrape_job_page(slug, job_id)
            await asyncio.sleep(rate_limit_delay)  # Rate limiting
            
            if job_html:
                job_parsed = parse_job_page(job_html)
                
                # Build job model
                job = build_job_from_parsed(job_parsed, slug, job_id)
                if job.title:  # Only add if we have a title
                    jobs.append(job)
                
                # Collect founder data from job page (backup)
                if job_parsed.get('founders'):
                    job_founders.extend(job_parsed['founders'])
            else:
                logger.warning(f"Failed to scrape job page for {slug}/jobs/{job_id}")
        
        # Build company model
        company = build_company_from_hiring_json(company_data, company_parsed)
        
        # Merge founders
        company_founders = build_founders_from_parsed(company_parsed.get('founders', []))
        job_founders_models = build_founders_from_parsed(job_founders)
        merged_founders = merge_founders(company_founders, job_founders_models)
        
        # Build output
        output = CompanyOutput(
            company=company,
            founders=merged_founders,
            jobs=jobs,
            scrapedAt=datetime.utcnow()
        )
        
        logger.info(f"Processed {company.name}: {len(jobs)} jobs, {len(merged_founders)} founders")
        return output
        
    except Exception as e:
        logger.error(f"Error processing company {slug}: {str(e)}", exc_info=True)
        return None


def extract_job_ids_from_parsed_page(html: str) -> List[str]:
    """Extract job IDs from parsed HTML."""
    # This is a helper that tries multiple methods to find job IDs
    job_ids = extract_job_ids_from_company_page(html)
    
    # Alternative: look for job listing elements
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'lxml')
    
    # Find all links that might be job links
    for link in soup.find_all('a', href=True):
        href = link.get('href', '')
        match = re.search(r'/jobs/([a-zA-Z0-9_-]+)', href)
        if match:
            job_id = match.group(1)
            if job_id not in job_ids:
                job_ids.append(job_id)
    
    return job_ids


async def main():
    """Main actor entry point."""
    async with Actor() as actor:
        # Get input
        input_data = await actor.get_input() or {}
        
        max_companies = input_data.get('maxCompanies')
        filter_by_batch = input_data.get('filterByBatch', [])
        filter_by_industry = input_data.get('filterByIndustry', [])
        filter_by_stage = input_data.get('filterByStage', [])
        filter_by_location = input_data.get('filterByLocation', [])
        top_companies_only = input_data.get('topCompaniesOnly', False)
        include_founder_descriptions = input_data.get('includeFounderDescriptions', True)
        rate_limit_delay = input_data.get('rateLimitDelay', 1.5)
        
        logger.info("Starting YC Jobs Scraper")
        logger.info(f"Input: maxCompanies={max_companies}, filters={input_data}")
        
        # Fetch hiring.json
        companies_data = await fetch_hiring_json()
        
        # Filter companies
        filtered_companies = filter_companies(
            companies_data,
            max_companies=max_companies,
            filter_by_batch=filter_by_batch,
            filter_by_industry=filter_by_industry,
            filter_by_stage=filter_by_stage,
            filter_by_location=filter_by_location,
            top_companies_only=top_companies_only
        )
        
        # Process companies
        results = []
        for i, company_data in enumerate(filtered_companies, 1):
            logger.info(f"Processing company {i}/{len(filtered_companies)}")
            result = await process_company(
                company_data,
                include_founder_descriptions=include_founder_descriptions,
                rate_limit_delay=rate_limit_delay
            )
            
            if result:
                # Push to dataset
                await actor.push_data(result.model_dump(mode='json'))
                results.append(result)
        
        logger.info(f"Completed scraping. Processed {len(results)} companies")
        
        # Set output summary
        await actor.set_value('OUTPUT', {
            'totalCompanies': len(results),
            'totalJobs': sum(len(r.jobs) for r in results),
            'totalFounders': sum(len(r.founders) for r in results)
        })
