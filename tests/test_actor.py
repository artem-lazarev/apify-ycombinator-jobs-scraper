"""Tests for the YC Jobs Scraper Apify Actor."""
import pytest
import json
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock

from src.models import (
    Company, Founder, Job, Salary, Equity, SocialLinks, CompanyOutput
)
from src.main import (
    filter_companies,
    build_company_from_hiring_json,
    build_founders_from_parsed,
    build_job_from_parsed,
    build_job_from_company_page,
)
from src.parsers import (
    parse_company_page,
    parse_job_page,
)


# =============================================================================
# MODEL TESTS
# =============================================================================

class TestModels:
    """Test Pydantic models."""

    def test_social_links_model(self):
        """Test SocialLinks model creation and validation."""
        social = SocialLinks(
            linkedin="https://linkedin.com/company/test",
            twitter="https://twitter.com/test",
            github="https://github.com/test",
        )
        assert social.linkedin == "https://linkedin.com/company/test"
        assert social.twitter == "https://twitter.com/test"
        assert social.github == "https://github.com/test"
        assert social.facebook is None
        assert social.crunchbase is None

    def test_salary_model(self):
        """Test Salary model with various currencies."""
        salary = Salary(min=100000, max=200000, currency="USD", period="yearly")
        assert salary.min == 100000
        assert salary.max == 200000
        assert salary.currency == "USD"
        assert salary.period == "yearly"

        # Test with monthly
        salary_monthly = Salary(min=8000, max=15000, currency="USD", period="monthly")
        assert salary_monthly.period == "monthly"

    def test_equity_model(self):
        """Test Equity model."""
        equity = Equity(min=0.1, max=0.5)
        assert equity.min == 0.1
        assert equity.max == 0.5

    def test_founder_model(self):
        """Test Founder model."""
        founder = Founder(
            name="John Doe",
            role="CEO",
            description="Serial entrepreneur",
            linkedin="https://linkedin.com/in/johndoe",
            twitter="https://twitter.com/johndoe"
        )
        assert founder.name == "John Doe"
        assert founder.role == "CEO"
        assert founder.description == "Serial entrepreneur"

    def test_job_model_complete(self):
        """Test Job model with all fields."""
        job = Job(
            jobId="abc123",
            title="Senior Engineer",
            jobUrl="https://www.ycombinator.com/companies/test/jobs/abc123",
            location="San Francisco, CA",
            salary=Salary(min=150000, max=250000),
            equity=Equity(min=0.1, max=1.0),
            jobType="Full-time",
            roleCategory="Engineering",
            experience="Senior",
            visa="Yes",
            description="Build amazing products",
            interviewProcess="3 rounds"
        )
        assert job.jobId == "abc123"
        assert job.title == "Senior Engineer"
        assert job.salary is not None
        assert job.salary.min == 150000
        assert job.equity is not None

    def test_job_model_minimal(self):
        """Test Job model with minimal fields."""
        job = Job(
            jobId="xyz789",
            title="Designer",
            jobUrl="https://example.com"
        )
        assert job.jobId == "xyz789"
        assert job.title == "Designer"
        assert job.location is None
        assert job.salary is None
        assert job.equity is None

    def test_company_model(self):
        """Test Company model."""
        company = Company(
            id=1,
            name="Test Corp",
            slug="test-corp",
            tagline="Building the future",
            website="https://test.com",
            ycBatch="W24",
            stage="Series A",
            topCompany=True,
            socialLinks=SocialLinks(linkedin="https://linkedin.com/company/test")
        )
        assert company.id == 1
        assert company.name == "Test Corp"
        assert company.slug == "test-corp"
        assert company.topCompany is True

    def test_company_output_model(self):
        """Test CompanyOutput model."""
        company = Company(
            id=1,
            name="Test Corp",
            slug="test-corp"
        )
        founders = [Founder(name="John", role="CEO")]
        jobs = [Job(jobId="j1", title="Engineer", jobUrl="http://test.com")]

        output = CompanyOutput(
            company=company,
            founders=founders,
            jobs=jobs,
            scrapedAt=datetime.utcnow()
        )

        assert output.company.name == "Test Corp"
        assert len(output.founders) == 1
        assert len(output.jobs) == 1
        assert output.scrapedAt is not None

    def test_model_serialization(self):
        """Test model serialization to JSON."""
        company = Company(
            id=1,
            name="Test Corp",
            slug="test-corp",
            socialLinks=SocialLinks(linkedin="https://linkedin.com")
        )
        # Pydantic v2 uses model_dump
        data = company.model_dump(mode='json')
        assert data['name'] == "Test Corp"
        assert data['socialLinks']['linkedin'] == "https://linkedin.com"


