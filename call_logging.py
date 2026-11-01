"""Run-scoped LLM calls: flushed JSONL details and a readable timing log."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import json
from time import monotonic
from uuid import uuid4

CALL_DIRECTORY = ContextVar("call_directory", default=None)


def event(call_id, event_type, **details):
    directory = CALL_DIRECTORY.get()
    if directory is None:
        return
    record = dict(timestamp=datetime.now(timezone.utc).isoformat(), call_id=call_id,
                  event=event_type, **details)
    with (directory / "llm_calls.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    brief = {k: v for k, v in details.items() if k not in {"request", "response"}}
    with (directory / "llm_calls.log").open("a", encoding="utf-8") as handle:
        handle.write(f"{record['timestamp']} {call_id[:8]} {event_type} "
                     + json.dumps(brief, ensure_ascii=False) + "\n")


@contextmanager
def logged_call(kind, **details):
    call_id = uuid4().hex
    started = monotonic()
    event(call_id, "start", kind=kind, **details)
    try:
        yield call_id
    except BaseException as exc:
        event(call_id, "error", elapsed_seconds=round(monotonic() - started, 3),
              error_type=type(exc).__name__, error=str(exc))
        raise
    else:
        event(call_id, "end", elapsed_seconds=round(monotonic() - started, 3))
