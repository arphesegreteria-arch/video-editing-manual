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


CONTRACT = ROOT / "carabellese_cleanup_contract.json"
PREFERENCES = ROOT / "carabellese_preferences.json"


class CarabelleseContractTests(unittest.TestCase):
    def _module(self):
        self.assertIsNotNone(
            importlib.util.find_spec("bridge.carabellese_contract"),
            "bridge.carabellese_contract must exist",
        )
        return importlib.import_module("bridge.carabellese_contract")

    def test_contract_pins_workflow_format_pause_bands_and_review_policy(self):
        module = self._module()
        contract = module.load_carabellese_contract(CONTRACT)

        self.assertEqual("CARABELLESE_YOUTUBE_CLEANUP", contract.workflow_id)
        self.assertEqual((1920, 1080), contract.resolution)
        self.assertEqual("source", contract.frame_rate_mode)
        self.assertEqual(0.7, contract.retain_below_seconds)
        self.assertEqual(1.5, contract.contextual_through_seconds)
        self.assertEqual(0.6, contract.residual_min_seconds)
        self.assertEqual(0.8, contract.residual_max_seconds)
        self.assertTrue(contract.cue_review_required)
        self.assertEqual("ARPHE_TRANSCRIPT_V1", contract.transcript_schema)

    def test_contract_loader_rejects_unknown_keys_and_fingerprint_is_canonical(self):
        module = self._module()
        payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            bad = Path(directory) / "bad.json"
            bad.write_text(json.dumps({**payload, "unexpected": True}), encoding="utf-8")
            with self.assertRaisesRegex(Exception, "campi sconosciuti"):
                module.load_carabellese_contract(bad)

            reordered = Path(directory) / "reordered.json"
            reordered.write_text(json.dumps(dict(reversed(list(payload.items())))), encoding="utf-8")
            self.assertEqual(
                module.carabellese_contract_fingerprint(
                    module.load_carabellese_contract(CONTRACT)
                ),
                module.carabellese_contract_fingerprint(
                    module.load_carabellese_contract(reordered)
                ),
            )

    def test_preferences_are_strictly_isolated_to_carabellese(self):
        module = self._module()
        preferences = module.load_carabellese_preferences(PREFERENCES)
        self.assertEqual("CARABELLESE_YOUTUBE_CLEANUP", preferences.workflow_id)
        self.assertEqual(0.6, preferences.residual_pause_seconds)
        self.assertGreaterEqual(preferences.minimum_learning_samples, 1)

        payload = json.loads(PREFERENCES.read_text(encoding="utf-8"))
        payload["workflow_id"] = "ARPHE_PODCAST_REELS_CTA"
        with tempfile.TemporaryDirectory() as directory:
            wrong = Path(directory) / "wrong.json"
            wrong.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(Exception, "workflow_id"):
                module.load_carabellese_preferences(wrong)

    def test_config_defaults_carabellese_state_beside_workstation_state(self):
        from bridge.config import load_config

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = root / "creative.json"
            config_path.write_text(json.dumps({
                "runtime_id": "ARPHE_MCP_BRIDGE_CREATIVE_03",
                "workstation_id": "PC_PERSONALE",
                "state_path": str(root / "state" / "creative_state.json"),
                "feature_flags": {},
            }), encoding="utf-8")

            config = load_config(config_path)

        expected = root / "state"
        self.assertEqual(expected / "carabellese_jobs.json", config.carabellese_jobs_path)
        self.assertEqual(expected / "carabellese_journal.jsonl", config.carabellese_journal_path)
        self.assertEqual(expected / "carabellese_profile_overlay.json",
                         config.carabellese_profile_overlay_path)
        self.assertEqual(expected / "carabellese_profile_proposals.json",
                         config.carabellese_profile_proposals_path)
        self.assertEqual(expected / "carabellese-checkpoints", config.carabellese_checkpoint_root)


if __name__ == "__main__":
    unittest.main()
