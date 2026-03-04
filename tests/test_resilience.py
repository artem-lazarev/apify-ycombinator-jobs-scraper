"""Resilience and edge-case tests for YC Jobs Scraper."""

from datetime import datetime, timezone
import asyncio
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from src.main import (
    build_company_from_hiring_json,
    fetch_hiring_json,
    filter_companies,
    main,
    process_company,
)
from src.models import Company, CompanyOutput, Founder, Job
from src.scraper import scrape_company_page, scrape_job_page, scrape_page


class _AsyncContext:
    """Simple async context manager for mocking aiohttp responses."""

    def __init__(self, value=None, exc=None):
        self.value = value
        self.exc = exc

    async def __aenter__(self):
        if self.exc is not None:
            raise self.exc
        return self.value

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _make_response(status: int, text: str = ""):
    response = MagicMock()
    response.status = status
    response.text = AsyncMock(return_value=text)
    return response


def _make_client_session(contexts):
    session = MagicMock()
    session.get = MagicMock(side_effect=contexts)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    return session


def _build_output(slug: str, jobs_count: int = 1, founders_count: int = 1) -> CompanyOutput:
    company = Company(id=1, name=f"Company {slug}", slug=slug)
    founders = [Founder(name=f"Founder {i}") for i in range(founders_count)]
    jobs = [
        Job(
            jobId=f"job-{i}",
            title=f"Job {i}",
            jobUrl=f"https://www.ycombinator.com/companies/{slug}/jobs/job-{i}",
        )
        for i in range(jobs_count)
    ]
    return CompanyOutput(
        company=company,
        founders=founders,
        jobs=jobs,
        scrapedAt=datetime.now(timezone.utc),
    )


