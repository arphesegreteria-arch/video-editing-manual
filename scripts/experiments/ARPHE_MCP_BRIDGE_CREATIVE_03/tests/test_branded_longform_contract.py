from __future__ import annotations

import importlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CONTRACT = ROOT / "branded_longform_contract.json"


class BrandedLongformContractTests(unittest.TestCase):
    def test_profiles_are_isolated_and_pending_kit_cannot_apply_graphics(self):
        self.assertIsNotNone(importlib.util.find_spec("bridge.branded_longform_contract"))
        module = importlib.import_module("bridge.branded_longform_contract")
        contract = module.load_branded_longform_contract(CONTRACT)
        self.assertEqual("BRANDED_LONGFORM_EDITORIAL", contract.workflow_id)
        self.assertEqual("READY", contract.profile("ARPHE_LONGFORM_EDITORIAL").kit_status)
        carabellese = contract.profile("CARABELLESE_LONGFORM_EDITORIAL")
        self.assertEqual("PENDING", carabellese.kit_status)
        self.assertFalse(carabellese.allows_operation("GRAPHIC"))

    def test_loader_rejects_unknown_top_level_key_and_duplicate_profile(self):
        module = importlib.import_module("bridge.branded_longform_contract")
        payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            bad = root / "bad.json"
            bad.write_text(json.dumps({**payload, "surprise": True}), encoding="utf-8")
            with self.assertRaisesRegex(Exception, "sconosciuti"):
                module.load_branded_longform_contract(bad)
            duplicate = dict(payload)
            duplicate["profiles"] = [*payload["profiles"], dict(payload["profiles"][0])]
            duplicate_path = root / "duplicate.json"
            duplicate_path.write_text(json.dumps(duplicate), encoding="utf-8")
            with self.assertRaisesRegex(Exception, "duplicato"):
                module.load_branded_longform_contract(duplicate_path)

    def test_config_keeps_branded_longform_state_workstation_local(self):
        from bridge.config import load_config
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            config_path = root / "config.json"
            config_path.write_text(json.dumps({
                "runtime_id": "ARPHE_MCP_BRIDGE_CREATIVE_03",
                "workstation_id": "PC_PERSONALE",
                "state_path": str(root / "state" / "creative.json"),
                "feature_flags": {},
            }), encoding="utf-8")
            config = load_config(config_path)
        self.assertEqual(root / "state" / "branded_longform_jobs.json", config.branded_longform_jobs_path)
        self.assertEqual(root / "state" / "branded_longform_journal.jsonl", config.branded_longform_journal_path)


if __name__ == "__main__":
    unittest.main()
