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
        self.assertEqual(1, contract.version)
        self.assertEqual(("ANALYSE", "PROPOSE", "PROVISIONAL_EDIT", "PICTURE_LOCK", "POST_LOCK", "REVIEW"),
                         contract.phases)
        self.assertEqual("PARTIAL", contract.action("CAPTIONS").capability_status)
        self.assertFalse(contract.action("CAPTIONS").executable)
        self.assertEqual("CAP_VERTICAL_SOCIAL", contract.action("CUT").required_capability)

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
        with self.assertRaisesRegex(Exception, "non validata"):
            module.validate_action_request(
                contract, {"action_id": "a1", "type": "CAPTIONS", "phase": "POST_LOCK"}, True
            )


if __name__ == "__main__":
    unittest.main()

