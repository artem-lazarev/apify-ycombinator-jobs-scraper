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
    
    Each founder card contains:
    - Image
    - Name (usually in a heading or strong element)
    - Social links (Twitter icon linking to their Twitter, LinkedIn icon)
    - Role (e.g., "Founder/CEO")
    - Description paragraph
    """
    founders = []
    seen_names = set()
    
    # Find "Active Founders" heading
    founders_heading = soup.find(string=lambda text: text and 'Active Founders' in text if text else False)
    
    if not founders_heading:
        # Try alternative: just "Founders"
        founders_heading = soup.find(string=lambda text: text and text.strip() == 'Founders' if text else False)
    
    if founders_heading:
        # Find the container holding all founder cards
        container = founders_heading.find_parent(['div', 'section'])
        if container:
            # Go up a few levels to get the full founders section
            for _ in range(5):
                if container.parent and container.parent.name in ['div', 'section']:
                    container = container.parent
            
            # Find all founder cards - they usually have images with founder names as alt text
            founder_images = container.find_all('img', alt=True)
            
            for img in founder_images:
                alt_text = img.get('alt', '')
                # Skip non-founder images (logos, icons, etc.)
                if not alt_text or alt_text in ['Twitter account', 'X (Twitter) logo', 'LinkedIn', 'Y Combinator Logo']:
                    continue
                
                # Skip if it's a company logo (usually small)
                src = img.get('src', '')
                if 'small_logos' in src or 'logos/' in src:
                    continue
                
                # The alt text is usually the founder's name
                founder_name = alt_text.strip()
                
                # Skip duplicates (YC pages sometimes show founders twice)
                if founder_name in seen_names:
                    continue
                seen_names.add(founder_name)
                
                # Find the card container for this founder - go up multiple levels
                card = img
                for _ in range(8):
                    if card.parent:
                        card = card.parent
                        # Check if this contains the founder's social links and role
                        card_links = card.find_all('a', href=True)
                        card_text = card.get_text()
                        has_founder_links = any(
                            'linkedin.com/in/' in (l.get('href', '') or '').lower() or
                            'x.com/' in (l.get('href', '') or '').lower() or
                            'twitter.com/' in (l.get('href', '') or '').lower()
                            for l in card_links
                        )
                        has_role = any(keyword in card_text for keyword in ['CEO', 'CTO', 'Founder', 'COO', 'CFO'])
                        
                        if has_founder_links and has_role:
                            break
                
                founder = _extract_founder_from_card_v2(card, founder_name)
                if founder and founder.get('name'):
                    founders.append(founder)
    
    return founders


def _extract_founder_from_card_v2(card: Tag, name_hint: str = None) -> Optional[Dict]:
    """Extract founder information from a card element (improved version)."""
    founder = {
        'name': name_hint,
        'role': None,
        'description': None,
        'linkedin': None,
        'twitter': None
    }
    
    # Get all text content to find role and description
    all_text = card.get_text(separator='\n', strip=True)
    lines = [line.strip() for line in all_text.split('\n') if line.strip()]
    
    # Find role - usually contains CEO, CTO, Founder, etc.
    role_keywords = ['CEO', 'CTO', 'COO', 'CFO', 'Founder', 'Co-founder', 'Cofounder', 'Partner']
    for line in lines:
        if any(keyword in line for keyword in role_keywords):
            # This is likely the role
            if len(line) < 100:  # Role shouldn't be too long
                founder['role'] = line
                break
    
    # Find description - usually the longest text block
    for line in lines:
        if len(line) > 100 and line != founder.get('role'):
            # Skip if it's just repeated name or role
            if name_hint and line.startswith(name_hint):
                continue
            founder['description'] = line
            break
    
    # Extract LinkedIn and Twitter links
    for link in card.find_all('a', href=True):
        href = link.get('href', '')
        href_lower = href.lower()
        
        # Personal LinkedIn (/in/) for founders
        if 'linkedin.com/in/' in href_lower and not founder['linkedin']:
            founder['linkedin'] = href
        # Twitter/X
        elif ('twitter.com/' in href_lower or 'x.com/' in href_lower) and not founder['twitter']:
            founder['twitter'] = href
    
    # Only return if we have at least a name
    if founder['name']:
        return founder
    return None


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
        match = re.search(pattern, card_text)
        if match:
            location = match.group(1).strip()
            # Exclude things that look like locations but aren't
            if location not in ['Any', 'Apply Now']:
                job['location'] = location
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
        'skills': [],
        'description': None,
        'interviewProcess': None,
        'applyUrl': None,
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
    
    # Extract apply URL
    # Look for links containing "apply" in text or href
    apply_patterns = ['apply to role', 'apply now', 'apply ›', 'apply']
    for pattern in apply_patterns:
        apply_link = soup.find('a', href=True, string=lambda text: text and pattern in text.lower() if text else False)
        if apply_link:
            result['applyUrl'] = apply_link['href']
            break
    
    # Fallback: look for workatastartup.com links
    if not result['applyUrl']:
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            if 'workatastartup.com' in href or 'application' in href:
                result['applyUrl'] = href
                break
    
    # Extract skills (often in bullet points within the description)
    # Look for technology keywords mentioned
    tech_keywords = ['Python', 'JavaScript', 'TypeScript', 'React', 'Node.js', 'Go', 'Rust',
                     'C++', 'Java', 'Kubernetes', 'Docker', 'AWS', 'GCP', 'Azure', 'SQL',
                     'PostgreSQL', 'MongoDB', 'Redis', 'GraphQL', 'REST API']
    for keyword in tech_keywords:
        if keyword.lower() in page_text.lower():
            if keyword not in result['skills']:
                result['skills'].append(keyword)
    
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
