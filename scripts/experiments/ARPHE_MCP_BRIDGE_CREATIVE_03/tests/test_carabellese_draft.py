from __future__ import annotations

from fractions import Fraction
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.carabellese_draft import draft_cuts  # noqa: E402
from bridge.safety import ValidationError  # noqa: E402


class DraftCutTests(unittest.TestCase):
    def test_quantizes_and_keeps_distinct_ranges(self):
        cuts = draft_cuts((
            {"candidate_id": "P002", "start_seconds": 2.01, "end_seconds": 2.04},
            {"candidate_id": "P001", "start_seconds": 1.00, "end_seconds": 1.01},
        ), Fraction(30), 300)
        self.assertEqual(["P001", "P002"], [cut["candidate_id"] for cut in cuts])
        self.assertEqual((30, 31), (cuts[0]["start_frame"], cuts[0]["end_frame_exclusive"]))

    def test_rejects_overlap_and_bounds(self):
        with self.assertRaisesRegex(ValidationError, "sovrapposti"):
            draft_cuts((
                {"candidate_id": "P001", "start_seconds": 1.0, "end_seconds": 2.0},
                {"candidate_id": "P002", "start_seconds": 1.5, "end_seconds": 2.5},
            ), Fraction(30), 300)
        with self.assertRaisesRegex(ValidationError, "fuori"):
            draft_cuts(({"candidate_id": "P003", "start_seconds": 9.9, "end_seconds": 10.1},),
                       Fraction(30), 300)


if __name__ == "__main__":
    unittest.main()
