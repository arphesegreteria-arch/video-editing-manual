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
        self.assertTrue(proposals[0].executable)

    def test_pending_profile_cannot_propose_graphic(self):
        from bridge.branded_longform_editorial import validate_proposal
        with self.assertRaisesRegex(Exception, "pending"):
            validate_proposal("CARABELLESE_LONGFORM_EDITORIAL", "GRAPHIC")

    def test_pending_profile_can_propose_but_not_execute_graphics(self):
        from bridge.branded_longform_editorial import propose_editorial
        proposals = propose_editorial([
            {"class": "EXPLAIN", "items": 3, "start": 1, "end": 4, "fps": 30},
        ], profile_id="CARABELLESE_LONGFORM_EDITORIAL")
        self.assertEqual("PROGRESSIVE_LIST", proposals[0].kind)
        self.assertFalse(proposals[0].executable)
        self.assertEqual("KIT_PENDING", proposals[0].blocked_reason)

    def test_card_fingerprint_changes_with_content(self):
        from bridge.branded_longform_editorial import proposal_card, proposal_fingerprint, propose_editorial
        first = proposal_card("job", propose_editorial([
            {"class": "ARGUE", "start": 1, "end": 2}
        ], "ARPHE_LONGFORM_EDITORIAL"))
        second = proposal_card("job", propose_editorial([
            {"class": "ARGUE", "start": 1, "end": 3}
        ], "ARPHE_LONGFORM_EDITORIAL"))
        self.assertEqual(1, first["card_count"])
        self.assertNotEqual(proposal_fingerprint(first), proposal_fingerprint(second))
