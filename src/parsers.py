"""HTML parsing functions for YC company and job pages."""
import re
from typing import List, Optional, Dict
from bs4 import BeautifulSoup, Tag
from .models import Founder, SocialLinks, Job, Salary, Equity


def parse_company_page(html: str) -> Dict:
    """
    Parse company page HTML to extract:
    - Social links (LinkedIn, Twitter, GitHub, Facebook, Crunchbase) - COMPANY links only
    - Founders (name, role, description, LinkedIn, Twitter) - from Active Founders section
    - Founded year
    - Jobs with details (title, location, salary, equity, experience)
    """
    soup = BeautifulSoup(html, 'lxml')
    result = {
        'socialLinks': {},
        'founders': [],
        'foundedYear': None,
        'jobs': []
    }
    
    # Extract company social links from the company info section
    # These are near "Founded:", "Batch:", "Team Size:", "Status:", "Location:"
    result['socialLinks'] = _extract_company_social_links(soup)
    
    # Extract founded year
    result['foundedYear'] = _extract_founded_year(soup)
    
    # Extract founders from "Active Founders" section
    result['founders'] = _extract_founders(soup)
    
    # Extract jobs from job listings section
    result['jobs'] = _extract_jobs_from_company_page(soup)
    
    return result


def _extract_company_social_links(soup: BeautifulSoup) -> Dict[str, str]:
    """
    Extract company social links from the company info sidebar.
    
    Company social links are in a specific section containing:
    - Founded: year
    - Batch: batch name
    - Team Size: number
    - Status: Active/Inactive
    - Location: city, country
    
    The social links (website, linkedin, twitter, crunchbase, github) 
    are grouped together after this metadata in a small container.
    """
    social_links = {}
    
    # Find the section containing company metadata like "Founded:", "Team Size:", etc.
    # The company social links are in a SMALL container nearby (level 0-2)
    # NOT in a larger container that includes founder links
    
    for text_marker in ['Founded:', 'Team Size:', 'Batch:']:
        marker_elem = soup.find(string=lambda text: text and text_marker in text if text else False)
        if marker_elem:
            # Find the parent container - stay close (level 0-2 only)
            parent = marker_elem.find_parent(['div', 'section', 'aside'])
            if parent:
                # Go up only 0-2 levels to find the SMALL container with company links
                for level in range(3):
                    links = parent.find_all('a', href=True)
                    
                    # Check if this is the right container
                    # It should have linkedin.com/company but NOT linkedin.com/in
                    has_company_linkedin = any('linkedin.com/company' in (l.get('href', '') or '').lower() for l in links)
                    has_personal_linkedin = any('linkedin.com/in/' in (l.get('href', '') or '').lower() for l in links)
                    
                    if has_company_linkedin and not has_personal_linkedin:
                        # This is the right container - extract social links
                        for link in links:
                            href = link.get('href', '')
                            href_lower = href.lower()
                            
                            if 'linkedin.com/company/' in href_lower and 'linkedin' not in social_links:
                                social_links['linkedin'] = href
                            elif ('twitter.com/' in href_lower or 'x.com/' in href_lower) and 'twitter' not in social_links:
                                # In this small container, the Twitter is company's
                                social_links['twitter'] = href
                            elif 'github.com/' in href_lower and 'github' not in social_links:
                                if 'github.com/ycombinator' not in href_lower:
                                    social_links['github'] = href
                            elif 'crunchbase.com/' in href_lower and 'crunchbase' not in social_links:
                                social_links['crunchbase'] = href
                            elif 'facebook.com/' in href_lower and 'facebook' not in social_links:
                                if 'facebook.com/ycombinator' not in href_lower:
                                    social_links['facebook'] = href
                        break
                    
                    # Go up one level
                    if parent.parent and parent.parent.name in ['div', 'section', 'aside']:
                        parent = parent.parent
                    else:
                        break
                
                if social_links:
                    break
    
    # Fallback: if we didn't find company linkedin, search more specifically
    if 'linkedin' not in social_links:
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            if 'linkedin.com/company/' in href.lower():
                social_links['linkedin'] = href
                break
    
    # Fallback for twitter: look specifically for twitter.com (not x.com founder links)
    if 'twitter' not in social_links:
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            href_lower = href.lower()
            # Prefer twitter.com over x.com (x.com links are often founder personal)
            if 'twitter.com/' in href_lower and 'twitter.com/ycombinator' not in href_lower:
                social_links['twitter'] = href
                break
    
    return social_links


