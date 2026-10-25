from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.colorist_jobs import (approve_colorist_job, new_colorist_job, record_colorist_apply,
                                  record_colorist_apply_started, record_colorist_preview_start)  # noqa: E402
from bridge.colorist_resolve import (  # noqa: E402
    apply_colorist_job,
    inspect_colorist_context,
    preview_colorist_version,
    restore_colorist_preview,
)
from bridge.safety import ValidationError  # noqa: E402


class FakeGraph:
    def __init__(self, apply_ok=True):
        self.apply_ok = apply_ok
        self.drx_calls = []

    def GetNumNodes(self):
        return 1

    def ApplyGradeFromDRX(self, path, mode, all_layers=False):
        self.drx_calls.append((path, mode, all_layers))
        return self.apply_ok


class FakeClip:
    def __init__(self, clip_id, name, *, add_ok=True, cdl_ok=True, copy_ok=True,
                 restore_ok=True, load_changes=True):
        self.clip_id = clip_id
        self.name = name
        self.add_ok = add_ok
        self.cdl_ok = cdl_ok
        self.copy_ok = copy_ok
        self.restore_ok = restore_ok
        self.load_changes = load_changes
        self.versions = ["Original"]
        self.current = "Original"
        self.add_calls = []
        self.load_calls = []
        self.cdl_calls = []
        self.copy_calls = []
        self.graph = FakeGraph()

    def GetUniqueId(self): return self.clip_id
    def GetName(self): return self.name
    def GetStart(self): return 100
    def GetEnd(self): return 200
    def GetCurrentVersion(self): return {"versionName": self.current, "versionType": 0}
    def GetVersionNameList(self, version_type): return list(self.versions) if version_type == 0 else []

    def AddVersion(self, name, version_type):
        self.add_calls.append((name, version_type))
        if not self.add_ok:
            return False
        self.versions.append(name)
        self.current = name
        return True

    def LoadVersionByName(self, name, version_type):
        self.load_calls.append((name, version_type))
        if name == "Original" and not self.restore_ok:
            return False
        if version_type != 0 or name not in self.versions:
            return False
        if self.load_changes:
            self.current = name
        return True

    def SetCDL(self, payload):
        self.cdl_calls.append(dict(payload))
        return self.cdl_ok

    def CopyGrades(self, targets):
        self.copy_calls.append([target.clip_id for target in targets])
        return self.copy_ok

    def GetNodeGraph(self): return self.graph


class FakeTimeline:
    def __init__(self, clips):
        self.clips = clips

    def GetName(self): return "ARPHE_COLOR_TEST"
    def GetUniqueId(self): return "timeline-123"
    def GetTrackCount(self, kind): return 1 if kind == "video" else 0
    def GetItemListInTrack(self, kind, index): return list(self.clips) if kind == "video" and index == 1 else []


class FakeProject:
    def GetName(self): return "ARPHE_TEST"


CDL_A = {"NodeIndex": 1, "Slope": "1.000000 1.000000 1.000000",
         "Offset": "-0.000000 -0.000000 -0.000000",
         "Power": "1.000000 1.000000 1.000000", "Saturation": "1.000000"}
CDL_B = {"NodeIndex": 1, "Slope": "1.100000 1.000000 0.900000",
         "Offset": "0.000000 0.000000 0.000000",
         "Power": "1.000000 1.000000 1.000000", "Saturation": "0.950000"}


def approved_job(clips, *, reference="clip-a", drx=None):
    prepared = new_colorist_job(
        workstation_id="PC_PERSONALE", project_name="ARPHE_TEST",
        timeline_name="ARPHE_COLOR_TEST", timeline_identity="timeline-123",
        clip_ids=tuple(clip.clip_id for clip in clips), reference_clip_id=reference,
        adjustments={}, preset_name="ARPHE_CLEAN_NEUTRAL", drx_preset_name=drx,
        drx_asset_identity=(None if drx is None else {
            "relative_path": "looks/look.drx", "size": 7, "sha256": "0" * 64,
        }),
        before_versions={clip.clip_id: {"versionName": "Original", "versionType": 0} for clip in clips},
        cdl={}, plan_schema="ARPHE_COLORIST_PLAN_V2",
        matching_strategy="PER_CLIP_MEASURED",
        adjustments_by_clip={
            clip.clip_id: {"temperature": 0.0, "tint": 0.0, "exposure_stops": 0.0,
                           "contrast": 0.0, "saturation": 1.0}
            for clip in clips
        },
        observations_by_clip={
            clip.clip_id: {"source": "SCOPES", "sample_frames": [10],
                           "neutral_rgb": [0.5, 0.5, 0.5]}
            for clip in clips
        },
        cdl_by_clip={clip.clip_id: (CDL_A if index == 0 else CDL_B)
                     for index, clip in enumerate(clips)},
    )
    approved = approve_colorist_job(prepared, prepared.plan_fingerprint, "ALESSIO")
    return record_colorist_apply_started(approved)


