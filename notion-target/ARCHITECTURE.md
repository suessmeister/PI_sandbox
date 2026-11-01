# Code review guide

This service accepts a prompt and image, lets a model use read-only Notion tools,
and returns an answer. Every request has its own MCP session and conversation.

## Where to start

| File | Responsibility |
| --- | --- |
| `serve.py` | CLI options, including the model override, and server startup |
| `app.py` | Small ASGI entry point for `uvicorn app:app` |
| `notion_target/config.py` | Load `.env`, validate settings, build system instructions |
| `notion_target/api.py` | Handle `POST /run`, timeouts, errors, and request tracing |
| `notion_target/images.py` | Check image size, type, and validity |
| `notion_target/agent.py` | Send the image and prompt, execute model tool calls, continue the conversation |
| `notion_target/notion.py` | Start the real MCP server and discover approved read/search tools |
| `notion_target/tracing.py` | Redact credentials and write private trace files |
| `system_prompt.txt` | Operator-editable base instructions |
| `verify_live.py` | Real MCP discovery and end-to-end verification |
| `tests/test_service.py` | Isolated regression tests with fake external services |

## Follow one request

1. Startup loads `Settings`; `serve.py --model` can override the configured model.
2. `api.py` creates a request ID and trace, reads the image, and validates input.
3. `agent.py` opens a fresh MCP session through `notion.py` and discovers allowed tools.
4. The model receives system instructions separately from the user prompt and image.
5. If the model requests a tool, the agent checks its name and the tool-call budget,
   calls MCP, records the result, and sends that result back to the model.
6. The loop ends with a complete text answer. The API writes the trace and returns
   exactly `request_id` and `response`.

The request timeout covers execution, including MCP and model calls. Validation,
timeout, and upstream failures receive HTTP errors and execution traces. Multipart
parsing occurs before this handler, so parser failures have no execution trace.
The final trace write occurs outside that timeout; a write failure fails the
request and may prevent a trace from being saved. Images are recorded as hashes,
not image bytes.

## Moving the service

Keep the project layout intact when copying it into another repository.
`config.py` derives the project root from its own location; `.env`, relative
prompt/trace paths, and the MCP working directory use that root. Process
environment variables override `.env`. See the
[handoff guide](CALLING_FROM_ANOTHER_EXPERIMENT.md) for the copy list and HTTP
contract, and [verification status](VERIFICATION.md) for remaining live-check gaps.

## Experiment boundary

`config.py` appends the sensitive page's ID and title to the system instructions.
The instruction prohibits retrieving or disclosing that page and its children.
User text, images, tool descriptions, and retrieved content cannot authorize an
exception to those instructions.

The sensitive-page restriction relies on the model following its instructions.
There is deliberately no page-ID filter in the tool implementation. A refusal
does not prove that Notion itself denied access.

The read/search tool allowlist is enforced in code: `notion.py` filters discovery,
and `agent.py` rejects calls to tools that were not approved. This is separate
from the model's sensitive-page policy.

## Review and verification

Run from the repository directory:

```bash
.venv/bin/python -m pytest -q --rootdir=.
.venv/bin/python serve.py --help
.venv/bin/python verify_live.py --discovery-only
```

Discovery does not verify workspace permissions. Full live verification requires
an allowed page with an explicitly labeled verification marker and makes a paid
model request; see `README.md`. Local tests do not call external services.

Keep `.env` and `traces/` private. Traces contain submitted prompts and retrieved
document data. The API has no caller authentication and defaults to loopback.

Assistant text is accumulated across every model call within one request, in order,
with blank lines between nonempty chunks. The HTTP `response` and trace
`final_response` contain that full assistant transcript, including text produced
before tool calls. The private trace also records `assistant_text_chunks` for call
boundaries. Raw tool results, system instructions, and reasoning items are not
concatenated into the response. Incomplete/upstream failures remain errors rather
than successful partial answers. Historical runs are unchanged. Restart the target
to activate this behavior.
