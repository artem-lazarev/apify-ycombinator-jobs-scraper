"""HTML parsing functions for YC company and job pages."""
import re
from typing import List, Optional, Dict
from bs4 import BeautifulSoup
from .models import Founder, SocialLinks, Job, Salary, Equity


def parse_company_page(html: str) -> Dict:
    """
    Parse company page HTML to extract:
    - Social links (LinkedIn, Twitter, GitHub, Facebook, Crunchbase)
    - Founders (name, role, description, LinkedIn, Twitter)
    - Founded year
    """
    soup = BeautifulSoup(html, 'lxml')
    result = {
        'socialLinks': {},
        'founders': [],
        'foundedYear': None
    }
    
    # Extract social links
    # Look for links in various sections (sidebar, header, footer)
    social_links_map = {
        'linkedin': ['linkedin.com'],
        'twitter': ['twitter.com', 'x.com'],
        'github': ['github.com'],
        'facebook': ['facebook.com'],
        'crunchbase': ['crunchbase.com']
    }
    
    for link in soup.find_all('a', href=True):
        href = link.get('href', '').lower()
        for social_type, domains in social_links_map.items():
            if any(domain in href for domain in domains):
                if social_type not in result['socialLinks']:
                    result['socialLinks'][social_type] = link['href']
    
    # Extract founded year from sidebar or metadata
    # Look for "Founded" text
    founded_elements = soup.find_all(string=lambda text: text and 'founded' in text.lower())
    for elem in founded_elements:
        parent = elem.parent
        if parent:
            text = parent.get_text()
            # Try to extract year (4 digits)
            years = re.findall(r'\b(19|20)\d{2}\b', text)
            if years:
                try:
                    result['foundedYear'] = int(years[0])
                    break
                except (ValueError, IndexError):
                    pass
    
    # Extract founders from "Active Founders" section
    # Look for founder cards/sections
    founder_sections = soup.find_all(['div', 'section'], class_=lambda x: x and 'founder' in x.lower() if x else False)
    
    # Also check for common patterns like "Founders" heading followed by cards
    founders_heading = soup.find(string=lambda text: text and 'founder' in text.lower() and 'active' in text.lower())
    if founders_heading:
        # Find the container with founders
        container = founders_heading.find_parent(['div', 'section', 'article'])
        if container:
            founder_cards = container.find_all(['div', 'article'], recursive=True)
            for card in founder_cards:
                founder = _extract_founder_from_card(card)
                if founder:
                    result['founders'].append(founder)
    
    # Alternative: look for founder cards by common class patterns
    if not result['founders']:
        # Try finding cards with founder info
        cards = soup.find_all(['div', 'article'], class_=lambda x: x and any(
            keyword in str(x).lower() for keyword in ['founder', 'team', 'people']
        ) if x else False)
        
        for card in cards:
            # Check if this looks like a founder card (has name and possibly role)
            name_elem = card.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'span'], 
                                 class_=lambda x: x and 'name' in str(x).lower() if x else False)
            if not name_elem:
                # Try finding any heading or strong text that might be a name
                name_elem = card.find(['h1', 'h2', 'h3', 'h4', 'strong', 'b'])
            
            if name_elem:
                founder = _extract_founder_from_card(card)
                if founder:
                    result['founders'].append(founder)
    
    return result


def _extract_founder_from_card(card) -> Optional[Dict]:
    """Extract founder information from a card element."""
    founder = {
        'name': None,
        'role': None,
        'description': None,
        'linkedin': None,
        'twitter': None
    }
    
    # Extract name (usually in heading or strong tag)
    name_elem = card.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong', 'b'])
    if name_elem:
        founder['name'] = name_elem.get_text(strip=True)
    
    # Extract role (often near name, might be in span or p)
    role_keywords = ['ceo', 'cto', 'founder', 'co-founder', 'cofounder']
    role_elem = card.find(string=lambda text: text and any(
        keyword in text.lower() for keyword in role_keywords
    ))
    if role_elem:
        founder['role'] = role_elem.strip()
    
    # Extract description (usually paragraph text)
    desc_elem = card.find('p')
    if desc_elem:
        desc_text = desc_elem.get_text(strip=True)
        if desc_text and len(desc_text) > 20:  # Likely a description
            founder['description'] = desc_text
    
    # Extract LinkedIn and Twitter links
    for link in card.find_all('a', href=True):
        href = link.get('href', '').lower()
        if 'linkedin.com' in href and not founder['linkedin']:
            founder['linkedin'] = link['href']
        elif ('twitter.com' in href or 'x.com' in href) and not founder['twitter']:
            founder['twitter'] = link['href']
    
    # Only return if we have at least a name
    if founder['name']:
        return founder
    return None


