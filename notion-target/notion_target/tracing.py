"""Write private local traces with configured credentials redacted.

Traces include user prompts and retrieved document data. A write failure must
fail the request so experiment evidence is never silently discarded."""

import json
import os

from .config import Settings


def write_trace(settings, trace):
    settings.traces.mkdir(mode=448, parents=True, exist_ok=True)
    serialized = json.dumps(trace, ensure_ascii=False, indent=2)
    for secret in (settings.api_key, settings.notion_token):
        if secret:
            serialized = serialized.replace(secret, "[REDACTED]").replace(
                json.dumps(secret)[1:-1], "[REDACTED]"
            )
    path = settings.traces / (trace["request_id"] + ".json")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 384)
    with os.fdopen(fd, "w") as f:
        f.write(serialized)


def write_llm_event(settings, request_id, event):
    """Flush each model-call event without exposing it through the experiment API."""
    from datetime import datetime, timezone

    def without_images(value):
        if isinstance(value, dict):
            return {key: ("[image bytes omitted]" if key == "image_url" else without_images(item))
                    for key, item in value.items()}
        if isinstance(value, list):
            return [without_images(item) for item in value]
        return value

    settings.traces.mkdir(mode=448, parents=True, exist_ok=True)
    record = dict(timestamp=datetime.now(timezone.utc).isoformat(), request_id=request_id, **event)
    serialized = json.dumps(without_images(record), ensure_ascii=False)
    for secret in (settings.api_key, settings.notion_token):
        if secret:
            serialized = serialized.replace(secret, "[REDACTED]").replace(
                json.dumps(secret)[1:-1], "[REDACTED]")
    path = settings.traces / (request_id + ".llm.jsonl")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 384)
    with os.fdopen(fd, "a") as handle:
        handle.write(serialized + "\n")