def _extract_founded_year(soup: BeautifulSoup) -> Optional[int]:
    """Extract the founded year from company metadata."""
    # Look for "Founded:" followed by a year
    founded_elem = soup.find(string=lambda text: text and 'Founded:' in text if text else False)
    if founded_elem:
        parent = founded_elem.find_parent()
        if parent:
            # The year is usually in a sibling or nearby element
            text = parent.get_text()
            years = re.findall(r'\b(19\d{2}|20\d{2})\b', text)
            if years:
                try:
                    return int(years[0])
                except ValueError:
                    pass
    
    # Alternative: look for standalone year near "Founded"
    for elem in soup.find_all(string=lambda text: text and 'founded' in text.lower() if text else False):
        parent = elem.find_parent()
        if parent:
            # Look in next siblings for year
            for sibling in parent.find_next_siblings(limit=3):
                if sibling:
                    text = sibling.get_text() if hasattr(sibling, 'get_text') else str(sibling)
                    years = re.findall(r'\b(19\d{2}|20\d{2})\b', text)
                    if years:
                        try:
                            return int(years[0])
                        except ValueError:
                            pass
    
    return None


def _extract_founders(soup: BeautifulSoup) -> List[Dict]:
    """
    Extract founders from the "Active Founders" section.
    
    The page structure is predictable:
    - "Active Founders" heading
    - For each founder: Image (with name as alt) → Name → Social links → Role → Description
    - Section ends at "Latest News" or similar heading
    """
    founders = []
    seen_names = set()
    
    # Find "Active Founders" heading
    founders_heading = soup.find(string=lambda text: text and 'Active Founders' in text if text else False)
    
    if not founders_heading:
        # Try alternative: just "Founders"
        founders_heading = soup.find(string=lambda text: text and text.strip() == 'Founders' if text else False)
    
    if not founders_heading:
        return founders
    
    # Get the parent container and find the section boundaries
    container = founders_heading.find_parent(['div', 'section'])
    if not container:
        return founders
    
    # Go up to get the full founders section
    for _ in range(5):
        if container.parent and container.parent.name in ['div', 'section']:
            container = container.parent
    
    # Get the text content of the founders section
    # We'll extract everything between "Active Founders" and the next major section
    full_text = container.get_text(separator='\n', strip=True)
    
    # Find the founders section boundaries
    start_idx = full_text.find('Active Founders')
    if start_idx == -1:
        start_idx = 0
    else:
        start_idx += len('Active Founders')
    
    # Find where founders section ends (next major section)
    end_markers = ['Latest News', 'Company Launches', 'Jobs at', 'YC Photos', 'Founded:']
    end_idx = len(full_text)
    for marker in end_markers:
        idx = full_text.find(marker, start_idx)
        if idx != -1 and idx < end_idx:
            end_idx = idx
    
    founders_text = full_text[start_idx:end_idx]
    
    # Find all founder images in the section (they have person names as alt text)
    # This gives us the list of founder names
    founder_names = []
    for img in container.find_all('img', alt=True):
        alt_text = img.get('alt', '').strip()
        
        # Skip non-person images and known non-founder names
        skip_terms = ['Twitter', 'LinkedIn', 'Logo', 'photo', 'image', 'icon', 'video', 'YouTube', 
                      'Y Combinator', 'Combinator', 'YC']
        if not alt_text or any(term.lower() in alt_text.lower() for term in skip_terms):
            continue
        
        # Check if it looks like a name (2-4 words)
        # Note: Don't require capitalization - some founders use lowercase names (e.g., "matt debergalis")
        words = alt_text.split()
        if len(words) >= 2 and len(words) <= 4:
            # IMPORTANT: Only include names that actually appear in the founders section text
            # This prevents picking up random images from other parts of the page
            if alt_text in founders_text and alt_text not in founder_names:
                founder_names.append(alt_text)
    
    # Now extract info for each founder from the text
    # Role keywords to identify roles
    role_keywords = ['CEO', 'CTO', 'COO', 'CFO', 'Founder', 'Co-founder', 'Cofounder', 'Partner', 'President']
    
    for name in founder_names:
        if name in seen_names:
            continue
        seen_names.add(name)
        
        founder = {
            'name': name,
            'role': None,
            'description': None,
            'linkedin': None,
            'twitter': None
        }
        
        # Find this founder's section in the text
        # Look for the name and extract the role and description that follow
        name_idx = founders_text.find(name)
        if name_idx == -1:
            continue
        
        # Get text after the name (up to next founder or end)
        next_founder_idx = len(founders_text)
        for other_name in founder_names:
            if other_name != name:
                idx = founders_text.find(other_name, name_idx + len(name))
                if idx != -1 and idx < next_founder_idx:
                    next_founder_idx = idx
        
        founder_section = founders_text[name_idx:next_founder_idx]
        lines = [line.strip() for line in founder_section.split('\n') if line.strip()]
        
        # Parse the lines: Name → Role → Description
        for i, line in enumerate(lines):
            # Skip the name itself
            if line == name:
                continue
            
            # Check if this is a role line
            if any(keyword in line for keyword in role_keywords) and len(line) < 50:
                if not founder['role']:
                    founder['role'] = line
                continue
            
            # Check if this is a description (long text, often starts with the founder's name)
            if len(line) > 80:
                if not founder['description']:
                    founder['description'] = line
                break
        
        # Extract social links from the HTML for this founder
        # Find the founder's image and look for links in the same card
        founder_img = container.find('img', alt=name)
        if founder_img:
            # Go up to find the founder card container
            card = founder_img
            for _ in range(6):
                if card.parent:
                    card = card.parent
                    # Check if this card has social links and role text
                    card_text = card.get_text()
                    card_links = card.find_all('a', href=True)
                    has_personal_linkedin = any('linkedin.com/in/' in (l.get('href', '') or '').lower() for l in card_links)
                    has_role = any(kw in card_text for kw in role_keywords)
                    if has_personal_linkedin and has_role:
                        break
            
            # Extract links from the card
            for link in card.find_all('a', href=True):
                href = link.get('href', '')
                href_lower = href.lower()
                
                if 'linkedin.com/in/' in href_lower and not founder['linkedin']:
                    founder['linkedin'] = href
                elif ('x.com/' in href_lower or 'twitter.com/' in href_lower) and not founder['twitter']:
                    # Skip company twitter (usually has _HQ or company name)
                    if '_HQ' not in href and 'ycombinator' not in href_lower:
                        founder['twitter'] = href
        
        founders.append(founder)
    
    return founders


