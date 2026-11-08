from __future__ import annotations

import unittest

from bridge.resolve21_compat import compatibility_card, parse_resolve_version


class Fake:
    def __init__(self, **methods):
        self.__dict__.update(methods)


class Resolve21CompatibilityTests(unittest.TestCase):
    def test_version_parser_accepts_resolve_four_part_version(self):
        self.assertEqual((21, 2, 0, 6), parse_resolve_version("21.2.0.6"))

    def test_project_manager_is_distinct_from_unreachable_resolve(self):
        resolve = Fake(GetVersionString=lambda: "21.2.0.6")
        result = compatibility_card(resolve, Fake(), None, None)
        self.assertTrue(result["ok"])
        self.assertEqual("PROJECT_MANAGER", result["state"])
        self.assertTrue(result["supported"])
        self.assertFalse(result["native_api"]["export_thumbnails"])

    def test_live_21_2_reports_review_and_transcription_apis(self):
        media = Fake(TranscribeAudio=lambda *_: True, GetTranscription=lambda: {})
        clip = Fake(GetMediaPoolItem=lambda: media)
        timeline = Fake(
            ExportFrame=lambda *_: {},
            ExportThumbnails=lambda *_: {},
            CreateSubtitlesFromAudio=lambda *_: True,
            GetItemListInTrack=lambda *_: [clip],
        )
        resolve = Fake(GetVersionString=lambda: "21.2.0.6")
        result = compatibility_card(resolve, Fake(), Fake(), timeline)
        self.assertEqual("READY", result["state"])
        self.assertEqual(
            {
                "export_frame": True,
                "export_thumbnails": True,
                "native_transcription": True,
                "native_subtitles": True,
            },
            result["native_api"],
        )

    def test_resolve_20_is_not_supported_for_new_adapters(self):
        resolve = Fake(GetVersionString=lambda: "20.3.2")
        result = compatibility_card(resolve, Fake(), Fake(), Fake())
        self.assertFalse(result["supported"])
        self.assertEqual("UNSUPPORTED_VERSION", result["state"])


if __name__ == "__main__":
    unittest.main()
