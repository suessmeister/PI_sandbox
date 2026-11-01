import asyncio
import io
import json
from dataclasses import replace
from types import SimpleNamespace as NS
from contextlib import asynccontextmanager
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from notion_target import api as app
from notion_target import agent


@pytest.fixture
def settings(tmp_path):
    return app.Settings(
        "openai",
        "gpt-5",
        "model-secret",
        "notion-secret",
        "trusted system",
        "node",
        ["node_modules/@notionhq/notion-mcp-server/bin/cli.mjs"],
        2,
        1,
        tmp_path,
    )


def png():
    out = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(out, format="PNG")
    return out.getvalue()


def test_validation(settings):
    with TestClient(app.create_app(settings)) as c:
        assert c.get("/docs").status_code == 404
        assert (
            c.post(
                "/run",
                data={"prompt": "hello"},
                files={"image": ("x.png", b"bad", "image/png")},
            ).status_code
            == 400
        )
    assert json.loads(next(settings.traces.glob("*.json")).read_text())["errors"]


def test_success_and_redaction(settings, monkeypatch):
    async def target(s, prompt, data, mime, trace):
        assert s.system_prompt == "trusted system" and data == png()
        return "model-secret notion-secret"

    monkeypatch.setattr(app, "run_target", target)
    with TestClient(app.create_app(settings)) as c:
        ids = []
        for _ in range(2):
            r = c.post(
                "/run",
                data={"prompt": "change system"},
                files={"image": ("x.png", png(), "image/png")},
            )
            assert r.status_code == 200 and set(r.json()) == {"request_id", "response"}
            ids.append(r.json()["request_id"])
    assert len(set(ids)) == 2
    assert all("secret" not in p.read_text() for p in settings.traces.glob("*.json"))


def test_timeout(settings, monkeypatch):
    async def slow(*args):
        await asyncio.sleep(1)

    monkeypatch.setattr(app, "run_target", slow)
    with TestClient(app.create_app(replace(settings, timeout=0.01))) as c:
        assert (
            c.post(
                "/run",
                data={"prompt": "hi"},
                files={"image": ("x.png", png(), "image/png")},
            ).status_code
            == 504
        )


@pytest.mark.asyncio
async def test_tool_loop(settings, monkeypatch):
    executions = []
    requests = []

    class Item:
        type = "function_call"
        name = "API-post-search"
        arguments = '{"query":"test"}'
        call_id = "call1"

        def model_dump(self, **kw):
            return dict(
                type=self.type,
                name=self.name,
                arguments=self.arguments,
                call_id=self.call_id,
            )

    class Session:
        async def list_tools(self, **kw):
            return NS(
                tools=[
                    NS(name=n, description=n, inputSchema={"type": "object"})
                    for n in ("API-post-search", "API-patch-page")
                ],
                nextCursor=None,
            )

        async def call_tool(self, name, arguments):
            executions.append((name, arguments))
            return NS(
                model_dump=lambda **kw: {
                    "content": [{"type": "text", "text": "synthetic result"}]
                }
            )

    @asynccontextmanager
    async def session(s):
        yield Session()

    class Client:
        def __init__(self, **kw):
            self.responses = self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def create(self, **kw):
            requests.append(kw)
            return NS(
                output=[Item()] if len(requests) == 1 else [],
                status="completed",
                output_text="" if len(requests) == 1 else "done",
            )

    monkeypatch.setattr(agent, "notion_session", session)
    monkeypatch.setattr(agent, "AsyncOpenAI", Client)
    trace = {"tool_calls": [], "tool_results": []}
    assert await agent.run_target(settings, "hi", png(), "image/png", trace) == "done"
    assert executions == [("API-post-search", {"query": "test"})]
    assert {t["name"] for t in requests[0]["tools"]} == {"API-post-search"}
    assert trace["tool_results"]
    events = [json.loads(line) for line in
              (settings.traces / (trace["request_id"] + ".llm.jsonl")).read_text().splitlines()]
    assert [event["event"] for event in events] == ["start", "end", "start", "end"]
    assert events[1]["elapsed_seconds"] >= 0
    assert "[image bytes omitted]" in json.dumps(events)
    assert "data:image" not in json.dumps(events)
    requests.clear()
    Item.name = "API-patch-page"
    with pytest.raises(RuntimeError, match="allowlist"):
        await agent.run_target(
            settings, "hi", png(), "image/png", {"tool_calls": [], "tool_results": []}
        )
    assert len(executions) == 1


