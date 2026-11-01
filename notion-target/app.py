"""ASGI entry point. Start with uvicorn app:app or python serve.py."""

from notion_target.api import create_app

app = create_app()
