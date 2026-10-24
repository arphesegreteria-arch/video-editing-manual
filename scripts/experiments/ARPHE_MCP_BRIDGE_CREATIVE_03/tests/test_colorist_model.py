from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.colorist_model import (  # noqa: E402
    build_cdl,
    load_colorist_presets,
    plan_fingerprint,
)
from bridge.safety import ValidationError  # noqa: E402


class ColoristModelTests(unittest.TestCase):
    def test_neutral_adjustments_produce_identity_cdl(self):
        presets = {"ARPHE_CLEAN_NEUTRAL": {
            "temperature": 0.0, "tint": 0.0, "exposure_stops": 0.0,
            "contrast": 0.0, "saturation": 1.0,
        }}
        self.assertEqual({
            "NodeIndex": 1,
            "Slope": "1.000000 1.000000 1.000000",
            "Offset": "-0.000000 -0.000000 -0.000000",
            "Power": "1.000000 1.000000 1.000000",
            "Saturation": "1.000000",
        }, build_cdl({}, "ARPHE_CLEAN_NEUTRAL", presets))

    def test_adjustments_map_to_hand_checked_bounded_cdl(self):
        presets = {"ARPHE_CLEAN_NEUTRAL": {
            "temperature": 0.0, "tint": 0.0, "exposure_stops": 0.0,
            "contrast": 0.0, "saturation": 1.0,
        }}
        result = build_cdl({
            "temperature": 0.5,
            "tint": 0.25,
            "exposure_stops": 1.0,
            "contrast": 0.4,
            "saturation": 1.2,
        }, "ARPHE_CLEAN_NEUTRAL", presets)
        self.assertEqual("2.333100 2.156000 2.110900", result["Slope"])
        self.assertEqual("-0.050000 -0.050000 -0.050000", result["Offset"])
        self.assertEqual("1.200000", result["Saturation"])

    def test_numeric_validation_rejects_bool_nan_infinity_and_out_of_range(self):
        presets = {"ARPHE_CLEAN_NEUTRAL": {
            "temperature": 0.0, "tint": 0.0, "exposure_stops": 0.0,
            "contrast": 0.0, "saturation": 1.0,
        }}
        for adjustments in (
            {"temperature": True},
            {"tint": float("nan")},
            {"exposure_stops": float("inf")},
            {"contrast": 1.01},
            {"saturation": -0.01},
        ):
            with self.subTest(adjustments=adjustments), self.assertRaises(ValidationError):
                build_cdl(adjustments, "ARPHE_CLEAN_NEUTRAL", presets)

    def test_preset_registry_is_closed_and_rejects_unknown_or_malformed_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "presets.json"
            path.write_text(json.dumps({
                "schema": "ARPHE_COLORIST_PRESETS_V1",
                "presets": {"ARPHE_CLEAN_NEUTRAL": {
                    "temperature": 0.0, "tint": 0.0, "exposure_stops": 0.0,
                    "contrast": 0.0, "saturation": 1.0,
                }},
                "drx_presets": {},
            }), encoding="utf-8")
            presets = load_colorist_presets(path)
            self.assertEqual({"ARPHE_CLEAN_NEUTRAL"}, set(presets["presets"]))
            with self.assertRaisesRegex(ValidationError, "Preset"):
                build_cdl({}, "ARPHE_UNKNOWN", presets["presets"])

            path.write_text(json.dumps({"schema": "wrong", "presets": {}, "drx_presets": {}}),
                            encoding="utf-8")
            with self.assertRaises(ValidationError):
                load_colorist_presets(path)

    def test_fingerprint_is_stable_across_mapping_order_and_changes_with_payload(self):
        first = plan_fingerprint({"clips": ["a", "b"], "adjustments": {"tint": 0.1, "temperature": 0.2}})
        second = plan_fingerprint({"adjustments": {"temperature": 0.2, "tint": 0.1}, "clips": ["a", "b"]})
        changed = plan_fingerprint({"clips": ["a", "b"], "adjustments": {"tint": 0.2, "temperature": 0.2}})
        self.assertRegex(first, r"^[0-9a-f]{64}$")
        self.assertEqual(first, second)
        self.assertNotEqual(first, changed)


if __name__ == "__main__":
    unittest.main()
