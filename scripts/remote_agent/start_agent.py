"""Command-line entry point for the visible Windows agent."""

from __future__ import annotations

import argparse
from pathlib import Path

from scripts.remote_agent.app import build_application


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ARPHE Remote Agent")
    parser.add_argument("--config", type=Path, required=True, help="Path to local config.json")
    parser.add_argument("--source-commit", default="unknown")
    args = parser.parse_args(argv)
    application = build_application(args.config, source_commit=args.source_commit)
    application.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
