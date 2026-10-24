from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from bridge import server
from bridge.asset_tools import add_asset
from bridge.config import DEFAULT_FLAGS
from bridge.safety import ValidationError


class FakeItem:
    def __init__(self, start: int, end: int):
        self.start = start
        self.end = end
        self.name = ""

    def GetStart(self):
        return self.start

    def GetEnd(self):
        return self.end

    def SetName(self, name):
        self.name = name
        return True


class FakeTimeline:
    def __init__(self, *, fail_add_after=None, bad_count_after_add=False):
        self.video_tracks = 1
        self.fail_add_after = fail_add_after
        self.add_calls = 0
        self.bad_count_after_add = bad_count_after_add
        self.deleted_clips = []
        self.deleted_tracks = []

    def GetName(self):
        return "ARPHE_ASSET_TEST"

    def GetTrackCount(self, track_type):
        if self.bad_count_after_add and self.add_calls:
            return None
        return self.video_tracks if track_type == "video" else 0

    def AddTrack(self, track_type):
        if track_type != "video":
            return False
        self.add_calls += 1
        if self.fail_add_after is not None and self.add_calls > self.fail_add_after:
            return False
        self.video_tracks += 1
        return True

    def DeleteClips(self, items, ripple=False):
        self.deleted_clips.extend(items)
        return not ripple

    def DeleteTrack(self, track_type, track_index):
        if track_type != "video" or track_index != self.video_tracks:
            return False
        self.deleted_tracks.append(track_index)
        self.video_tracks -= 1
        return True


class FakePool:
    def __init__(self, timeline, *, wrong_range=False, append_empty=False, append_multiple=False):
        self.timeline = timeline
        self.wrong_range = wrong_range
        self.append_empty = append_empty
        self.append_multiple = append_multiple
        self.records = []

    def CreateEmptyTimeline(self, _name):
        return object()

    def ImportMedia(self, paths):
        return [SimpleNamespace(path=paths[0])]

    def AppendToTimeline(self, records):
        self.records.extend(records)
        record = records[0]
        if record["trackIndex"] > self.timeline.video_tracks:
            return []
        if self.append_empty:
            return []
        start = record["recordFrame"]
        end = start + record["endFrame"] - record["startFrame"] + 1
        if self.wrong_range:
            end += 60
        item = FakeItem(start, end)
        return [item, FakeItem(start, end)] if self.append_multiple else [item]


class FakeProject:
    def __init__(self, pool):
        self.pool = pool

    def GetName(self):
        return "ARPHE_ASSET_PROJECT"

    def GetMediaStorage(self):
        return None

    def GetMediaPool(self):
        return self.pool

    def SetCurrentTimeline(self, _timeline):
        return True

    def GetTimelineCount(self):
        return 1

    def GetTimelineByIndex(self, _index):
        return object()

    def GetSetting(self, _name):
        return ""

    def SetSetting(self, _name, _value):
        return True


