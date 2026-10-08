from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.editorial_workflows import (  # noqa: E402
    load_render_profile_registry,
    load_workflow_registry,
    resolve_delivery_profile,
    validate_editorial_brief,
)
from bridge.safety import ValidationError  # noqa: E402


WORKFLOWS = ROOT / "editorial_workflows.json"
PROFILES = ROOT / "render_profiles.json"


class EditorialWorkflowRegistryTests(unittest.TestCase):
    def setUp(self):
        self.workflows = load_workflow_registry(WORKFLOWS)
        self.profiles = load_render_profile_registry(PROFILES)

    def test_four_workflows_load_with_unique_ids_and_required_questions(self):
        self.assertEqual(
            {
                "ARPHE_PODCAST_REELS_CTA",
                "ARPHE_VERTICAL_SOCIAL",
                "CARABELLESE_YOUTUBE_CLEANUP",
                "ARPHE_LONGFORM_EDITORIAL",
            },
            set(self.workflows.workflows),
        )
        for workflow in self.workflows.workflows.values():
            self.assertGreaterEqual(len(workflow.questions), 9)
            self.assertEqual(len(workflow.questions), len(set(workflow.questions)))

        carabellese = self.workflows.workflows["CARABELLESE_YOUTUBE_CLEANUP"]
        self.assertEqual("fixed", carabellese.format_contract["resolution_mode"])
        self.assertEqual([1920, 1080], carabellese.format_contract["resolution"])
        self.assertEqual("source", carabellese.format_contract["frame_rate_mode"])
        vertical = self.workflows.workflows["ARPHE_VERTICAL_SOCIAL"]
        self.assertEqual([1080, 1920], vertical.format_contract["resolution"])
        self.assertEqual("30", vertical.format_contract["frame_rate"])
        podcast = self.workflows.workflows["ARPHE_PODCAST_REELS_CTA"]
        self.assertEqual("fixed", podcast.format_contract["frame_rate_mode"])
        self.assertEqual("30", podcast.format_contract["frame_rate"])

    def test_standard_secretary_brief_resolves_only_allowed_profiles(self):
        brief = validate_editorial_brief({
            "workflow_id": "CARABELLESE_YOUTUBE_CLEANUP",
            "operator_role": "SEGRETERIA",
            "primary_source": "podcast-01.mov",
            "requested_outputs": ["publishable"],
            "format_request": {"source_rates": ["30000/1001"]},
            "answers": {str(index): "confermato" for index in range(1, 12)},
        }, self.workflows)
        profile = resolve_delivery_profile(brief, "YOUTUBE_H264", self.profiles)
        self.assertEqual("publishable", profile.delivery_class)
        with self.assertRaisesRegex(ValidationError, "non consentito"):
            resolve_delivery_profile(brief, "VERTICAL_PRORES_MASTER", self.profiles)

    def test_ambiguous_or_incomplete_brief_keeps_unresolved_questions(self):
        brief = validate_editorial_brief({
            "operator_role": "SEGRETERIA",
            "requested_outputs": [],
            "format_request": {},
            "answers": {},
        }, self.workflows)
        self.assertIn("workflow_id", brief.unresolved_questions)
        self.assertIn("primary_source", brief.unresolved_questions)
        self.assertIn("requested_outputs", brief.unresolved_questions)

    def test_fixed_rate_podcast_does_not_ask_for_primary_rate(self):
        brief = validate_editorial_brief({
            "workflow_id": "ARPHE_PODCAST_REELS_CTA",
            "operator_role": "SEGRETERIA",
            "primary_source": "podcast.mov",
            "requested_outputs": ["publishable"],
            "format_request": {"source_rates": ["25", "30000/1001"]},
            "answers": {str(index): "confermato" for index in range(1, 10)},
        }, self.workflows)
        self.assertNotIn("primary_frame_rate", brief.unresolved_questions)

    def test_new_registry_entry_loads_without_render_engine_branch(self):
        payload = json.loads(WORKFLOWS.read_text(encoding="utf-8"))
        clone = dict(payload["workflows"][0])
        clone["workflow_id"] = "FUTURE_LINE_05"
        clone["label"] = "Future line"
        payload["workflows"].append(clone)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "workflows.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            loaded = load_workflow_registry(path)
        self.assertIn("FUTURE_LINE_05", loaded.workflows)

    def test_registry_rejects_unknown_keys_duplicate_ids_and_nontechnical_override(self):
        payload = json.loads(WORKFLOWS.read_text(encoding="utf-8"))
        payload["unexpected"] = True
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "campi sconosciuti"):
                load_workflow_registry(path)

        brief = validate_editorial_brief({
            "workflow_id": "CARABELLESE_YOUTUBE_CLEANUP",
            "operator_role": "SEGRETERIA",
            "primary_source": "podcast.mov",
            "requested_outputs": ["publishable"],
            "format_request": {"source_rates": ["25"], "override": True},
            "answers": {str(index): "ok" for index in range(1, 12)},
        }, self.workflows)
        with self.assertRaisesRegex(ValidationError, "ruolo tecnico"):
            resolve_delivery_profile(brief, "YOUTUBE_H264", self.profiles)


if __name__ == "__main__":
    unittest.main()
