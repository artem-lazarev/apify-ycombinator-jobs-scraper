"""Pytest configuration and fixtures for YC Jobs Scraper tests."""
import pytest
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture
def sample_hiring_json():
    """Sample hiring.json data for testing."""
    return [
        {
            "id": 1,
            "name": "Airbnb",
            "slug": "airbnb",
            "batch": "W09",
            "industry": "Consumer",
            "stage": "Public",
            "all_locations": "San Francisco, CA",
            "isHiring": True,
            "top_company": True,
            "website": "https://airbnb.com",
            "url": "https://www.ycombinator.com/companies/airbnb",
            "small_logo_thumb_url": "https://example.com/logo.png",
            "team_size": 5000,
            "one_liner": "Book accommodations worldwide",
            "industries": ["Consumer", "Travel"],
            "tags": ["Marketplace", "Mobile"]
        },
        {
            "id": 2,
            "name": "Stripe",
            "slug": "stripe",
            "batch": "W10",
            "industry": "Fintech",
            "stage": "Series G",
            "all_locations": "San Francisco, CA / Dublin, Ireland / Remote",
            "isHiring": True,
            "top_company": True,
            "website": "https://stripe.com",
            "url": "https://www.ycombinator.com/companies/stripe",
            "small_logo_thumb_url": "https://example.com/stripe.png",
            "team_size": 7000,
            "one_liner": "Payments infrastructure",
            "industries": ["Fintech", "B2B"],
            "tags": ["API", "Developer Tools"]
        },
        {
            "id": 3,
            "name": "Startup A",
            "slug": "startup-a",
            "batch": "W24",
            "industry": "B2B",
            "stage": "Seed",
            "all_locations": "New York, NY",
            "isHiring": True,
            "top_company": False,
            "website": "https://startupa.com",
            "url": "https://www.ycombinator.com/companies/startup-a",
            "small_logo_thumb_url": "https://example.com/startup.png",
            "team_size": 5,
            "one_liner": "B2B solution",
            "industries": ["B2B", "SaaS"],
            "tags": ["AI"]
        },
    ]


@pytest.fixture
def sample_company_html():
    """Sample HTML for a company page."""
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Test Company - Y Combinator</title></head>
    <body>
        <h1>Test Company</h1>
        <div class="company-info">
            <span>Founded:</span> <span>2023</span>
            <span>Batch:</span> <span>W24</span>
            <span>Team Size:</span> <span>10</span>
            <span>Status:</span> <span>Active</span>
            <span>Location:</span> <span>San Francisco, CA</span>
        </div>
        <div class="social-links">
            <a href="https://linkedin.com/company/testcompany">LinkedIn</a>
            <a href="https://twitter.com/testcompany">Twitter</a>
            <a href="https://github.com/testcompany">GitHub</a>
        </div>
        <section class="founders">
            <h2>Active Founders</h2>
            <div class="founder-card">
                <img alt="John Doe" src="/img/john.jpg">
                <span>John Doe</span>
                <span>CEO</span>
                <p>Founder description here</p>
                <a href="https://linkedin.com/in/johndoe">LinkedIn</a>
                <a href="https://twitter.com/johndoe">Twitter</a>
            </div>
        </section>
        <section class="jobs">
            <h2>Jobs at Test Company</h2>
            <div class="job-listing">
                <a href="/companies/test-company/jobs/abc123">Senior Engineer</a>
                <span>$140K - $250K</span>
                <span>0.10% - 0.40%</span>
                <span>San Francisco, CA / Remote</span>
                <span>Senior</span>
            </div>
        </section>
    </body>
    </html>
    """


@pytest.fixture
def sample_job_html():
    """Sample HTML for a job page."""
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Senior Engineer - Test Company - Y Combinator</title></head>
    <body>
        <h1>Senior Engineer</h1>
        <div class="job-header">
            <p>$140K - $250K • 0.10% - 0.40% • San Francisco, CA / Remote (US)</p>
        </div>
        <div class="job-meta">
            <div>
                <strong>Job type</strong>
                <div>Full-time</div>
            </div>
            <div>
                <strong>Role</strong>
                <div>Engineering, Full stack</div>
            </div>
            <div>
                <strong>Experience</strong>
                <div>Senior</div>
            </div>
            <div>
                <strong>Visa</strong>
                <div>Yes</div>
            </div>
        </div>
        <section class="about-role">
            <h2>About the role</h2>
            <p>We are building amazing products. Join our team!</p>
            <p>Requirements:</p>
            <ul>
                <li>5+ years experience</li>
                <li>Strong coding skills</li>
            </ul>
        </section>
        <section class="about-interview">
            <h2>About the interview</h2>
            <p>3 phone screens and 1 on-site</p>
        </section>
        <section class="founders">
            <h2>Founders</h2>
            <div class="founder-card">
                <img alt="John Doe" src="/img/john.jpg">
                <span>John Doe</span>
                <span>CEO</span>
                <a href="https://linkedin.com/in/johndoe">LinkedIn</a>
            </div>
        </section>
    </body>
    </html>
    """


@pytest.fixture
def mock_apify_actor():
    """Mock Apify Actor for testing."""
    from unittest.mock import AsyncMock, MagicMock

    actor_mock = MagicMock()
    actor_mock.get_input = AsyncMock(return_value={
        'maxCompanies': 3,
        'includeJobDetails': True,
        'includeFounderDescriptions': True,
    })
    actor_mock.push_data = AsyncMock()
    actor_mock.set_value = AsyncMock()

    return actor_mock
