from __future__ import annotations

import importlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CONTRACT = ROOT / "vertical_social_contract.json"


class VerticalSocialContractTests(unittest.TestCase):
    def _module(self):
        self.assertIsNotNone(
            importlib.util.find_spec("bridge.vertical_social_contract"),
            "bridge.vertical_social_contract must exist",
        )
        return importlib.import_module("bridge.vertical_social_contract")

    def _load(self):
        module = self._module()
        return module, module.load_vertical_social_contract(CONTRACT)

    def test_shipped_contract_defines_vertical_social_actions_and_phases(self):
        _, contract = self._load()

        self.assertEqual("ARPHE_VERTICAL_SOCIAL", contract.workflow_id)
        self.assertEqual(5, contract.version)
        self.assertEqual(("ANALYSE", "PROPOSE", "PROVISIONAL_EDIT", "PICTURE_LOCK", "POST_LOCK", "REVIEW"),
                         contract.phases)
        self.assertEqual("VALIDATED", contract.action("CAPTIONS").capability_status)
        self.assertTrue(contract.action("CAPTIONS").executable)
        self.assertEqual("CAP_VERTICAL_SOCIAL", contract.action("CUT").required_capability)
        self.assertTrue(contract.action("CUT").executable)
        self.assertTrue(contract.action("REFRAME").executable)
        self.assertTrue(contract.action("B_ROLL_PROVIDED").executable)
        self.assertTrue(contract.action("MUSIC_DUCK").executable)
        self.assertTrue(contract.action("GRAPHIC").executable)
        self.assertTrue(contract.action("CTA").executable)
        self.assertFalse(contract.action("B_ROLL_GENERATED").executable)

    def test_loader_rejects_unknown_key_and_duplicate_action(self):
        module, _ = self._load()
        payload = json.loads(CONTRACT.read_text(encoding="utf-8"))

        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            unknown = root / "unknown.json"
            unknown.write_text(json.dumps({**payload, "surprise": True}), encoding="utf-8")
            with self.assertRaisesRegex(Exception, "campi sconosciuti"):
                module.load_vertical_social_contract(unknown)

            duplicate = dict(payload)
            duplicate["actions"] = [*payload["actions"], dict(payload["actions"][0])]
            duplicate_path = root / "duplicate.json"
            duplicate_path.write_text(json.dumps(duplicate), encoding="utf-8")
            with self.assertRaisesRegex(Exception, "duplicata"):
                module.load_vertical_social_contract(duplicate_path)

    def test_validator_rejects_unknown_actions_dependencies_and_early_captions(self):
        module, contract = self._load()

        with self.assertRaisesRegex(Exception, "sconosciuta"):
            module.validate_action_request(
                contract, {"action_id": "a1", "type": "UNKNOWN", "phase": "PROVISIONAL_EDIT"}, False
            )
        with self.assertRaisesRegex(Exception, "dipendenza"):
            module.validate_action_request(
                contract, {"action_id": "a1", "type": "CUT", "phase": "PROVISIONAL_EDIT",
                           "depends_on": ["missing"]},
                False,
                known_action_ids=set(),
            )
        with self.assertRaisesRegex(Exception, "picture lock"):
            module.validate_action_request(
                contract, {"action_id": "a1", "type": "CAPTIONS", "phase": "POST_LOCK"}, False
            )
        caption = module.validate_action_request(
            contract, {"action_id": "a1", "type": "CAPTIONS", "phase": "POST_LOCK"}, True
        )
        self.assertTrue(caption.executable)

    def test_config_keeps_vertical_social_state_local_and_disabled(self):
        from bridge.config import load_config

        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            path = root / "creative.json"
            path.write_text(json.dumps({
                "runtime_id": "ARPHE_MCP_BRIDGE_CREATIVE_03",
                "workstation_id": "PC_PERSONALE",
                "state_path": str(root / "state" / "creative_state.json"),
                "feature_flags": {},
            }), encoding="utf-8")
            config = load_config(path)

        self.assertFalse(config.flags["CAP_VERTICAL_SOCIAL"])
        self.assertEqual(root / "state" / "vertical_social_plans.json", config.vertical_social_plans_path)
        self.assertEqual(root / "state" / "vertical_social_journal.jsonl", config.vertical_social_journal_path)


if __name__ == "__main__":
    unittest.main()