def _extract_founders_from_job_page(soup: BeautifulSoup) -> List[Dict]:
    """
    Extract founders from the job page.
    
    Job pages have a "Founders" section (NOT "Active Founders") with simpler cards:
    - The card is in a div with class "ycdc-card-new"
    - Each founder has: image (with name as alt), name text, LinkedIn link, role
    
    This is used as a backup when the company page has no active founders.
    
    IMPORTANT: We must NOT pick up company logos from "Similar Jobs" section!
    """
    founders = []
    seen_names = set()
    
    # Find "Founders" heading on job page (note: NOT "Active Founders")
    founders_heading = None
    for elem in soup.find_all(string=lambda text: text and text.strip() == 'Founders' if text else False):
        # Make sure it's just "Founders", not "Active Founders"
        founders_heading = elem
        break
    
    if not founders_heading:
        return founders
    
    # Find the founder cards - they are in divs with class "ycdc-card-new" near the Founders heading
    # First, get the parent that contains the "Founders" heading
    founders_parent = founders_heading.find_parent(['div', 'section'])
    if not founders_parent:
        return founders
    
    # Find the specific founder card container - look for ycdc-card-new class
    # Go up only 2-3 levels to find the card container, not the entire page
    founder_cards_container = None
    container = founders_parent
    for _ in range(3):
        if container.parent:
            container = container.parent
            # Look for the ycdc-card-new div within this container
            card_divs = container.find_all('div', class_=lambda c: c and 'ycdc-card' in c)
            if card_divs:
                # Check if this container has personal LinkedIn links (founder links)
                # but is NOT the Similar Jobs section
                container_text = container.get_text()
                if 'Similar Jobs' not in container_text:
                    founder_cards_container = container
                    break
    
    if not founder_cards_container:
        # Fallback: just use immediate parent of Founders heading
        founder_cards_container = founders_parent
        for _ in range(2):
            if founder_cards_container.parent:
                founder_cards_container = founder_cards_container.parent
    
    # Now extract founders, but be very careful to only look in the founders section
    # Get text boundaries - stop at "Similar Jobs" or other sections
    container_text = founder_cards_container.get_text()
    
    # Find where founders section ends
    similar_jobs_idx = container_text.find('Similar Jobs')
    if similar_jobs_idx != -1:
        # Limit our search to before "Similar Jobs"
        founders_section_text = container_text[:similar_jobs_idx]
    else:
        founders_section_text = container_text
    
    # Find all images that are BEFORE the Similar Jobs section
    for img in founder_cards_container.find_all('img', alt=True):
        alt_text = img.get('alt', '').strip()
        
        # Skip non-person images
        skip_terms = ['Twitter', 'LinkedIn', 'Logo', 'photo', 'image', 'icon', 'video', 
                      'YouTube', 'Y Combinator', 'Combinator', 'YC', 'logo']
        if not alt_text or any(term.lower() in alt_text.lower() for term in skip_terms):
            continue
        
        # Check if it looks like a name (2-4 words)
        # Note: Don't require capitalization - some founders use lowercase names (e.g., "matt debergalis")
        words = alt_text.split()
        if len(words) < 2 or len(words) > 4:
            continue
        
        # CRITICAL: Only include if the name appears in the founders section text (before Similar Jobs)
        if alt_text not in founders_section_text:
            continue
        
        if alt_text in seen_names:
            continue
        seen_names.add(alt_text)
        
        founder = {
            'name': alt_text,
            'role': None,
            'description': None,
            'linkedin': None,
            'twitter': None
        }
        
        # Find the founder card container - go up from the image
        # The card should be small and contain: name, role, linkedin
        card = img
        for _ in range(5):
            if card.parent:
                card = card.parent
                card_text = card.get_text()
                card_links = card.find_all('a', href=True)
                has_linkedin = any('linkedin.com/in/' in (l.get('href', '') or '').lower() for l in card_links)
                
                # Check if this contains the founder's name and has LinkedIn link
                # But make sure it's not too big (not the whole page)
                if alt_text in card_text and has_linkedin and len(card_text) < 500:
                    break
        
        # Extract role from the card
        role_keywords = ['CEO', 'CTO', 'COO', 'CFO', 'Founder', 'Co-founder', 'Cofounder', 
                         'Partner', 'President', 'Co-Founder']
        
        card_text = card.get_text(separator='\n', strip=True)
        lines = [line.strip() for line in card_text.split('\n') if line.strip()]
        
        for line in lines:
            if line == alt_text:
                continue
            if any(keyword.lower() in line.lower() for keyword in role_keywords) and len(line) < 50:
                founder['role'] = line
                break
        
        # Extract LinkedIn and Twitter links from the card
        for link in card.find_all('a', href=True):
            href = link.get('href', '')
            href_lower = href.lower()
            
            if 'linkedin.com/in/' in href_lower and not founder['linkedin']:
                founder['linkedin'] = href
            elif ('x.com/' in href_lower or 'twitter.com/' in href_lower) and not founder['twitter']:
                # Skip company twitter
                if '_HQ' not in href and 'ycombinator' not in href_lower:
                    founder['twitter'] = href
        
        # Only add if we found a LinkedIn (confirms it's a real founder card)
        if founder['name'] and founder['linkedin']:
            founders.append(founder)
    
    return founders


