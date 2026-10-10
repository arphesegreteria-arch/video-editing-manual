from __future__ import annotations
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class Timeline:
    def GetName(self): return "Original_EDITORIAL"


class BrandedLongformGraphicsTests(unittest.TestCase):
    def test_arphe_proposal_is_mapped_to_verified_graphic(self):
        from bridge.branded_longform_graphics import apply_editorial_graphic
        job = SimpleNamespace(editorial_timeline="Original_EDITORIAL", profile_id="ARPHE_LONGFORM_EDITORIAL")
        proposal = {"proposal_id": "P001", "kind": "PROGRESSIVE_LIST", "start_frame": 30,
                    "end_frame": 90, "rationale": "Tre elementi", "executable": True,
                    "operator_modification": "Uno\nDue\nTre"}
        cfg = SimpleNamespace(palette={"cream": "#EFE3CF"})
        with patch("bridge.branded_longform_graphics.create_longform_overlay_composition",
                   return_value=(object(), object())), \
             patch("bridge.branded_longform_graphics.build_graphic_graph",
                   return_value={"text_readback": True, "font": "Satoshi"}) as build:
            result = apply_editorial_graphic(object(), Timeline(), cfg, job, proposal)
        self.assertTrue(result["ok"])
        self.assertEqual("P001", result["proposal_id"])
        self.assertIn("Uno", build.call_args.args[1]["text"])

    def test_pending_kit_never_executes_graphic(self):
        from bridge.branded_longform_graphics import apply_editorial_graphic
        job = SimpleNamespace(editorial_timeline="Original_EDITORIAL", profile_id="CARABELLESE_LONGFORM_EDITORIAL")
        with self.assertRaisesRegex(Exception, "pending"):
            apply_editorial_graphic(object(), Timeline(), SimpleNamespace(), job,
                                    {"proposal_id": "P", "executable": False})
