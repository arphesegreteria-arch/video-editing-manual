"""Command-line entry point for the visible Windows agent."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


if __package__ in {None, ""}:
    # Direct invocation adds only this script's directory to sys.path.  Add the
    # verified repository root, not a user-controlled or current directory.
    _repository_root = Path(__file__).resolve().parents[2]
    if not (_repository_root / "scripts" / "remote_agent").is_dir():
        raise RuntimeError("remote agent package root is unavailable")
    sys.path.insert(0, str(_repository_root))

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
