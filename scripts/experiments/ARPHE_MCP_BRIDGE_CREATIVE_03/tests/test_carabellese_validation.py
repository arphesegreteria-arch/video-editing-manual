from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "scripts"))

from validate_carabellese_cleanup import validate_carabellese_cleanup_ledger  # noqa: E402


LEDGER = REPO / "validation" / "carabellese-cleanup-ledger.json"


class CarabelleseValidationTests(unittest.TestCase):
    def validate(self, payload):
        with tempfile.TemporaryDirectory() as raw_root:
            path = Path(raw_root) / "ledger.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            return validate_carabellese_cleanup_ledger(path)

    def test_repository_ledger_is_valid_and_both_live_gates_remain_pending(self):
        payload = json.loads(LEDGER.read_text(encoding="utf-8"))
        self.assertEqual([], validate_carabellese_cleanup_ledger(LEDGER))
        self.assertEqual({"PENDING"}, {gate["status"]
                                      for gate in payload["workstation_gates"].values()})
        self.assertFalse(payload["capability_default"])

    def test_missing_check_enabled_default_and_private_content_are_rejected(self):
        base = json.loads(LEDGER.read_text(encoding="utf-8"))
        mutations = []
        missing = copy.deepcopy(base); missing["workstation_gates"]["PC_PERSONALE"]["checks"].pop("checkpoint_restore"); mutations.append(missing)
        enabled = copy.deepcopy(base); enabled["capability_default"] = True; mutations.append(enabled)
        private = copy.deepcopy(base); private["automated_evidence"]["limitations"].append("C:/Users/alessio/private.mov"); mutations.append(private)
        for payload in mutations:
            with self.subTest(payload=payload):
                self.assertTrue(self.validate(payload))

    def test_one_pc_cannot_validate_the_other(self):
        payload = json.loads(LEDGER.read_text(encoding="utf-8"))
        gate = payload["workstation_gates"]["PC_SEGRETERIA"]
        gate["evidence"] = [{"evidence_id": "wrong-machine", "workstation_id": "PC_PERSONALE",
            "observed_at": "2026-10-09T17:00:00+02:00", "result": "PASS",
            "checks": sorted(gate["checks"]), "limitations": ["synthetic"]}]
        self.assertTrue(any("another workstation" in error for error in self.validate(payload)))


if __name__ == "__main__":
    unittest.main()
