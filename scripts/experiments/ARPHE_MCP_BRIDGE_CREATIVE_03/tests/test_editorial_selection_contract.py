from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.editorial_selection_contract import (  # noqa: E402
    canonical_digest,
    load_preference_profile,
    load_selection_contract,
)
from bridge.safety import ValidationError  # noqa: E402


CONTRACT = ROOT / "editorial_selection_contract.json"
PROFILE = ROOT / "editorial_preferences.json"


class EditorialSelectionContractTests(unittest.TestCase):
    def _write(self, root: Path, name: str, payload: object) -> Path:
        path = root / name
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def _profile(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": 1,
            "profile_version": 1,
            "workflow_id": "ARPHE_PODCAST_REELS_CTA",
            "aggregate_preferences": {},
            "sample_counts": {},
        }
        payload["digest"] = canonical_digest(payload)
        return payload

    def test_shipped_contract_bounds_only_podcast_reel_workflow(self):
        contract = load_selection_contract(CONTRACT)

        self.assertEqual("ARPHE_PODCAST_REELS_CTA", contract.workflow_id)
        self.assertEqual(20, contract.max_candidates)
        self.assertEqual(180.0, contract.max_final_seconds)
        self.assertGreater(contract.cta_duration_seconds, 0)
        self.assertGreater(contract.modified_anchor_window_seconds, 0)
        self.assertIn(contract.marker_color, {"Blue", "Cyan", "Green", "Yellow", "Red", "Pink", "Purple"})

    def test_shipped_profile_is_empty_aggregate_and_self_authenticating(self):
        profile = load_preference_profile(PROFILE)

        self.assertEqual(1, profile.profile_version)
        self.assertEqual({}, profile.aggregate_preferences)
        self.assertEqual({}, profile.sample_counts)
        raw = json.loads(PROFILE.read_text(encoding="utf-8"))
        digest = raw.pop("digest")
        self.assertEqual(digest, canonical_digest(raw))

    def test_contract_rejects_unknown_key_wrong_type_and_schema(self):
        valid = json.loads(CONTRACT.read_text(encoding="utf-8"))
        invalids = []
        unknown = dict(valid, surprise=True)
        invalids.append(unknown)
        wrong_type = dict(valid, max_candidates="20")
        invalids.append(wrong_type)
        wrong_schema = dict(valid, schema_version=2)
        invalids.append(wrong_schema)

        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            for index, payload in enumerate(invalids):
                with self.subTest(index=index), self.assertRaises(ValidationError):
                    load_selection_contract(self._write(root, f"contract-{index}.json", payload))

    def test_profile_rejects_unknown_key_and_tampered_digest(self):
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            unknown = self._profile()
            unknown["surprise"] = True
            tampered = self._profile()
            tampered["digest"] = "0" * 64

            for index, payload in enumerate((unknown, tampered)):
                with self.subTest(index=index), self.assertRaises(ValidationError):
                    load_preference_profile(self._write(root, f"profile-{index}.json", payload))

    def test_profile_rejects_count_without_matching_aggregate(self):
        payload = self._profile()
        payload["sample_counts"] = {"preferred_duration_seconds": 3}
        payload["digest"] = canonical_digest({k: v for k, v in payload.items() if k != "digest"})

        with tempfile.TemporaryDirectory() as raw_root, self.assertRaises(ValidationError):
            load_preference_profile(self._write(Path(raw_root), "profile.json", payload))

    def test_profile_accepts_typed_aggregate_with_matching_count(self):
        payload = self._profile()
        payload["aggregate_preferences"] = {
            "preferred_duration_seconds": {"min": 35.0, "max": 72.0},
            "weak_opening_tags": ["slow_context", "repeated_premise"],
        }
        payload["sample_counts"] = {
            "preferred_duration_seconds": 8,
            "weak_opening_tags": 5,
        }
        payload["digest"] = canonical_digest({k: v for k, v in payload.items() if k != "digest"})

        with tempfile.TemporaryDirectory() as raw_root:
            profile = load_preference_profile(self._write(Path(raw_root), "profile.json", payload))

        self.assertEqual(72.0, profile.aggregate_preferences["preferred_duration_seconds"]["max"])
        self.assertEqual(5, profile.sample_counts["weak_opening_tags"])

    def test_profile_rejects_sensitive_strings_recursively(self):
        forbidden_values = (
            "C:/Users/alessio/Desktop/podcast.mp4",
            "../transcripts/episode.json",
            'ha detto "questa è la frase originale"',
            "editorial_0123456789abcdef",
            "mario.rossi@example.it",
        )

        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            for index, value in enumerate(forbidden_values):
                payload = self._profile()
                payload["aggregate_preferences"] = {"weak_opening_tags": [value]}
                payload["sample_counts"] = {"weak_opening_tags": 1}
                payload["digest"] = canonical_digest({k: v for k, v in payload.items() if k != "digest"})
                with self.subTest(value=value), self.assertRaises(ValidationError):
                    load_preference_profile(self._write(root, f"sensitive-{index}.json", payload))

    def test_canonical_digest_is_order_independent_but_value_sensitive(self):
        first = {"b": [2, 1], "a": {"x": 1}}
        reordered = {"a": {"x": 1}, "b": [2, 1]}
        changed = {"a": {"x": 2}, "b": [2, 1]}

        self.assertEqual(canonical_digest(first), canonical_digest(reordered))
        self.assertNotEqual(canonical_digest(first), canonical_digest(changed))


if __name__ == "__main__":
    unittest.main()
