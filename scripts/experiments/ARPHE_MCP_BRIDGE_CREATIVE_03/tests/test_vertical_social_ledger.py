from __future__ import annotations
import json
from pathlib import Path
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))
from scripts.validate_vertical_social import validate_vertical_social_ledger  # noqa: E402


class VerticalSocialLedgerTests(unittest.TestCase):
    def test_requires_isolated_pending_gates_and_disabled_default(self):
        payload = {
            "schema_version": 1, "workflow_id": "ARPHE_VERTICAL_SOCIAL",
            "capability_default": False,
            "automated_evidence": {"result": "PASS", "test_results": ["targeted tests passed"]},
            "workstation_gates": {
                key: {"workstation_id": key, "status": "PENDING", "checks": {"native_gate": "PENDING"}, "evidence": []}
                for key in ("PC_PERSONALE", "PC_SEGRETERIA")
            },
        }
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "ledger.json"; path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual([], validate_vertical_social_ledger(path))
            payload["capability_default"] = True; path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertTrue(validate_vertical_social_ledger(path))


if __name__ == "__main__":
    unittest.main()

