# Verification status

Updated on 2026-10-29.

## Current local checks

- Repeated on 2026-10-29 with Python 3.12.15 and Node.js v22.20.0.
- All six isolated regression tests passed using `python -m pytest -q --rootdir=.`. One upstream Starlette/httpx deprecation warning remains. The explicit root keeps pytest's cache in this project when it is nested inside another repository.
- `python serve.py --help` works.
- ASGI import and CLI model override wiring passed a local check with server startup mocked; the selected model and port reached the startup configuration.
- `python verify_live.py --discovery-only` initialized the real official Notion MCP server and discovered nine allowlisted read/search tools. This check makes no Notion API calls and does not prove workspace access.
- All four Markdown guides were reviewed against the source. Setup/start examples now use portable paths, and the caller guide includes a transfer manifest, request limits, and error behavior.
- Paid model requests and authenticated page retrieval were not repeated in this review or after the refactor. The earlier live results below describe the pre-refactor code; a complete successful live verifier run remains outstanding.

## Earlier live checks (previously recorded; not repeated in this review)

- A real OpenAI `gpt-5` request through `/run` recognized a red PNG.
- After granting the integration page access, the app successfully searched for and retrieved `Office Information`, including its opening time and Wi-Fi name. The model also recognized the red image. The automated verifier's marker assertion failed because it requested a "verification marker" and the page contained ordinary office information rather than an explicitly labeled marker. Retrieval itself succeeded; the complete verifier was not recorded as passing.
- A direct request to read the configured sensitive page returned HTTP 200 with a refusal and zero tool calls. Request ID: `191eb0d3-d658-4ce5-a9d5-ba88c5b19224`.
- That refusal demonstrates model compliance for one request. It does not prove resistance to every prompt or verify the integration's underlying read access to the sensitive page. No direct sensitive-page permission check was performed.

## Repeat the checks

From the repository directory:

```bash
.venv/bin/python -m pytest -q --rootdir=.
.venv/bin/python serve.py --help
.venv/bin/python verify_live.py --discovery-only
```

For full live verification, place an explicit line such as `Verification marker: OFFICE-CHECK-123` in an allowed page, then run:

```bash
.venv/bin/python verify_live.py \
  --page-title 'Office Information' \
  --expect 'OFFICE-CHECK-123'
```

This makes a paid model request and authenticates to Notion. The expected marker is checked locally and is not sent to the model in the request prompt.
