"""Write scraped YC jobs into Notion through an Apify MCP connector.

The Actor never holds a Notion token. Apify injects APIFY_MCP_PROXY_URL and
APIFY_TOKEN into every run; we speak MCP to the proxy with the run token, and
the proxy swaps in the user's Notion credential server-side before forwarding.
"""
import json
import logging
import os
import re
from typing import Any, Dict, Iterator, List, Optional, Sequence

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from .models import CompanyOutput

logger = logging.getLogger(__name__)

NOTION_MCP_URL = "https://mcp.notion.com/mcp"
CREATE_PAGES_TOOL = "notion-create-pages"
FETCH_TOOL = "notion-fetch"

# notion-create-pages accepts a batch of pages per call. Keep batches modest so
# a single failure doesn't cost the whole run, and so payloads stay well under
# any request size ceiling.
PAGE_BATCH_SIZE = 20


def parse_data_source_id(value: Optional[str]) -> Optional[str]:
    """Normalize a Notion data source reference to a bare UUID.

    notion-create-pages parents a page on a *data source*, not a database. In
    Notion's current API a database can hold several data sources, and the
    tool rejects "database_id" whenever that is the case. Data source URLs look
    like "collection://<uuid>", which is what we strip here.
    """
    if not value:
        return None
    cleaned = value.strip()
    if cleaned.startswith('collection://'):
        cleaned = cleaned[len('collection://') :]
    return cleaned or None


_DATA_SOURCE_STATE_RE = re.compile(
    r'<data-source-state>\s*(\{.*?\})\s*</data-source-state>', re.DOTALL
)


def parse_data_source_schema(payload: str) -> Dict[str, str]:
    """Pull {column name: property type} out of a notion-fetch response.

    The tool answers with a document, not JSON: a <data-source-state> block
    wrapping the real schema, plus a SQLite CREATE TABLE rendering of the same
    thing. We read the former.
    """
    # notion-fetch returns a JSON envelope whose "text" field holds the markup.
    # Unwrap it first, or the regex below matches JSON-escaped junk.
    try:
        envelope = json.loads(payload)
        if isinstance(envelope, dict) and isinstance(envelope.get('text'), str):
            payload = envelope['text']
    except json.JSONDecodeError:
        pass

    match = _DATA_SOURCE_STATE_RE.search(payload)
    if not match:
        return {}

    try:
        state = json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}

    schema = state.get('schema')
    if not isinstance(schema, dict):
        return {}

    return {
        name: (spec or {}).get('type', '')
        for name, spec in schema.items()
        if isinstance(name, str)
    }


def _title_column(schema: Dict[str, str]) -> Optional[str]:
    """A data source has exactly one title property, but it can be named anything."""
    for name, prop_type in schema.items():
        if prop_type == 'title':
            return name
    return None


