from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge import vertical_social_captions as captions


class CaptionLayoutRegressionTests(unittest.TestCase):
    def setUp(self):
        self.captions = captions

    @staticmethod
    def phrase(position="LOWER"):
        return {
            "position": position,
            "words": (
                {"text": "CERCHIAMO", "range": (0, 8), "emphasis": False},
                {"text": "UN", "range": (8, 11), "emphasis": False},
                {"text": "MEDICO", "range": (11, 17), "emphasis": False},
                {"text": "DERMATOLOGO,", "range": (17, 26), "emphasis": True},
            ),
        }

    def assert_rows_are_safe(self, phrase, words):
        if phrase["position"] == "UPPER":
            center_x = 0.5
            span = self.captions.upper_karaoke_layout()["span"]
        else:
            layout = self.captions.lower_caption_layout()
            center_x = layout["center"]["x"]
            span = layout["width"]
        safe_left = center_x - span / 2
        safe_right = center_x + span / 2
        rows = sorted({word["row_index"] for word in words})
        self.assertLessEqual(len(rows), 2)
        for row in rows:
            row_words = [word for word in words if word["row_index"] == row]
            self.assertGreaterEqual(
                row_words[0]["x"] - row_words[0]["card_width"] / 2,
                safe_left - 1e-5,
            )
            self.assertLessEqual(
                row_words[-1]["x"] + row_words[-1]["card_width"] / 2,
                safe_right + 1e-5,
            )
            for left, right in zip(row_words, row_words[1:]):
                gap = (
                    right["x"] - right["card_width"] / 2
                    - (left["x"] + left["card_width"] / 2)
                )
                self.assertGreaterEqual(gap, 0.0139)

    def test_dense_phrase_uses_only_two_canonical_sizes_and_two_rows(self):
        phrase = self.phrase()
        words = self.captions.phrase_word_layout(phrase)

        self.assertEqual({word["font_size"] for word in words}, {0.050, 0.065})
        self.assertEqual({word["row_index"] for word in words}, {0, 1})
        self.assertEqual([word["text"] for word in words], [word["text"] for word in phrase["words"]])
        self.assertEqual([word["range"] for word in words], [word["range"] for word in phrase["words"]])
        self.assert_rows_are_safe(phrase, words)

    def test_long_emphasized_words_keep_the_emphasis_size_and_card_padding(self):
        for text in ("DERMATOLOGO,", "POLIAMBULATORIO,", "COLLABORAZIONE", "CONTATTACI"):
            with self.subTest(text=text):
                phrase = {
                    "position": "LOWER",
                    "words": ({"text": text, "range": (0, 20), "emphasis": True},),
                }
                word = self.captions.phrase_word_layout(phrase)[0]
                self.assertEqual(word["font_size"], 0.065)
                self.assertAlmostEqual(word["card_width"] - word["text_width"], 0.016, places=5)
                self.assert_rows_are_safe(phrase, (word,))

    def test_upper_and_lower_layouts_keep_fixed_sizes_and_distinct_row_positions(self):
        for position in ("UPPER", "LOWER"):
            with self.subTest(position=position):
                phrase = self.phrase(position)
                words = self.captions.phrase_word_layout(phrase)
                self.assertTrue(all(word["font_size"] in {0.050, 0.065} for word in words))
                row_y = {word["row_index"]: word["y"] for word in words}
                self.assertEqual(len(row_y), 2)
                self.assertNotEqual(row_y[0], row_y[1])
                self.assert_rows_are_safe(phrase, words)

    def test_two_rows_stay_inside_vertical_story_safe_area(self):
        for position in ("UPPER", "LOWER"):
            with self.subTest(position=position):
                words = self.captions.phrase_word_layout(self.phrase(position))
                height = (self.captions.upper_karaoke_layout()["height"]
                          if position == "UPPER"
                          else self.captions.lower_caption_layout()["height"])
                self.assertLessEqual(max(word["y"] + height / 2 for word in words), 0.90)
                self.assertGreaterEqual(min(word["y"] - height / 2 for word in words), 0.18)

    def test_glyph_measurement_keeps_punctuation_narrower_than_wide_letters(self):
        phrase = {
            "position": "LOWER",
            "words": (
                {"text": "III,", "range": (0, 5), "emphasis": False},
                {"text": "WWW", "range": (5, 10), "emphasis": False},
            ),
        }
        words = self.captions.phrase_word_layout(phrase)

        self.assertEqual([word["font_size"] for word in words], [0.050, 0.050])
        self.assertLess(words[0]["text_width"], words[1]["text_width"])

    def test_grouping_splits_before_a_candidate_that_cannot_fit_two_rows(self):
        cues = tuple(
            {
                "text": text,
                "range": (index * 5, index * 5 + 5),
                "position": "LOWER",
                "emphasis": index == 2,
            }
            for index, text in enumerate(
                ("COLLABORAZIONE", "POLIAMBULATORIO", "DERMATOLOGO", "COLLABORAZIONE", "POLIAMBULATORIO")
            )
        )

        phrases = self.captions.phrase_groups_from_word_cues(
            cues, max_words=20, max_characters=200, pause_frames=100
        )

        self.assertGreater(len(phrases), 1)
        flattened = [word["text"] for phrase in phrases for word in phrase["words"]]
        self.assertEqual(flattened, [cue["text"] for cue in cues])
        for phrase in phrases:
            self.assert_rows_are_safe(phrase, self.captions.phrase_word_layout(phrase))

    def test_fusion_builder_uses_each_words_row_position_and_canonical_size(self):
        class FakeTool:
            def __init__(self, reg_id, name):
                self.reg_id = reg_id
                self.name = name
                self.inputs = {}

            def SetInput(self, name, value, *args):
                self.inputs[name] = value

            def GetInput(self, name):
                return self.inputs.get(name)

        phrase = self.phrase()
        phrase["range"] = (0, 26)
        phrase["phrase_id"] = "phrase_001"
        created = []

        def new_tool(_comp, reg_id, name):
            tool = FakeTool(reg_id, name)
            created.append(tool)
            return tool

        palette = {"black": "#000000", "burgundy": "#852542", "white": "#FFFFFF"}
        fake_media_out = FakeTool("MediaOut", "MediaOut1")
        with (
            patch.object(self.captions, "_media_out", return_value=fake_media_out),
            patch.object(self.captions, "_new_tool", side_effect=new_tool),
            patch.object(self.captions, "_set_color", return_value=None),
            patch.object(self.captions, "connect_input", return_value=True),
            patch.object(self.captions, "add_layer", side_effect=lambda *_args: object()),
            patch.object(self.captions, "set_visibility_window", return_value=True),
        ):
            self.captions.build_caption_graph(object(), (phrase,), palette)

        layout = self.captions.phrase_word_layout(phrase)
        text_tools = [tool for tool in created if tool.reg_id == "TextPlus"]
        mask_tools = [tool for tool in created if tool.reg_id == "RectangleMask"]
        expected_y = [word["y"] for word in layout]
        self.assertEqual([tool.inputs["Center"][2] for tool in text_tools], expected_y)
        self.assertEqual([tool.inputs["Center"][2] for tool in mask_tools], expected_y)
        self.assertEqual([tool.inputs["Size"] for tool in text_tools], [word["font_size"] for word in layout])


if __name__ == "__main__":
    unittest.main()
