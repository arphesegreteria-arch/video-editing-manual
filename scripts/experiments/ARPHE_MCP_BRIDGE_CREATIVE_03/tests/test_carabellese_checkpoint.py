from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.carabellese_checkpoint import (  # noqa: E402
    export_timeline_checkpoint,
    restore_timeline_checkpoint,
    timeline_content_fingerprint,
    verify_timeline_checkpoint,
)
from bridge.carabellese_jobs import CarabelleseJobStore, new_carabellese_job  # noqa: E402
from bridge.safety import ValidationError  # noqa: E402


class FakeItem:
    def __init__(self, start=0, end=300): self.start, self.end = start, end
    def GetStart(self): return self.start
    def GetEnd(self): return self.end
    def GetDuration(self): return self.end - self.start


class FakeTimeline:
    def __init__(self, name="PODCAST_YOUTUBE", signature=300, export_behavior="write"):
        self.name, self.signature, self.export_behavior = name, signature, export_behavior
        self.playback = "30"
        self.export_calls = []
    def GetName(self): return self.name
    def SetName(self, value): self.name = value; return True
    def GetUniqueId(self): return "id-" + self.name
    def GetStartFrame(self): return 0
    def GetEndFrame(self): return self.signature
    def GetSetting(self, key):
        return {"timelineResolutionWidth": "1920", "timelineResolutionHeight": "1080",
                "timelineFrameRate": "30", "timelinePlaybackFrameRate": self.playback}.get(key)
    def SetSetting(self, key, value):
        if key != "timelinePlaybackFrameRate": return False
        self.playback = value; return True
    def GetTrackCount(self, kind): return 1 if kind in {"video", "audio"} else 0
    def GetItemListInTrack(self, kind, index): return [FakeItem(0, self.signature)]
    def Export(self, path, export_type):
        self.export_calls.append((path, export_type))
        if self.export_behavior == "missing": return True
        Path(path).write_bytes(b"" if self.export_behavior == "empty" else b"DRT-CHECKPOINT")
        return True


class FakePool:
    def __init__(self, project, imported_signature=300):
        self.project, self.imported_signature = project, imported_signature
        self.import_calls, self.delete_calls = [], []
        self.fail_delete = None
    def ImportTimelineFromFile(self, path, options):
        self.import_calls.append((path, dict(options)))
        timeline = FakeTimeline(options["timelineName"], self.imported_signature)
        self.project.timelines.append(timeline)
        return timeline
    def DeleteTimelines(self, timelines):
        self.delete_calls.append(list(timelines))
        if self.fail_delete is not None and self.fail_delete in timelines:
            return False
        for timeline in timelines:
            if timeline in self.project.timelines: self.project.timelines.remove(timeline)
        return True


class FakeProject:
    def __init__(self, timeline, imported_signature=300):
        self.timelines, self.current = [timeline], timeline
        self.pool = FakePool(self, imported_signature)
    def GetName(self): return "STUDIO_CARABELLESE"
    def GetCurrentTimeline(self): return self.current
    def GetMediaPool(self): return self.pool
    def GetTimelineCount(self): return len(self.timelines)
    def GetTimelineByIndex(self, index): return self.timelines[index - 1]
    def SetCurrentTimeline(self, timeline): self.current = timeline; return True
    def GetSetting(self, key): return self.current.GetSetting(key)
    def SetSetting(self, key, value): return self.current.SetSetting(key, value)


class FakeResolve:
    EXPORT_DRT = 77


class TimelineProxy:
    def __init__(self, target): self.target = target
    def __getattr__(self, name): return getattr(self.target, name)


def reviewed_job(store, timeline):
    created = store.create(new_carabellese_job(
        workstation_id="PC_PERSONALE", workflow_version=1, project_name="STUDIO_CARABELLESE",
        timeline_name="PODCAST_YOUTUBE", timeline_identity="resolve:id-PODCAST_YOUTUBE",
        timeline_fingerprint=timeline_content_fingerprint(timeline), source_fingerprint="1" * 64,
        transcript_fingerprint="2" * 64, contract_fingerprint="3" * 64,
        proposal_fingerprint="4" * 64,
        candidates=({"candidate_id": "C01"},),
    ))
    marked = store.save(replace(created, state="MARKED"), created.revision)
    return store.save(replace(marked, state="REVIEWED", review_fingerprint="5" * 64), marked.revision)


