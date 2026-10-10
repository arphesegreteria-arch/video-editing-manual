from __future__ import annotations
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class BrandedLongformEditorialTests(unittest.TestCase):
    def test_list_gets_card_and_personal_passage_stays_unadorned(self):
        from bridge.branded_longform_editorial import propose_editorial
        proposals = propose_editorial([
            {"class": "EXPLAIN", "items": 3, "start": 1, "end": 4},
            {"class": "PERSONAL", "items": 0, "start": 5, "end": 9},
        ], profile_id="ARPHE_LONGFORM_EDITORIAL")
        self.assertEqual("PROGRESSIVE_LIST", proposals[0].kind)
        self.assertEqual("NO_OVERLAY", proposals[1].kind)

    def test_pending_profile_cannot_propose_graphic(self):
        from bridge.branded_longform_editorial import validate_proposal
        with self.assertRaisesRegex(Exception, "pending"):
            validate_proposal("CARABELLESE_LONGFORM_EDITORIAL", "GRAPHIC")
