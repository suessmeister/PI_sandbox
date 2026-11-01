"""Structured feedback calls for the judge, generator, and selector."""

import json
import os
from pathlib import Path

import httpx

from call_logging import event, logged_call
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel


def ask(schema: type[BaseModel], instructions: str, context: dict, *,
        model_name: str, provider: str = "openai") -> BaseModel:
    if provider not in {"openai", "openrouter"}:
        raise ValueError("Feedback provider must be openai or openrouter.")
    load_dotenv(Path(__file__).with_name(".env"), override=False)
    key_name = "OPENAI_API_KEY" if provider == "openai" else "OPENROUTER_API_KEY"
    key = os.getenv(key_name, "").strip()
    if not key:
        raise ValueError(f"Set {key_name} in .env or your environment.")
    base_url = "https://api.openai.com/v1" if provider == "openai" else "https://openrouter.ai/api/v1"
    with logged_call("feedback", provider=provider, model=model_name, schema=schema.__name__,
                     mutation_mode=context.get("mutation_mode"), timeout_seconds=120, max_retries=2,
                     request={"instructions": instructions, "context": context}) as call_id:
        attempts = 0
        def on_request(request):
            nonlocal attempts
            attempts += 1
            event(call_id, "attempt_start", attempt=attempts)
        def on_response(response):
            event(call_id, "attempt_response", attempt=attempts, status_code=response.status_code,
                  request_id=response.headers.get("x-request-id"))
        with httpx.Client(event_hooks={"request": [on_request], "response": [on_response]}) as transport:
            with OpenAI(api_key=key, base_url=base_url, timeout=120, max_retries=2,
                        http_client=transport) as client:
                response = client.responses.parse(
                    model=model_name, instructions=instructions,
                    input=json.dumps(context, ensure_ascii=False), text_format=schema, store=False,
                )
        event(call_id, "response", response_id=response.id, status=response.status,
              usage=response.usage.model_dump() if response.usage else None,
              response=response.model_dump(mode="json"))
        if response.status != "completed" or response.output_parsed is None:
            raise ValueError("Feedback model refused or did not return a complete structured answer.")
        return response.output_parsed
