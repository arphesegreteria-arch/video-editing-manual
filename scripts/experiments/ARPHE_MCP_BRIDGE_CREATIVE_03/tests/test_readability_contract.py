from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.readability_contract import (  # noqa: E402
    ReadabilityContractError,
    contract_digest,
    load_readability_contract,
    verify_graphic_kit_checkout,
)


CONTRACT_PATH = ROOT / "review_readability_contract.json"


class ReadabilityContractTests(unittest.TestCase):
    def write_contract(self, root: Path, payload: dict) -> Path:
        path = root / "contract.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_loads_the_pinned_contract_without_graphic_kit_checkout(self):
        policy = load_readability_contract(CONTRACT_PATH)

        self.assertEqual(policy.policy_version, "ARPHE_VIDEO_READABILITY_V1")
        self.assertEqual(policy.graphic_kit_commit, "a404fa869dc5c49c89548ba06b0a7a51f82aa243")
        self.assertEqual(
            contract_digest(policy),
            "68b240d727e23707b4b64e5da069c47519e166a25bce94e33cc3de5ae005c0fe",
        )
        self.assertEqual(policy.canvases["story_reel_1080x1920"]["width"], 1080)

    def test_missing_contract_is_a_stable_contract_mismatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            missing = Path(temporary) / "missing.json"
            with self.assertRaisesRegex(ReadabilityContractError, "CONTRACT_MISMATCH"):
                load_readability_contract(missing)

    def test_rejects_malformed_schema_unknown_canvas_and_policy_drift(self):
        source = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        mutations = []

        unknown_key = copy.deepcopy(source)
        unknown_key["unexpected"] = True
        mutations.append(unknown_key)

        unknown_canvas = copy.deepcopy(source)
        unknown_canvas["policy"]["canvases"]["other_canvas"] = (
            unknown_canvas["policy"]["canvases"].pop("story_reel_1080x1920")
        )
        mutations.append(unknown_canvas)

        changed_value = copy.deepcopy(source)
        changed_value["policy"]["reading"]["words_per_second"] = 5.0
        mutations.append(changed_value)

        wrong_digest = copy.deepcopy(source)
        wrong_digest["graphic_kit_policy_digest"] = "0" * 64
        mutations.append(wrong_digest)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index, payload in enumerate(mutations):
                with self.subTest(index=index), self.assertRaisesRegex(
                    ReadabilityContractError, "CONTRACT_MISMATCH"
                ):
                    load_readability_contract(self.write_contract(root, payload))

    def test_checkout_verification_compares_exact_head_and_policy_digest(self):
        policy = load_readability_contract(CONTRACT_PATH)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "tokens").mkdir()
            (root / "tokens" / "video-readability.json").write_text(
                json.dumps(policy.policy), encoding="utf-8"
            )
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Contract Test"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "contract@example.invalid"], cwd=root, check=True)
            subprocess.run(["git", "add", "tokens/video-readability.json"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "fixture"], cwd=root, check=True)
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
            ).stdout.strip()

            errors = verify_graphic_kit_checkout(policy, root)
            self.assertIn(f"commit atteso {policy.graphic_kit_commit}, trovato {head}", errors)
            self.assertFalse(any("digest" in error for error in errors), errors)

            payload = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
            payload["graphic_kit_commit"] = head
            matched = load_readability_contract(self.write_contract(root, payload))
            self.assertEqual(verify_graphic_kit_checkout(matched, root), [])

            kit_policy = json.loads((root / "tokens" / "video-readability.json").read_text())
            kit_policy["reading"]["minimum_seconds"] = 4
            (root / "tokens" / "video-readability.json").write_text(
                json.dumps(kit_policy), encoding="utf-8"
            )
            self.assertTrue(
                any("digest" in error for error in verify_graphic_kit_checkout(matched, root))
            )


if __name__ == "__main__":
    unittest.main()