class ColoristResolveTests(unittest.TestCase):
    def test_inspection_reports_stable_clips_and_required_api_surface_without_writing(self):
        clips = [FakeClip("clip-a", "Camera A"), FakeClip("clip-b", "Camera B")]
        result = inspect_colorist_context(FakeProject(), FakeTimeline(clips))
        self.assertTrue(result["ok"])
        self.assertEqual(["clip-a", "clip-b"], [item["clip_id"] for item in result["clips"]])
        self.assertTrue(result["technically_available"])
        self.assertEqual([], clips[0].add_calls)

    def test_v2_without_drx_does_not_require_legacy_copy_or_node_graph_api(self):
        clips = [FakeClip("clip-a", "Camera A"), FakeClip("clip-b", "Camera B")]
        for clip in clips:
            clip.CopyGrades = None
            clip.GetNodeGraph = None

        inspected = inspect_colorist_context(FakeProject(), FakeTimeline(clips))
        applied = apply_colorist_job(FakeProject(), FakeTimeline(clips), approved_job(clips))

        self.assertTrue(inspected["technically_available"])
        self.assertFalse(inspected["clips"][0]["api"]["CopyGrades"])
        self.assertFalse(inspected["clips"][0]["api"]["GetNodeGraph"])
        self.assertTrue(applied["ok"])

    def test_v2_apply_creates_local_versions_and_applies_distinct_cdl_to_each_clip(self):
        clips = [FakeClip("clip-a", "Camera A"), FakeClip("clip-b", "Camera B")]
        result = apply_colorist_job(FakeProject(), FakeTimeline(clips), approved_job(clips))
        self.assertTrue(result["ok"])
        self.assertEqual(1, len(clips[0].cdl_calls))
        self.assertEqual(1, len(clips[1].cdl_calls))
        self.assertEqual([], clips[0].copy_calls)
        self.assertEqual([], clips[1].copy_calls)
        self.assertEqual(CDL_A, clips[0].cdl_calls[0])
        self.assertEqual(CDL_B, clips[1].cdl_calls[0])
        self.assertTrue(all(call[1] == 0 for clip in clips for call in clip.add_calls))
        self.assertEqual({"clip-a", "clip-b"}, {item["clip_id"] for item in result["evidence"]})
        self.assertTrue(all(item["cdl_applied_directly"] for item in result["evidence"]))
        self.assertEqual(
            {"553ac1acbd222db636a44c2a26ff768f048d22b8e6706a02f444d6edae322b3e",
             "ec878e28769c7a5377b7380f053b0d17ce5eb88342224b30de9d700026f4248a"},
            {item["cdl_sha256"] for item in result["evidence"]},
        )

    def test_optional_drx_is_applied_independently_to_every_v2_clip(self):
        clips = [FakeClip("clip-a", "Camera A"), FakeClip("clip-b", "Camera B")]
        with tempfile.TemporaryDirectory() as directory:
            drx = Path(directory) / "look.drx"
            drx.write_text("fixture", encoding="utf-8")
            result = apply_colorist_job(FakeProject(), FakeTimeline(clips),
                                        approved_job(clips, drx="ARPHE_LOOK"), drx_path=drx)
        self.assertTrue(result["ok"])
        self.assertEqual([(str(drx.resolve()), 0, False)], clips[0].graph.drx_calls)
        self.assertEqual([(str(drx.resolve()), 0, False)], clips[1].graph.drx_calls)

    def test_v2_partial_cdl_failure_restores_every_previous_version_without_copygrades(self):
        clips = [FakeClip("clip-a", "Camera A"),
                 FakeClip("clip-b", "Camera B", cdl_ok=False)]
        result = apply_colorist_job(FakeProject(), FakeTimeline(clips), approved_job(clips))
        self.assertFalse(result["ok"])
        self.assertTrue(result["recoverable"])
        self.assertEqual("Original", clips[0].current)
        self.assertEqual("Original", clips[1].current)
        self.assertEqual([], clips[0].copy_calls)
        self.assertEqual([], clips[1].copy_calls)

    def test_version_collision_or_stale_context_stops_before_any_write(self):
        clips = [FakeClip("clip-a", "Camera A"), FakeClip("clip-b", "Camera B")]
        job = approved_job(clips)
        collision = "ARPHE_COLOR_" + job.colorist_job_id.split("_", 1)[1].upper() + "_01"
        clips[0].versions.append(collision)
        with self.assertRaisesRegex(ValidationError, "version"):
            apply_colorist_job(FakeProject(), FakeTimeline(clips), job)
        self.assertEqual([], clips[0].add_calls)
        self.assertEqual([], clips[1].add_calls)

        clips = [FakeClip("clip-a", "Camera A"), FakeClip("clip-b", "Camera B")]
        clips[1].current = "Different"
        clips[1].versions.append("Different")
        with self.assertRaisesRegex(ValidationError, "stale"):
            apply_colorist_job(FakeProject(), FakeTimeline(clips), approved_job(clips))
        self.assertEqual([], clips[0].add_calls)

    def test_partial_failure_restores_every_previously_active_version(self):
        clips = [FakeClip("clip-a", "Camera A"), FakeClip("clip-b", "Camera B", add_ok=False)]
        result = apply_colorist_job(FakeProject(), FakeTimeline(clips), approved_job(clips))
        self.assertFalse(result["ok"])
        self.assertTrue(result["recoverable"])
        self.assertEqual("Original", clips[0].current)
        self.assertEqual("Original", clips[1].current)
        self.assertIn(("Original", 0), clips[0].load_calls)

    def test_partial_failure_reports_manual_recovery_when_restore_is_incomplete(self):
        clips = [FakeClip("clip-a", "Camera A", restore_ok=False),
                 FakeClip("clip-b", "Camera B", add_ok=False)]
        result = apply_colorist_job(FakeProject(), FakeTimeline(clips), approved_job(clips))
        self.assertFalse(result["ok"])
        self.assertFalse(result["recoverable"])
        self.assertTrue(result["manual_recovery_required"])
        self.assertNotIn("clip-a", result["restored_clip_ids"])

    def test_partial_failure_requires_restore_readback_not_only_true_return(self):
        clips = [FakeClip("clip-a", "Camera A", load_changes=False),
                 FakeClip("clip-b", "Camera B", add_ok=False)]
        result = apply_colorist_job(FakeProject(), FakeTimeline(clips), approved_job(clips))
        self.assertFalse(result["ok"])
        self.assertFalse(result["recoverable"])
        self.assertTrue(result["manual_recovery_required"])
        self.assertNotIn("clip-a", result["restored_clip_ids"])

    def test_preview_loads_only_recorded_before_or_after_versions_and_restore_returns_after(self):
        clips = [FakeClip("clip-a", "Camera A"), FakeClip("clip-b", "Camera B")]
        applying = approved_job(clips)
        applied_result = apply_colorist_job(FakeProject(), FakeTimeline(clips), applying)
        applied = record_colorist_apply(applying, applied_result["evidence"])
        applied = record_colorist_preview_start(applied, "clip-a", clips[0].current)
        before = preview_colorist_version(FakeProject(), FakeTimeline(clips), applied, "clip-a", "before")
        self.assertEqual("Original", before["loaded_version"])
        after = preview_colorist_version(FakeProject(), FakeTimeline(clips), applied, "clip-a", "after")
        self.assertTrue(after["loaded_version"].startswith("ARPHE_COLOR_"))
        clip_b_loads = list(clips[1].load_calls)
        restored = restore_colorist_preview(
            FakeProject(), FakeTimeline(clips), applied, "clip-a", applied.preview_restore_versions["clip-a"]
        )
        self.assertTrue(restored["ok"])
        self.assertTrue(clips[0].current.startswith("ARPHE_COLOR_"))
        self.assertEqual(clip_b_loads, clips[1].load_calls)

    def test_preview_requires_version_readback_after_true_return(self):
        clips = [FakeClip("clip-a", "Camera A"), FakeClip("clip-b", "Camera B")]
        applying = approved_job(clips)
        applied_result = apply_colorist_job(FakeProject(), FakeTimeline(clips), applying)
        applied = record_colorist_apply(applying, applied_result["evidence"])
        clips[0].load_changes = False

        with self.assertRaisesRegex(RuntimeError, "read-back"):
            preview_colorist_version(FakeProject(), FakeTimeline(clips), applied, "clip-a", "before")

    def test_restore_requires_version_readback_after_true_return(self):
        clips = [FakeClip("clip-a", "Camera A"), FakeClip("clip-b", "Camera B")]
        applying = approved_job(clips)
        applied_result = apply_colorist_job(FakeProject(), FakeTimeline(clips), applying)
        applied = record_colorist_apply(applying, applied_result["evidence"])
        applied = record_colorist_preview_start(applied, "clip-a", clips[0].current)
        preview_colorist_version(FakeProject(), FakeTimeline(clips), applied, "clip-a", "before")
        clips[0].load_changes = False

        with self.assertRaisesRegex(RuntimeError, "read-back"):
            restore_colorist_preview(
                FakeProject(), FakeTimeline(clips), applied, "clip-a",
                applied.preview_restore_versions["clip-a"],
            )
        self.assertEqual("Original", clips[0].current)

    def test_drx_graph_is_preflighted_before_any_version_is_created(self):
        clips = [FakeClip("clip-a", "Camera A"), FakeClip("clip-b", "Camera B")]
        clips[0].graph.ApplyGradeFromDRX = None
        with tempfile.TemporaryDirectory() as directory:
            drx = Path(directory) / "look.drx"
            drx.write_text("fixture", encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "DRX"):
                apply_colorist_job(FakeProject(), FakeTimeline(clips),
                                    approved_job(clips, drx="ARPHE_LOOK"), drx_path=drx)
        self.assertEqual([], clips[0].add_calls)
        self.assertEqual([], clips[1].add_calls)


if __name__ == "__main__":
    unittest.main()
