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
        self.assertEqual((0.12, 0.80, 0.69, 0.77),
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

    def test_caption_schema_rejects_when_cutoff_removes_every_cue(self):
        from bridge.vertical_social_captions import validate_caption_action
        action = self.action()
        action["caption_cutoff_frame"] = 0
        with self.assertRaisesRegex(Exception, "prima del cutoff"):
            validate_caption_action(action, 60)

    def test_karaoke_rejects_upper_geometry_until_it_has_scaled_safe_bounds(self):
        from bridge.vertical_social_captions import validate_caption_action
        action = self.action()
        action["style"] = {"caption_mode": "KARAOKE_WORD", "uppercase": True,
                           "font_scale": 1.2}
        with self.assertRaisesRegex(Exception, "LOWER"):
            validate_caption_action(action, 60)

    def test_phrase_karaoke_validates_fixed_phrase_and_word_windows(self):
        from bridge.vertical_social_captions import validate_caption_action
        action = self.action()
        action["cues"] = [{
            "cue_id": "c1", "start_frame": 0, "end_frame": 20,
            "text": "CIAO MONDO", "position": "LOWER",
            "words": [
                {"text": "CIAO", "start_frame": 0, "end_frame": 8},
                {"text": "MONDO", "start_frame": 8, "end_frame": 20},
            ],
        }]
        action["style"] = {"caption_mode": "KARAOKE_PHRASE", "uppercase": True,
                           "font_scale": 1.2}
        result = validate_caption_action(action, 60)
        self.assertEqual("CIAO MONDO", result["cues"][0]["text"])
        self.assertEqual(((0, 8), (8, 20)),
                         tuple(word["range"] for word in result["cues"][0]["words"]))
        self.assertEqual(40, 60 - result["cues"][-1]["range"][1])

    def test_phrase_karaoke_requires_uppercase_and_twenty_percent_scale(self):
        from bridge.vertical_social_captions import validate_caption_action
        action = self.action()
        action["cues"] = [{"cue_id": "c1", "start_frame": 0, "end_frame": 20,
                           "text": "CIAO", "position": "LOWER",
                           "words": [{"text": "CIAO", "start_frame": 0, "end_frame": 20}]}]
        action["style"] = {"caption_mode": "KARAOKE_PHRASE", "uppercase": False,
                           "font_scale": 1.2}
        with self.assertRaisesRegex(Exception, "maiuscolo"):
            validate_caption_action(action, 60)
        action["style"] = {"caption_mode": "KARAOKE_PHRASE", "uppercase": True,
                           "font_scale": 1.1}
        with self.assertRaisesRegex(Exception, "1.2"):
            validate_caption_action(action, 60)

    def test_phrase_word_slots_keep_long_words_inside_two_row_safe_card(self):
        from bridge.vertical_social_captions import phrase_word_slots, measured_satoshi_bold_width
        slots = phrase_word_slots(
            ["SOPRATTUTTO", "TANTISSIME", "EFFETTIVAMENTE", "C'È"], 1.2)
        self.assertEqual(4, len(slots))
        self.assertLessEqual(len({slot["row"] for slot in slots}), 2)
        self.assertGreaterEqual(measured_satoshi_bold_width("COSTRUIAMO", 1.2), 0.29)
        self.assertTrue(all(0.15 <= slot["x"] - slot["width"] / 2
                            and slot["x"] + slot["width"] / 2 <= 0.77 for slot in slots))
        for row in {slot["row"] for slot in slots}:
            row_slots = [slot for slot in slots if slot["row"] == row]
            for left, right in zip(row_slots, row_slots[1:]):
                self.assertLessEqual(left["x"] + left["width"] / 2 + 0.015,
                                     right["x"] - right["width"] / 2)

    def test_satoshi_measurement_releases_font_when_screen_dc_allocation_fails(self):
        from bridge.vertical_social_captions import measured_satoshi_bold_width

        class Function:
            def __init__(self, result=None): self.result = result; self.calls = []
            def __call__(self, *args): self.calls.append(args); return self.result

        gdi = SimpleNamespace(
            CreateFontW=Function(123), SelectObject=Function(), GetTextFaceW=Function(),
            GetTextExtentPoint32W=Function(), DeleteObject=Function(1))
        user = SimpleNamespace(GetDC=Function(0), ReleaseDC=Function(1))
        with patch("bridge.vertical_social_captions.ctypes.WinDLL",
                   side_effect=[gdi, user]):
            with self.assertRaisesRegex(Exception, "non misurabile"):
                measured_satoshi_bold_width("TEST", 1.2)
        self.assertEqual([(123,)], gdi.DeleteObject.calls)

    def test_satoshi_measurement_releases_resources_when_font_selection_fails(self):
        from bridge.vertical_social_captions import measured_satoshi_bold_width

        class Function:
            def __init__(self, result=None): self.result = result; self.calls = []
            def __call__(self, *args): self.calls.append(args); return self.result

        gdi = SimpleNamespace(
            CreateFontW=Function(123), SelectObject=Function(0), GetTextFaceW=Function(),
            GetTextExtentPoint32W=Function(), DeleteObject=Function(1))
        user = SimpleNamespace(GetDC=Function(456), ReleaseDC=Function(1))
        with patch("bridge.vertical_social_captions.ctypes.WinDLL",
                   side_effect=[gdi, user]):
            with self.assertRaisesRegex(Exception, "non selezionabile"):
                measured_satoshi_bold_width("TEST", 1.2)
        self.assertEqual([(123,)], gdi.DeleteObject.calls)
        self.assertEqual([(None, 456)], user.ReleaseDC.calls)

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

    def test_caption_executor_uses_one_full_timeline_composition(self):
        from bridge.vertical_social_captions import apply_caption_action
        cfg = SimpleNamespace(palette={"burgundy": "#6C2438", "white": "#FFFFFF"})
        timeline = SimpleNamespace(
            GetStartFrame=lambda: 0, GetEndFrame=lambda: 60, GetName=lambda: "ARPHE_TEST")
        with patch("bridge.vertical_social_captions.create_overlay_composition", return_value=(object(), object())) as create, \
             patch("bridge.vertical_social_captions.build_caption_graph", return_value={"cue_count": 2, "text_readback": True}) as build:
            result = apply_caption_action(object(), timeline, cfg, self.action(), 60)
        create.assert_called_once()
        build.assert_called_once()
        self.assertEqual(2, result["cue_count"])

    def test_caption_executor_uses_absolute_carrier_and_local_fusion_cue_frames(self):
        from bridge.vertical_social_captions import apply_caption_action

        timeline = SimpleNamespace(
            GetStartFrame=lambda: 108000,
            GetEndFrame=lambda: 108060,
            GetName=lambda: "ARPHE_TEST",
        )
        item = SimpleNamespace(GetName=lambda: "ARPHE_CAPTIONS")
        cfg = SimpleNamespace(palette={"burgundy": "#6C2438", "white": "#FFFFFF"})
        with patch("bridge.vertical_social_captions.create_overlay_composition",
                   return_value=(item, object())) as create, \
             patch("bridge.vertical_social_captions.build_caption_graph",
                   return_value={"cue_count": 2, "text_readback": True}) as build:
            result = apply_caption_action(object(), timeline, cfg, self.action(), 60)

        self.assertEqual((108000, 108060), create.call_args.args[3:5])
        local_cues = build.call_args.args[1]
        self.assertEqual(((0, 20), (30, 60)),
                         tuple(cue["range"] for cue in local_cues))
        self.assertEqual([108000, 108060], result["range"])

    def test_caption_graph_uses_resolve_owned_keyframes_for_cue_visibility(self):
        from bridge.vertical_social_captions import build_caption_graph

        class Tool:
            def __init__(self):
                self.values = {}
            def SetInput(self, key, value, *args):
                self.values[key] = value
            def GetInput(self, key):
                return self.values.get(key)

        class Comp:
            def BezierSpline(self):
                return {}

        outer = Tool()
        cue = ({"cue_id": "c1", "range": (3, 7), "text": "Testo", "position": "LOWER"},)
        palette = {"black": "#000000", "burgundy": "#6C2438", "white": "#FFFFFF"}
        with patch("bridge.vertical_social_captions._media_out", return_value=Tool()), \
             patch("bridge.vertical_social_captions._new_tool", side_effect=lambda *args: Tool()), \
             patch("bridge.vertical_social_captions.connect_input", return_value=True), \
             patch("bridge.vertical_social_captions.add_layer", return_value=outer):
            build_caption_graph(Comp(), cue, palette)

        self.assertEqual({0: 0.0, 2: 0.0, 3: 1.0, 6: 1.0, 7: 0.0}, outer.Blend)

    def test_karaoke_graph_uses_kit_highlight_and_twenty_percent_larger_safe_text(self):
        from bridge.vertical_social_captions import build_caption_graph

        class Tool:
            def __init__(self, name=""):
                self.name = name; self.values = {}
            def SetInput(self, key, value, *args): self.values[key] = value
            def GetInput(self, key): return self.values.get(key)

        class Comp:
            def BezierSpline(self): return {}

        created = {}
        def new_tool(comp, kind, name):
            tool = Tool(name); created[name] = tool; return tool

        cue = ({"cue_id": "c1", "range": (3, 7), "text": "C'È", "position": "LOWER"},)
        palette = {"black": "#111111", "burgundy": "#6C2438",
                   "white": "#FFFFFF", "cream": "#EFE3CF"}
        with patch("bridge.vertical_social_captions._media_out", return_value=Tool()), \
             patch("bridge.vertical_social_captions._new_tool", side_effect=new_tool), \
             patch("bridge.vertical_social_captions.connect_input", return_value=True), \
             patch("bridge.vertical_social_captions.add_layer", return_value=Tool()):
            try:
                result = build_caption_graph(Comp(), cue, palette,
                                             caption_mode="KARAOKE_WORD", font_scale=1.2)
            except TypeError as exc:
                self.fail(f"stile karaoke generico non implementato: {exc}")

        text = created["ARPHE_CAPTION_001_TEXT"]
        self.assertEqual("C'È", text.values["StyledText"])
        self.assertAlmostEqual(0.060, text.values["Size"], places=6)
        self.assertAlmostEqual(239 / 255, text.values["Red1"], places=6)
        self.assertLessEqual(result["lower_layout"]["bounds"]["bottom"], 0.82)
        self.assertEqual("cream", result["highlight_role"])

    def test_caption_graph_rejects_silent_style_readback_mismatch(self):
        from bridge.vertical_social_captions import build_caption_graph

        class Tool:
            def __init__(self, name=""):
                self.name = name; self.values = {}
            def SetInput(self, key, value, *args): self.values[key] = value
            def GetInput(self, key):
                if self.name.endswith("_TEXT") and key == "Size":
                    return 0.01
                return self.values.get(key)

        class Comp:
            def BezierSpline(self): return {}

        cue = ({"cue_id": "c1", "range": (3, 7), "text": "TEST", "position": "LOWER"},)
        palette = {"black": "#111111", "burgundy": "#6C2438",
                   "white": "#FFFFFF", "cream": "#EFE3CF"}
        with patch("bridge.vertical_social_captions._media_out", return_value=Tool()), \
             patch("bridge.vertical_social_captions._new_tool",
                   side_effect=lambda comp, kind, name: Tool(name)), \
             patch("bridge.vertical_social_captions.connect_input", return_value=True), \
             patch("bridge.vertical_social_captions.add_layer", return_value=Tool()):
            with self.assertRaisesRegex(Exception, "Read-back stile"):
                build_caption_graph(Comp(), cue, palette,
                                    caption_mode="KARAOKE_WORD", font_scale=1.2)

    def test_phrase_karaoke_keeps_full_phrase_and_moves_only_active_highlight(self):
        from bridge.vertical_social_captions import build_caption_graph

        class Tool:
            def __init__(self, name=""):
                self.name = name; self.values = {}
            def SetInput(self, key, value, *args): self.values[key] = value
            def GetInput(self, key): return self.values.get(key)

        class Comp:
            def BezierSpline(self): return {}

        created = {}
        def new_tool(comp, kind, name):
            tool = Tool(name); created[name] = tool; return tool

        cue = ({
            "cue_id": "c1", "range": (3, 11),
            "text": "SOPRATTUTTO TANTISSIME EFFETTIVAMENTE C'È", "position": "LOWER",
            "words": (
                {"text": "SOPRATTUTTO", "range": (3, 5)},
                {"text": "TANTISSIME", "range": (5, 7)},
                {"text": "EFFETTIVAMENTE", "range": (7, 9)},
                {"text": "C'È", "range": (9, 11)},
            ),
        },)
        palette = {"black": "#111111", "burgundy": "#6C2438", "beige": "#D7C2A6",
                   "white": "#FFFFFF", "cream": "#EFE3CF"}
        with patch("bridge.vertical_social_captions._media_out", return_value=Tool()), \
             patch("bridge.vertical_social_captions._new_tool", side_effect=new_tool), \
             patch("bridge.vertical_social_captions.connect_input", return_value=True), \
             patch("bridge.vertical_social_captions.add_layer", return_value=Tool()):
            result = build_caption_graph(Comp(), cue, palette,
                                         caption_mode="KARAOKE_PHRASE", font_scale=1.2)

        first_base = created["ARPHE_CAPTION_001_WORD_001_BASE"]
        first_active = created["ARPHE_CAPTION_001_WORD_001_ACTIVE"]
        second_base = created["ARPHE_CAPTION_001_WORD_002_BASE"]
        second_active = created["ARPHE_CAPTION_001_WORD_002_ACTIVE"]
        self.assertEqual(("SOPRATTUTTO", "TANTISSIME"),
                         (first_base.values["StyledText"], second_base.values["StyledText"]))
        self.assertEqual(first_base.values["Center"], first_active.values["Center"])
        self.assertEqual(second_base.values["Center"], second_active.values["Center"])
        self.assertEqual({0: 0.0, 2: 0.0, 3: 1.0, 4: 1.0, 5: 0.0},
                         created["ARPHE_CAPTION_001_WORD_001_ACTIVE_MERGE"].Blend)
        self.assertEqual({0: 0.0, 4: 0.0, 5: 1.0, 6: 1.0, 7: 0.0},
                         created["ARPHE_CAPTION_001_WORD_002_ACTIVE_MERGE"].Blend)
        self.assertEqual(4, result["active_word_count"])
        self.assertTrue(result["phrase_stable"])
        self.assertEqual(0.16, result["lower_layout"]["height"])
        self.assertLessEqual(result["lower_layout"]["bounds"]["bottom"], 0.82)

    def test_phrase_card_karaoke_moves_burgundy_card_behind_spoken_word(self):
        from bridge.vertical_social_captions import build_caption_graph

        class Tool:
            def __init__(self, name=""):
                self.name = name; self.values = {}
            def SetInput(self, key, value, *args): self.values[key] = value
            def GetInput(self, key): return self.values.get(key)

        class Comp:
            def BezierSpline(self): return {}

        created = {}
        def new_tool(comp, kind, name):
            tool = Tool(name); created[name] = tool; return tool

        cue = ({
            "cue_id": "c1", "range": (3, 11),
            "text": "SOPRATTUTTO TANTISSIME EFFETTIVAMENTE C'È", "position": "LOWER",
            "words": (
                {"text": "SOPRATTUTTO", "range": (3, 5)},
                {"text": "TANTISSIME", "range": (5, 7)},
                {"text": "EFFETTIVAMENTE", "range": (7, 9)},
                {"text": "C'È", "range": (9, 11)},
            ),
        },)
        palette = {"black": "#111111", "burgundy": "#6C2438", "beige": "#D7C2A6",
                   "white": "#FFFFFF", "cream": "#EFE3CF"}
        with patch("bridge.vertical_social_captions._media_out", return_value=Tool()), \
             patch("bridge.vertical_social_captions._new_tool", side_effect=new_tool), \
             patch("bridge.vertical_social_captions.connect_input", return_value=True), \
             patch("bridge.vertical_social_captions.add_layer", return_value=Tool()):
            result = build_caption_graph(
                Comp(), cue, palette, caption_mode="KARAOKE_PHRASE_CARD", font_scale=1.2)

        self.assertNotIn("ARPHE_CAPTION_001_BG", created)
        for word_index, expected_blend in enumerate((
                {0: 0.0, 2: 0.0, 3: 1.0, 4: 1.0, 5: 0.0},
                {0: 0.0, 4: 0.0, 5: 1.0, 6: 1.0, 7: 0.0},
                {0: 0.0, 6: 0.0, 7: 1.0, 8: 1.0, 9: 0.0}), start=1):
            stem = f"ARPHE_CAPTION_001_WORD_{word_index:03d}"
            base = created[f"{stem}_BASE"]
            mask = created[f"{stem}_HIGHLIGHT_MASK"]
            self.assertEqual(base.values["Center"], mask.values["Center"])
            self.assertGreater(mask.values["Width"], base.values["LayoutWidth"])
            self.assertEqual(expected_blend, created[f"{stem}_HIGHLIGHT_MERGE"].Blend)
            self.assertEqual(expected_blend, created[f"{stem}_ACTIVE_MERGE"].Blend)
        self.assertEqual("burgundy", result["highlight_card_role"])
        self.assertFalse(result["full_phrase_card"])
        self.assertTrue(result["phrase_stable"])

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