class AssetToolTests(unittest.TestCase):
    def config(self, root: Path):
        return SimpleNamespace(
            flags={**DEFAULT_FLAGS, "CAP_ASSETS": True},
            asset_root=root,
            media_roots=(),
            allowed_timelines=frozenset(),
        )

    def registry(self):
        return SimpleNamespace(timeline_allowed=lambda _project, _timeline: True)

    def test_image_asset_creates_missing_track_and_uses_explicit_source_range(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            image = root / "chart.png"
            image.write_bytes(b"png")
            timeline = FakeTimeline()
            pool = FakePool(timeline)

            result = add_asset(
                FakeProject(pool), timeline, self.config(root), self.registry(),
                str(image), "image", 30, 120, 2,
            )

            self.assertTrue(result["ok"])
            self.assertEqual(2, timeline.video_tracks)
            self.assertEqual({
                "mediaPoolItem": pool.records[0]["mediaPoolItem"],
                "startFrame": 0,
                "endFrame": 89,
                "recordFrame": 30,
                "mediaType": 1,
                "trackIndex": 2,
            }, pool.records[0])

    def test_image_asset_rejects_unverified_timeline_range(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            image = root / "chart.png"
            image.write_bytes(b"png")
            timeline = FakeTimeline()
            pool = FakePool(timeline, wrong_range=True)

            with self.assertRaisesRegex(ValidationError, "range"):
                add_asset(
                    FakeProject(pool), timeline, self.config(root), self.registry(),
                    str(image), "image", 30, 120, 2,
                )
            self.assertEqual(1, timeline.video_tracks)
            self.assertEqual([2], timeline.deleted_tracks)
            self.assertEqual(1, len(timeline.deleted_clips))

    def test_image_asset_rolls_back_new_track_when_append_returns_no_item(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            image = root / "chart.png"
            image.write_bytes(b"png")
            timeline = FakeTimeline()
            pool = FakePool(timeline, append_empty=True)

            with self.assertRaisesRegex(ValidationError, "non verificabile"):
                add_asset(
                    FakeProject(pool), timeline, self.config(root), self.registry(),
                    str(image), "image", 30, 120, 2,
                )
            self.assertEqual(1, timeline.video_tracks)
            self.assertEqual([2], timeline.deleted_tracks)
            self.assertEqual([], timeline.deleted_clips)

    def test_image_asset_rolls_back_tracks_when_later_track_creation_fails(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            image = root / "chart.png"
            image.write_bytes(b"png")
            timeline = FakeTimeline(fail_add_after=1)
            pool = FakePool(timeline)

            with self.assertRaisesRegex(ValidationError, "creare la traccia"):
                add_asset(
                    FakeProject(pool), timeline, self.config(root), self.registry(),
                    str(image), "image", 30, 120, 3,
                )
            self.assertEqual(1, timeline.video_tracks)
            self.assertEqual([2], timeline.deleted_tracks)
            self.assertEqual([], pool.records)

    def test_image_asset_keeps_preexisting_track_when_append_returns_no_item(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            image = root / "chart.png"
            image.write_bytes(b"png")
            timeline = FakeTimeline()
            pool = FakePool(timeline, append_empty=True)

            with self.assertRaisesRegex(ValidationError, "non verificabile"):
                add_asset(
                    FakeProject(pool), timeline, self.config(root), self.registry(),
                    str(image), "image", 30, 120, 1,
                )
            self.assertEqual(1, timeline.video_tracks)
            self.assertEqual([], timeline.deleted_tracks)

    def test_image_asset_removes_all_returned_items_when_append_returns_multiple(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            image = root / "chart.png"
            image.write_bytes(b"png")
            timeline = FakeTimeline()
            pool = FakePool(timeline, append_multiple=True)

            with self.assertRaisesRegex(ValidationError, "non verificabile"):
                add_asset(
                    FakeProject(pool), timeline, self.config(root), self.registry(),
                    str(image), "image", 30, 120, 2,
                )
            self.assertEqual(1, timeline.video_tracks)
            self.assertEqual([2], timeline.deleted_tracks)
            self.assertEqual(2, len(timeline.deleted_clips))

    def test_image_asset_rolls_back_when_track_count_readback_is_incoherent(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            image = root / "chart.png"
            image.write_bytes(b"png")
            timeline = FakeTimeline(fail_add_after=1, bad_count_after_add=True)
            pool = FakePool(timeline)

            with self.assertRaisesRegex(ValidationError, "traccia|Rollback"):
                add_asset(
                    FakeProject(pool), timeline, self.config(root), self.registry(),
                    str(image), "image", 30, 120, 2,
                )
            self.assertEqual(1, timeline.video_tracks)
            self.assertEqual([2], timeline.deleted_tracks)
            self.assertEqual([], pool.records)

    def test_public_asset_tool_holds_global_resolve_lock(self):
        class TrackingLock:
            active = False

            def __enter__(self):
                self.active = True

            def __exit__(self, *_args):
                self.active = False

        lock = TrackingLock()

        def checked_call(*_args):
            self.assertTrue(lock.active)
            return {"ok": True}

        runtime = (None, None, object(), object(), object(), object(), None)
        with patch.object(server, "RESOLVE_ACCESS_LOCK", lock), \
             patch.object(server, "_runtime", return_value=runtime), \
             patch.object(server, "_call", side_effect=checked_call):
            result = server.add_image_asset("chart.png", 0, 30)
        self.assertTrue(result["ok"])


if __name__ == "__main__":
    unittest.main()
