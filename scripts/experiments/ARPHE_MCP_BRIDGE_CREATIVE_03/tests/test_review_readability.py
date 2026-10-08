from __future__ import annotations

import copy
import math
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.font_readiness import FontReadiness  # noqa: E402
from bridge.readability_contract import ReadabilityPolicy, load_readability_contract  # noqa: E402
from bridge.review_readability import (  # noqa: E402
    assess_review,
    assess_sequence,
    suggest_sentence_split,
)


POLICY = load_readability_contract(ROOT / "review_readability_contract.json")
FONTS_READY = FontReadiness(True, (), ())


class ScaledMeasurer:
    def __init__(self, factor: float = 0.10):
        self.factor = factor
        self.sizes: list[float] = []

    def font_available(self, _family: str, _weight: int) -> bool:
        return True

    def measure_text(self, text: str, _family: str, _weight: int, font_size: float) -> float:
        self.sizes.append(font_size)
        return len(text) * font_size * self.factor


class NaNMeasurer(ScaledMeasurer):
    def measure_text(self, text: str, family: str, weight: int, font_size: float) -> float:
        return math.nan


def words(count: int) -> str:
    return " ".join(f"w{index}" for index in range(count))


class ReviewReadabilityTests(unittest.TestCase):
    def assess(self, text: str, measurer=None):
        return assess_review(
            text,
            "story_reel_1080x1920",
            30.0,
            POLICY,
            measurer or ScaledMeasurer(),
            FONTS_READY,
        )

    def test_duration_uses_four_words_per_second_plus_settle_time(self):
        expected = {20: 6, 30: 9, 40: 11, 44: 12, 45: 13, 70: 19}
        for count, seconds in expected.items():
            with self.subTest(count=count):
                assessment = self.assess(words(count), ScaledMeasurer(0.01))
                self.assertEqual(assessment.duration_seconds, seconds)
                self.assertEqual(assessment.duration_frames, seconds * 30)
                self.assertEqual(
                    assessment.status,
                    "PASS" if count <= 44 else "NEEDS_REVIEW",
                )
                self.assertEqual(
                    assessment.reason_codes,
                    () if count <= 44 else ("TOO_LONG_FOR_STANDARD",),
                )

    def test_size_tiers_are_tried_largest_first_and_never_below_minimum(self):
        cases = ((270, 0.047), (300, 0.042), (400, None))
        for character_count, expected_size in cases:
            with self.subTest(character_count=character_count):
                assessment = self.assess("x" * character_count, ScaledMeasurer(0.055))
                self.assertEqual(assessment.selected_size, expected_size)
                if expected_size is None:
                    self.assertEqual(assessment.status, "BLOCKED")
                    self.assertIn("TEXT_OVERFLOW", assessment.reason_codes)
                else:
                    self.assertGreaterEqual(assessment.selected_size, 0.042)

    def test_seven_explicit_lines_pass_and_eight_block(self):
        seven = self.assess("\n".join(["riga"] * 7))
        eight = self.assess("\n".join(["riga"] * 8))

        self.assertEqual(seven.line_count, 7)
        self.assertEqual(seven.status, "PASS")
        self.assertEqual(eight.line_count, 8)
        self.assertEqual(eight.status, "BLOCKED")
        self.assertIn("TEXT_OVERFLOW", eight.reason_codes)

    def test_problematic_text_inputs_are_deterministic_and_never_truncated(self):
        cases = {
            "": "BLOCKED",
            "   \t  ": "BLOCKED",
            "L'esperienza   è stata chiara, precisa e rispettosa.": "PASS",
            "Qualità, ascolto — e serenità. È ciò che cercavo!": "PASS",
            "cura" * 1000: "BLOCKED",
            "Esperienza 🌿 molto positiva; professionalità e umanità.": "PASS",
        }
        for text, status in cases.items():
            with self.subTest(text=text[:20]):
                assessment = self.assess(text)
                self.assertEqual(assessment.status, status)
                if text:
                    self.assertNotIn(text, str(assessment.to_dict()))
                if status == "BLOCKED":
                    self.assertIn("TEXT_OVERFLOW", assessment.reason_codes)

    def test_non_finite_measurement_blocks_instead_of_looping_or_guessing(self):
        assessment = self.assess("Testo sintetico per il controllo", NaNMeasurer())

        self.assertEqual(assessment.status, "BLOCKED")
        self.assertEqual(assessment.reason_codes, ("TEXT_OVERFLOW",))
        self.assertIsNone(assessment.selected_size)

    def test_missing_fonts_block_before_measurement(self):
        measurer = ScaledMeasurer()
        fonts = FontReadiness(
            False,
            (("Satoshi", 400),),
            (("Satoshi", 400),),
        )

        assessment = assess_review(
            "Testo sintetico",
            "story_reel_1080x1920",
            30.0,
            POLICY,
            measurer,
            fonts,
        )

        self.assertEqual(assessment.status, "BLOCKED")
        self.assertEqual(assessment.reason_codes, ("FONT_UNAVAILABLE",))
        self.assertEqual(measurer.sizes, [])

    def test_sentence_split_returns_the_exact_nearest_boundary(self):
        text = "Prima frase completa. Seconda frase completa e un poco più lunga."

        offset = suggest_sentence_split(text, ScaledMeasurer(), POLICY)

        self.assertEqual(offset, len("Prima frase completa."))
        self.assertEqual(text[:offset] + text[offset:], text)

    def test_sequence_fingerprint_covers_editorial_and_contract_inputs(self):
        reviews = [
            {"text": "Prima frase completa. Seconda frase completa.", "stars": 5},
            {"text": "Terza recensione sintetica.", "stars": 4},
        ]
        baseline = assess_sequence(
            reviews,
            "story_reel_1080x1920",
            30.0,
            POLICY,
            ScaledMeasurer(),
            FONTS_READY,
        )

        variants = []
        punctuation = copy.deepcopy(reviews)
        punctuation[0]["text"] += "!"
        variants.append((punctuation, "story_reel_1080x1920", 30.0, POLICY))
        variants.append((list(reversed(reviews)), "story_reel_1080x1920", 30.0, POLICY))
        stars = copy.deepcopy(reviews)
        stars[0]["stars"] = 4
        variants.append((stars, "story_reel_1080x1920", 30.0, POLICY))
        variants.append((reviews, "unknown_canvas", 30.0, POLICY))
        variants.append((reviews, "story_reel_1080x1920", 29.97, POLICY))
        changed = copy.deepcopy(POLICY.policy)
        changed["reading"]["minimum_seconds"] = 4
        changed_policy = ReadabilityPolicy(
            changed,
            POLICY.graphic_kit_repository,
            POLICY.graphic_kit_commit,
            "f" * 64,
        )
        variants.append((reviews, "story_reel_1080x1920", 30.0, changed_policy))

        for review_payload, canvas, fps, policy in variants:
            with self.subTest(fps=fps, digest=policy.graphic_kit_policy_digest):
                assessment = assess_sequence(
                    review_payload,
                    canvas,
                    fps,
                    policy,
                    ScaledMeasurer(),
                    FONTS_READY,
                )
                self.assertNotEqual(assessment.fingerprint, baseline.fingerprint)

        serialized = str(baseline.to_dict())
        self.assertNotIn(reviews[0]["text"], serialized)
        self.assertNotIn(reviews[1]["text"], serialized)


if __name__ == "__main__":
    unittest.main()
