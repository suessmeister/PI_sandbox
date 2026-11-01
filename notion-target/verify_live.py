"""Real MCP discovery or real image/model/Notion integration check. No mocks."""

import argparse
import asyncio
import io
import json
from fastapi.testclient import TestClient
from PIL import Image
from notion_target.config import Settings, ROOT
from notion_target.api import create_app
from notion_target.notion import discover, notion_session


async def discovery(s):
    async with asyncio.timeout(30):
        async with notion_session(s) as session:
            tools = await discover(session)
            print("Real MCP read/search tools:", ", ".join(sorted(tools)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--discovery-only", action="store_true")
    parser.add_argument("--page-title")
    parser.add_argument(
        "--expect", help="Marker stored in the allowed page; never sent to the model"
    )
    args = parser.parse_args()
    if args.discovery_only:
        s = Settings(
            "openai",
            "unused",
            "",
            "ntn_discovery_only",
            "unused",
            "node",
            ["node_modules/@notionhq/notion-mcp-server/bin/cli.mjs"],
            8,
            30,
            ROOT / "traces",
        )
        asyncio.run(discovery(s))
        return
    if not args.page_title or not args.expect:
        parser.error("Supply --page-title and --expect")
    s = Settings.load()
    asyncio.run(discovery(s))
    image = io.BytesIO()
    Image.new("RGB", (64, 64), "red").save(image, format="PNG")
    with TestClient(create_app(s)) as client:
        result = client.post(
            "/run",
            data={
                "prompt": f"Retrieve the Notion page titled {args.page_title!r} and report its verification marker. Also name the solid color of the attached image."
            },
            files={"image": ("test.png", image.getvalue(), "image/png")},
        )
        if result.status_code != 200:
            raise SystemExit(f"FAILED HTTP {result.status_code}: {result.text}")
        body = result.json()
        trace = json.loads((s.traces / (body["request_id"] + ".json")).read_text())
        assert set(body) == {"request_id", "response"}
        assert (
            args.expect.casefold() in body["response"].casefold()
        ), "Notion marker missing"
        assert "red" in body["response"].casefold(), "Image color missing"
        assert any(
            r["result"].get("isError") is not True for r in trace["tool_results"]
        ), "No successful MCP result"
        print(
            "PASS image + model + Notion through POST /run; request_id="
            + body["request_id"]
        )


if __name__ == "__main__":
    main()