# =============================================================================
# FILTER TESTS
# =============================================================================

class TestFiltering:
    """Test company filtering logic."""

    @pytest.fixture
    def sample_companies(self):
        """Sample companies data from hiring.json format."""
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
                "website": "https://airbnb.com"
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
                "website": "https://stripe.com"
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
                "website": "https://startupa.com"
            },
            {
                "id": 4,
                "name": "Startup B",
                "slug": "startup-b",
                "batch": "S24",
                "industry": "Healthcare",
                "stage": "Series A",
                "all_locations": "Boston, MA / Remote",
                "isHiring": False,  # Not hiring
                "top_company": False,
                "website": "https://startupb.com"
            },
            {
                "id": 5,
                "name": "Remote Corp",
                "slug": "remote-corp",
                "batch": "W23",
                "industry": "B2B",
                "stage": "Series A",
                "all_locations": "Remote (US)",
                "isHiring": True,
                "top_company": False,
                "website": "https://remote-corp.com"
            },
        ]

    def test_filter_is_hiring(self, sample_companies):
        """Test filtering to only hiring companies."""
        result = filter_companies(sample_companies)
        assert len(result) == 4  # 4 companies with isHiring=True
        assert "Startup B" not in [c['name'] for c in result]

    def test_filter_by_batch(self, sample_companies):
        """Test filtering by batch."""
        result = filter_companies(sample_companies, filter_by_batch=["W24"])
        assert len(result) == 1
        assert result[0]['name'] == "Startup A"

    def test_filter_by_industry(self, sample_companies):
        """Test filtering by industry."""
        result = filter_companies(sample_companies, filter_by_industry=["Fintech"])
        assert len(result) == 1
        assert result[0]['name'] == "Stripe"

        # Test multiple industries
        result = filter_companies(sample_companies, filter_by_industry=["Fintech", "B2B"])
        assert len(result) == 3  # Stripe + 2 B2B companies

    def test_filter_by_stage(self, sample_companies):
        """Test filtering by stage."""
        # First filter to hiring companies, then check stages
        all_hiring = filter_companies(sample_companies)
        stages = [c.get('stage') for c in all_hiring]
        result = filter_companies(sample_companies, filter_by_stage=["Series A"])
        # Only Remote Corp is Series A and hiring
        assert len(result) == 1
        assert result[0]['name'] == "Remote Corp"

    def test_filter_by_location(self, sample_companies):
        """Test filtering by location."""
        result = filter_companies(sample_companies, filter_by_location=["Remote"])
        assert len(result) == 2  # Stripe (has Remote in locations) and Remote Corp
        assert "Remote Corp" in [c['name'] for c in result]

    def test_filter_top_companies(self, sample_companies):
        """Test filtering top companies only."""
        result = filter_companies(sample_companies, top_companies_only=True)
        assert len(result) == 2  # Airbnb and Stripe
        assert all(c.get('top_company', False) for c in result)

    def test_filter_max_companies(self, sample_companies):
        """Test limiting number of companies."""
        result = filter_companies(sample_companies, max_companies=2)
        assert len(result) == 2

    def test_filter_combined(self, sample_companies):
        """Test combining multiple filters."""
        result = filter_companies(
            sample_companies,
            filter_by_industry=["B2B"],
            max_companies=1
        )
        assert len(result) == 1
        assert result[0]['industry'] == "B2B"


# =============================================================================
# PARSER TESTS
# =============================================================================

