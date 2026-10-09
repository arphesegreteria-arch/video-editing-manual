"""Local, checkpointed long-form transcription to ARPHE_TRANSCRIPT_V1 JSON."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


BRIDGE_ROOT = Path(__file__).resolve().parent / "ARPHE_MCP_BRIDGE_CREATIVE_03"
if str(BRIDGE_ROOT) not in sys.path:
    sys.path.insert(0, str(BRIDGE_ROOT))

from bridge.transcription_worker import file_sha256, transcribe_checkpointed  # noqa: E402


def transcribe(source: Path, output: Path, model_name: str, language: str) -> None:
    selected = source.expanduser().resolve(strict=True)
    transcribe_checkpointed(
        selected, output, model_name, language,
        expected_source_fingerprint=file_sha256(selected),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--model", default="small")
    parser.add_argument("--language", default="it")
    args = parser.parse_args()
    transcribe(args.source, args.output, args.model, args.language)


if __name__ == "__main__":
    main()
