"""Connect to Notion MCP and expose only audited read/search tools.

The allowlist blocks writes at discovery and dispatch. Sensitive page IDs are
not filtered here: that restriction is deliberately a model-policy experiment."""

import os
from contextlib import asynccontextmanager

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .config import ROOT, Settings

READ_TOOLS = frozenset(
    {
        "API-post-search",
        "API-retrieve-a-page",
        "API-get-block-children",
        "API-retrieve-a-block",
        "API-retrieve-a-database",
        "API-query-data-source",
        "API-retrieve-a-data-source",
        "API-retrieve-page-markdown",
        "API-retrieve-a-page-property",
    }
)


@asynccontextmanager
async def notion_session(settings):
    env = {
        k: os.environ[k]
        for k in ("PATH", "HOME", "TMPDIR", "SYSTEMROOT")
        if k in os.environ
    }
    env["NOTION_TOKEN"] = settings.notion_token
    with open(os.devnull, "w") as stderr_sink:
        async with stdio_client(
            StdioServerParameters(
                command=settings.command, args=settings.args, env=env, cwd=str(ROOT)
            ),
            errlog=stderr_sink,
        ) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session


async def discover(session):
    selected = {}
    cursor = None
    while True:
        page = await session.list_tools(cursor=cursor)
        selected.update(
            {tool.name: tool for tool in page.tools if tool.name in READ_TOOLS}
        )
        cursor = page.nextCursor
        if not cursor:
            break
    if not selected:
        raise RuntimeError("No supported Notion read/search tools discovered")
    return selected
