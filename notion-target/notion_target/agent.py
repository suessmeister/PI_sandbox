"""Run one fresh model conversation and continue its Notion function calls.

System instructions are trusted; user text, images, and tool results are data.
Every requested tool is checked again before execution."""

import base64
import json
import time
from uuid import uuid4

from openai import AsyncOpenAI

from .tracing import write_llm_event
from .config import Settings
from .notion import discover, notion_session


async def run_target(settings, prompt, data, mime, trace):
    async with notion_session(settings) as session:
        tools = await discover(session)
        trace["available_tools"] = list(tools)
        schemas = [
            dict(
                type="function",
                name=tool.name,
                description=tool.description or "",
                parameters=tool.inputSchema,
                strict=False,
            )
            for tool in tools.values()
        ]
        messages = [
            dict(
                role="user",
                content=[
                    dict(type="input_text", text=prompt),
                    dict(
                        type="input_image",
                        image_url=f"data:{mime};base64,"
                        + base64.b64encode(data).decode(),
                    ),
                ],
            )
        ]
        base_url = (
            None if settings.provider == "openai" else "https://openrouter.ai/api/v1"
        )
        async with AsyncOpenAI(
            api_key=settings.api_key,
            base_url=base_url,
            timeout=settings.timeout,
            max_retries=0,
        ) as client:
            tool_calls_used = 0
            assistant_texts = []
            trace["assistant_text_chunks"] = assistant_texts
            while True:
                call_id = uuid4().hex
                request_id = trace.setdefault("request_id", str(uuid4()))
                started = time.monotonic()
                write_llm_event(settings, request_id, dict(
                    event="start", call_id=call_id, model=settings.model, provider=settings.provider,
                    timeout_seconds=settings.timeout, max_retries=0,
                    request=dict(instructions=settings.system_prompt, input=messages, tools=schemas)))
                try:
                    result = await client.responses.create(
                        model=settings.model,
                        instructions=settings.system_prompt,
                        input=messages,
                        tools=schemas,
                        store=False,
                    )
                    write_llm_event(settings, request_id, dict(
                        event="end", call_id=call_id, elapsed_seconds=time.monotonic() - started,
                        response_id=getattr(result, "id", None), status=result.status,
                        usage=result.usage.model_dump() if getattr(result, "usage", None) else None,
                        response=dict(output=[item.model_dump(exclude_none=True) for item in result.output],
                                      output_text=result.output_text)))
                except BaseException as exc:
                    write_llm_event(settings, request_id, dict(
                        event="error", call_id=call_id, elapsed_seconds=time.monotonic() - started,
                        error_type=type(exc).__name__, error=str(exc)))
                    raise
                if result.output_text:
                    assistant_texts.append(result.output_text)
                messages.extend(
                    (item.model_dump(exclude_none=True) for item in result.output)
                )
                calls = [item for item in result.output if item.type == "function_call"]
                if not calls:
                    if result.status != "completed" or not any(text.strip() for text in assistant_texts):
                        raise RuntimeError(
                            "Model did not produce a complete text answer"
                        )
                    return "\n\n".join(text for text in assistant_texts if text.strip())
                for call in calls:
                    record = dict(
                        name=call.name, arguments=call.arguments, call_id=call.call_id
                    )
                    trace["tool_calls"].append(record)
                    if tool_calls_used >= settings.steps:
                        raise RuntimeError("Maximum tool-call steps exceeded")
                    if call.name not in tools:
                        raise RuntimeError(
                            "Model requested a tool outside the read-only allowlist"
                        )
                    tool_calls_used += 1
                    started = time.monotonic()
                    tool_result = await session.call_tool(
                        call.name, json.loads(call.arguments)
                    )
                    payload = tool_result.model_dump(mode="json", exclude_none=True)
                    trace["tool_results"].append(
                        dict(
                            call_id=call.call_id,
                            result=payload,
                            elapsed_seconds=time.monotonic() - started,
                        )
                    )
                    messages.append(
                        dict(
                            type="function_call_output",
                            call_id=call.call_id,
                            output=json.dumps(payload),
                        )
                    )
