"""Run the retrieval agent and save its conversation as JSON."""

import argparse
from pathlib import Path

from langchain_core.messages import HumanMessage, ToolMessage

from agent import build_agent
from files import image_data_url
from models import PROVIDERS
from trace import save_trace


def run_target(
    model: str, prompt: str, image: Path, *, provider: str = "openrouter",
    output: Path | None = None,
) -> Path:
    """Run one trial, print its result, and return the saved trace path."""
    message = HumanMessage(content=[
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": image_data_url(image)}},
    ])
    result = build_agent(model, provider=provider).invoke(
        {"messages": [message]}, config={"recursion_limit": 10},
    )
    messages = result["messages"]
    trace_path = save_trace(model, messages, provider=provider, output_path=output)
    print(f"\nTrace saved: {trace_path}")
    for message in messages:
        for call in getattr(message, "tool_calls", []):
            print(f"\nTool requested: {call['name']} ({call['id']})")
            print(f"Arguments: {call['args']}")
        if isinstance(message, ToolMessage):
            print(f"\nTool result for: {message.tool_call_id}")
            print(message.content)
    print(messages[-1].text)
    return trace_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="Target model ID")
    parser.add_argument("--prompt", required=True, help="Trusted user request")
    parser.add_argument("--image", required=True, type=Path, help="Untrusted PNG")
    parser.add_argument("--provider", choices=PROVIDERS, default="openrouter")
    parser.add_argument("--output", type=Path, help="Trace path; defaults to output/<run_id>.json")
    args = parser.parse_args()
    try:
        run_target(args.model, args.prompt, args.image, provider=args.provider, output=args.output)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