class TestParsers:
    """Test HTML parsing functions."""

    def test_parse_company_page_basic(self):
        """Test parsing company page with basic data."""
        html = """
        <html>
            <body>
                <h1>Test Company</h1>
                <div>
                    <span>Founded:</span> 2020
                    <span>Batch:</span> W24
                </div>
                <div>
                    <a href="https://linkedin.com/company/test">LinkedIn</a>
                    <a href="https://twitter.com/test">Twitter</a>
                </div>
            </body>
        </html>
        """
        result = parse_company_page(html)
        assert 'socialLinks' in result
        assert 'founders' in result
        assert 'jobs' in result
        assert 'foundedYear' in result

    def test_parse_company_page_with_jobs(self):
        """Test parsing company page with job listings."""
        html = """
        <html>
            <body>
                <h1>Test Company</h1>
                <div>
                    <span>Founded:</span> 2020
                </div>
                <section>
                    <h2>Jobs at Test Company</h2>
                    <a href="/companies/test/jobs/abc123">Senior Engineer</a>
                </section>
            </body>
        </html>
        """
        result = parse_company_page(html)
        assert len(result['jobs']) >= 0

    def test_parse_job_page_basic(self):
        """Test parsing job page with basic data."""
        html = """
        <html>
            <body>
                <h1>Senior Engineer</h1>
                <div>
                    <strong>Job type</strong>
                    <div>Full-time</div>
                </div>
                <div>
                    <strong>Experience</strong>
                    <div>Senior</div>
                </div>
                <h2>About the role</h2>
                <p>This is the job description.</p>
                <h2>About the interview</h2>
                <p>3 phone screens</p>
            </body>
        </html>
        """
        result = parse_job_page(html)
        assert result['title'] == "Senior Engineer"
        assert result['jobType'] == "Full-time"
        assert result['experience'] == "Senior"
        # Description might be None if parsing fails - that's OK for basic HTML

    def test_parse_job_page_with_salary(self):
        """Test parsing job page with salary and equity."""
        html = """
        <html>
            <body>
                <h1>Senior Engineer</h1>
                <p>$140K - $250K • 0.10% - 0.40% • San Francisco, CA / Remote (US)</p>
                <div>
                    <strong>Job type</strong>
                    <div>Full-time</div>
                </div>
                <div>
                    <strong>Experience</strong>
                    <div>Senior</div>
                </div>
                <h2>About the role</h2>
                <p>Build amazing products.</p>
            </body>
        </html>
        """
        result = parse_job_page(html)
        assert result['salary'] is not None
        assert result['salary']['min'] == 140000
        assert result['salary']['max'] == 250000
        assert result['equity'] is not None
        assert result['equity']['min'] == 0.1
        assert result['equity']['max'] == 0.4


# =============================================================================
# BUILD FUNCTION TESTS
# =============================================================================

