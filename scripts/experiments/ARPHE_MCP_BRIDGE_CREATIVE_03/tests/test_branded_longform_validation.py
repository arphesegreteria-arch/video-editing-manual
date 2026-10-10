from __future__ import annotations
import json
from pathlib import Path
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))
from scripts.validate_branded_longform import validate_branded_longform_ledger  # noqa: E402


class BrandedLongformValidationTests(unittest.TestCase):
    def test_requires_disabled_default_and_separate_workstation_gates(self):
        payload = {
            "schema_version": 1, "workflow_id": "BRANDED_LONGFORM_EDITORIAL",
            "capability_default": False, "automated_evidence": {"result": "PASS"},
            "workstation_gates": {name: {"workstation_id": name, "status": "PENDING"}
                                  for name in ("PC_PERSONALE", "PC_SEGRETERIA")},
        }
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "ledger.json"; path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual([], validate_branded_longform_ledger(path))
            payload["capability_default"] = True; path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertTrue(validate_branded_longform_ledger(path))
