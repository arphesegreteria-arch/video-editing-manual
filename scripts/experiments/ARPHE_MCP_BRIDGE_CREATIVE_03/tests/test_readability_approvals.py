from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.font_readiness import FontReadiness  # noqa: E402
from bridge.readability_approvals import (  # noqa: E402
    ReadabilityApprovalError,
    approve_readability,
    require_current_approval,
)
from bridge.readability_contract import load_readability_contract  # noqa: E402
from bridge.registry import Registry  # noqa: E402
from bridge.review_readability import assess_sequence  # noqa: E402


POLICY = load_readability_contract(ROOT / "review_readability_contract.json")
FONTS_READY = FontReadiness(True, (), ())


class CompactMeasurer:
    def font_available(self, _family: str, _weight: int) -> bool:
        return True

    def measure_text(self, text: str, _family: str, _weight: int, font_size: float) -> float:
        return len(text) * font_size * 0.01


def sentence(prefix: str, count: int) -> str:
    return " ".join([prefix] * count) + "."


class ReadabilityApprovalTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.registry_path = Path(self.temporary.name) / "registry.json"
        self.registry = Registry(self.registry_path)
        self.measurer = CompactMeasurer()

    def tearDown(self):
        self.temporary.cleanup()

    def assessment(self, reviews, *, fps=30.0, policy=POLICY):
        return assess_sequence(
            reviews,
            "story_reel_1080x1920",
            fps,
            policy,
            self.measurer,
            FONTS_READY,
        )

    def test_pass_requires_no_approval(self):
        assessment = self.assessment([{"text": "Esperienza sintetica.", "stars": 5}])

        self.assertIsNone(require_current_approval(self.registry, assessment, None))

    def test_long_single_and_verbatim_split_are_bound_to_explicit_metadata(self):
        long_single = self.assessment([{"text": sentence("cura", 45), "stars": 5}])
        approval = approve_readability(
            self.registry,
            "PC_PERSONALE",
            long_single.fingerprint,
            [{"review_index": 0, "decision": "LONG_SINGLE"}],
            "ALESSIO",
        )
        self.assertEqual(
            require_current_approval(self.registry, long_single, approval.token),
            approval,
        )

        split_assessment = self.assessment(
            [{"text": sentence("prima", 23) + " " + sentence("seconda", 23), "stars": 5}]
        )
        offset = split_assessment.reviews[0].suggested_split
        self.assertIsNotNone(offset)
        split_approval = approve_readability(
            self.registry,
            "PC_PERSONALE",
            split_assessment.fingerprint,
            [{"review_index": 0, "decision": "VERBATIM_SPLIT", "split_offset": offset}],
            "TECNICO",
        )
        self.assertEqual(
            require_current_approval(self.registry, split_assessment, split_approval.token),
            split_approval,
        )

    def test_invalid_role_decision_and_split_are_rejected(self):
        assessment = self.assessment(
            [{"text": sentence("prima", 23) + " " + sentence("seconda", 23), "stars": 5}]
        )
        with self.assertRaises(ValueError):
            approve_readability(
                self.registry,
                "PC_PERSONALE",
                assessment.fingerprint,
                [{"review_index": 0, "decision": "LONG_SINGLE"}],
                "OSPITE",
            )
        with self.assertRaises(ValueError):
            approve_readability(
                self.registry,
                "PC_PERSONALE",
                assessment.fingerprint,
                [{"review_index": 0, "decision": "RIASSUNTO"}],
                "ALESSIO",
            )

        wrong = approve_readability(
            self.registry,
            "PC_PERSONALE",
            assessment.fingerprint,
            [{"review_index": 0, "decision": "VERBATIM_SPLIT", "split_offset": 1}],
            "ALESSIO",
        )
        with self.assertRaises(ValueError):
            require_current_approval(self.registry, assessment, wrong.token)

    def test_every_needs_review_item_requires_one_decision(self):
        assessment = self.assessment(
            [
                {"text": sentence("prima", 45), "stars": 5},
                {"text": sentence("seconda", 45), "stars": 4},
            ]
        )
        incomplete = approve_readability(
            self.registry,
            "PC_PERSONALE",
            assessment.fingerprint,
            [{"review_index": 0, "decision": "LONG_SINGLE"}],
            "SEGRETERIA",
        )

        with self.assertRaises(ValueError):
            require_current_approval(self.registry, assessment, incomplete.token)

    def test_registry_persists_no_review_text_or_fragments(self):
        private_text = sentence("contenuto-riservato", 45)
        assessment = self.assessment([{"text": private_text, "stars": 5}])
        approval = approve_readability(
            self.registry,
            "PC_PERSONALE",
            assessment.fingerprint,
            [{"review_index": 0, "decision": "LONG_SINGLE"}],
            "SEGRETERIA",
        )

        stored = self.registry_path.read_text(encoding="utf-8")
        self.assertNotIn(private_text, stored)
        self.assertNotIn("contenuto-riservato", stored)
        self.assertIn(approval.token, stored)
        payload = json.loads(stored)
        record = payload["readability_approvals"][approval.token]
        self.assertEqual(
            set(record),
            {
                "assessment_fingerprint",
                "created_at",
                "decisions",
                "operator_role",
                "token",
                "workstation_id",
            },
        )

    def test_editorial_or_contract_change_makes_old_approval_stale(self):
        reviews = [
            {"text": sentence("prima", 45), "stars": 5},
            {"text": sentence("seconda", 45), "stars": 4},
        ]
        assessment = self.assessment(reviews)
        approval = approve_readability(
            self.registry,
            "PC_PERSONALE",
            assessment.fingerprint,
            [
                {"review_index": 0, "decision": "LONG_SINGLE"},
                {"review_index": 1, "decision": "LONG_SINGLE"},
            ],
            "ALESSIO",
        )

        changed_policy_payload = json.loads(json.dumps(POLICY.policy))
        changed_policy = type(POLICY)(
            changed_policy_payload,
            POLICY.graphic_kit_repository,
            POLICY.graphic_kit_commit,
            "f" * 64,
        )
        variants = []
        punctuation = json.loads(json.dumps(reviews))
        punctuation[0]["text"] += "!"
        variants.append(self.assessment(punctuation))
        variants.append(self.assessment(list(reversed(reviews))))
        variants.append(self.assessment(reviews, fps=29.97))
        variants.append(self.assessment(reviews, policy=changed_policy))

        for changed in variants:
            with self.subTest(fingerprint=changed.fingerprint), self.assertRaisesRegex(
                ReadabilityApprovalError, "STALE_APPROVAL"
            ):
                require_current_approval(self.registry, changed, approval.token)

    def test_changed_split_boundary_is_rejected_even_with_same_fingerprint(self):
        assessment = self.assessment(
            [{"text": sentence("prima", 23) + " " + sentence("seconda", 23), "stars": 5}]
        )
        offset = assessment.reviews[0].suggested_split
        approval = approve_readability(
            self.registry,
            "PC_PERSONALE",
            assessment.fingerprint,
            [{"review_index": 0, "decision": "VERBATIM_SPLIT", "split_offset": offset}],
            "ALESSIO",
        )
        changed_review = replace(assessment.reviews[0], suggested_split=offset + 1)
        changed = replace(assessment, reviews=(changed_review,))

        with self.assertRaises(ValueError):
            require_current_approval(self.registry, changed, approval.token)


if __name__ == "__main__":
    unittest.main()
