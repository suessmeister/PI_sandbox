"""Check that a configured model provider responds."""

import argparse

from models import PROVIDERS, build_model


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="Model ID")
    parser.add_argument("--provider", choices=PROVIDERS, default="openai")
    args = parser.parse_args()
    try:
        response = build_model(args.model, args.provider).invoke(
            "Reply with exactly: connection successful"
        )
    except ValueError as exc:
        parser.exit(1, f"Error: {exc}\n")
    print(f"Model: {args.model}")
    print(response.text)


if __name__ == "__main__":
    main()
