"""Tests for the Notion MCP connector sync."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models import Company, CompanyOutput, Equity, Job, Salary
from src.notion_sync import (
    CREATE_PAGES_TOOL,
    _tool_error_text,
    build_job_rows,
    sync_jobs_to_notion,
)

PROXY_ENV = {
    'APIFY_MCP_PROXY_URL': 'https://mcp-proxy.apify.com',
    'APIFY_TOKEN': 'apify_api_test',
}


def _output(slug: str = 'acme', jobs_count: int = 1) -> CompanyOutput:
    company = Company(id=1, name='Acme', slug=slug, ycBatch='W24', website='https://acme.com')
    jobs = [
        Job(
            jobId=f'job-{i}',
            title=f'Engineer {i}',
            jobUrl=f'https://www.ycombinator.com/companies/{slug}/jobs/job-{i}',
            location='Remote',
            roleCategory='Engineering',
            salary=Salary(min=150000, max=200000, currency='USD'),
            equity=Equity(min=0.1, max=0.5),
            description='Build   things\n\nwith  us',
        )
        for i in range(jobs_count)
    ]
    return CompanyOutput(
        company=company,
        founders=[],
        jobs=jobs,
        scrapedAt=datetime(2026, 8, 11, 12, 0, 0, tzinfo=timezone.utc),
    )


class _ToolResult:
    """Stand-in for mcp.types.CallToolResult."""

    def __init__(self, is_error=False, text=None):
        self.is_error = is_error
        block = MagicMock()
        block.text = text
        self.content = [block] if text else []


def _make_session(tool_names=(CREATE_PAGES_TOOL,), call_results=None):
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.initialize = AsyncMock()

    tools_result = MagicMock()
    tools_result.tools = [MagicMock(name=n) for n in tool_names]
    # MagicMock(name=...) sets the mock's repr name, not .name - set it explicitly.
    for mock_tool, tool_name in zip(tools_result.tools, tool_names):
        mock_tool.name = tool_name
    session.list_tools = AsyncMock(return_value=tools_result)

    session.call_tool = AsyncMock(side_effect=call_results or [_ToolResult()])
    return session


def _patch_transport(session):
    """Patch the streamable-HTTP transport and ClientSession used by the module."""
    transport = MagicMock()
    transport.__aenter__ = AsyncMock(return_value=(MagicMock(), MagicMock(), MagicMock()))
    transport.__aexit__ = AsyncMock(return_value=None)

    http_client = MagicMock()
    http_client.__aenter__ = AsyncMock(return_value=http_client)
    http_client.__aexit__ = AsyncMock(return_value=None)

    return (
        patch('src.notion_sync.streamable_http_client', return_value=transport),
        patch('src.notion_sync.ClientSession', return_value=session),
        patch('src.notion_sync.httpx.AsyncClient', return_value=http_client),
    )


class TestBuildJobRows:
    def test_maps_job_fields_to_scalar_properties(self):
        rows = build_job_rows([_output(jobs_count=1)])

        assert len(rows) == 1
        props = rows[0]['properties']
        assert props['Name'] == 'Engineer 0'
        assert props['Company'] == 'Acme'
        assert props['YC Batch'] == 'W24'
        assert props['Salary Min'] == 150000
        assert props['Equity Max'] == 0.5

    def test_all_property_values_are_scalars(self):
        """The Notion MCP wrapper rejects nested property blocks."""
        rows = build_job_rows([_output(jobs_count=2)])

        for row in rows:
            for value in row['properties'].values():
                assert isinstance(value, (str, int, float)), value

    def test_date_uses_prefixed_key_form(self):
        props = build_job_rows([_output()])[0]['properties']

        assert 'date:Scraped At:start' in props
        assert 'Scraped At' not in props
        assert props['date:Scraped At:start'].startswith('2026-08-11T12:00:00')

    def test_drops_empty_values_instead_of_writing_nulls(self):
        output = _output()
        output.jobs[0].location = None
        output.jobs[0].salary = None

        props = build_job_rows([output])[0]['properties']

        assert 'Location' not in props
        assert 'Salary Min' not in props

    def test_collapses_whitespace_in_description(self):
        props = build_job_rows([_output()])[0]['properties']

        assert props['Summary'] == 'Build things with us'

    def test_respects_max_rows(self):
        rows = build_job_rows([_output(jobs_count=10)], max_rows=3)

        assert len(rows) == 3

    def test_flattens_across_companies(self):
        rows = build_job_rows([_output('a', 2), _output('b', 3)])

        assert len(rows) == 5


class TestToolErrorText:
    def test_returns_none_on_success(self):
        assert _tool_error_text(_ToolResult(is_error=False)) is None

    def test_reads_snake_case_is_error_flag(self):
        """The Python SDK uses is_error, not the TS SDK's isError."""
        assert _tool_error_text(_ToolResult(is_error=True, text='bad schema')) == 'bad schema'

    def test_error_without_text_still_reports(self):
        assert _tool_error_text(_ToolResult(is_error=True)) == 'unknown error'