def _extract_jobs_from_company_page(soup: BeautifulSoup) -> List[Dict]:
    """
    Extract job listings from the company page.
    
    Jobs section contains:
    - Job title (link to job page)
    - Location
    - Salary range
    - Equity range
    - Experience level
    """
    jobs = []
    
    # Find jobs section - usually has "Jobs at {Company}" heading
    jobs_heading = soup.find(string=lambda text: text and 'Jobs at' in text if text else False)
    if not jobs_heading:
        jobs_heading = soup.find(string=lambda text: text and text.strip() == 'Jobs' if text else False)
    
    if jobs_heading:
        # Find container with job listings
        container = jobs_heading.find_parent(['div', 'section'])
        if container:
            # Go up to get full jobs section
            for _ in range(3):
                if container.parent and container.parent.name in ['div', 'section']:
                    container = container.parent
            
            # Find all job links
            job_links = container.find_all('a', href=lambda h: h and '/jobs/' in h if h else False)
            
            seen_job_ids = set()
            for link in job_links:
                href = link.get('href', '')
                # Extract job ID from URL
                job_match = re.search(r'/jobs/([a-zA-Z0-9_-]+)', href)
                if job_match:
                    job_id = job_match.group(1)
                    if job_id in seen_job_ids:
                        continue
                    seen_job_ids.add(job_id)
                    
                    # Get job title from link text
                    title = link.get_text(strip=True)
                    if title and title not in ['View all jobs', 'Apply Now', 'Apply']:
                        # Find the job card container
                        job_card = link.find_parent(['div', 'li', 'article'])
                        job_data = _extract_job_from_card(job_card, job_id, title)
                        if job_data:
                            jobs.append(job_data)
    
    return jobs


