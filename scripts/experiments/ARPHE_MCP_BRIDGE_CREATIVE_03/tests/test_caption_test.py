from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class CaptionTestCueTests(unittest.TestCase):
    SPANS = [
        {"source_start_frame": 270, "source_end_frame": 360, "timeline_start_frame": 0},
        {"source_start_frame": 600, "source_end_frame": 630, "timeline_start_frame": 100},
    ]

    def test_maps_explicit_source_frame_spans_without_filling_removed_gaps(self):
        from bridge.caption_test import caption_cues_from_segments, validate_source_spans
        spans = validate_source_spans(self.SPANS, 30.0)
        cues = caption_cues_from_segments([{"words": [
            {"start": 9.10, "end": 9.30, "word": " Primo"},
            {"start": 9.30, "end": 9.55, "word": " blocco."},
            {"start": 15.10, "end": 15.30, "word": " escluso"},
            {"start": 20.10, "end": 20.30, "word": " Secondo"},
            {"start": 20.30, "end": 20.55, "word": " blocco."},
        ]}], spans, 30.0)
        self.assertEqual([(3, 17, "Primo blocco."), (103, 117, "Secondo blocco.")],
                         [(cue["start_frame"], cue["end_frame"], cue["text"]) for cue in cues])

    def test_rejects_overlapping_and_non_integer_source_mapping(self):
        from bridge.caption_test import validate_source_spans
        with self.assertRaisesRegex(Exception, "sovrapposti"):
            validate_source_spans([
                {"source_start_frame": 0, "source_end_frame": 10, "timeline_start_frame": 0},
                {"source_start_frame": 20, "source_end_frame": 30, "timeline_start_frame": 9},
            ], 30.0)
        with self.assertRaisesRegex(Exception, "interi"):
            validate_source_spans([{"source_start_frame": 0.5, "source_end_frame": 10,
                                    "timeline_start_frame": 0}], 30.0)

    def test_rejoins_apostrophe_tokens_and_limits_caption_length(self):
        from bridge.caption_test import caption_cues_from_segments, validate_source_spans
        spans = validate_source_spans(self.SPANS, 30.0)
        cues = caption_cues_from_segments([{"words": [
            {"start": 9.00, "end": 9.10, "word": " l"},
            {"start": 9.10, "end": 9.40, "word": "'attenzione"},
            {"start": 9.40, "end": 9.70, "word": " conta"},
            {"start": 9.70, "end": 10.00, "word": " sempre"},
            {"start": 10.00, "end": 10.30, "word": " molto."},
        ]}], spans, 30.0)
        self.assertEqual("l'attenzione conta sempre", cues[0]["text"])
        self.assertEqual("molto.", cues[1]["text"])
        self.assertTrue(all(len(cue["text"]) <= 84 for cue in cues))

    def test_does_not_split_apostrophe_token_at_chunk_boundary(self):
        from bridge.caption_test import caption_cues_from_segments, validate_source_spans
        spans = validate_source_spans(self.SPANS, 30.0)
        cues = caption_cues_from_segments([{"words": [
            {"start": 9.10, "end": 9.30, "word": " soprattutto"},
            {"start": 9.30, "end": 9.55, "word": " tantissime"},
            {"start": 9.55, "end": 9.80, "word": " effettivamente"},
            {"start": 9.80, "end": 9.90, "word": " c"},
            {"start": 9.90, "end": 10.00, "word": "'è"},
            {"start": 10.00, "end": 10.20, "word": " seguito."},
        ]}], spans, 30.0)
        texts = [cue["text"] for cue in cues]
        self.assertNotIn("c", texts)
        self.assertFalse(any(text.startswith(("'", "’")) for text in texts))
        self.assertIn("c'è", " ".join(texts))

    def test_karaoke_word_mode_uses_word_timing_uppercase_and_keeps_apostrophes(self):
        from bridge.caption_test import caption_cues_from_segments, validate_source_spans
        spans = validate_source_spans(self.SPANS, 30.0)
        try:
            cues = caption_cues_from_segments([{"words": [
                {"start": 9.10, "end": 9.30, "word": " ciao"},
                {"start": 9.30, "end": 9.40, "word": " c"},
                {"start": 9.40, "end": 9.55, "word": "'è"},
                {"start": 9.55, "end": 9.80, "word": " seguito."},
            ]}], spans, 30.0, caption_mode="KARAOKE_WORD", uppercase=True)
        except TypeError as exc:
            self.fail(f"caption mode generico non implementato: {exc}")
        self.assertEqual([(3, 9, "CIAO"), (9, 17, "C'È"), (17, 24, "SEGUITO.")],
                         [(cue["start_frame"], cue["end_frame"], cue["text"])
                          for cue in cues])

    def test_removes_only_one_owned_caption_layer_from_duplicate(self):
        import bridge.caption_test as caption_test
        self.assertTrue(hasattr(caption_test, "remove_owned_caption_overlay"),
                        "manca la sostituzione generica del layer caption posseduto")

        class Comp:
            def FindTool(self, name): return object() if name == "ARPHE_VERTICAL_CAPTIONS_CANVAS" else None

        class Item:
            def __init__(self, name): self.name = name
            def GetName(self): return self.name
            def GetStart(self): return 0
            def GetEnd(self): return 60
            def GetDuration(self): return 60
            def GetFusionCompCount(self): return 1
            def GetFusionCompByIndex(self, index): return Comp() if index == 1 else None

        class Timeline:
            def __init__(self):
                self.tracks = {1: [Item("VIDEO")],
                               2: [Item("ARPHE_VERTICAL_CAPTIONS_captions")]}
                self.deleted_tracks = []
            def GetStartFrame(self): return 0
            def GetEndFrame(self): return 60
            def GetTrackCount(self, kind): return len(self.tracks) if kind == "video" else 0
            def GetItemListInTrack(self, kind, index): return self.tracks.get(index, [])
            def DeleteClips(self, items, ripple):
                for index in self.tracks:
                    self.tracks[index] = [item for item in self.tracks[index] if item not in items]
                return True
            def DeleteTrack(self, kind, index):
                self.deleted_tracks.append((kind, index)); self.tracks.pop(index); return True

        timeline = Timeline()
        result = caption_test.remove_owned_caption_overlay(timeline)
        self.assertEqual({"removed": True, "track": 2}, result)
        self.assertEqual([("video", 2)], timeline.deleted_tracks)
        self.assertEqual(["VIDEO"], [item.GetName() for item in timeline.tracks[1]])

    def test_refuses_named_but_unowned_caption_layer(self):
        from bridge.caption_test import remove_owned_caption_overlay

        class Item:
            def GetName(self): return "ARPHE_VERTICAL_CAPTIONS_captions"
            def GetStart(self): return 0
            def GetEnd(self): return 60
            def GetDuration(self): return 60
            def GetFusionCompCount(self): return 1
            def GetFusionCompByIndex(self, index): return SimpleNamespace(FindTool=lambda name: None)

        class Timeline:
            def GetStartFrame(self): return 0
            def GetEndFrame(self): return 60
            def GetTrackCount(self, kind): return 1
            def GetItemListInTrack(self, kind, index): return [Item()]

        with self.assertRaisesRegex(Exception, "posseduto"):
            remove_owned_caption_overlay(Timeline())

    def test_removal_readback_detects_same_owned_item_returned_as_new_proxy(self):
        from bridge.caption_test import remove_owned_caption_overlay

        class Comp:
            def FindTool(self, name): return object() if name == "ARPHE_VERTICAL_CAPTIONS_CANVAS" else None

        class Item:
            def GetName(self): return "ARPHE_VERTICAL_CAPTIONS_captions"
            def GetUniqueId(self): return "fusion-item-1"
            def GetStart(self): return 0
            def GetEnd(self): return 60
            def GetDuration(self): return 60
            def GetFusionCompCount(self): return 1
            def GetFusionCompByIndex(self, index): return Comp() if index == 1 else None

        class Timeline:
            def __init__(self): self.calls = 0
            def GetStartFrame(self): return 0
            def GetEndFrame(self): return 60
            def GetTrackCount(self, kind): return 1
            def GetItemListInTrack(self, kind, index):
                self.calls += 1
                return [Item()]  # Resolve may return a fresh proxy for the same item.
            def DeleteClips(self, items, ripple): return True  # Silent non-removal.

        with self.assertRaisesRegex(Exception, "Read-back rimozione"):
            remove_owned_caption_overlay(Timeline())

    def test_generic_wrapper_rolls_back_new_copy_when_fusion_write_fails(self):
        from bridge.caption_test import create_caption_test

        class Timeline:
            def __init__(self, name): self.name = name
            def GetStartFrame(self): return 0
            def GetEndFrame(self): return 60
            def GetName(self): return self.name
            def GetSetting(self, key): return "30" if key == "timelineFrameRate" else None

        class Pool:
            def __init__(self): self.deleted = []
            def DeleteTimelines(self, values): self.deleted.extend(values); return True

        class Project:
            def __init__(self):
                self.source = Timeline("ARPHE_SOURCE")
                self.copy = Timeline("ARPHE_CAPTION_TEST")
                self.timeline = self.source; self.pool = Pool(); self.restored = None
            def GetCurrentTimeline(self): return self.timeline
            def SetCurrentTimeline(self, value): self.timeline = value; self.restored = value; return True
            def GetMediaPool(self): return self.pool

        project = Project()
        with patch("bridge.caption_test.duplicate_timeline", return_value={"ok": True, "created_timeline": "ARPHE_CAPTION_TEST"}), \
             patch("bridge.caption_test.find_timeline", return_value=project.copy), \
             patch("bridge.caption_test._load_segments", return_value=[{"words": [
                 {"start": 0.10, "end": 0.30, "word": " Test."}]}]), \
             patch("bridge.caption_test.timeline_edit_fingerprint", return_value="a" * 64), \
             patch("bridge.caption_test.apply_caption_action", side_effect=RuntimeError("Fusion rejected")):
            with self.assertRaisesRegex(RuntimeError, "Fusion rejected"):
                create_caption_test(project, object(), object(), "input", "ARPHE_CAPTION_TEST",
                                    "transcript.json", [{"source_start_frame": 0,
                                    "source_end_frame": 30, "timeline_start_frame": 0}], 60)
        self.assertEqual([project.copy], project.pool.deleted)
        self.assertIs(project.source, project.restored)
        self.assertIs(project.source, project.timeline)

    def test_selects_exact_duplicate_even_when_resolve_keeps_source_current(self):
        from bridge.caption_test import create_caption_test

        class Timeline:
            def __init__(self, name): self.name = name
            def GetName(self): return self.name
            def GetStartFrame(self): return 0
            def GetEndFrame(self): return 60
            def GetSetting(self, key): return "30" if key == "timelineFrameRate" else None

        source, duplicate = Timeline("ARPHE_SOURCE"), Timeline("ARPHE_TARGET")
        project = SimpleNamespace(
            current=source,
            GetCurrentTimeline=lambda: project.current,
            SetCurrentTimeline=lambda value: setattr(project, "current", value) is None,
        )
        with patch("bridge.caption_test.duplicate_timeline", return_value={"ok": True, "created_timeline": "ARPHE_TARGET"}), \
             patch("bridge.caption_test.find_timeline", return_value=duplicate), \
             patch("bridge.caption_test._load_segments", return_value=[{"words": [
                 {"start": 0.10, "end": 0.30, "word": " Test."}]}]), \
             patch("bridge.caption_test.timeline_edit_fingerprint", return_value="a" * 64), \
             patch("bridge.caption_test.apply_caption_action", return_value={"cue_count": 1}) as apply:
            result = create_caption_test(project, object(), object(), "ARPHE_SOURCE", "ARPHE_TARGET",
                                         "transcript.json", [{"source_start_frame": 0,
                                         "source_end_frame": 30, "timeline_start_frame": 0}], 60)
        self.assertIs(duplicate, apply.call_args.args[1])
        self.assertEqual("ARPHE_TARGET", result["created_timeline"])

    def test_public_caption_wrapper_holds_resolve_lock_for_operation(self):
        from bridge import server
        events = []

        class Lock:
            def __enter__(self): events.append("lock_enter")
            def __exit__(self, *args): events.append("lock_exit")

        def operation(*args):
            events.append("operation")
            return {"ok": True}

        runtime = (object(), object(), object(), object(), object(), object(), None)
        with patch.object(server, "RESOLVE_ACCESS_LOCK", Lock()), \
             patch.object(server, "_runtime", return_value=runtime), \
             patch.object(server, "do_create_caption_test", side_effect=operation):
            result = server.create_caption_test(
                "ARPHE_SOURCE", "ARPHE_TARGET", "transcript.json",
                [{"source_start_frame": 0, "source_end_frame": 30,
                  "timeline_start_frame": 0}], 30)
        self.assertTrue(result["ok"])
        self.assertEqual(["lock_enter", "operation", "lock_exit"], events)


if __name__ == "__main__":
    unittest.main()