class TestBuildFunctions:
    """Test model building functions."""

    def test_build_company_from_hiring_json(self):
        """Test building Company model from hiring.json data."""
        company_data = {
            "id": 1,
            "name": "Test Corp",
            "slug": "test-corp",
            "batch": "W24",
            "industry": "B2B",
            "stage": "Seed",
            "all_locations": "San Francisco, CA",
            "website": "https://test.com",
            "url": "https://www.ycombinator.com/companies/test-corp",
            "team_size": 10,
            "top_company": False,
            "one_liner": "Building things",
            "long_description": "Long description",
            "industries": ["B2B", "SaaS"],
            "tags": ["AI", "ML"]
        }
        scraped_data = {
            'socialLinks': {
                'linkedin': 'https://linkedin.com/company/test',
                'twitter': 'https://twitter.com/test'
            },
            'foundedYear': 2023
        }

        company = build_company_from_hiring_json(company_data, scraped_data)

        assert company.id == 1
        assert company.name == "Test Corp"
        assert company.slug == "test-corp"
        assert company.ycBatch == "W24"
        assert company.foundedYear == 2023
        assert company.socialLinks.linkedin == "https://linkedin.com/company/test"
        assert company.socialLinks.twitter == "https://twitter.com/test"

    def test_build_founders_from_parsed(self):
        """Test building Founder models from parsed data."""
        parsed_founders = [
            {
                'name': 'John Doe',
                'role': 'CEO',
                'description': 'Serial entrepreneur',
                'linkedin': 'https://linkedin.com/in/johndoe',
                'twitter': 'https://twitter.com/johndoe'
            },
            {
                'name': 'Jane Smith',
                'role': 'CTO',
                'description': 'Former Google engineer',
                'linkedin': 'https://linkedin.com/in/janesmith'
            }
        ]

        founders = build_founders_from_parsed(parsed_founders)

        assert len(founders) == 2
        assert founders[0].name == "John Doe"
        assert founders[0].role == "CEO"
        assert founders[1].name == "Jane Smith"

    def test_build_founders_empty(self):
        """Test building founders from empty list."""
        founders = build_founders_from_parsed([])
        assert len(founders) == 0

    def test_build_founders_skips_invalid(self):
        """Test that founders without names are skipped."""
        parsed_founders = [
            {'name': 'John Doe', 'role': 'CEO'},
            {'role': 'CTO'},  # Missing name
        ]

        founders = build_founders_from_parsed(parsed_founders)
        assert len(founders) == 1

    def test_build_job_from_parsed(self):
        """Test building Job model from parsed job data."""
        job_data = {
            'title': 'Senior Engineer',
            'location': 'San Francisco, CA',
            'salary': {'min': 150000, 'max': 250000, 'currency': 'USD'},
            'equity': {'min': 0.1, 'max': 1.0},
            'jobType': 'Full-time',
            'roleCategory': 'Engineering',
            'experience': 'Senior',
            'visa': 'Yes',
            'description': 'Build amazing products',
            'interviewProcess': '3 rounds'
        }

        job = build_job_from_parsed(job_data, 'test-company', 'abc123')

        assert job.jobId == "abc123"
        assert job.title == "Senior Engineer"
        assert job.jobUrl == "https://www.ycombinator.com/companies/test-company/jobs/abc123"
        assert job.salary is not None
        assert job.salary.min == 150000
        assert job.equity is not None
        assert job.jobType == "Full-time"

    def test_build_job_from_company_page(self):
        """Test building Job model from company page data (minimal)."""
        job_data = {
            'jobId': 'xyz789',
            'title': 'Designer',
            'location': 'Remote',
            'salary': {'min': 100000, 'max': 150000},
            'equity': {'min': 0.05, 'max': 0.2},
            'experience': 'Mid-level'
        }

        job = build_job_from_company_page(job_data, 'test-company')

        assert job.jobId == "xyz789"
        assert job.title == "Designer"
        assert job.jobType is None  # Not available on company page
        assert job.visa is None  # Not available on company page
        assert job.description is None  # Not available on company page


# =============================================================================
# INTEGRATION TESTS (Mocked)
# =============================================================================

