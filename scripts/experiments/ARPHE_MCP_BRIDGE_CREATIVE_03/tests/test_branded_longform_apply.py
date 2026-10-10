from __future__ import annotations
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class BrandedLongformApplyTests(unittest.TestCase):
    def test_only_approved_items_in_a_batch_are_ready_to_apply(self):
        from bridge.branded_longform_apply import approve_proposal_batch
        result = approve_proposal_batch("fingerprint", [
            {"proposal_id": "P001", "decision": "APPROVE"},
            {"proposal_id": "P002", "decision": "REJECT"},
            {"proposal_id": "P003", "decision": "MODIFY", "replacement": "keyword only"},
        ], "ALESSIO")
        self.assertEqual(("P001", "P003"), result.approved_ids)
        self.assertEqual("fingerprint", result.proposal_fingerprint)

    def test_non_technical_role_cannot_approve_batch(self):
        from bridge.branded_longform_apply import approve_proposal_batch
        with self.assertRaisesRegex(Exception, "ruolo"):
            approve_proposal_batch("x", [], "SEGRETERIA")

    def test_duplicate_decision_id_is_rejected(self):
        from bridge.branded_longform_apply import approve_proposal_batch
        with self.assertRaisesRegex(Exception, "duplicata"):
            approve_proposal_batch("x", [
                {"proposal_id": "P001", "decision": "APPROVE"},
                {"proposal_id": "P001", "decision": "MODIFY", "replacement": "Titolo"},
            ], "ALESSIO")