class TestScraperResilience:
    @pytest.mark.asyncio
    async def test_scrape_page_success_first_attempt(self):
        html = "<html>ok</html>"
        response = _make_response(200, html)
        session = _make_client_session([_AsyncContext(value=response)])

        with patch("src.scraper.aiohttp.ClientSession", return_value=session):
            result = await scrape_page("https://example.com", retries=3, delay=0.1)

        assert result == html
        assert session.get.call_count == 1

    @pytest.mark.asyncio
    async def test_scrape_page_retries_then_succeeds(self):
        response_500 = _make_response(500, "")
        response_200 = _make_response(200, "<html>ok</html>")
        session = _make_client_session([
            _AsyncContext(value=response_500),
            _AsyncContext(value=response_200),
        ])

        with patch("src.scraper.aiohttp.ClientSession", return_value=session), patch(
            "src.scraper.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            result = await scrape_page("https://example.com", retries=2, delay=0.25)

        assert result == "<html>ok</html>"
        mock_sleep.assert_awaited_once_with(0.25)

    @pytest.mark.asyncio
    async def test_scrape_page_timeout_exhausts_retries(self):
        session = _make_client_session(
            [
                _AsyncContext(exc=asyncio.TimeoutError()),
                _AsyncContext(exc=asyncio.TimeoutError()),
                _AsyncContext(exc=asyncio.TimeoutError()),
            ]
        )

        with patch("src.scraper.aiohttp.ClientSession", return_value=session), patch(
            "src.scraper.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            result = await scrape_page("https://example.com", retries=3, delay=0.5)

        assert result is None
        assert mock_sleep.await_args_list == [call(0.5), call(1.0)]

    @pytest.mark.asyncio
    async def test_scrape_page_empty_html_returns_none(self):
        session = _make_client_session(
            [
                _AsyncContext(value=_make_response(200, "")),
                _AsyncContext(value=_make_response(200, "")),
            ]
        )

        with patch("src.scraper.aiohttp.ClientSession", return_value=session):
            result = await scrape_page("https://example.com", retries=2)

        assert result is None

    @pytest.mark.asyncio
    async def test_scrape_company_page_constructs_expected_url(self):
        with patch("src.scraper.scrape_page", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.return_value = "<html />"
            result = await scrape_company_page("airbnb", retries=4)

        assert result == "<html />"
        mock_scrape.assert_awaited_once_with(
            "https://www.ycombinator.com/companies/airbnb", retries=4
        )

    @pytest.mark.asyncio
    async def test_scrape_job_page_constructs_expected_url(self):
        with patch("src.scraper.scrape_page", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.return_value = "<html />"
            result = await scrape_job_page("airbnb", "abc123", retries=2)

        assert result == "<html />"
        mock_scrape.assert_awaited_once_with(
            "https://www.ycombinator.com/companies/airbnb/jobs/abc123", retries=2
        )


class TestMainAndProcessingResilience:
    def test_filter_companies_handles_invalid_entries_and_filters(self):
        companies = [
            "bad-row",
            {"name": "A", "isHiring": True, "industry": "Fintech", "all_locations": "Remote"},
            {"name": "B", "isHiring": True, "industry": "AI", "all_locations": None},
            {"name": "C", "isHiring": False, "industry": "Fintech", "all_locations": "Remote"},
        ]

        filtered = filter_companies(
            companies,
            filter_by_industry=["fin"],
            filter_by_location=[None, "remote", 123],
            max_companies=-10,
        )

        assert filtered == []

    def test_build_company_from_hiring_json_handles_nullable_list_fields(self):
        company_data = {
            "id": 1,
            "name": "Test",
            "slug": "test",
            "former_names": None,
            "tags": None,
            "regions": None,
            "industries": None,
            "industry": "Fintech",
        }

        company = build_company_from_hiring_json(company_data, {"socialLinks": {}})

        assert company.formerNames == []
        assert company.tags == []
        assert company.regions == []
        assert company.industries == ["Fintech"]

    @pytest.mark.asyncio
    async def test_fetch_hiring_json_rejects_non_list_payload(self):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"unexpected": "object"})

        mock_session = MagicMock()
        mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("src.main.aiohttp.ClientSession", return_value=mock_session):
            with pytest.raises(Exception, match="Unexpected hiring.json payload type"):
                await fetch_hiring_json()

    @pytest.mark.asyncio
    async def test_process_company_uses_fallbacks_and_sanitizes_delay(self):
        company_data = {
            "id": 1,
            "name": "Fallback Co",
            "slug": "fallback-co",
            "isHiring": True,
        }

        company_parsed = {
            "socialLinks": {},
            "founders": [],
            "foundedYear": 2024,
            "jobs": [
                {
                    "jobId": "job1",
                    "title": "Backend Engineer",
                    "location": "Remote",
                    "salary": {"min": 120000, "max": 180000, "currency": "USD"},
                }
            ],
        }
        job_parsed = {
            "title": None,
            "location": None,
            "salary": None,
            "equity": {"min": 0.01, "max": 0.05},
            "jobType": "Full-time",
            "roleCategory": "Engineering",
            "experience": "Senior",
            "visa": "No",
            "description": "Long job description for testing.",
            "interviewProcess": "Interview steps.",
            "founders": [
                {
                    "name": "Alice Founder",
                    "role": "CEO",
                    "description": "Founder bio from job page",
                    "linkedin": "https://linkedin.com/in/alice-founder",
                }
            ],
        }

        with patch("src.main.scrape_company_page", new_callable=AsyncMock) as mock_company, patch(
            "src.main.scrape_job_page", new_callable=AsyncMock
        ) as mock_job, patch("src.main.parse_company_page", return_value=company_parsed), patch(
            "src.main.parse_job_page", return_value=job_parsed
        ), patch("src.main.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            mock_company.return_value = "<html company>"
            mock_job.return_value = "<html job>"

            result = await process_company(
                company_data,
                include_founder_descriptions=False,
                include_job_details=True,
                rate_limit_delay=-5,
            )

        assert result is not None
        assert len(result.jobs) == 1
        assert result.jobs[0].title == "Backend Engineer"
        assert result.jobs[0].jobType == "Full-time"
        assert result.jobs[0].equity is not None
        assert len(result.founders) == 1
        assert result.founders[0].name == "Alice Founder"
        assert result.founders[0].description is None
        assert mock_sleep.await_args_list == [call(0.0), call(0.0)]

    @pytest.mark.asyncio
    async def test_process_company_job_page_failure_falls_back_to_company_data(self):
        company_data = {"id": 1, "name": "Fallback", "slug": "fallback", "isHiring": True}
        company_parsed = {
            "socialLinks": {},
            "founders": [{"name": "Jane Founder", "role": "CEO"}],
            "foundedYear": 2023,
            "jobs": [{"jobId": "x1", "title": "Designer", "location": "Remote"}],
        }

        with patch("src.main.scrape_company_page", new_callable=AsyncMock) as mock_company, patch(
            "src.main.scrape_job_page", new_callable=AsyncMock
        ) as mock_job, patch("src.main.parse_company_page", return_value=company_parsed), patch(
            "src.main.asyncio.sleep", new_callable=AsyncMock
        ):
            mock_company.return_value = "<html company>"
            mock_job.return_value = None

            result = await process_company(company_data, include_job_details=True, rate_limit_delay=0)

        assert result is not None
        assert len(result.jobs) == 1
        assert result.jobs[0].title == "Designer"
        assert result.jobs[0].jobType is None

    @pytest.mark.asyncio
    async def test_process_company_returns_none_on_unexpected_parse_exception(self):
        company_data = {"id": 1, "name": "Boom", "slug": "boom", "isHiring": True}

        with patch("src.main.scrape_company_page", new_callable=AsyncMock) as mock_company, patch(
            "src.main.parse_company_page", side_effect=RuntimeError("parse failure")
        ), patch("src.main.asyncio.sleep", new_callable=AsyncMock):
            mock_company.return_value = "<html />"
            result = await process_company(company_data, rate_limit_delay=0)

        assert result is None

    @pytest.mark.asyncio
    async def test_main_normalizes_weird_input_and_sets_summary(self):
        actor = MagicMock()
        actor.get_input = AsyncMock(
            return_value={
                "maxCompanies": "2",
                "filterByBatch": "W24",
                "filterByIndustry": ["AI", None, 7],
                "filterByStage": None,
                "filterByLocation": "Remote",
                "topCompaniesOnly": "true",
                "includeFounderDescriptions": "false",
                "includeJobDetails": "0",
                "rateLimitDelay": "-7",
            }
        )
        actor.push_data = AsyncMock()
        actor.set_value = AsyncMock()

        actor_context = MagicMock()
        actor_context.__aenter__ = AsyncMock(return_value=actor)
        actor_context.__aexit__ = AsyncMock(return_value=None)

        companies = [{"id": 1, "name": "A", "slug": "a", "isHiring": True}]
        output = _build_output("a", jobs_count=2, founders_count=3)

        with patch("src.main.Actor", new=lambda: actor_context), patch(
            "src.main.fetch_hiring_json", new_callable=AsyncMock
        ) as mock_fetch, patch("src.main.filter_companies") as mock_filter, patch(
            "src.main.process_company", new_callable=AsyncMock
        ) as mock_process:
            mock_fetch.return_value = companies
            mock_filter.return_value = companies
            mock_process.return_value = output

            await main()

        mock_filter.assert_called_once_with(
            companies,
            max_companies=2,
            filter_by_batch=["W24"],
            filter_by_industry=["AI", "7"],
            filter_by_stage=[],
            filter_by_location=["Remote"],
            top_companies_only=True,
        )
        mock_process.assert_awaited_once_with(
            companies[0],
            include_founder_descriptions=False,
            include_job_details=False,
            rate_limit_delay=0.0,
        )
        actor.push_data.assert_awaited_once()
        actor.set_value.assert_awaited_once_with(
            "OUTPUT",
            {"totalCompanies": 1, "totalJobs": 2, "totalFounders": 3},
        )

    @pytest.mark.asyncio
    async def test_main_pushes_only_successful_results(self):
        actor = MagicMock()
        actor.get_input = AsyncMock(return_value={"maxCompanies": 2, "rateLimitDelay": 0})
        actor.push_data = AsyncMock()
        actor.set_value = AsyncMock()

        actor_context = MagicMock()
        actor_context.__aenter__ = AsyncMock(return_value=actor)
        actor_context.__aexit__ = AsyncMock(return_value=None)

        companies = [
            {"id": 1, "name": "A", "slug": "a", "isHiring": True},
            {"id": 2, "name": "B", "slug": "b", "isHiring": True},
        ]
        successful_output = _build_output("a", jobs_count=1, founders_count=1)

        with patch("src.main.Actor", new=lambda: actor_context), patch(
            "src.main.fetch_hiring_json", new_callable=AsyncMock
        ) as mock_fetch, patch("src.main.filter_companies") as mock_filter, patch(
            "src.main.process_company", new_callable=AsyncMock
        ) as mock_process:
            mock_fetch.return_value = companies
            mock_filter.return_value = companies
            mock_process.side_effect = [successful_output, None]

            await main()

        assert actor.push_data.await_count == 1
        actor.set_value.assert_awaited_once_with(
            "OUTPUT",
            {"totalCompanies": 1, "totalJobs": 1, "totalFounders": 1},
        )