class CarabelleseCheckpointTests(unittest.TestCase):
    def test_fingerprint_treats_blank_playback_as_inherited_timeline_rate(self):
        explicit = FakeTimeline()
        inherited = FakeTimeline(); inherited.playback = ""

        self.assertEqual(timeline_content_fingerprint(explicit),
                         timeline_content_fingerprint(inherited))

    def test_export_uses_drt_verifies_file_and_retry_reuses_checkpoint(self):
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            timeline = FakeTimeline()
            project = FakeProject(timeline)
            store = CarabelleseJobStore(root / "jobs.json", "PC_PERSONALE")
            checkpointed = export_timeline_checkpoint(FakeResolve(), project, timeline, store,
                                                      reviewed_job(store, timeline), root / "checkpoints")
            replay = export_timeline_checkpoint(FakeResolve(), project, timeline, store,
                                                checkpointed, root / "checkpoints")
            evidence = verify_timeline_checkpoint(checkpointed)
        self.assertEqual("CHECKPOINTED", checkpointed.state)
        self.assertEqual(1, len(timeline.export_calls))
        self.assertEqual(77, timeline.export_calls[0][1])
        self.assertEqual(checkpointed, replay)
        self.assertTrue(evidence["ok"])
        self.assertNotIn("path", evidence)

    def test_missing_or_empty_export_never_transitions(self):
        for behavior in ("missing", "empty"):
            with self.subTest(behavior=behavior), tempfile.TemporaryDirectory() as raw_root:
                root = Path(raw_root)
                timeline = FakeTimeline(export_behavior=behavior)
                project = FakeProject(timeline)
                store = CarabelleseJobStore(root / "jobs.json", "PC_PERSONALE")
                reviewed = reviewed_job(store, timeline)
                with self.assertRaises(ValidationError):
                    export_timeline_checkpoint(FakeResolve(), project, timeline, store, reviewed,
                                               root / "checkpoints")
                self.assertEqual("REVIEWED", store.get(reviewed.carabellese_job_id,
                                                        "PC_PERSONALE").state)

    def test_unsupported_export_is_zero_write(self):
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            timeline = FakeTimeline()
            timeline.Export = None
            project = FakeProject(timeline)
            store = CarabelleseJobStore(root / "jobs.json", "PC_PERSONALE")
            reviewed = reviewed_job(store, timeline)
            with self.assertRaisesRegex(ValidationError, "support"):
                export_timeline_checkpoint(FakeResolve(), project, timeline, store, reviewed,
                                           root / "checkpoints")
            self.assertFalse((root / "checkpoints").exists())

    def test_hash_tamper_is_detected(self):
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            timeline = FakeTimeline(); project = FakeProject(timeline)
            store = CarabelleseJobStore(root / "jobs.json", "PC_PERSONALE")
            checkpointed = export_timeline_checkpoint(FakeResolve(), project, timeline, store,
                                                      reviewed_job(store, timeline), root / "checkpoints")
            checkpoint_path = Path(checkpointed.checkpoint_manifest["path"])
            checkpoint_path.write_bytes(b"X" * checkpoint_path.stat().st_size)
            with self.assertRaisesRegex(ValidationError, "hash"):
                verify_timeline_checkpoint(checkpointed)

    def test_restore_verifies_import_before_removing_failed_timeline(self):
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            failed = FakeTimeline(); project = FakeProject(failed)
            store = CarabelleseJobStore(root / "jobs.json", "PC_PERSONALE")
            checkpointed = export_timeline_checkpoint(FakeResolve(), project, failed, store,
                                                      reviewed_job(store, failed), root / "checkpoints")
            restored = restore_timeline_checkpoint(FakeResolve(), project, store, checkpointed)
        self.assertEqual("CHECKPOINTED", restored.state)
        self.assertEqual(1, len(project.timelines))
        self.assertEqual("PODCAST_YOUTUBE", project.timelines[0].name)
        self.assertIs(project.current, project.timelines[0])
        self.assertIn(failed, project.pool.delete_calls[0])

    def test_restore_renames_import_when_resolve_ignores_requested_timeline_name(self):
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            failed = FakeTimeline(); project = FakeProject(failed)
            store = CarabelleseJobStore(root / "jobs.json", "PC_PERSONALE")
            checkpointed = export_timeline_checkpoint(FakeResolve(), project, failed, store,
                                                      reviewed_job(store, failed), root / "checkpoints")

            def import_ignoring_options(path, options):
                project.pool.import_calls.append((path, dict(options)))
                timeline = FakeTimeline("PODCAST_YOUTUBE 1")
                project.timelines.append(timeline)
                return timeline

            project.pool.ImportTimelineFromFile = import_ignoring_options
            restored = restore_timeline_checkpoint(FakeResolve(), project, store, checkpointed)

        self.assertEqual("CHECKPOINTED", restored.state)
        self.assertEqual(["PODCAST_YOUTUBE"], [item.name for item in project.timelines])

    def test_restore_repairs_playback_rate_omitted_by_drt_import(self):
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            failed = FakeTimeline(); project = FakeProject(failed)
            store = CarabelleseJobStore(root / "jobs.json", "PC_PERSONALE")
            checkpointed = export_timeline_checkpoint(FakeResolve(), project, failed, store,
                                                      reviewed_job(store, failed), root / "checkpoints")
            original_import = project.pool.ImportTimelineFromFile

            def import_without_playback(path, options):
                timeline = original_import(path, options)
                timeline.playback = ""
                return timeline

            project.pool.ImportTimelineFromFile = import_without_playback
            restored = restore_timeline_checkpoint(FakeResolve(), project, store, checkpointed)

        self.assertEqual("CHECKPOINTED", restored.state)
        self.assertEqual("30", project.current.playback)

    def test_restore_accepts_project_inheritance_when_timeline_rejects_setting(self):
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            failed = FakeTimeline(); project = FakeProject(failed)
            store = CarabelleseJobStore(root / "jobs.json", "PC_PERSONALE")
            checkpointed = export_timeline_checkpoint(FakeResolve(), project, failed, store,
                                                      reviewed_job(store, failed), root / "checkpoints")
            original_import = project.pool.ImportTimelineFromFile

            def import_without_timeline_setter(path, options):
                timeline = original_import(path, options)
                timeline.playback = ""
                timeline.SetSetting = lambda _key, _value: False
                return timeline

            def project_setting(key, value):
                if key != "timelinePlaybackFrameRate": return False
                project.current.playback = value; return True

            project.pool.ImportTimelineFromFile = import_without_timeline_setter
            project.SetSetting = project_setting
            restored = restore_timeline_checkpoint(FakeResolve(), project, store, checkpointed)

        self.assertEqual("CHECKPOINTED", restored.state)
        self.assertEqual("", project.current.playback)

    def test_restore_rereads_playback_after_selecting_imported_timeline(self):
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            failed = FakeTimeline(); project = FakeProject(failed)
            store = CarabelleseJobStore(root / "jobs.json", "PC_PERSONALE")
            checkpointed = export_timeline_checkpoint(FakeResolve(), project, failed, store,
                                                      reviewed_job(store, failed), root / "checkpoints")
            original_import = project.pool.ImportTimelineFromFile

            def import_with_deferred_playback(path, options):
                timeline = original_import(path, options)
                timeline.playback = ""
                timeline.SetSetting = lambda _key, _value: False
                return timeline

            def select_with_deferred_playback(timeline):
                project.current = timeline
                if timeline is not failed: timeline.playback = "30"
                return True

            project.pool.ImportTimelineFromFile = import_with_deferred_playback
            project.SetCurrentTimeline = select_with_deferred_playback
            project.SetSetting = lambda _key, _value: False
            restored = restore_timeline_checkpoint(FakeResolve(), project, store, checkpointed)

        self.assertEqual("CHECKPOINTED", restored.state)
        self.assertEqual("30", project.current.playback)

    def test_restore_accepts_distinct_resolve_wrapper_for_canonical_timeline(self):
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            failed = FakeTimeline(); project = FakeProject(failed)
            store = CarabelleseJobStore(root / "jobs.json", "PC_PERSONALE")
            checkpointed = export_timeline_checkpoint(FakeResolve(), project, failed, store,
                                                      reviewed_job(store, failed), root / "checkpoints")
            original_get = project.GetTimelineByIndex
            project.GetTimelineByIndex = lambda index: TimelineProxy(original_get(index))

            restored = restore_timeline_checkpoint(FakeResolve(), project, store, checkpointed)

        self.assertEqual("CHECKPOINTED", restored.state)
        self.assertEqual(1, len(project.timelines))

    def test_bad_import_never_removes_failed_timeline(self):
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            failed = FakeTimeline(); project = FakeProject(failed, imported_signature=250)
            store = CarabelleseJobStore(root / "jobs.json", "PC_PERSONALE")
            checkpointed = export_timeline_checkpoint(FakeResolve(), project, failed, store,
                                                      reviewed_job(store, failed), root / "checkpoints")
            with self.assertRaisesRegex(ValidationError, "contenuto"):
                restore_timeline_checkpoint(FakeResolve(), project, store, checkpointed)
        self.assertIn(failed, project.timelines)
        self.assertNotIn(failed, [item for call in project.pool.delete_calls for item in call])

    def test_restore_promotion_failure_rolls_back_to_original_timeline(self):
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            failed = FakeTimeline(); project = FakeProject(failed)
            project.pool.fail_delete = failed
            store = CarabelleseJobStore(root / "jobs.json", "PC_PERSONALE")
            checkpointed = export_timeline_checkpoint(FakeResolve(), project, failed, store,
                                                      reviewed_job(store, failed), root / "checkpoints")

            with self.assertRaisesRegex(ValidationError, "rimuovere timeline guasta"):
                restore_timeline_checkpoint(FakeResolve(), project, store, checkpointed)

        self.assertIs(project.current, failed)
        self.assertEqual("PODCAST_YOUTUBE", failed.name)
        self.assertEqual([failed], project.timelines)


if __name__ == "__main__":
    unittest.main()
