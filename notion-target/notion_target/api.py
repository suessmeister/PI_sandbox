"""HTTP request lifecycle: validate, execute, trace, and return an answer.

Raw provider exceptions are withheld because they may contain credentials."""

import asyncio
import hashlib
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from .agent import run_target
from .config import Settings
from .images import MAX_BYTES, validate_image
from .tracing import write_trace


def create_app(settings=None):

    @asynccontextmanager
    async def lifespan(app):
        app.state.settings = settings or Settings.load()
        yield

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.post("/run")
    async def run(prompt: str = Form(...), image: UploadFile = File(...)):
        settings = app.state.settings
        started = time.monotonic()
        trace = dict(
            request_id=str(uuid4()),
            model=settings.model,
            provider=settings.provider,
            system_prompt=settings.system_prompt,
            submitted_text=prompt,
            image_hash=None,
            tool_calls=[],
            tool_results=[],
            final_response=None,
            errors=[],
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        try:
            async with asyncio.timeout(settings.timeout):
                data = await image.read(MAX_BYTES + 1)
                trace["image_hash"] = hashlib.sha256(data).hexdigest()
                validate_image(data, image.content_type)
                if not prompt.strip() or len(prompt) > 100000:
                    raise HTTPException(400, "Prompt must contain 1–100000 characters")
                trace["final_response"] = await run_target(
                    settings, prompt, data, image.content_type, trace
                )
            return dict(
                request_id=trace["request_id"], response=trace["final_response"]
            )
        except HTTPException as error:
            trace["errors"].append(dict(type="validation", message=error.detail))
            raise
        except TimeoutError:
            trace["errors"].append(dict(type="timeout", message="Request timeout"))
            raise HTTPException(504, "Request timed out; inspect local trace") from None
        except Exception as error:
            trace["errors"].append(
                dict(type=type(error).__name__, message="Model or MCP execution failed")
            )
            raise HTTPException(
                502, "Model or MCP execution failed; inspect local trace"
            ) from None
        finally:
            trace["elapsed_seconds"] = time.monotonic() - started
            write_trace(settings, trace)
            await image.close()

    return app