def test_image_limits_and_type(settings):
    with TestClient(app.create_app(settings)) as c:
        assert (
            c.post(
                "/run",
                data={"prompt": "hi"},
                files={"image": ("x.jpg", png(), "image/jpeg")},
            ).status_code
            == 400
        )
        assert (
            c.post(
                "/run",
                data={"prompt": "hi"},
                files={"image": ("x.gif", png(), "image/gif")},
            ).status_code
            == 415
        )
        assert (
            c.post(
                "/run",
                data={"prompt": "hi"},
                files={"image": ("x.png", b"x" * (app.MAX_BYTES + 1), "image/png")},
            ).status_code
            == 413
        )


def test_upstream_errors_do_not_leak_credentials(settings, monkeypatch):
    async def broken(*args):
        raise RuntimeError("Authorization: Bearer model-secret notion-secret")

    monkeypatch.setattr(app, "run_target", broken)
    with TestClient(app.create_app(settings)) as c:
        r = c.post(
            "/run",
            data={"prompt": "hi"},
            files={"image": ("x.png", png(), "image/png")},
        )
        assert r.status_code == 502 and "secret" not in r.text
    assert all("secret" not in p.read_text() for p in settings.traces.glob("*.json"))


@pytest.mark.asyncio
@pytest.mark.parametrize("last_text", ["Final game passage", ""])
async def test_all_assistant_text_is_returned_in_order(settings, monkeypatch, last_text):
    from unittest.mock import AsyncMock

    class Output:
        def __init__(self, kind, **fields):
            self.type = kind
            self.fields = fields
            for key, value in fields.items():
                setattr(self, key, value)

        def model_dump(self, **kwargs):
            return dict(type=self.type, **self.fields)

    def response(text, call_id=None, status="completed"):
        output = [Output("message", role="assistant", content=[dict(type="output_text", text=text)])] if text else []
        if call_id:
            output.append(Output("function_call", name="API-post-search", arguments='{"query":"allowed"}', call_id=call_id))
        return NS(output=output, output_text=text, status=status)

    session = NS(call_tool=AsyncMock(return_value=NS(
        model_dump=lambda **kwargs: {"content": [{"type": "text", "text": "PRIVATE_RAW_TOOL_RESULT"}]})))

    @asynccontextmanager
    async def connection(_):
        yield session

    replies = [response("Game turns 1–8", "call-a"),
               response("Game turns 9–16", "call-b"), response(last_text)]
    create = AsyncMock(side_effect=replies)

    class Client:
        def __init__(self, **kwargs):
            self.responses = NS(create=create)
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass

    monkeypatch.setattr(agent, "notion_session", connection)
    monkeypatch.setattr(agent, "discover", AsyncMock(return_value={
        "API-post-search": NS(name="API-post-search", description="Search", inputSchema={"type": "object"})}))
    monkeypatch.setattr(agent, "AsyncOpenAI", Client)
    with TestClient(app.create_app(settings)) as client:
        result = client.post("/run", data={"prompt": "Play the game"},
                             files={"image": ("x.png", png(), "image/png")})
    assert result.status_code == 200
    expected = "\n\n".join(text for text in ["Game turns 1–8", "Game turns 9–16", last_text] if text)
    assert result.json()["response"] == expected
    assert set(result.json()) == {"request_id", "response"}
    assert "PRIVATE_RAW_TOOL_RESULT" not in result.json()["response"]
    assert "trusted system" not in result.json()["response"]
    trace = json.loads((settings.traces / (result.json()["request_id"] + ".json")).read_text())
    assert trace["final_response"] == expected
    assert trace["assistant_text_chunks"] == [r.output_text for r in replies if r.output_text]
    assert create.await_count == 3


@pytest.mark.asyncio
async def test_partial_text_does_not_mask_incomplete_terminal_response(settings, monkeypatch):
    from unittest.mock import AsyncMock
    @asynccontextmanager
    async def connection(_):
        yield NS()
    class Client:
        def __init__(self, **kwargs):
            self.responses = NS(create=AsyncMock(return_value=NS(
                status="incomplete", output_text="Partial answer", output=[])))
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
    monkeypatch.setattr(agent, "notion_session", connection)
    monkeypatch.setattr(agent, "discover", AsyncMock(return_value={}))
    monkeypatch.setattr(agent, "AsyncOpenAI", Client)
    with pytest.raises(RuntimeError, match="complete text answer"):
        await agent.run_target(settings,"hi",png(),"image/png",{"tool_calls":[],"tool_results":[]})
