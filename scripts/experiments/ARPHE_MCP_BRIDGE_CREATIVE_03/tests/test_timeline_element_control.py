from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from bridge.safety import ValidationError
from bridge.timeline_element_control import (
    TimelineElementSnapshot,
    TimelineElementStore,
    capture_item_snapshot,
    execute_element_removal,
    inspect_elements,
    prepare_element_removal,
    register_created_item,
    set_element_enabled,
    snapshot_fingerprint,
)


UTC = timezone.utc
NOW = datetime(2026, 11, 14, 10, 0, tzinfo=UTC)


def snapshot(**changes: object) -> TimelineElementSnapshot:
    values: dict[str, object] = {
        "workstation_id": "PC_PERSONALE",
        "project_name": "ARPHE_ADV",
        "timeline_name": "ARPHE_MASTER",
        "media_type": "video",
        "track_index": 2,
        "start_frame": 100,
        "end_frame": 150,
        "duration_frames": 50,
        "display_name": "Titolo sicuro",
        "media_identity": "media-123",
        "enabled": True,
    }
    values.update(changes)
    return TimelineElementSnapshot(**values)


class FakeNamed:
    def __init__(self, name: str):
        self.name = name

    def GetName(self):
        return self.name


class FakeMediaPoolItem:
    def GetMediaId(self):
        return "media-id-7"

    def GetClipProperty(self, key=None):
        values = {
            "File Path": r"C:\secret\patient\source.mov",
            "Clip Name": "Source clip",
            "Reel Name": "A001",
        }
        return values if key is None else values.get(key)


class FakeItem:
    def GetStart(self):
        return 100

    def GetEnd(self):
        return 150

    def GetDuration(self):
        return 50

    def GetName(self):
        return "  Bad / name\nwith path C:\\secret\\source.mov  "

    def GetMediaPoolItem(self):
        return FakeMediaPoolItem()

    def GetClipEnabled(self):
        return True