def _looks_like_title(location: str, title: Optional[str]) -> bool:
    """True when a 'location' match is really part of the job title.

    YC job cards put the title and the location in the same block of text, and
    the loosest location pattern ("Capitalized, Capitalized") happily matches a
    title such as "Product Engineer, New Products".
    """
    if not title or not location:
        return False
    normalized_title = ' '.join(title.split()).lower()
    normalized_location = ' '.join(location.split()).lower()
    return normalized_location in normalized_title


def _extract_job_from_card(card: Tag, job_id: str, title: str) -> Optional[Dict]:
    """Extract job information from a job card on the company page."""
    job = {
        'jobId': job_id,
        'title': title,
        'location': None,
        'salary': None,
        'equity': None,
        'experience': None
    }
    
    if not card:
        return job
    
    # The job card might be too small - go up levels to find the full card with all details
    # Job info format: "Title | Location | $XXK - $XXK | X.XX% - X.XX% | Experience | Apply"
    card_text = card.get_text(separator=' | ', strip=True)
    
    # If card is too small (no salary/location info), go up a few levels
    if '$' not in card_text and '£' not in card_text and '€' not in card_text:
        parent = card
        for _ in range(3):  # Go up max 3 levels
            if parent.parent:
                parent = parent.parent
                parent_text = parent.get_text(separator=' | ', strip=True)
                # Check if this level has salary info and is still a single job card
                if ('$' in parent_text or '£' in parent_text or '€' in parent_text):
                    # Make sure this is a single job card (contains our job title)
                    if title in parent_text:
                        # Find where this job's info ends (before next job title or "Apply Now")
                        # Split by common delimiters
                        parts = parent_text.split(' | ')
                        job_parts = []
                        found_title = False
                        for part in parts:
                            if title in part:
                                found_title = True
                            if found_title:
                                job_parts.append(part)
                                if 'Apply Now' in part or 'Apply ›' in part:
                                    break
                        if job_parts:
                            card_text = ' | '.join(job_parts)
                            break
    
    # Extract location - usually city, state format or "Remote"
    # Common patterns: "Deerfield, MA, US / Remote (US)", "UK / Remote (US)", etc.
    location_patterns = [
        r'([A-Z][a-zA-Z\s]+,\s*[A-Z]{2}(?:,\s*[A-Z]{2})?\s*/\s*Remote(?:\s*\([^)]+\))?)',  # City, ST, US / Remote (US)
        r'([A-Z][a-zA-Z\s]+,\s*[A-Z]{2}\s*/\s*Remote(?:\s*\([^)]+\))?)',  # City, ST / Remote
        r'([A-Z]{2,}\s*/\s*Remote\s*\([^)]+\))',  # UK / Remote (US)
        r'(Remote\s*\([^)]+\))',  # Remote (US)
        r'([A-Z][a-zA-Z\s]+,\s*[A-Z][a-zA-Z\s]+)',  # City, State/Country
    ]
    for pattern in location_patterns:
        for match in re.finditer(pattern, card_text):
            location = match.group(1).strip()
            # Exclude things that look like locations but aren't. The last
            # pattern is just "Capitalized, Capitalized", which also matches job
            # titles carrying a comma ("Senior Account Executive, Korea"), so
            # reject anything the title already contains.
            if location in ['Any', 'Apply Now']:
                continue
            if _looks_like_title(location, title):
                continue
            job['location'] = location
            break
        if job['location']:
            break
    
    # Extract salary - patterns like "$140K - $250K" or "£80K - £150K GBP"
    salary_match = re.search(r'[\$£€](\d+)K?\s*[-–]\s*[\$£€]?(\d+)K?(?:\s*(USD|GBP|EUR))?', card_text, re.IGNORECASE)
    if salary_match:
        min_sal = int(salary_match.group(1))
        max_sal = int(salary_match.group(2))
        # If values are small, they're in K (thousands)
        if min_sal < 1000:
            min_sal *= 1000
        if max_sal < 1000:
            max_sal *= 1000
        currency = salary_match.group(3) or 'USD'
        if '£' in card_text:
            currency = 'GBP'
        elif '€' in card_text:
            currency = 'EUR'
        job['salary'] = {'min': min_sal, 'max': max_sal, 'currency': currency}
    
    # Extract equity - patterns like "0.10% - 0.40%"
    equity_match = re.search(r'(\d+\.?\d*)\s*%\s*[-–]\s*(\d+\.?\d*)\s*%', card_text)
    if equity_match:
        job['equity'] = {
            'min': float(equity_match.group(1)),
            'max': float(equity_match.group(2))
        }
    
    # Extract experience level
    exp_patterns = ['Any (new grads ok)', 'New grad', 'Entry level', 'Mid-level', 'Senior', 'Staff', 'Principal']
    for exp in exp_patterns:
        if exp.lower() in card_text.lower():
            job['experience'] = exp
            break
    
    return job


