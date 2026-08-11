"""Write scraped YC jobs into Notion through an Apify MCP connector.

The Actor never holds a Notion token. Apify injects APIFY_MCP_PROXY_URL and
APIFY_TOKEN into every run; we speak MCP to the proxy with the run token, and
the proxy swaps in the user's Notion credential server-side before forwarding.
"""
import logging
import os
from typing import Any, Dict, Iterator, List, Optional, Sequence

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from .models import CompanyOutput

logger = logging.getLogger(__name__)

NOTION_MCP_URL = "https://mcp.notion.com/mcp"
CREATE_PAGES_TOOL = "notion-create-pages"

# notion-create-pages accepts a batch of pages per call. Keep batches modest so
# a single failure doesn't cost the whole run, and so payloads stay well under
# any request size ceiling.
PAGE_BATCH_SIZE = 20


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
    max_rows: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Flatten scraped companies into one Notion page payload per job.

    The Notion MCP wrapper takes *scalar* property values (str | int | float |
    None) and maps them onto the database columns itself. Raw Notion API
    property blocks are rejected. Date columns use the "date:<Column>:start"
    key form rather than the bare column name.
    """
    rows: List[Dict[str, Any]] = []

    for result in results:
        company = result.company
        scraped_at = result.scrapedAt.isoformat() if result.scrapedAt else None

        for job in result.jobs:
            salary = job.salary
            equity = job.equity

            properties: Dict[str, Any] = {
                'Name': job.title,
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
                'date:Scraped At:start': scraped_at,
            }

            # Drop empty values instead of writing nulls into the database.
            rows.append({
                'properties': {k: v for k, v in properties.items() if v is not None}
            })

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


async def sync_jobs_to_notion(
    results: Sequence[CompanyOutput],
    connector_id: str,
    database_id: str,
    max_rows: Optional[int] = None,
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

    rows = build_job_rows(results, max_rows=max_rows)
    if not rows:
        logger.info("📭 No jobs to sync to Notion")
        return 0

    logger.info(f"📤 Syncing {len(rows)} jobs to Notion via MCP connector")
    created = 0

    try:
        async with httpx.AsyncClient(
            headers={'Authorization': f'Bearer {token}'},
            timeout=httpx.Timeout(60.0),
        ) as http_client:
            async with streamable_http_client(
                f"{proxy_url}/{connector_id}",
                http_client=http_client,
            ) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()

                    available = {tool.name for tool in (await session.list_tools()).tools}
                    logger.info(f"🔧 Tools allowed through the connector: {sorted(available)}")

                    if CREATE_PAGES_TOOL not in available:
                        logger.error(
                            f"❌ {CREATE_PAGES_TOOL} is not available. The proxy only exposes "
                            f"tools declared in the input schema and permitted by the connector."
                        )
                        return 0

                    for batch_no, batch in enumerate(_chunk(rows, PAGE_BATCH_SIZE), 1):
                        response = await session.call_tool(
                            CREATE_PAGES_TOOL,
                            arguments={
                                'parent': {'database_id': database_id},
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
