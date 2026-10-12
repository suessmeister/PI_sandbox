"""Shared model configuration for the target and judge."""

import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.language_models import BaseChatModel
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

ROOT = Path(__file__).resolve().parent
PROVIDERS = ("openai", "openrouter", "ollama")


def build_model(model_name: str, provider: str, *, num_ctx: int = 4096) -> BaseChatModel:
    """Load local credentials and construct the selected provider's model."""
    if provider not in PROVIDERS:
        raise ValueError(f"Unsupported provider: {provider}")
    load_dotenv(ROOT / ".env", override=False)
    if provider == "ollama":
        return ChatOllama(
            model=model_name, base_url="http://localhost:11434", num_ctx=num_ctx,
        )

    key_name = "OPENROUTER_API_KEY" if provider == "openrouter" else "OPENAI_API_KEY"
    api_key = os.getenv(key_name, "").strip()
    if not api_key:
        raise ValueError(f"Set {key_name} in .env or your environment.")
    options = {}
    if provider == "openrouter":
        options = {
            "base_url": "https://openrouter.ai/api/v1",
            "extra_body": {"provider": {"require_parameters": True, "sort": "price"}},
        }
    return ChatOpenAI(
        model=model_name, api_key=api_key, timeout=60, max_retries=5, **options,
    )