def parse_job_page(html: str) -> Dict:
    """
    Parse job page HTML to extract complete job information.
    
    YC job pages have this structure:
    - Job metadata section with labels like "Job type", "Role", "Experience", "Visa"
    - "About the role" section with full description
    - "About the interview" section
    - Apply link
    """
    soup = BeautifulSoup(html, 'lxml')
    result = {
        'title': None,
        'salary': None,
        'equity': None,
        'location': None,
        'jobType': None,
        'roleCategory': None,
        'experience': None,
        'visa': None,
        'description': None,
        'interviewProcess': None,
        'founders': []  # Backup founder data
    }
    
    # Extract job title (usually in h1)
    title_elem = soup.find('h1')
    if title_elem:
        result['title'] = title_elem.get_text(strip=True)
    
    # Get full page text for salary/equity extraction
    page_text = soup.get_text()
    
    # Extract salary - handle multiple formats:
    # 1. Range: "$140K - $250K" or "£80K - £150K"
    # 2. Monthly: "$6K / monthly" or "$6K/monthly"
    # 3. Annual single: "$150K" (less common)
    
    # Try monthly salary first (e.g., "$6K / monthly")
    monthly_match = re.search(r'[\$£€](\d+)K?\s*/?\s*monthly', page_text, re.IGNORECASE)
    if monthly_match:
        monthly_amount = int(monthly_match.group(1))
        if monthly_amount < 1000:
            monthly_amount *= 1000
        currency = 'USD'
        match_text = monthly_match.group(0)
        if '£' in match_text:
            currency = 'GBP'
        elif '€' in match_text:
            currency = 'EUR'
        result['salary'] = {'min': monthly_amount, 'max': monthly_amount, 'currency': currency, 'period': 'monthly'}
    else:
        # Try salary range (e.g., "$140K - $250K")
        salary_match = re.search(r'[\$£€](\d+)K?\s*[-–—•]\s*[\$£€]?(\d+)K?', page_text)
        if salary_match:
            min_sal = int(salary_match.group(1))
            max_sal = int(salary_match.group(2))
            # If values are small, they're in K (thousands)
            if min_sal < 1000:
                min_sal *= 1000
            if max_sal < 1000:
                max_sal *= 1000
            currency = 'USD'
            if '£' in page_text[:page_text.find(salary_match.group(0)) + 50]:
                currency = 'GBP'
            elif '€' in page_text[:page_text.find(salary_match.group(0)) + 50]:
                currency = 'EUR'
            result['salary'] = {'min': min_sal, 'max': max_sal, 'currency': currency}
    
    # Extract equity range - patterns like "0.10% - 0.40%"
    equity_match = re.search(r'(\d+\.?\d*)\s*%\s*[-–—•]\s*(\d+\.?\d*)\s*%', page_text)
    if equity_match:
        result['equity'] = {
            'min': float(equity_match.group(1)),
            'max': float(equity_match.group(2))
        }
    
    # Extract location from the header line (format: "$140K - $250K•0.10% - 0.40%•Location")
    # Or look for text after salary/equity before "Job type"
    location_patterns = [
        r'[\d.]+%\s*•\s*([^•\n]+?)(?:\s*Job type|\s*$)',  # After equity percentage
        r'([A-Z][a-zA-Z\s]+,\s*[A-Z]{2}(?:,\s*[A-Z]{2})?\s*/\s*Remote(?:\s*\([^)]+\))?)',  # City, ST / Remote
        r'(Remote\s*\([^)]+\))',  # Remote (US)
    ]
    for pattern in location_patterns:
        match = re.search(pattern, page_text)
        if match:
            location = match.group(1).strip()
            if location and location not in ['Any', 'Apply Now', 'Apply to role']:
                result['location'] = location
                break
    
    # Extract job metadata (Job type, Role, Experience, Visa)
    # YC pages have a pattern like:
    # <strong>Job type</strong> followed by <div>Full-time</div>
    # or the text appears as "Job type\nFull-time"
    
    # Method 1: Look for strong/bold labels followed by values
    for strong in soup.find_all(['strong', 'b']):
        label = strong.get_text(strip=True).lower()
        # Get the next sibling or parent's next sibling for the value
        value = None
        
        # Check next sibling
        next_elem = strong.find_next_sibling()
        if next_elem:
            value = next_elem.get_text(strip=True)
        
        # If no sibling, check parent's next sibling
        if not value and strong.parent:
            parent_next = strong.parent.find_next_sibling()
            if parent_next:
                value = parent_next.get_text(strip=True)
        
        # If still no value, look at text right after the strong tag
        if not value:
            parent = strong.parent
            if parent:
                full_text = parent.get_text(strip=True)
                label_text = strong.get_text(strip=True)
                if label_text in full_text:
                    value = full_text.replace(label_text, '').strip()
        
        if value:
            if label == 'job type' and not result['jobType']:
                result['jobType'] = value
            elif label == 'role' and not result['roleCategory']:
                result['roleCategory'] = value
            elif label == 'experience' and not result['experience']:
                result['experience'] = value
            elif label == 'visa' and not result['visa']:
                result['visa'] = value
    
    # Method 2: Text-based extraction as fallback
    # Split text into lines and look for patterns
    lines = [line.strip() for line in page_text.split('\n') if line.strip()]
    for i, line in enumerate(lines):
        line_lower = line.lower()
        next_line = lines[i + 1] if i + 1 < len(lines) else ''
        
        if line_lower == 'job type' and not result['jobType'] and next_line:
            if next_line.lower() in ['full-time', 'part-time', 'contract', 'internship', 'full time', 'part time']:
                result['jobType'] = next_line
        elif line_lower == 'role' and not result['roleCategory'] and next_line:
            # Role can be multi-word like "Engineering, Full stack"
            if len(next_line) < 100 and not next_line.lower().startswith('about'):
                result['roleCategory'] = next_line
        elif line_lower == 'experience' and not result['experience'] and next_line:
            if len(next_line) < 50:
                result['experience'] = next_line
        elif line_lower == 'visa' and not result['visa'] and next_line:
            if len(next_line) < 100:
                result['visa'] = next_line
    
    # Extract "About the role" section (job description)
    # The description is between "About the role" heading and "About the interview" section
    # Note: There may be an "About {CompanyName}" SUBSECTION within the role description - keep that!
    # The separate company info section comes AFTER "About the interview" and has a tagline like "We're building..."
    
    # Find where "About the role" starts
    about_role_start = page_text.lower().find('about the role')
    
    if about_role_start != -1:
        # Get text after "About the role"
        desc_start = about_role_start + len('about the role')
        remaining_text = page_text[desc_start:]
        
        # Find where to stop - look for patterns that indicate end of description:
        # Primary stop: "About the interview" section
        # Secondary stops: Company info section markers
        stop_patterns = [
            # "About the interview" is the most reliable stop point
            (r'About\s+the\s+interview', re.IGNORECASE),
            # Company info section - look for the tagline pattern after company name
            # This matches "About CompanyName" followed by newline(s) and then "We're building" or similar
            (r'About\s+[A-Z][a-zA-Z]+\s*\n+\s*We\'re\s+building', re.IGNORECASE),
            # Founders section
            (r'\n\s*Founders\s*\n.*?CEO', re.IGNORECASE | re.DOTALL),
            # Similar Jobs section  
            (r'\n\s*Similar\s+Jobs\s*\n', re.IGNORECASE),
            # Company metadata footer (Founded:2012, Batch:W12, etc.)
            (r'Founded:\s*\d{4}\s*Batch:', re.IGNORECASE),
        ]
        
        end_pos = len(remaining_text)
        for pattern, flags in stop_patterns:
            match = re.search(pattern, remaining_text, flags) if flags else re.search(pattern, remaining_text)
            if match and match.start() < end_pos:
                end_pos = match.start()
        
        desc_text = remaining_text[:end_pos].strip()
        
        # Clean up the description
        if desc_text:
            # Remove duplicate paragraphs (YC pages often have content repeated)
            lines = desc_text.split('\n')
            seen_lines = set()
            unique_lines = []
            for line in lines:
                line = line.strip()
                if line and len(line) > 10:
                    # Normalize line for comparison (remove extra spaces)
                    normalized = ' '.join(line.split())
                    if normalized not in seen_lines:
                        seen_lines.add(normalized)
                        unique_lines.append(line)
            
            # Join and clean up
            desc_text = '\n\n'.join(unique_lines)
            
            # Remove any remaining job metadata that might have leaked in
            desc_text = re.sub(r'^(Job type|Role|Experience|Visa)\s*$', '', desc_text, flags=re.MULTILINE)
            desc_text = re.sub(r'^(Full-time|Part-time|Contract|Internship)\s*$', '', desc_text, flags=re.MULTILINE)
            desc_text = re.sub(r'^(Engineering,?\s*(?:Full stack|Backend|Frontend))\s*$', '', desc_text, flags=re.MULTILINE)
            desc_text = re.sub(r'^Any \(new grads ok\)\s*$', '', desc_text, flags=re.MULTILINE)
            desc_text = re.sub(r'Apply to.*?Apply to role ›', '', desc_text, flags=re.DOTALL)
            
            # Clean up multiple newlines
            desc_text = re.sub(r'\n{3,}', '\n\n', desc_text).strip()
            
            if len(desc_text) > 50:
                result['description'] = desc_text
    
    # Extract "About the interview" section
    about_interview_heading = soup.find(string=lambda text: text and 'about the interview' in text.lower() if text else False)
    if about_interview_heading:
        container = about_interview_heading.find_parent(['div', 'section']) if hasattr(about_interview_heading, 'find_parent') else None
        if container:
            # Find text after the heading
            interview_text = []
            found_heading = False
            for elem in container.find_all(['h2', 'h3', 'p', 'div'], recursive=True):
                elem_text = elem.get_text(strip=True)
                if 'about the interview' in elem_text.lower():
                    found_heading = True
                    continue
                if found_heading and elem_text:
                    # Stop at next section
                    if elem.name in ['h2'] and 'about' in elem_text.lower():
                        break
                    if len(elem_text) > 10 and elem_text not in interview_text:
                        interview_text.append(elem_text)
                        # Usually just one paragraph
                        if len(interview_text) >= 2:
                            break
            
            if interview_text:
                result['interviewProcess'] = '\n\n'.join(interview_text)
    
    # Fallback for interview section
    if not result['interviewProcess']:
        interview_match = re.search(
            r'About the interview\s*(.+?)(?:About |Founders|Similar Jobs|$)',
            page_text,
            re.DOTALL | re.IGNORECASE
        )
        if interview_match:
            interview_text = interview_match.group(1).strip()
            # Clean up
            interview_text = re.sub(r'\s+', ' ', interview_text)
            # Take first sentence or two
            sentences = re.split(r'(?<=[.!?])\s+', interview_text)
            if sentences:
                result['interviewProcess'] = ' '.join(sentences[:3])
    
    # Extract founders from job page (backup when company page has no active founders)
    # Job pages have a "Founders" section with cards containing name, LinkedIn, role
    result['founders'] = _extract_founders_from_job_page(soup)
    
    return result