class TestSyncJobsToNotion:
    async def test_skips_cleanly_when_proxy_env_missing(self):
        """Local runs have no MCP proxy - must short-circuit, not raise."""
        with patch.dict('os.environ', {}, clear=True):
            created = await sync_jobs_to_notion(
                [_output()], connector_id='conn_1', database_id='db_1'
            )

        assert created == 0

    async def test_writes_all_rows_and_returns_count(self):
        session = _make_session(call_results=[_ToolResult()])

        with patch.dict('os.environ', PROXY_ENV, clear=True):
            p1, p2, p3 = _patch_transport(session)
            with p1, p2, p3:
                created = await sync_jobs_to_notion(
                    [_output(jobs_count=5)], connector_id='conn_1', database_id='db_1'
                )

        assert created == 5
        args = session.call_tool.await_args.args
        kwargs = session.call_tool.await_args.kwargs
        assert args[0] == CREATE_PAGES_TOOL
        assert kwargs['arguments']['parent'] == {'database_id': 'db_1'}
        assert len(kwargs['arguments']['pages']) == 5

    async def test_failed_batch_is_logged_not_raised(self):
        session = _make_session(call_results=[_ToolResult(is_error=True, text='invalid_union')])

        with patch.dict('os.environ', PROXY_ENV, clear=True):
            p1, p2, p3 = _patch_transport(session)
            with p1, p2, p3:
                created = await sync_jobs_to_notion(
                    [_output(jobs_count=2)], connector_id='conn_1', database_id='db_1'
                )

        assert created == 0

    async def test_returns_zero_when_tool_not_permitted(self):
        """The proxy filters tools/list to what the input schema declared."""
        session = _make_session(tool_names=('notion-search',))

        with patch.dict('os.environ', PROXY_ENV, clear=True):
            p1, p2, p3 = _patch_transport(session)
            with p1, p2, p3:
                created = await sync_jobs_to_notion(
                    [_output()], connector_id='conn_1', database_id='db_1'
                )

        assert created == 0
        session.call_tool.assert_not_awaited()

    async def test_transport_error_does_not_propagate(self):
        with patch.dict('os.environ', PROXY_ENV, clear=True):
            with patch('src.notion_sync.httpx.AsyncClient', side_effect=RuntimeError('boom')):
                created = await sync_jobs_to_notion(
                    [_output()], connector_id='conn_1', database_id='db_1'
                )

        assert created == 0

    async def test_no_jobs_skips_connection_entirely(self):
        empty = CompanyOutput(
            company=Company(id=1, name='Acme', slug='acme'),
            founders=[],
            jobs=[],
            scrapedAt=datetime.now(timezone.utc),
        )

        with patch.dict('os.environ', PROXY_ENV, clear=True):
            with patch('src.notion_sync.httpx.AsyncClient') as http_client:
                created = await sync_jobs_to_notion(
                    [empty], connector_id='conn_1', database_id='db_1'
                )

        assert created == 0
        http_client.assert_not_called()
