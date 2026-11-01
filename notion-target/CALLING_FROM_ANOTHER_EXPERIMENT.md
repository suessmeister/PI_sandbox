# Calling the Notion experiment server

## Handoff to another repository

If the other repository only calls this running service, it needs the HTTP example
below and the server URL. It does not need to copy the service code or credentials.

To move the service itself, copy these files together into a dedicated directory
such as `notion-target/` in the destination repository:

- `app.py`, `serve.py`, `verify_live.py`, and the entire `notion_target/` package
  (excluding `__pycache__/`).
- `system_prompt.txt` and `.env.example`.
- `requirements.txt`, `requirements-dev.txt`, `requirements.lock.txt`,
  `package.json`, and `package-lock.json`.
- `tests/` (excluding caches), `.gitignore`, and all four Markdown guides:
  `README.md`, `ARCHITECTURE.md`, `CALLING_FROM_ANOTHER_EXPERIMENT.md`, and
  `VERIFICATION.md`.

Exclude `.env`, `traces/`, `.venv/`, `node_modules/`, `.git/`, and caches. Recreate
the Python environment and install dependencies using [README.md](README.md),
then configure a new local `.env`. Keep the directory layout intact: configuration
paths and the MCP working directory are based on the parent of `notion_target/`.
If merging into an existing repository root, merge dependency and ignore files
instead of overwriting that repository's files.

Run the local checks in [VERIFICATION.md](VERIFICATION.md) after transfer. The
discovery check does not prove workspace access; the full live verifier still
requires an allowed page with a labeled marker.

At the 2026-10-29 review, this source repository had no tracked files. A Git-based
handoff requires adding and committing the intended source files first; local
files alone will not appear in a clone or `git archive`.

## Start the server

Run this command from any directory on the computer where this project is installed:

```bash
/absolute/path/to/notion-target/.venv/bin/python \
  /absolute/path/to/notion-target/serve.py \
  --model gpt-4.1 \
  --host 127.0.0.1 \
  --port 8000
```

Replace both project paths with the service's installation directory. Leave the terminal running. The server loads its credentials and system instructions from the project configuration. Existing process environment variables take precedence over `.env`. Restart the server after changing that configuration.

Replace `gpt-4.1` with the model ID you want to call. The model must support image inputs, the Responses API, and tool calling. The `--model` option overrides `MODEL_NAME` for this run without editing `.env`. Omit it to use the configured model. Stop and restart the server with a new `--model` value to change models. With `MODEL_PROVIDER=openai` in `.env`, requests go to OpenAI.

## Call from another experiment on the same computer

Your experiment can live in any directory. Install `requests` in that experiment's Python environment if needed:

```bash
python -m pip install requests
```

Send a multipart request containing both a prompt and an image:

```python
import requests

with open("/absolute/path/to/image.png", "rb") as image:
    result = requests.post(
        "http://127.0.0.1:8000/run",
        data={"prompt": "Read Office Information and report the opening time."},
        files={"image": ("image.png", image, "image/png")},
        timeout=150,
    )

result.raise_for_status()
print(result.json())
```

Replace the image path and prompt with your experiment inputs. For a JPEG, use `image/jpeg` instead of `image/png`.

The response contains exactly these two fields:

```json
{
  "request_id": "...",
  "response": "..."
}
```

Both `prompt` and `image` are required. Each call starts a fresh model conversation and MCP session. The server retains its configured system instructions, including the sensitive-page prohibition. The caller does not need the OpenAI or Notion credentials.

## Request limits and failures

The prompt must contain non-whitespace text and be at most 100,000 characters.
The image must be a valid PNG or JPEG with a matching multipart MIME type, at most
10 MiB and 20 megapixels. The execution timeout defaults to 120 seconds; set the
client timeout above the configured `REQUEST_TIMEOUT_SECONDS` (the example uses
150 seconds). The default tool-call budget is eight individual calls.

| HTTP status | Meaning |
| --- | --- |
| 400 | Invalid prompt, corrupt image, MIME mismatch, or excessive pixel count |
| 413 | Image exceeds 10 MiB |
| 415 | Unsupported image MIME type |
| 422 | Missing required multipart fields |
| 502 | Model/MCP execution failure, including exceeding the tool-call budget |
| 504 | Execution timeout |
| 500 | Unhandled server failure, such as being unable to write a trace |

Handled errors return a JSON `detail` field; they do not have the success schema
or a response `request_id`. Parser/framework failures may have different details.
The server writes execution traces to `TRACE_DIR/<request_id>.json` (default
`traces/` under the project directory). Traces contain the prompt, system
instructions, tool calls/results, final answer, errors, and timings; images are
represented by a SHA-256 hash, not stored image bytes. Failures before entering
the route have no execution trace, and a trace-write failure can prevent one.
There is no HTTP trace, health, or API-documentation endpoint.

## Call from another computer or cloud machine

Keep the server bound to `127.0.0.1`. The endpoint has no caller authentication, so do not expose it directly to the internet.

If the experiment machine can SSH into the computer running this server, run this command on the experiment machine:

```bash
ssh -N -L 8000:127.0.0.1:8000 YOUR_USERNAME@SERVER_SSH_ADDRESS
```

Replace `YOUR_USERNAME` and `SERVER_SSH_ADDRESS` with the SSH login and reachable address of the computer running the Notion server. SSH access must already be configured. Leave the tunnel running, then use the same Python example and `http://127.0.0.1:8000/run` URL on the experiment machine.

If local port 8000 is already occupied on the experiment machine, forward a different local port:

```bash
ssh -N -L 8001:127.0.0.1:8000 YOUR_USERNAME@SERVER_SSH_ADDRESS
```

Then call `http://127.0.0.1:8001/run` from the experiment.

Assistant text is accumulated across every model call within one request, in order,
with blank lines between nonempty chunks. The HTTP `response` and trace
`final_response` contain that full assistant transcript, including text produced
before tool calls. The private trace also records `assistant_text_chunks` for call
boundaries. Raw tool results, system instructions, and reasoning items are not
concatenated into the response. Incomplete/upstream failures remain errors rather
than successful partial answers. Historical runs are unchanged. Restart the target
to activate this behavior.
