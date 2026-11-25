from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class VerticalSocialCaptionTests(unittest.TestCase):
    def action(self):
        return {"action_id": "cap", "type": "CAPTIONS", "state": "APPROVED",
                "locked_edit_fingerprint": "a" * 64,
                "cues": [
                    {"cue_id": "c1", "start_frame": 0, "end_frame": 20,
                     "text": "Prima frase", "position": "LOWER"},
                    {"cue_id": "c2", "start_frame": 30, "end_frame": 60,
                     "text": "Seconda frase", "position": "UPPER"},
                ], "caption_cutoff_frame": 60, "reason": "sottotitoli approvati"}

    def test_caption_schema_preserves_gap_and_safe_positions(self):
        from bridge.vertical_social_captions import validate_caption_action
        result = validate_caption_action(self.action(), 60)
        self.assertEqual(((0, 20), (30, 60)), tuple(cue["range"] for cue in result["cues"]))

    def test_lower_caption_layout_stays_inside_story_safe_area_and_clear_of_social_ui(self):
        from bridge.vertical_social_captions import lower_caption_layout
        layout = lower_caption_layout()
        bounds = layout["bounds"]
        self.assertGreaterEqual(bounds["left"], 0.08)
        self.assertLessEqual(bounds["right"], 0.84)
        self.assertGreaterEqual(bounds["top"], 0.10)
        self.assertLessEqual(bounds["bottom"], 0.82)
        self.assertEqual((0.12, 0.80, 0.695, 0.765),
                         (bounds["left"], bounds["right"], bounds["top"], bounds["bottom"]))

    def test_caption_cues_exclude_the_cta_and_reject_a_cue_crossing_it(self):
        from bridge.vertical_social_captions import cues_before_frame
        cues = (
            {"cue_id": "spoken", "range": (100, 220)},
            {"cue_id": "cta", "range": (866, 920)},
        )
        self.assertEqual(("spoken",), tuple(cue["cue_id"] for cue in cues_before_frame(cues, 866)))
        with self.assertRaisesRegex(Exception, "CTA"):
            cues_before_frame(({"cue_id": "crossing", "range": (840, 880)},), 866)

    def test_caption_schema_enforces_a_declared_cta_cutoff(self):
        from bridge.vertical_social_captions import validate_caption_action
        action = self.action()
        action["caption_cutoff_frame"] = 30
        result = validate_caption_action(action, 60)
        self.assertEqual(((0, 20),), tuple(cue["range"] for cue in result["cues"]))
        crossing = self.action()
        crossing["caption_cutoff_frame"] = 30
        crossing["cues"][1].update({"start_frame": 25, "end_frame": 40})
        with self.assertRaisesRegex(Exception, "CTA"):
            validate_caption_action(crossing, 60)

    def test_lower_caption_text_frame_is_contained_inside_its_safe_card(self):
        from bridge.vertical_social_captions import lower_caption_layout
        layout = lower_caption_layout()
        text = layout["text_frame"]
        card = layout["bounds"]
        self.assertGreaterEqual(text["left"], card["left"])
        self.assertLessEqual(text["right"], card["right"])
        self.assertGreaterEqual(text["top"], card["top"])
        self.assertLessEqual(text["bottom"], card["bottom"])

    def test_caption_schema_rejects_overlap_long_text_and_missing_lock_fingerprint(self):
        from bridge.vertical_social_captions import validate_caption_action
        overlap = self.action(); overlap["cues"][1]["start_frame"] = 10
        with self.assertRaisesRegex(Exception, "sovrapposte"):
            validate_caption_action(overlap, 60)
        long = self.action(); long["cues"][0]["text"] = "x" * 85
        with self.assertRaisesRegex(Exception, "84"):
            validate_caption_action(long, 60)
        missing = self.action(); missing["locked_edit_fingerprint"] = ""
        with self.assertRaisesRegex(Exception, "fingerprint"):
            validate_caption_action(missing, 60)
        missing_cutoff = self.action(); missing_cutoff.pop("caption_cutoff_frame")
        with self.assertRaisesRegex(Exception, "cutoff"):
            validate_caption_action(missing_cutoff, 60)

    def test_caption_text_frame_fails_closed_when_fusion_does_not_apply_it(self):
        from bridge.vertical_social_captions import configure_caption_text_frame, lower_caption_layout

        class Tool:
            def SetInput(self, key, value):
                if key == "LayoutWidth":
                    raise RuntimeError("unsupported")
            def GetInput(self, key):
                return None

        with self.assertRaisesRegex(Exception, "LayoutWidth"):
            configure_caption_text_frame(Tool(), lower_caption_layout())

        class MismatchedTool:
            def __init__(self): self.values = {}
            def SetInput(self, key, value): self.values[key] = value
            def GetInput(self, key):
                return 0.61 if key == "LayoutWidth" else self.values.get(key)

        with self.assertRaisesRegex(Exception, "Read-back"):
            configure_caption_text_frame(MismatchedTool(), lower_caption_layout())

    def test_caption_schema_allows_picture_lock_placeholder_only_during_planning(self):
        from bridge.vertical_social_captions import validate_caption_action
        pending = self.action(); pending["locked_edit_fingerprint"] = "AT_PICTURE_LOCK"
        with self.assertRaisesRegex(Exception, "fingerprint"):
            validate_caption_action(pending, 60)
        result = validate_caption_action(pending, 60, allow_picture_lock_placeholder=True)
        self.assertEqual("AT_PICTURE_LOCK", result["locked_edit_fingerprint"])


    def test_karaoke_graph_adds_a_subtle_dark_text_outline(self):
        from bridge import vertical_social_captions as captions

        class InputRecorder:
            def __init__(self):
                self.inputs = {}

            def SetInput(self, key, value):
                self.inputs[key] = value

            def GetInput(self, key):
                return self.inputs.get(key)

        nodes = []

        def create_tool(comp, reg_id, name):
            node = InputRecorder()
            if reg_id == "TextPlus":
                nodes.append(node)
            return node

        words = tuple(
            {"display_text": text, "font_size": size, "emphasis": emphasis,
             "x": 0.5, "y": 0.25, "card_width": 0.10, "card_height": 0.05, "range": span}
            for text, size, emphasis, span in (
                ("TESTO", 0.050, False, (0, 12)),
                ("CHIARO", 0.065, True, (12, 25)),
            )
        )
        with patch.object(captions, "_media_out", return_value=object()), \
             patch.object(captions, "_new_tool", side_effect=create_tool), \
             patch.object(captions, "connect_input", return_value=True), \
             patch.object(captions, "add_layer", return_value=object()), \
             patch.object(captions, "set_visibility_window", return_value=True), \
             patch.object(captions, "phrase_word_layout", return_value=words):
            captions.build_caption_graph(
                object(), ({"position": "LOWER", "range": (0, 25), "words": words},),
                {"burgundy": "#680C09", "white": "#FFFFFF"},
            )

        self.assertEqual(2, len(nodes))
        for node, style in zip(nodes, ("Bold", "Bold Italic")):
            with self.subTest(style=style):
                self.assertEqual(style, node.inputs["Style"])
                self.assertEqual(1.0, node.inputs["Alpha1"])
                self.assertEqual(1.0, node.inputs.get("Enabled2"))
                self.assertEqual(1.0, node.inputs.get("ElementShape2"))
                self.assertEqual(1.0, node.inputs.get("OutsideOnly2"))
                self.assertAlmostEqual(0.018, node.inputs["Thickness2"])
                self.assertAlmostEqual(0.75, node.inputs["Alpha2"])
                self.assertEqual((27, 23, 14), tuple(round(node.inputs[channel] * 255)
                                 for channel in ("Red2", "Green2", "Blue2")))

    def test_caption_executor_uses_one_full_timeline_composition(self):
        from bridge.vertical_social_captions import apply_caption_action
        cfg = SimpleNamespace(palette={"burgundy": "#6C2438", "white": "#FFFFFF"})
        with patch("bridge.vertical_social_captions.create_overlay_composition", return_value=(object(), object())) as create, \
             patch("bridge.vertical_social_captions.build_caption_graph", return_value={"cue_count": 2, "text_readback": True}) as build:
            result = apply_caption_action(object(), object(), cfg, self.action(), 60)
        create.assert_called_once()
        build.assert_called_once()
        self.assertEqual(2, result["cue_count"])

    def test_edit_fingerprint_changes_when_same_length_media_is_replaced(self):
        from bridge.vertical_social_captions import timeline_edit_fingerprint

        class Media:
            def __init__(self, unique_id): self.unique_id = unique_id
            def GetUniqueId(self): return self.unique_id
            def GetClipProperty(self): return {"File Path": f"C:/private/{self.unique_id}.mp4"}
        class Item:
            def __init__(self, unique_id): self.media = Media(unique_id)
            def GetStart(self): return 0
            def GetEnd(self): return 60
            def GetDuration(self): return 60
            def GetMediaPoolItem(self): return self.media
        class Timeline:
            def __init__(self, unique_id): self.item = Item(unique_id)
            def GetStartFrame(self): return 0
            def GetEndFrame(self): return 60
            def GetSetting(self, key):
                return {"timelineResolutionWidth": "1080", "timelineResolutionHeight": "1920",
                        "timelineFrameRate": "30", "timelinePlaybackFrameRate": "30"}[key]
            def GetTrackCount(self, kind): return 1 if kind == "video" else 0
            def GetItemListInTrack(self, kind, index): return [self.item]

        first = timeline_edit_fingerprint(Timeline("source-a"))
        second = timeline_edit_fingerprint(Timeline("source-b"))
        self.assertNotEqual(first, second)
        self.assertEqual(first, timeline_edit_fingerprint(Timeline("source-a")))
