"""Command-line entry point for the visible Windows agent."""

from __future__ import annotations

import argparse
import getpass
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
from scripts.remote_agent.config import AgentConfig
from scripts.remote_agent.credentials import CredentialStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ARPHE Remote Agent")
    parser.add_argument("--config", type=Path, required=True, help="Path to local config.json")
    parser.add_argument("--source-commit", default="unknown")
    parser.add_argument(
        "--set-github-token",
        action="store_true",
        help="Prompt privately and store the GitHub token in Windows Credential Manager",
    )
    args = parser.parse_args(argv)
    if args.set_github_token:
        token = getpass.getpass("GitHub token (stored in Windows Credential Manager): ").strip()
        if not token:
            raise SystemExit("A non-empty GitHub token is required.")
        CredentialStore(AgentConfig.load(args.config)).set_token(token)
        print("GitHub token stored in Windows Credential Manager.")
        return 0
    application = build_application(args.config, source_commit=args.source_commit)
    application.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
