"""Persist completed experiment conversations."""

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from langchain_core.messages import BaseMessage, messages_to_dict

ROOT = Path(__file__).resolve().parent


def save_trace(
    model_name: str, messages: list[BaseMessage], *, provider: str,
    output_path: Path | None = None,
) -> Path:
    """Save a trace without overwriting a previous run."""
    run_id = uuid4().hex
    path = (output_path or ROOT / "output" / f"{run_id}.json").expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "schema_version": 2,
        "provider": provider,
        "run_id": run_id,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "requested_model": model_name,
        "messages": messages_to_dict(messages),
    }
    with path.open("x", encoding="utf-8") as handle:
        json.dump(record, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return path