def _truncate(value: Optional[str], limit: int) -> Optional[str]:
    """Clip long free text. Notion rejects oversized rich-text values."""
    if not value:
        return None
    collapsed = ' '.join(value.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + '…'


def build_job_rows(
    results: Sequence[CompanyOutput],
    schema: Optional[Dict[str, str]] = None,
    max_rows: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Flatten scraped companies into one Notion page payload per job.

    Property values are *scalars* (str | int | float); the wrapper maps them onto
    the column types itself, and rejects raw Notion API property blocks. Date
    columns use the "date:<Column>:start" key form rather than the bare name.

    When `schema` is given, only columns that actually exist in the target data
    source are written, and the job title goes to whatever the title property is
    called. Notion rejects the whole batch if any property name is unknown, so
    guessing a column layout is not an option for a published Actor.
    """
    title_key = _title_column(schema) if schema else 'Name'
    rows: List[Dict[str, Any]] = []

    for result in results:
        company = result.company
        scraped_at = result.scrapedAt.isoformat() if result.scrapedAt else None

        for job in result.jobs:
            salary = job.salary
            equity = job.equity

            candidates: Dict[str, Any] = {
                'Company': company.name,
                'YC Batch': company.ycBatch,
                'Location': job.location,
                'Role': job.roleCategory,
                'Job Type': job.jobType,
                'Experience': job.experience,
                'Visa': job.visa,
                'Salary Min': salary.min if salary else None,
                'Salary Max': salary.max if salary else None,
                'Currency': salary.currency if salary else None,
                'Equity Min': equity.min if equity else None,
                'Equity Max': equity.max if equity else None,
                'Job URL': job.jobUrl,
                'Company URL': company.website,
                'Summary': _truncate(job.description, 2000),
            }

            properties: Dict[str, Any] = {}
            if title_key:
                properties[title_key] = job.title

            for column, value in candidates.items():
                if value is None:
                    continue
                if schema is not None and column not in schema:
                    continue
                properties[column] = value

            if scraped_at and (schema is None or schema.get('Scraped At') == 'date'):
                properties['date:Scraped At:start'] = scraped_at

            rows.append({'properties': properties})

            if max_rows is not None and len(rows) >= max_rows:
                return rows

    return rows


def _chunk(items: Sequence[Dict[str, Any]], size: int) -> Iterator[List[Dict[str, Any]]]:
    """Yield fixed-size batches."""
    for start in range(0, len(items), size):
        yield list(items[start : start + size])


def _tool_error_text(result: Any) -> Optional[str]:
    """Return the error text of a failed tool call, or None if it succeeded.

    The Python MCP SDK exposes this as `is_error` (snake_case). It is a field on
    the result, not an exception - a failed tool call returns normally.
    """
    if not getattr(result, 'is_error', False):
        return None

    for block in getattr(result, 'content', None) or []:
        text = getattr(block, 'text', None)
        if text:
            return text
    return 'unknown error'


async def _fetch_data_source_schema(session: Any, source_id: str) -> Dict[str, str]:
    """Ask Notion for the target data source's columns. Returns {} on failure."""
    try:
        response = await session.call_tool(
            FETCH_TOOL, arguments={'id': f'collection://{source_id}'}
        )
    except Exception as e:
        logger.warning(f"⚠️ {FETCH_TOOL} call failed: {str(e)}")
        return {}

    error_text = _tool_error_text(response)
    if error_text:
        logger.warning(f"⚠️ {FETCH_TOOL} returned an error: {error_text}")
        return {}

    for block in getattr(response, 'content', None) or []:
        text = getattr(block, 'text', None)
        if not text:
            continue
        schema = parse_data_source_schema(text)
        if schema:
            return schema
    return {}


async def _dump_tool_schemas(tools: Any) -> None:
    """Save the connector's tool schemas to the key-value store.

    Apify Console truncates long log lines, so a tool's inputSchema is
    effectively unreadable in the log. Writing it to the KV store is the only
    practical way to see what a tool actually expects.
    """
    from apify import Actor

    payload = [
        {
            'name': tool.name,
            'description': getattr(tool, 'description', None),
            'inputSchema': getattr(tool, 'inputSchema', None),
        }
        for tool in tools
    ]
    await Actor.set_value('NOTION_TOOL_SCHEMA', payload)
    logger.info(f"🧪 Wrote {len(payload)} tool schemas to key-value store record NOTION_TOOL_SCHEMA")


async def sync_jobs_to_notion(
    results: Sequence[CompanyOutput],
    connector_id: str,
    data_source_id: str,
    max_rows: Optional[int] = None,
    debug_schema: bool = False,
) -> int:
    """Create one Notion page per scraped job. Returns the number created.

    Never raises: the scrape has already succeeded by the time this runs, so a
    Notion problem is logged and swallowed rather than failing the whole run.
    """
    proxy_url = os.environ.get('APIFY_MCP_PROXY_URL')
    token = os.environ.get('APIFY_TOKEN')

    if not proxy_url or not token:
        logger.warning(
            "⚠️ APIFY_MCP_PROXY_URL/APIFY_TOKEN not set - skipping Notion sync. "
            "MCP connectors only resolve on the Apify platform, not in local runs."
        )
        return 0

    source_id = parse_data_source_id(data_source_id)
    if not source_id:
        logger.warning("⚠️ No Notion data source ID - skipping Notion sync")
        return 0

    if not any(result.jobs for result in results):
        logger.info("📭 No jobs to sync to Notion")
        return 0

    logger.info("📤 Connecting to Notion via MCP connector")
    created = 0

    try:
        async with httpx.AsyncClient(
            headers={'Authorization': f'Bearer {token}'},
            timeout=httpx.Timeout(60.0),
        ) as http_client:
            # mcp 2.x yields exactly (read_stream, write_stream). The Apify docs
            # snippet unpacks three values, which is the mcp 1.x shape and raises
            # "not enough values to unpack (expected 3, got 2)" here.
            async with streamable_http_client(
                f"{proxy_url}/{connector_id}",
                http_client=http_client,
            ) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()

                    tools = (await session.list_tools()).tools
                    available = {tool.name for tool in tools}
                    logger.info(f"🔧 Tools allowed through the connector: {sorted(available)}")

                    if debug_schema:
                        await _dump_tool_schemas(tools)
                        return 0

                    if CREATE_PAGES_TOOL not in available:
                        logger.error(
                            f"❌ {CREATE_PAGES_TOOL} is not available. The proxy only exposes "
                            f"tools declared in the input schema and permitted by the connector."
                        )
                        return 0

                    # Read the target's columns before writing. Notion rejects an
                    # entire batch if one property name is unknown, and every user
                    # lays their database out differently.
                    schema: Optional[Dict[str, str]] = None
                    if FETCH_TOOL in available:
                        # An empty result means "could not read", not "no columns".
                        # Collapsing it to None matters: an empty dict would filter
                        # every property out and silently create blank pages.
                        schema = await _fetch_data_source_schema(session, source_id) or None
                        if schema:
                            logger.info(f"🗂️ Target columns: {sorted(schema)}")
                        else:
                            logger.warning("⚠️ Could not read the data source schema - sending all columns")

                    rows = build_job_rows(results, schema=schema, max_rows=max_rows)
                    if not rows:
                        logger.info("📭 No jobs to sync to Notion")
                        return 0

                    for batch_no, batch in enumerate(_chunk(rows, PAGE_BATCH_SIZE), 1):
                        response = await session.call_tool(
                            CREATE_PAGES_TOOL,
                            arguments={
                                'parent': {'data_source_id': source_id},
                                'pages': batch,
                            },
                        )

                        error_text = _tool_error_text(response)
                        if error_text:
                            logger.error(f"❌ Notion batch {batch_no} failed: {error_text}")
                            continue

                        created += len(batch)
                        logger.info(f"✅ Notion batch {batch_no}: wrote {len(batch)} jobs")

    except Exception as e:
        logger.error(f"❌ Notion sync failed: {str(e)}", exc_info=True)
        return created

    logger.info(f"🎉 Notion sync complete: {created}/{len(rows)} jobs written")
    return created
