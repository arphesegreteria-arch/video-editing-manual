from __future__ import annotations
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

class ApplicationPlanTests(unittest.TestCase):
    def test_application_plan_only_contains_approved_proposals(self):
        from bridge.branded_longform_application_plan import build_application_plan
        plan = build_application_plan(
            {"P001": {"kind": "PROGRESSIVE_LIST"}, "P002": {"kind": "NO_OVERLAY"}},
            ("P001",),
        )
        self.assertEqual(("P001",), tuple(item["proposal_id"] for item in plan))
