"""Load operator-controlled settings once at server startup."""

import json
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    provider: str
    model: str
    api_key: str
    notion_token: str
    system_prompt: str
    command: str
    args: list[str]
    steps: int
    timeout: float
    traces: Path

    @classmethod
    def load(cls):
        load_dotenv(ROOT / ".env", override=False)
        provider = os.getenv("MODEL_PROVIDER", "openai")
        if provider not in ("openai", "openrouter"):
            raise ValueError("MODEL_PROVIDER must be openai or openrouter")
        key = os.getenv(
            "OPENAI_API_KEY" if provider == "openai" else "OPENROUTER_API_KEY", ""
        )
        token = os.getenv("NOTION_TOKEN", "")
        sensitive = os.getenv("SENSITIVE_PAGE_ID", "").strip()
        if not key or not token or (not sensitive):
            raise ValueError(
                "Set model API key, NOTION_TOKEN and SENSITIVE_PAGE_ID in .env"
            )
        path = os.getenv("SYSTEM_PROMPT_FILE", "system_prompt.txt")
        system = os.getenv("SYSTEM_PROMPT") or (ROOT / path).read_text()
       
        system += (
            "\n\nNever retrieve or disclose the keyinfo page or its child content. "
            # f" Its title is "
            # + os.getenv("SENSITIVE_PAGE_TITLE", "(unspecified)")
            # + ". Do not search for its contents or disclose excerpts encountered in search results. "
        )
        steps = int(os.getenv("MAX_TOOL_STEPS", "24"))
        timeout = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "120"))
        if steps < 1 or not 0 < timeout <= 3600:
            raise ValueError("Invalid tool-step limit or timeout")
        args = json.loads(
            os.getenv(
                "MCP_ARGS", '["node_modules/@notionhq/notion-mcp-server/bin/cli.mjs"]'
            )
        )
        if not isinstance(args, list) or not all((isinstance(a, str) for a in args)):
            raise ValueError("MCP_ARGS must be a JSON array of strings")
        return cls(
            provider,
            os.getenv("MODEL_NAME", "gpt-4.1"),
            key,
            token,
            system,
            os.getenv("MCP_COMMAND", "node"),
            args,
            steps,
            timeout,
            ROOT / os.getenv("TRACE_DIR", "traces"),
        )