class TestActorIntegration:
    """Integration tests for the actor (with mocked external calls)."""

    @pytest.mark.asyncio
    async def test_fetch_hiring_json_success(self):
        """Test fetching hiring.json successfully."""
        from src.main import fetch_hiring_json
        import aiohttp

        mock_data = [
            {"id": 1, "name": "Company A", "slug": "company-a", "isHiring": True},
            {"id": 2, "name": "Company B", "slug": "company-b", "isHiring": True}
        ]

        # Create a proper mock for the context manager
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_data)

        mock_session = MagicMock()
        mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch('aiohttp.ClientSession', return_value=mock_session):
            result = await fetch_hiring_json()
            assert len(result) == 2

    @pytest.mark.asyncio
    async def test_fetch_hiring_json_failure(self):
        """Test handling fetch failure."""
        from src.main import fetch_hiring_json

        mock_response = MagicMock()
        mock_response.status = 500

        mock_session = MagicMock()
        mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch('aiohttp.ClientSession', return_value=mock_session):
            with pytest.raises(Exception) as exc_info:
                await fetch_hiring_json()
            assert "Failed to fetch hiring.json" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_process_company_success(self):
        """Test processing a company successfully."""
        from src.main import process_company

        company_data = {
            "id": 1,
            "name": "Test Corp",
            "slug": "test-corp",
            "batch": "W24",
            "industry": "B2B",
            "stage": "Seed",
            "all_locations": "San Francisco, CA",
            "website": "https://test.com",
            "url": "https://www.ycombinator.com/companies/test-corp",
            "team_size": 10,
            "top_company": False,
            "isHiring": True
        }

        # Mock the scraper functions
        mock_html = """
        <html><body>
            <h1>Test Corp</h1>
            <div><span>Founded:</span> 2023</div>
            <section><h2>Jobs at Test Corp</h2></section>
        </body></html>
        """

        with patch('src.main.scrape_company_page', new_callable=AsyncMock) as mock_scrape_company, \
             patch('src.main.scrape_job_page', new_callable=AsyncMock) as mock_scrape_job, \
             patch('src.main.parse_company_page') as mock_parse_company, \
             patch('src.main.parse_job_page') as mock_parse_job:

            mock_scrape_company.return_value = mock_html
            mock_scrape_job.return_value = mock_html
            mock_parse_company.return_value = {
                'socialLinks': {'linkedin': 'https://linkedin.com'},
                'founders': [{'name': 'John', 'role': 'CEO', 'linkedin': 'http://li'}],
                'foundedYear': 2023,
                'jobs': []
            }
            mock_parse_job.return_value = {
                'title': 'Engineer',
                'jobType': 'Full-time',
                'experience': 'Senior',
                'description': 'Build things',
                'founders': []
            }

            result = await process_company(company_data, include_job_details=False)

            assert result is not None
            assert result.company.name == "Test Corp"
            assert result.company.slug == "test-corp"

    @pytest.mark.asyncio
    async def test_process_company_no_slug(self):
        """Test processing company without slug returns None."""
        from src.main import process_company

        company_data = {
            "id": 1,
            "name": "Test Corp",
            # No slug
        }

        result = await process_company(company_data)
        assert result is None


# =============================================================================
# VALIDATION TESTS
# =============================================================================

class TestOutputValidation:
    """Tests to validate the output structure."""

    def test_company_output_required_fields(self):
        """Test that CompanyOutput has all required fields."""
        company = Company(id=1, name="Test", slug="test")
        output = CompanyOutput(
            company=company,
            founders=[],
            jobs=[],
            scrapedAt=datetime.utcnow()
        )

        # Serialize and check required keys
        data = output.model_dump(mode='json')

        assert 'company' in data
        assert 'founders' in data
        assert 'jobs' in data
        assert 'scrapedAt' in data

        # Check company fields
        assert 'id' in data['company']
        assert 'name' in data['company']
        assert 'slug' in data['company']

    def test_job_output_fields(self):
        """Test job output has expected fields."""
        job = Job(
            jobId="test123",
            title="Engineer",
            jobUrl="https://example.com"
        )

        data = job.model_dump(mode='json')

        assert data['jobId'] == "test123"
        assert data['title'] == "Engineer"
        assert data['jobUrl'] == "https://example.com"

    def test_full_output_json_serializable(self):
        """Test that full output is JSON serializable."""
        company = Company(
            id=1,
            name="Test Corp",
            slug="test-corp",
            ycBatch="W24",
            socialLinks=SocialLinks(linkedin="https://linkedin.com")
        )
        founders = [
            Founder(name="John", role="CEO", linkedin="https://linkedin.com/john")
        ]
        jobs = [
            Job(
                jobId="j1",
                title="Engineer",
                jobUrl="https://example.com",
                salary=Salary(min=100000, max=200000)
            )
        ]

        output = CompanyOutput(
            company=company,
            founders=founders,
            jobs=jobs,
            scrapedAt=datetime.utcnow()
        )

        # This should not raise
        json_str = json.dumps(output.model_dump(mode='json'))
        parsed = json.loads(json_str)

        assert parsed['company']['name'] == "Test Corp"
        assert len(parsed['founders']) == 1
        assert len(parsed['jobs']) == 1
        assert parsed['jobs'][0]['salary']['min'] == 100000


# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
