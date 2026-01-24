"""Main actor logic for YC Jobs Scraper."""
import asyncio
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime
import aiohttp
from apify import Actor

from .models import Company, CompanyOutput, Founder, Job, SocialLinks, Salary, Equity
from .scraper import scrape_company_page, scrape_job_page
from .parsers import parse_company_page, parse_job_page

logger = logging.getLogger(__name__)

HIRING_JSON_URL = "https://yc-oss.github.io/api/companies/hiring.json"


async def fetch_hiring_json() -> List[Dict[str, Any]]:
    """Fetch the hiring.json API."""
    async with aiohttp.ClientSession() as session:
        async with session.get(HIRING_JSON_URL) as response:
            if response.status == 200:
                data = await response.json()
                logger.info(f"📥 Fetched {len(data)} companies from hiring.json")
                return data
            else:
                logger.error(f"❌ Failed to fetch hiring.json: {response.status}")
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
    
    # Filter to only companies that are actively hiring
    filtered = [c for c in filtered if c.get('isHiring', False) is True]
    logger.info(f"🔍 Filtered to {len(filtered)} companies with isHiring=True")
    
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
    
    logger.info(f"🔍 Filtered to {len(filtered)} companies")
    return filtered


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
            currency=job_data['salary'].get('currency', 'USD'),
            period=job_data['salary'].get('period')
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
        description=job_data.get('description'),
        interviewProcess=job_data.get('interviewProcess')
    )


def build_job_from_company_page(job_data: Dict, slug: str) -> Job:
    """Build Job model from job data parsed from company page."""
    job_id = job_data.get('jobId', '')
    
    # Build salary
    salary = None
    if job_data.get('salary'):
        salary = Salary(
            min=job_data['salary'].get('min'),
            max=job_data['salary'].get('max'),
            currency=job_data['salary'].get('currency', 'USD'),
            period=job_data['salary'].get('period')
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
        jobType=None,  # Not available on company page
        roleCategory=None,  # Not available on company page
        experience=job_data.get('experience'),
        visa=None,  # Not available on company page
        description=None,  # Not available on company page
        interviewProcess=None  # Not available on company page
    )


async def process_company(
    company_data: Dict[str, Any],
    include_founder_descriptions: bool = True,
    include_job_details: bool = True,
    rate_limit_delay: float = 1.5
) -> Optional[CompanyOutput]:
    """
    Process a single company: scrape company page and extract all data.
    
    Args:
        company_data: Company data from hiring.json
        include_founder_descriptions: Whether to scrape company page for founder descriptions
        include_job_details: Whether to scrape individual job pages for full details
        rate_limit_delay: Delay between requests in seconds
    
    Returns:
        CompanyOutput or None if processing failed
    """
    slug = company_data.get('slug')
    if not slug:
        logger.warning(f"⚠️ Company {company_data.get('name')} has no slug, skipping")
        return None
    
    logger.info(f"🏢 Processing company: {company_data.get('name')} ({slug})")
    
    try:
        # Scrape company page
        company_html = await scrape_company_page(slug)
        await asyncio.sleep(rate_limit_delay)  # Rate limiting
        
        if not company_html:
            logger.warning(f"⚠️ Failed to scrape company page for {slug}")
            return None
        
        # Parse company page - this extracts social links, founders, AND basic job info
        company_parsed = parse_company_page(company_html)
        
        # Build company model
        company = build_company_from_hiring_json(company_data, company_parsed)
        
        # Build founders from parsed data
        founders = build_founders_from_parsed(company_parsed.get('founders', []))
        
        # Build jobs - get basic info from company page, then enrich with job page details
        jobs = []
        job_page_founders = []  # Backup founders from job pages
        
        for job_data in company_parsed.get('jobs', []):
            job_id = job_data.get('jobId', '')
            
            if include_job_details and job_id:
                # Scrape individual job page for complete details
                logger.info(f"📄 Scraping job page: {slug}/jobs/{job_id}")
                job_html = await scrape_job_page(slug, job_id)
                await asyncio.sleep(rate_limit_delay)  # Rate limiting
                
                if job_html:
                    # Parse job page for full details
                    job_page_data = parse_job_page(job_html)
                    
                    # Extract founders from job page as backup (if company page has none)
                    if not founders and not job_page_founders:
                        job_founders_data = job_page_data.get('founders', [])
                        if job_founders_data:
                            job_page_founders = job_founders_data
                            logger.info(f"👥 Found {len(job_page_founders)} founders on job page for {slug}")
                    
                    # Merge job data: prefer job page data, fall back to company page data
                    merged_job_data = {
                        'jobId': job_id,
                        'title': job_page_data.get('title') or job_data.get('title'),
                        'location': job_page_data.get('location') or job_data.get('location'),
                        'salary': job_page_data.get('salary') or job_data.get('salary'),
                        'equity': job_page_data.get('equity') or job_data.get('equity'),
                        'jobType': job_page_data.get('jobType'),
                        'roleCategory': job_page_data.get('roleCategory'),
                        'experience': job_page_data.get('experience') or job_data.get('experience'),
                        'visa': job_page_data.get('visa'),
                        'description': job_page_data.get('description'),
                        'interviewProcess': job_page_data.get('interviewProcess'),
                    }
                    
                    job = build_job_from_parsed(merged_job_data, slug, job_id)
                else:
                    # Fallback to company page data only
                    job = build_job_from_company_page(job_data, slug)
            else:
                # Use company page data only (faster but less complete)
                job = build_job_from_company_page(job_data, slug)
            
            if job and job.title:
                jobs.append(job)
        
        # If no founders from company page, use founders from job page
        if not founders and job_page_founders:
            founders = build_founders_from_parsed(job_page_founders)
            logger.info(f"👥 Using {len(founders)} founders from job page for {slug}")
        
        # Build output
        output = CompanyOutput(
            company=company,
            founders=founders,
            jobs=jobs,
            scrapedAt=datetime.utcnow()
        )
        
        logger.info(f"✅ Processed {company.name}: {len(jobs)} jobs, {len(founders)} founders")
        return output
        
    except Exception as e:
        logger.error(f"❌ Error processing company {slug}: {str(e)}", exc_info=True)
        return None


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
        include_job_details = input_data.get('includeJobDetails', True)
        rate_limit_delay = input_data.get('rateLimitDelay', 1.5)
        
        logger.info("🚀 Starting YC Jobs Scraper")
        logger.info(f"⚙️ Input: maxCompanies={max_companies}, includeJobDetails={include_job_details}, filters={input_data}")
        
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
            logger.info(f"🔄 Processing company {i}/{len(filtered_companies)}")
            result = await process_company(
                company_data,
                include_founder_descriptions=include_founder_descriptions,
                include_job_details=include_job_details,
                rate_limit_delay=rate_limit_delay
            )
            
            if result:
                # Push to dataset
                await actor.push_data(result.model_dump(mode='json'))
                results.append(result)
        
        logger.info(f"🎉 Completed scraping. Processed {len(results)} companies")
        
        # Set output summary
        await actor.set_value('OUTPUT', {
            'totalCompanies': len(results),
            'totalJobs': sum(len(r.jobs) for r in results),
            'totalFounders': sum(len(r.founders) for r in results)
        })