def _parse_salary_value(value: str) -> Optional[int]:
    """Parse salary string like '140K' or '140,000' to integer."""
    value = value.replace(',', '').strip()
    if value.upper().endswith('K'):
        try:
            return int(float(value[:-1]) * 1000)
        except ValueError:
            return None
    try:
        return int(value)
    except ValueError:
        return None


def merge_founders(company_founders: List[Founder], job_founders: List[Founder]) -> List[Founder]:
    """
    Merge founder data from company page and job page.
    Prefer company page data, but fill in missing information from job page.
    """
    # Use company founders as base
    merged_dict = {f.name: f for f in company_founders}
    
    # Fill in missing data from job founders
    for jf in job_founders:
        if jf.name not in merged_dict:
            # New founder, add it
            merged_dict[jf.name] = jf
        else:
            # Existing founder, merge data
            existing = merged_dict[jf.name]
            # Prefer longer description
            if not existing.description and jf.description:
                existing.description = jf.description
            elif jf.description and len(jf.description) > len(existing.description or ''):
                existing.description = jf.description
            
            # Fill missing role
            if not existing.role and jf.role:
                existing.role = jf.role
            
            # Fill missing links
            if not existing.linkedin and jf.linkedin:
                existing.linkedin = jf.linkedin
            if not existing.twitter and jf.twitter:
                existing.twitter = jf.twitter
    
    return list(merged_dict.values())
