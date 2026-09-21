# -*- coding: utf-8 -*-
"""stdio entry point for ARPHE_MCP_BRIDGE_CREATIVE_03."""

from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from bridge.server import run


if __name__ == "__main__":
    run()
