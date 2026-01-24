"""HTTP scraping logic for YC pages using aiohttp."""
import asyncio
import logging
from typing import Optional
import aiohttp

logger = logging.getLogger(__name__)

# Headers to mimic a real browser
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}


async def scrape_page(url: str, retries: int = 3, delay: float = 1.0) -> Optional[str]:
    """
    Scrape a single page using aiohttp.
    
    Args:
        url: URL to scrape
        retries: Number of retry attempts
        delay: Delay between retries in seconds
    
    Returns:
        HTML content or None if scraping failed
    """
    for attempt in range(retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        html = await response.text()
                        if html:
                            return html
                        else:
                            logger.warning(f"⚠️ Scraping {url} returned empty HTML (attempt {attempt + 1}/{retries})")
                    else:
                        logger.warning(f"⚠️ Scraping {url} returned status {response.status} (attempt {attempt + 1}/{retries})")
        except asyncio.TimeoutError:
            logger.error(f"⏱️ Timeout scraping {url} (attempt {attempt + 1}/{retries})")
        except aiohttp.ClientError as e:
            logger.error(f"❌ Client error scraping {url} (attempt {attempt + 1}/{retries}): {str(e)}")
        except Exception as e:
            logger.error(f"❌ Error scraping {url} (attempt {attempt + 1}/{retries}): {str(e)}")
        
        if attempt < retries - 1:
            await asyncio.sleep(delay * (2 ** attempt))  # Exponential backoff
        else:
            logger.error(f"❌ Failed to scrape {url} after {retries} attempts")
    
    return None


async def scrape_company_page(slug: str, retries: int = 3) -> Optional[str]:
    """
    Scrape a company page.
    
    Args:
        slug: Company slug (e.g., 'airbnb')
        retries: Number of retry attempts
    
    Returns:
        HTML content or None if scraping failed
    """
    url = f"https://www.ycombinator.com/companies/{slug}"
    logger.info(f"🏢 Scraping company page: {url}")
    return await scrape_page(url, retries=retries)


async def scrape_job_page(slug: str, job_id: str, retries: int = 3) -> Optional[str]:
    """
    Scrape a job page.
    
    Args:
        slug: Company slug
        job_id: Job ID (e.g., 'yaLKuLq')
        retries: Number of retry attempts
    
    Returns:
        HTML content or None if scraping failed
    """
    url = f"https://www.ycombinator.com/companies/{slug}/jobs/{job_id}"
    logger.info(f"📄 Scraping job page: {url}")
    return await scrape_page(url, retries=retries)
