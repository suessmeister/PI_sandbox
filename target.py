"""Send one prompt and image to the independently configured Notion sandbox."""

from pathlib import Path

import httpx

from call_logging import event, logged_call

DEFAULT_TARGET_URL = "http://127.0.0.1:8000/run"


def run_target(prompt: str, image: Path, *, target_url: str = DEFAULT_TARGET_URL,
               timeout: float = 150) -> dict:
    mime = "image/jpeg" if image.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
    with logged_call("target_request", target_url=target_url, timeout_seconds=timeout,
                     request={"prompt": prompt, "image_path": str(image)}) as call_id:
        with image.open("rb") as handle:
            response = httpx.post(target_url, data={"prompt": prompt},
                                  files={"image": (image.name, handle, mime)}, timeout=timeout)
        response.raise_for_status()
        record = response.json()
        if (not isinstance(record, dict) or set(record) != {"request_id", "response"}
                or not all(isinstance(value, str) and value.strip() for value in record.values())):
            raise ValueError("Target must return nonempty request_id and response strings.")
        event(call_id, "response", request_id=record["request_id"], response=record)
        return record
