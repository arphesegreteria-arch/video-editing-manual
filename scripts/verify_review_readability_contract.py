from __future__ import annotations

import argparse
from pathlib import Path
import sys


CREATIVE_ROOT = (
    Path(__file__).resolve().parent
    / "experiments"
    / "ARPHE_MCP_BRIDGE_CREATIVE_03"
)
sys.path.insert(0, str(CREATIVE_ROOT))

from bridge.readability_contract import (  # noqa: E402
    load_readability_contract,
    verify_graphic_kit_checkout,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the pinned Graphic Kit readability contract")
    parser.add_argument("--graphic-kit", required=True, type=Path)
    args = parser.parse_args()
    contract = load_readability_contract(CREATIVE_ROOT / "review_readability_contract.json")
    errors = verify_graphic_kit_checkout(contract, args.graphic_kit.resolve())
    if errors:
        print("REVIEW READABILITY CONTRACT: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print("REVIEW READABILITY CONTRACT: PASS")
    print(f"policy_version={contract.policy_version}")
    print(f"graphic_kit_commit={contract.graphic_kit_commit}")
    print(f"graphic_kit_policy_digest={contract.graphic_kit_policy_digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
