from __future__ import annotations

import json
import math
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.font_readiness import (  # noqa: E402
    WindowsGdiTextMeasurer,
    check_required_fonts,
)
from bridge.readability_contract import load_readability_contract  # noqa: E402


POLICY = load_readability_contract(ROOT / "review_readability_contract.json")


class FakeMeasurer:
    def __init__(self, available: set[tuple[str, int]]):
        self.available = available
        self.checks: list[tuple[str, int]] = []
        self.source_path = Path("C:/private/fonts/do-not-serialize.ttf")

    def font_available(self, family: str, weight: int) -> bool:
        self.checks.append((family, weight))
        return (family, weight) in self.available

    def measure_text(self, text: str, family: str, weight: int, font_size: float) -> float:
        if not self.font_available(family, weight):
            raise ValueError("font unavailable")
        return len(text) * font_size * 0.55


REQUIRED = {
    ("Noto Serif Display", 300),
    ("Satoshi", 400),
    ("Satoshi", 500),
    ("Satoshi", 700),
}


class FontReadinessTests(unittest.TestCase):
    def test_checks_each_required_family_and_weight_independently(self):
        measurer = FakeMeasurer(REQUIRED)

        readiness = check_required_fonts(POLICY, measurer)

        self.assertTrue(readiness.ready)
        self.assertEqual(set(measurer.checks), REQUIRED)
        self.assertEqual(readiness.missing, ())

    def test_one_missing_weight_blocks_readiness_without_hiding_other_checks(self):
        measurer = FakeMeasurer(REQUIRED - {("Satoshi", 500)})

        readiness = check_required_fonts(POLICY, measurer)

        self.assertFalse(readiness.ready)
        self.assertEqual(readiness.missing, (("Satoshi", 500),))
        self.assertEqual(set(measurer.checks), REQUIRED)
        self.assertEqual(readiness.reason_code, "FONT_UNAVAILABLE")

    def test_unicode_measurement_is_finite_and_readiness_serialization_has_no_paths(self):
        measurer = FakeMeasurer(REQUIRED)
        text = "L’esperienza è stata chiara — cura, ascolto, serenità 🌿" * 20

        width = measurer.measure_text(text, "Satoshi", 400, 42.0)
        serialized = json.dumps(check_required_fonts(POLICY, measurer).to_dict())

        self.assertTrue(math.isfinite(width))
        self.assertGreater(width, 0)
        self.assertNotIn("C:/", serialized)
        self.assertNotIn("do-not-serialize", serialized)


class WindowsGdiIntegrationTests(unittest.TestCase):
    def test_required_fonts_measure_deterministically_when_installed(self):
        measurer = WindowsGdiTextMeasurer()
        if not measurer.available:
            self.skipTest(measurer.unavailable_reason)
        readiness = check_required_fonts(POLICY, measurer)
        if not readiness.ready:
            self.skipTest(f"required fonts not installed: {readiness.missing}")

        text = "Misura Unicode: Arphè — 400/500/700"
        first = measurer.measure_text(text, "Satoshi", 400, 42.0)
        second = measurer.measure_text(text, "Satoshi", 400, 42.0)

        self.assertEqual(first, second)
        self.assertTrue(math.isfinite(first))
        self.assertGreater(first, 0)


if __name__ == "__main__":
    unittest.main()