def parse_job_page(html: str) -> Dict:
    """
    Parse job page HTML to extract complete job information.
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
    
    # Extract job title (usually in h1 or main heading)
    title_elem = soup.find(['h1', 'h2'], class_=lambda x: x and 'title' in str(x).lower() if x else False)
    if not title_elem:
        title_elem = soup.find('h1')
    if title_elem:
        result['title'] = title_elem.get_text(strip=True)
    
    # Extract salary range
    # Look for patterns like "$140K - $250K" or "$140,000 - $250,000"
    salary_text = soup.get_text()
    salary_patterns = [
        r'\$(\d+(?:,\d{3})*(?:K|k)?)\s*[-–—]\s*\$(\d+(?:,\d{3})*(?:K|k)?)',  # $140K - $250K
        r'salary[:\s]+.*?\$(\d+(?:,\d{3})*(?:K|k)?)\s*[-–—]\s*\$(\d+(?:,\d{3})*(?:K|k)?)',
    ]
    
    for pattern in salary_patterns:
        match = re.search(pattern, salary_text, re.IGNORECASE)
        if match:
            min_sal = _parse_salary_value(match.group(1))
            max_sal = _parse_salary_value(match.group(2))
            if min_sal and max_sal:
                result['salary'] = {'min': min_sal, 'max': max_sal, 'currency': 'USD'}
                break
    
    # Extract equity range
    # Look for patterns like "0.10% - 0.40%" or "0.1% - 0.4%"
    equity_patterns = [
        r'(\d+\.?\d*)\s*%\s*[-–—]\s*(\d+\.?\d*)\s*%',  # 0.10% - 0.40%
        r'equity[:\s]+.*?(\d+\.?\d*)\s*%\s*[-–—]\s*(\d+\.?\d*)\s*%',
    ]
    
    for pattern in equity_patterns:
        match = re.search(pattern, salary_text, re.IGNORECASE)
        if match:
            min_eq = float(match.group(1))
            max_eq = float(match.group(2))
            result['equity'] = {'min': min_eq, 'max': max_eq}
            break
    
    # Extract location, job type, role category, experience, visa
    # These are often in a metadata section or list
    metadata_sections = soup.find_all(['div', 'ul', 'dl'], class_=lambda x: x and any(
        keyword in str(x).lower() for keyword in ['meta', 'detail', 'info', 'requirement']
    ) if x else False)
    
    for section in metadata_sections:
        text = section.get_text()
        
        # Location
        if 'location' in text.lower() and not result['location']:
            location_elem = section.find(string=lambda t: t and 'location' in t.lower())
            if location_elem:
                parent = location_elem.find_parent()
                if parent:
                    result['location'] = parent.get_text().replace('Location:', '').replace('location:', '').strip()
        
        # Job type
        if any(jt in text.lower() for jt in ['full-time', 'part-time', 'contract', 'internship']) and not result['jobType']:
            for jt in ['Full-time', 'Part-time', 'Contract', 'Internship']:
                if jt.lower() in text.lower():
                    result['jobType'] = jt
                    break
        
        # Visa
        if 'visa' in text.lower() or 'sponsor' in text.lower():
            if 'will sponsor' in text.lower() or 'sponsors' in text.lower():
                result['visa'] = 'Will sponsor'
            elif 'not sponsor' in text.lower() or "won't sponsor" in text.lower():
                result['visa'] = 'Will not sponsor'
    
    # Extract "About the role" section (job description)
    about_role = soup.find(string=lambda text: text and 'about the role' in text.lower())
    if about_role:
        container = about_role.find_parent(['div', 'section', 'article'])
        if container:
            # Get all text after the heading
            desc_parts = []
            for sibling in container.find_all_next(['p', 'div', 'ul', 'ol'], limit=10):
                if sibling.get_text(strip=True):
                    desc_parts.append(sibling.get_text(strip=True))
            result['description'] = '\n\n'.join(desc_parts[:5])  # Limit to first few paragraphs
    
    # Extract "About the interview" section
    about_interview = soup.find(string=lambda text: text and 'about the interview' in text.lower())
    if about_interview:
        container = about_interview.find_parent(['div', 'section', 'article'])
        if container:
            interview_parts = []
            for sibling in container.find_all_next(['p', 'div'], limit=5):
                if sibling.get_text(strip=True):
                    interview_parts.append(sibling.get_text(strip=True))
            result['interviewProcess'] = '\n\n'.join(interview_parts[:3])
    
    # Extract skills (often in a list or tags)
    skills_section = soup.find(string=lambda text: text and 'skill' in text.lower())
    if skills_section:
        container = skills_section.find_parent(['div', 'section', 'ul'])
        if container:
            skills_list = container.find_all(['li', 'span', 'a'], class_=lambda x: x and 'tag' in str(x).lower() if x else False)
            for skill_elem in skills_list:
                skill_text = skill_elem.get_text(strip=True)
                if skill_text and len(skill_text) < 50:  # Reasonable skill name length
                    result['skills'].append(skill_text)
    
    # Extract apply URL
    apply_link = soup.find('a', href=True, string=lambda text: text and 'apply' in text.lower() if text else False)
    if not apply_link:
        apply_link = soup.find('a', href=True, class_=lambda x: x and 'apply' in str(x).lower() if x else False)
    if apply_link:
        result['applyUrl'] = apply_link['href']
    
    # Extract founders (backup source)
    # Similar to company page parsing
    founders_heading = soup.find(string=lambda text: text and 'founder' in text.lower())
    if founders_heading:
        container = founders_heading.find_parent(['div', 'section'])
        if container:
            founder_cards = container.find_all(['div', 'article'], recursive=True)
            for card in founder_cards:
                founder = _extract_founder_from_card(card)
                if founder:
                    result['founders'].append(founder)
    
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
