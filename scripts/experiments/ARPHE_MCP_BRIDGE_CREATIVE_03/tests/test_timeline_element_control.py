from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from bridge.safety import ValidationError
from bridge.timeline_element_control import (
    TimelineElementSnapshot,
    TimelineElementStore,
    capture_item_snapshot,
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


if __name__ == "__main__":
    unittest.main()
