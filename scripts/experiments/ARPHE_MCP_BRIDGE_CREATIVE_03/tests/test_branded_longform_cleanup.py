from __future__ import annotations
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class BrandedLongformCleanupTests(unittest.TestCase):
    def test_only_high_confidence_filler_is_auto_removable(self):
        from bridge.branded_longform_cleanup import plan_cleanup
        candidates = plan_cleanup([
            {"kind": "FILLER", "start": 1.0, "end": 1.2, "confidence": 0.95},
            {"kind": "EDITORIAL_CUE", "start": 2.0, "end": 3.0, "confidence": 0.99},
        ])
        self.assertTrue(candidates[0].auto_apply)
        self.assertFalse(candidates[1].auto_apply)
        self.assertTrue(candidates[1].review_required)

    def test_derived_names_preserve_original(self):
        from bridge.branded_longform_cleanup import derived_timeline_names
        self.assertEqual(("Podcast_CLEANUP", "Podcast_EDITORIAL"), derived_timeline_names("Podcast"))

    def test_sentence_restart_can_auto_apply_but_serious_note_requires_review(self):
        from bridge.branded_longform_cleanup import plan_cleanup
        restart, note = plan_cleanup([
            {"kind": "SENTENCE_RESTART", "start": 1, "end": 2, "confidence": 0.97},
            {"kind": "SERIOUS_PRODUCTION_NOTE", "start": 3, "end": 5, "confidence": 0.99},
        ])
        self.assertTrue(restart.auto_apply)
        self.assertFalse(note.auto_apply)
        self.assertTrue(note.review_required)

    def test_cleanup_ranges_merge_overlaps_and_preserve_review_only_events(self):
        from bridge.branded_longform_cleanup import plan_cleanup, cleanup_cut_ranges
        candidates = plan_cleanup([
            {"kind": "FILLER", "start": 1.0, "end": 1.5, "confidence": 0.99},
            {"kind": "SENTENCE_RESTART", "start": 1.4, "end": 2.0, "confidence": 0.96},
            {"kind": "SERIOUS_PRODUCTION_NOTE", "start": 3.0, "end": 4.0, "confidence": 0.99},
        ])
        self.assertEqual(((30, 60),), cleanup_cut_ranges(candidates, fps=30, total_frames=300))
