"""Start the Notion target with optional command-line model selection."""

import argparse
from dataclasses import replace

import uvicorn

from notion_target.config import Settings
from notion_target.api import create_app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", help="Model ID; overrides MODEL_NAME for this run")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if args.model is not None and not args.model.strip():
        parser.error("--model must not be empty")
    settings = Settings.load()
    if args.model is not None:
        settings = replace(settings, model=args.model.strip())
    print(f"Starting provider={settings.provider} model={settings.model}", flush=True)
    uvicorn.run(create_app(settings), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