class TimelineElementStoreTests(unittest.TestCase):
    def test_snapshot_fingerprint_is_deterministic_and_changes_for_every_identity_field(self):
        original = snapshot()
        self.assertEqual(snapshot_fingerprint(original), snapshot_fingerprint(original))
        self.assertEqual(
            {
                "workstation_id", "project_name", "timeline_name", "media_type",
                "track_index", "start_frame", "end_frame", "duration_frames",
                "display_name", "media_identity", "enabled",
            },
            set(original.__dataclass_fields__),
        )
        variants = {
            "workstation_id": "PC_SEGRETERIA",
            "project_name": "ARPHE_ALTRO",
            "timeline_name": "ARPHE_ALTRO_MASTER",
            "media_type": "audio",
            "track_index": 3,
            "start_frame": 101,
            "end_frame": 151,
            "duration_frames": 49,
            "display_name": "Altro titolo",
            "media_identity": "media-456",
            "enabled": False,
        }
        for field, value in variants.items():
            with self.subTest(field=field):
                self.assertNotEqual(
                    snapshot_fingerprint(original),
                    snapshot_fingerprint(replace(original, **{field: value})),
                )

    def test_capture_snapshot_sanitizes_name_and_never_persists_source_path(self):
        captured = capture_item_snapshot(
            "PC_PERSONALE", FakeNamed("ARPHE_ADV"), FakeNamed("ARPHE_MASTER"),
            "video", 2, FakeItem(),
        )
        self.assertNotIn("\\", captured.display_name)
        self.assertNotIn("\n", captured.display_name)
        self.assertNotIn("secret", captured.display_name.casefold())
        self.assertEqual("media-id-7", captured.media_identity)

    def test_store_rejects_foreign_workstation_file(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "elements.json"
            path.write_text(json.dumps({
                "schema": "ARPHE_TIMELINE_ELEMENT_CONTROL_V1",
                "workstation_id": "PC_SEGRETERIA",
                "handles": {}, "ownership": {}, "removals": {},
            }), encoding="utf-8")
            store = TimelineElementStore(path, "PC_PERSONALE")
            with self.assertRaisesRegex(ValidationError, "workstation"):
                store.issue_handle(snapshot())

    def test_handle_expires_and_cannot_be_reused_as_live(self):
        with TemporaryDirectory() as directory:
            store = TimelineElementStore(
                Path(directory) / "elements.json", "PC_PERSONALE",
                handle_ttl_seconds=5,
            )
            handle = store.issue_handle(snapshot(), now=NOW)
            live = store.require_handle(handle["element_id"], handle["fingerprint"], NOW)
            self.assertEqual(handle["element_id"], live["element_id"])
            with self.assertRaisesRegex(ValidationError, "scadut"):
                store.require_handle(
                    handle["element_id"], handle["fingerprint"],
                    NOW + timedelta(seconds=6),
                )

    def test_ownership_requires_exact_project_timeline_track_range_and_media_identity(self):
        with TemporaryDirectory() as directory:
            store = TimelineElementStore(Path(directory) / "elements.json", "PC_PERSONALE")
            owned = snapshot()
            record = store.register_ownership(owned, "create_fusion_title", "native-ref-1", now=NOW)
            self.assertEqual(record, store.matching_ownership(owned))
            variants = (
                replace(owned, project_name="ARPHE_OTHER"),
                replace(owned, timeline_name="ARPHE_OTHER_MASTER"),
                replace(owned, track_index=3),
                replace(owned, start_frame=101, end_frame=151),
                replace(owned, media_identity="media-other"),
            )
            for changed in variants:
                with self.subTest(changed=changed):
                    self.assertIsNone(store.matching_ownership(changed))

    def test_proposal_is_single_use_and_persists_durable_intent(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "elements.json"
            store = TimelineElementStore(path, "PC_PERSONALE")
            owned = snapshot()
            handle = store.issue_handle(owned, now=NOW)
            ownership = store.register_ownership(owned, "create_fusion_title", "native-ref-1", now=NOW)
            proposal = store.prepare_removal(handle, ownership, NOW)
            intent = store.begin_removal(
                proposal["removal_id"], proposal["proposal_fingerprint"], "ALESSIO", NOW,
            )
            self.assertEqual("INTENT", intent["state"])
            persisted = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual("INTENT", persisted["removals"][proposal["removal_id"]]["state"])
            with self.assertRaisesRegex(ValidationError, "già usata|stato"):
                store.begin_removal(
                    proposal["removal_id"], proposal["proposal_fingerprint"], "ALESSIO", NOW,
                )

    def test_atomic_store_preserves_previous_file_when_replace_fails(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "elements.json"
            store = TimelineElementStore(path, "PC_PERSONALE")
            store.issue_handle(snapshot(), now=NOW)
            previous = path.read_bytes()
            with patch("bridge.timeline_element_control.os.replace", side_effect=OSError("disk failure")):
                with self.assertRaises(OSError):
                    store.issue_handle(replace(snapshot(), start_frame=200, end_frame=250), now=NOW)
            self.assertEqual(previous, path.read_bytes())

    def test_register_created_item_persists_exact_post_readback_ownership(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            timeline = LiveTimeline()
            item = LiveItem(10, 40, "Caption overlay", "caption-media")
            timeline.tracks["video"][1] = [item]
            project = LiveProject(timeline)
            config = SimpleNamespace(
                workstation_id="PC_PERSONALE",
                timeline_element_control_path=root / "control.json",
                timeline_element_handle_ttl_seconds=300,
                timeline_element_removal_ttl_seconds=600,
            )
            evidence = register_created_item(
                config, project, timeline, "video", 1, item,
                "create_vertical_social_caption", "caption-action-cap",
            )
            self.assertRegex(evidence["ownership_id"], r"^ownership_[0-9a-f]{32}$")
            store = TimelineElementStore(root / "control.json", "PC_PERSONALE")
            snap = capture_item_snapshot(
                "PC_PERSONALE", project, timeline, "video", 1, item,
            )
            self.assertIsNotNone(store.matching_ownership(snap))


class LiveMediaPoolItem:
    def __init__(self, media_id: str):
        self.media_id = media_id

    def GetMediaId(self):
        return self.media_id


class LiveItem:
    def __init__(self, start: int, end: int, name: str, media_id: str, enabled: bool = True):
        self.start = start
        self.end = end
        self.name = name
        self.media = LiveMediaPoolItem(media_id)
        self.enabled = enabled
        self.set_calls: list[bool] = []

    def GetStart(self): return self.start
    def GetEnd(self): return self.end
    def GetDuration(self): return self.end - self.start
    def GetName(self): return self.name
    def GetMediaPoolItem(self): return self.media
    def GetClipEnabled(self): return self.enabled

    def SetClipEnabled(self, value):
        self.set_calls.append(value)
        self.enabled = value
        return True


class LiveTimeline:
    def __init__(self, name: str = "ARPHE_MASTER"):
        self.name = name
        self.tracks = {"video": {1: []}, "audio": {1: []}}
        self.links: dict[LiveItem, list[LiveItem]] = {}
        self.delete_calls: list[tuple[list[LiveItem], bool]] = []
        self.delete_result = True

    def GetName(self): return self.name
    def GetTrackCount(self, media_type): return max(self.tracks[media_type], default=0)
    def GetItemListInTrack(self, media_type, track): return list(self.tracks[media_type].get(track, []))
    def GetLinkedItems(self, item): return list(self.links.get(item, []))

    def DeleteClips(self, items, ripple):
        selected = list(items)
        self.delete_calls.append((selected, ripple))
        if not self.delete_result:
            return False
        for tracks in self.tracks.values():
            for track_items in tracks.values():
                for item in selected:
                    if item in track_items:
                        track_items.remove(item)
        return True


class LiveProject:
    def __init__(self, timeline: LiveTimeline, name: str = "ARPHE_ADV"):
        self.timeline = timeline
        self.name = name

    def GetName(self): return self.name
    def GetCurrentTimeline(self): return self.timeline


class LiveRegistry:
    def __init__(self, allowed: bool = True): self.allowed = allowed
    def project_allowed(self, _project): return self.allowed
    def timeline_allowed(self, _project, _timeline): return self.allowed


def live_config(root: Path, locked: bool = False):
    plans_path = root / "vertical_social_plans.json"
    if locked:
        plans_path.write_text(json.dumps({
            "workstation_id": "PC_PERSONALE",
            "plans": {
                "vertical_0123456789abcdef0123456789abcdef": {
                    "plan_id": "vertical_0123456789abcdef0123456789abcdef",
                    "version": 1,
                    "workstation_id": "PC_PERSONALE",
                    "target": {"project": "ARPHE_ADV", "timeline": "ARPHE_MASTER"},
                    "actions": [],
                }
            },
        }), encoding="utf-8")
        plans_path.with_name("vertical_social_plans_workflow.json").write_text(json.dumps({
            "vertical_0123456789abcdef0123456789abcdef": {
                "fingerprint": "a" * 64, "state": "APPROVED", "picture_locked": True,
            }
        }), encoding="utf-8")
    return SimpleNamespace(
        workstation_id="PC_PERSONALE",
        allowed_projects=frozenset(),
        allowed_timelines=frozenset(),
        flags={"CAP_TIMELINE_ELEMENT_CONTROL": True},
        vertical_social_plans_path=plans_path,
    )


class TimelineElementLiveTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = TimelineElementStore(self.root / "elements.json", "PC_PERSONALE")
        self.timeline = LiveTimeline()
        self.video = LiveItem(100, 150, "Titolo / sicuro", "video-1")
        self.audio = LiveItem(100, 150, "Dialogo", "audio-1")
        self.timeline.tracks["video"][1] = [self.video]
        self.timeline.tracks["audio"][1] = [self.audio]
        self.project = LiveProject(self.timeline)
        self.registry = LiveRegistry()
        self.config = live_config(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def inspect(self):
        return inspect_elements(
            self.project, self.timeline, self.config, self.registry, self.store, now=NOW,
        )

    def test_inspection_returns_opaque_handles_and_sanitized_fields_for_each_track_item(self):
        result = self.inspect()
        self.assertEqual(2, len(result["elements"]))
        for element in result["elements"]:
            self.assertRegex(element["element_id"], r"^element_[0-9a-f]{32}$")
            self.assertEqual(64, len(element["fingerprint"]))
            self.assertNotIn("/", element["display_name"])
            self.assertNotIn("media_identity", element)
            self.assertNotIn("snapshot", element)

    def test_inspection_reports_linked_peer_without_grouping_mutations(self):
        self.timeline.links = {self.video: [self.audio], self.audio: [self.video]}
        result = self.inspect()
        video = next(item for item in result["elements"] if item["media_type"] == "video")
        audio = next(item for item in result["elements"] if item["media_type"] == "audio")
        self.assertEqual([audio["fingerprint"]], video["related_fingerprints"])
        set_element_enabled(
            self.project, self.timeline, self.config, self.registry, self.store,
            video["element_id"], video["fingerprint"], False, NOW,
        )
        self.assertFalse(self.video.enabled)
        self.assertTrue(self.audio.enabled)
        self.assertEqual([], self.audio.set_calls)

    def test_disable_and_enable_are_idempotent_and_verified_by_readback(self):
        element = self.inspect()["elements"][0]
        disabled = set_element_enabled(
            self.project, self.timeline, self.config, self.registry, self.store,
            element["element_id"], element["fingerprint"], False, NOW,
        )
        self.assertTrue(disabled["ok"])
        self.assertFalse(disabled["idempotent"])
        self.assertEqual([False], self.video.set_calls)
        refreshed = inspect_elements(
            self.project, self.timeline, self.config, self.registry, self.store,
            media_type="video", now=NOW,
        )["elements"][0]
        enabled = set_element_enabled(
            self.project, self.timeline, self.config, self.registry, self.store,
            refreshed["element_id"], refreshed["fingerprint"], True, NOW,
        )
        self.assertTrue(enabled["ok"])
        self.assertTrue(self.video.enabled)

    def test_repeat_request_accepts_only_enabled_state_drift_to_the_requested_value(self):
        element = self.inspect()["elements"][0]
        self.video.enabled = False
        result = set_element_enabled(
            self.project, self.timeline, self.config, self.registry, self.store,
            element["element_id"], element["fingerprint"], False, NOW,
        )
        self.assertTrue(result["idempotent"])
        self.assertEqual([], self.video.set_calls)

    def test_mutation_rejects_expired_handle_before_set_clip_enabled(self):
        self.store = TimelineElementStore(
            self.root / "expiring.json", "PC_PERSONALE", handle_ttl_seconds=1,
        )
        element = self.inspect()["elements"][0]
        with self.assertRaisesRegex(ValidationError, "scadut"):
            set_element_enabled(
                self.project, self.timeline, self.config, self.registry, self.store,
                element["element_id"], element["fingerprint"], False,
                NOW + timedelta(seconds=2),
            )
        self.assertEqual([], self.video.set_calls)

    def test_mutation_rejects_ambiguous_live_rematch(self):
        element = self.inspect()["elements"][0]
        duplicate = LiveItem(100, 150, "Titolo / sicuro", "video-1")
        self.timeline.tracks["video"][1].append(duplicate)
        with self.assertRaisesRegex(ValidationError, "ambigu|univoc"):
            set_element_enabled(
                self.project, self.timeline, self.config, self.registry, self.store,
                element["element_id"], element["fingerprint"], False, NOW,
            )
        self.assertEqual([], self.video.set_calls)
        self.assertEqual([], duplicate.set_calls)

    def test_mutation_rejects_changed_project_timeline_track_range_media_name_or_enabled_state(self):
        changes = (
            lambda project, timeline, video: setattr(project, "name", "ARPHE_OTHER"),
            lambda project, timeline, video: setattr(timeline, "name", "ARPHE_OTHER_MASTER"),
            lambda project, timeline, video: timeline.tracks["video"].setdefault(2, []).append(timeline.tracks["video"][1].pop()),
            lambda project, timeline, video: setattr(video, "start", 101),
            lambda project, timeline, video: setattr(video.media, "media_id", "video-2"),
            lambda project, timeline, video: setattr(video, "name", "Altro titolo"),
            lambda project, timeline, video: setattr(video, "enabled", False),
        )
        for change in changes:
            with self.subTest(change=change):
                with TemporaryDirectory() as directory:
                    root = Path(directory)
                    store = TimelineElementStore(root / "elements.json", "PC_PERSONALE")
                    timeline = LiveTimeline()
                    video = LiveItem(100, 150, "Titolo / sicuro", "video-1")
                    timeline.tracks["video"][1] = [video]
                    project = LiveProject(timeline)
                    registry = LiveRegistry()
                    config = live_config(root)
                    element = inspect_elements(
                        project, timeline, config, registry, store,
                        media_type="video", now=NOW,
                    )["elements"][0]
                    change(project, timeline, video)
                    with self.assertRaises(ValidationError):
                        set_element_enabled(
                            project, timeline, config, registry, store,
                            element["element_id"], element["fingerprint"], True, NOW,
                        )
                    self.assertEqual([], video.set_calls)

    def test_mutation_rechecks_picture_lock_after_inspection(self):
        element = self.inspect()["elements"][0]
        self.config = live_config(self.root, locked=True)
        with self.assertRaisesRegex(ValidationError, "picture lock"):
            set_element_enabled(
                self.project, self.timeline, self.config, self.registry, self.store,
                element["element_id"], element["fingerprint"], False, NOW,
            )
        self.assertEqual([], self.video.set_calls)

    def test_inspection_does_not_grant_remove_from_arphe_name_alone(self):
        self.video.name = "ARPHE_BRIDGE_OWNED_LOOKING_TITLE"
        element = self.inspect()["elements"][0]
        self.assertFalse(element["remove_allowed"])


class TimelineElementRemovalTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = TimelineElementStore(self.root / "elements.json", "PC_PERSONALE")
        self.timeline = LiveTimeline()
        self.before = LiveItem(50, 100, "Prima", "video-before")
        self.target = LiveItem(100, 150, "Overlay", "video-target")
        self.after = LiveItem(150, 200, "Dopo", "video-after")
        self.timeline.tracks["video"][1] = [self.before, self.target, self.after]
        self.project = LiveProject(self.timeline)
        self.registry = LiveRegistry()
        self.config = live_config(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def own_and_inspect(self):
        snap = capture_item_snapshot(
            "PC_PERSONALE", self.project, self.timeline, "video", 1, self.target,
        )
        self.store.register_ownership(snap, "create_fusion_title", "native-ref", now=NOW)
        return inspect_elements(
            self.project, self.timeline, self.config, self.registry, self.store,
            media_type="video", start_frame=100, end_frame=150, now=NOW,
        )["elements"][0]

    def proposal(self):
        element = self.own_and_inspect()
        return prepare_element_removal(
            self.project, self.timeline, self.config, self.registry, self.store,
            element["element_id"], element["fingerprint"], NOW,
        )

    def execute(self, proposal):
        return execute_element_removal(
            self.project, self.timeline, self.config, self.registry, self.store,
            proposal["removal_id"], proposal["proposal_fingerprint"], "ALESSIO", NOW,
        )

    def test_prepare_removal_requires_exact_active_ownership_not_name_similarity(self):
        self.target.name = "ARPHE_BRIDGE_OWNED_LOOKING_TITLE"
        element = inspect_elements(
            self.project, self.timeline, self.config, self.registry, self.store,
            media_type="video", start_frame=100, end_frame=150, now=NOW,
        )["elements"][0]
        with self.assertRaisesRegex(ValidationError, "ownership"):
            prepare_element_removal(
                self.project, self.timeline, self.config, self.registry, self.store,
                element["element_id"], element["fingerprint"], NOW,
            )
        self.assertEqual([], self.timeline.delete_calls)

    def test_prepare_removal_refuses_historical_and_duplicated_unregistered_items(self):
        element = inspect_elements(
            self.project, self.timeline, self.config, self.registry, self.store,
            media_type="video", start_frame=100, end_frame=150, now=NOW,
        )["elements"][0]
        duplicate = LiveItem(100, 150, "Overlay", "video-target")
        self.timeline.tracks["video"][1].append(duplicate)
        with self.assertRaises(ValidationError):
            prepare_element_removal(
                self.project, self.timeline, self.config, self.registry, self.store,
                element["element_id"], element["fingerprint"], NOW,
            )

    def test_execute_removal_rechecks_picture_lock_and_live_fingerprint(self):
        proposal = self.proposal()
        self.config = live_config(self.root, locked=True)
        with self.assertRaisesRegex(ValidationError, "picture lock"):
            self.execute(proposal)
        self.assertEqual([], self.timeline.delete_calls)

    def test_execute_removal_calls_delete_clips_once_with_one_item_and_ripple_false(self):
        receipt = self.execute(self.proposal())
        self.assertTrue(receipt["ok"])
        self.assertEqual(1, len(self.timeline.delete_calls))
        items, ripple = self.timeline.delete_calls[0]
        self.assertEqual([self.target], items)
        self.assertFalse(ripple)

    def test_execute_removal_verifies_target_absent_and_neighbour_ranges_unchanged(self):
        receipt = self.execute(self.proposal())
        self.assertEqual("COMPLETED", receipt["state"])
        self.assertEqual([self.before, self.after], self.timeline.tracks["video"][1])
        self.assertEqual([[50, 100], [150, 200]], receipt["neighbour_ranges"])

    def test_execute_removal_does_not_consume_proposal_when_resolve_delete_fails(self):
        proposal = self.proposal()
        self.timeline.delete_result = False
        with self.assertRaisesRegex(ValidationError, "DeleteClips"):
            self.execute(proposal)
        stored = self.store.require_removal(
            proposal["removal_id"], proposal["proposal_fingerprint"], NOW,
        )
        self.assertEqual("PREPARED", stored["state"])
        self.assertIn(self.target, self.timeline.tracks["video"][1])

    def test_execute_removal_recovers_committed_delete_after_lost_response(self):
        proposal = self.proposal()
        with patch.object(self.store, "complete_removal", side_effect=RuntimeError("lost response")):
            with self.assertRaisesRegex(RuntimeError, "lost response"):
                self.execute(proposal)
        self.assertNotIn(self.target, self.timeline.tracks["video"][1])
        recovered = self.execute(proposal)
        self.assertEqual("COMPLETED", recovered["state"])
        self.assertEqual(1, len(self.timeline.delete_calls))

    def test_execute_removal_never_redirects_to_replacement_item(self):
        proposal = self.proposal()
        with patch.object(self.store, "complete_removal", side_effect=RuntimeError("lost response")):
            with self.assertRaises(RuntimeError):
                self.execute(proposal)
        replacement = LiveItem(100, 150, "Replacement", "video-replacement")
        self.timeline.tracks["video"][1].append(replacement)
        with self.assertRaisesRegex(ValidationError, "recovery|invariant|blocc"):
            self.execute(proposal)
        self.assertIn(replacement, self.timeline.tracks["video"][1])
        self.assertEqual(1, len(self.timeline.delete_calls))

    def test_completed_removal_returns_same_idempotent_receipt(self):
        proposal = self.proposal()
        first = self.execute(proposal)
        second = self.execute(proposal)
        self.assertEqual(first, second)
        self.assertEqual(1, len(self.timeline.delete_calls))


if __name__ == "__main__":
    unittest.main()
