from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class AdvCaptionCueTests(unittest.TestCase):
    def test_maps_word_timestamps_across_exact_source_spans_without_filling_removed_gaps(self):
        from bridge.adv_caption_test import caption_cues_from_segments

        segments = [{"words": [
            {"start": 9.10, "end": 9.30, "word": " Primo"},
            {"start": 9.30, "end": 9.55, "word": " blocco."},
            {"start": 20.00, "end": 20.20, "word": " escluso"},
            {"start": 27.35, "end": 27.55, "word": " Secondo"},
            {"start": 27.55, "end": 27.80, "word": " blocco."},
            {"start": 41.50, "end": 41.70, "word": " Finale."},
        ]}]

        cues = caption_cues_from_segments(segments)

        self.assertEqual(
            [(2, 16, "Primo blocco."), (311, 324, "Secondo blocco."), (615, 621, "Finale.")],
            [(cue["start_frame"], cue["end_frame"], cue["text"]) for cue in cues],
        )
        self.assertTrue(all(cue["position"] == "LOWER" for cue in cues))

    def test_rejoins_apostrophe_tokens_and_keeps_each_caption_within_four_words(self):
        from bridge.adv_caption_test import caption_cues_from_segments

        segments = [{"words": [
            {"start": 10.00, "end": 10.10, "word": " l"},
            {"start": 10.10, "end": 10.40, "word": "'attenzione"},
            {"start": 10.40, "end": 10.70, "word": " conta"},
            {"start": 10.70, "end": 11.00, "word": " sempre"},
            {"start": 11.00, "end": 11.30, "word": " molto."},
        ]}]

        cues = caption_cues_from_segments(segments)

        self.assertEqual("l'attenzione conta sempre", cues[0]["text"])
        self.assertEqual("molto.", cues[1]["text"])
        self.assertTrue(all(len(cue["text"]) <= 84 for cue in cues))

    def test_builds_a_caption_action_with_no_cta_and_a_hard_end_of_timeline_cutoff(self):
        from bridge.adv_caption_test import caption_action_for_segments

        action = caption_action_for_segments(
            [{"words": [{"start": 9.10, "end": 9.30, "word": " Test."}]}],
            locked_edit_fingerprint="a" * 64, total_frames=645,
        )

        self.assertEqual("CAPTIONS", action["type"])
        self.assertEqual("POST_LOCK", action["phase"])
        self.assertEqual(645, action["caption_cutoff_frame"])
        self.assertNotEqual("CTA", action["type"])

    def test_wrapper_rolls_back_the_caption_copy_when_the_fusion_write_fails(self):
        from bridge.adv_caption_test import create_advbeppe_caption_test

        class Timeline:
            def GetStartFrame(self): return 108000
            def GetEndFrame(self): return 108645
            def GetName(self): return "ARPHE_ADV_CAPTIONS_TEST"

        class Pool:
            def __init__(self): self.deleted = []
            def DeleteTimelines(self, values): self.deleted.extend(values); return True

        class Project:
            def __init__(self): self.timeline = Timeline(); self.pool = Pool(); self.restored = None
            def GetCurrentTimeline(self): return self.timeline
            def SetCurrentTimeline(self, value): self.restored = value; return True
            def GetMediaPool(self): return self.pool

        project = Project()
        with patch("bridge.adv_caption_test.duplicate_timeline", return_value={"ok": True}), \
             patch("bridge.adv_caption_test._segments_from_longform_transcript", return_value=[{
                 "words": [{"start": 9.10, "end": 9.30, "word": " Test."}]
             }]), \
             patch("bridge.adv_caption_test.timeline_edit_fingerprint", return_value="a" * 64), \
             patch("bridge.adv_caption_test.apply_caption_action", side_effect=RuntimeError("Fusion rejected")):
            with self.assertRaisesRegex(RuntimeError, "Fusion rejected"):
                create_advbeppe_caption_test(project, object(), object(),
                                              "ARPHE_ADV_SEAM_TEST_20261022", "ARPHE_ADV_CAPTIONS_TEST")

        self.assertEqual([project.timeline], project.pool.deleted)
        self.assertIs(project.timeline, project.restored)


if __name__ == "__main__":
    unittest.main()
