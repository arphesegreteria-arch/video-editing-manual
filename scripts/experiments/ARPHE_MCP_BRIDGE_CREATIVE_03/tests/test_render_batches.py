from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.editorial_workflows import (  # noqa: E402
    EditorialBrief, load_render_profile_registry,
)
from bridge.format_contract import ResolvedFormat  # noqa: E402
from bridge.registry import Registry  # noqa: E402
from bridge.config import CreativeConfig, DEFAULT_FLAGS, DEFAULT_PALETTE  # noqa: E402
from bridge.render_batches import (  # noqa: E402
    approve_render_batch, batch_fingerprint, create_render_batch, transition_batch,
)
from bridge.render_tools import (cancel_render_batch, get_render_batch_status,
                                 prepare_render_batch, start_render_batch)  # noqa: E402
from bridge.safety import ValidationError  # noqa: E402


def fixtures(override=False):
    brief = EditorialBrief("brief-1", "CARABELLESE_YOUTUBE_CLEANUP", 1, "SEGRETERIA",
                           "source.mov", ("publishable",), {"override": override}, {}, ())
    profile = load_render_profile_registry(ROOT / "render_profiles.json").profiles["YOUTUBE_H264"]
    contract = ResolvedFormat(1920, 1080, Fraction(30000, 1001), Fraction(30000, 1001))
    return brief, profile, contract


class RenderBatchStateTests(unittest.TestCase):
    def test_batch_transitions_are_monotonic_and_persist_across_registry_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = Registry(Path(directory) / "state.json")
            batch = create_render_batch(*fixtures(), "ARPHE_PROJECT", ("ARPHE_MAIN",),
                                        ("ARPHE_MAIN",), "PC_PERSONALE")
            registry.save_render_batch(batch)
            prepared = transition_batch(registry, batch.batch_id, "CONFIRMED", "PREPARED",
                                        {"created_job_ids": ["job-1"], "queue_before": ["old"]})
            self.assertEqual("PREPARED", Registry(registry.path).render_batch(batch.batch_id).status)
            with self.assertRaises(ValidationError):
                transition_batch(registry, batch.batch_id, "PREPARED", "CONFIRMED", {})
            self.assertEqual(("job-1",), prepared.created_job_ids)

    def test_secretary_can_approve_standard_final_but_not_override(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = Registry(Path(directory) / "state.json")
            standard = create_render_batch(*fixtures(), "ARPHE_PROJECT", ("ARPHE_MAIN",),
                                           ("ARPHE_MAIN",), "PC_SEGRETERIA")
            registry.save_render_batch(standard)
            prepared = transition_batch(registry, standard.batch_id, "CONFIRMED", "PREPARED",
                                        {"created_job_ids": ["job-1"]})
            approved = approve_render_batch(registry, prepared.batch_id, "SEGRETERIA")
            self.assertEqual("APPROVED", approved.status)
            self.assertTrue(approved.approval_token)

            override = create_render_batch(*fixtures(True), "ARPHE_PROJECT", ("ARPHE_MAIN",),
                                           ("ARPHE_OVERRIDE",), "PC_SEGRETERIA")
            registry.save_render_batch(override)
            transition_batch(registry, override.batch_id, "CONFIRMED", "PREPARED",
                             {"created_job_ids": ["job-2"]})
            with self.assertRaisesRegex(ValidationError, "tecnico"):
                approve_render_batch(registry, override.batch_id, "SEGRETERIA")

    def test_manifest_change_invalidates_approval_token(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = Registry(Path(directory) / "state.json")
            batch = create_render_batch(*fixtures(), "ARPHE_PROJECT", ("ARPHE_MAIN",),
                                        ("ARPHE_MAIN",), "PC_PERSONALE")
            registry.save_render_batch(batch)
            prepared = transition_batch(registry, batch.batch_id, "CONFIRMED", "PREPARED",
                                        {"created_job_ids": ["job-1"]})
            approved = approve_render_batch(registry, prepared.batch_id, "ALESSIO")
            changed = replace(approved, output_names=("DIFFERENT",))
            self.assertNotEqual(approved.approval_token, batch_fingerprint(changed))

    def test_retry_creates_new_attempt_linked_to_failed_batch(self):
        first = create_render_batch(*fixtures(), "ARPHE_PROJECT", ("ARPHE_MAIN",),
                                    ("ARPHE_MAIN",), "PC_PERSONALE")
        retry = create_render_batch(*fixtures(), "ARPHE_PROJECT", ("ARPHE_MAIN",),
                                    ("ARPHE_MAIN",), "PC_PERSONALE", 2, first.batch_id)
        self.assertEqual(2, retry.attempt)
        self.assertEqual(first.batch_id, retry.previous_batch_id)
        self.assertNotEqual(first.batch_id, retry.batch_id)

    def test_process_restart_reads_existing_render_lock_and_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            registry = Registry(path)
            batch = create_render_batch(*fixtures(), "ARPHE_PROJECT", ("ARPHE_MAIN",),
                                        ("ARPHE_MAIN",), "PC_PERSONALE")
            registry.save_render_batch(batch)
            registry.acquire_render_lock("ARPHE_PROJECT", batch.batch_id)
            restarted = Registry(path)
            self.assertEqual(batch.batch_id, restarted.render_batch(batch.batch_id).batch_id)
            self.assertEqual(batch.batch_id, restarted.render_lock("ARPHE_PROJECT")["batch_id"])
            with self.assertRaises(ValidationError):
                restarted.acquire_render_lock("ARPHE_PROJECT", "another")


class FakeRenderProject:
    def __init__(self):
        self.jobs = [{"JobId": "old-job", "TargetDir": "old", "CustomName": "old"}]
        self.started = []
        self.deleted = []
        self.settings = {}
        self.timeline = type("Timeline", (), {"GetName": lambda self: "ARPHE_MAIN",
                                               "GetStartFrame": lambda self: 0,
                                               "GetEndFrame": lambda self: 300})()

    def GetName(self): return "ARPHE_PROJECT"
    def GetCurrentTimeline(self): return self.timeline
    def SetCurrentTimeline(self, timeline): self.timeline = timeline; return True
    def GetTimelineCount(self): return 1
    def GetTimelineByIndex(self, _index): return self.timeline
    def GetRenderJobList(self): return [dict(job) for job in self.jobs]
    def SetCurrentRenderFormatAndCodec(self, container, codec): self.settings.update(container=container, codec=codec); return True
    def SetRenderSettings(self, settings): self.settings.update(settings); return True
    def AddRenderJob(self):
        job_id = f"new-job-{len(self.jobs)}"
        self.jobs.append({"JobId": job_id, **self.settings})
        return job_id
    def DeleteRenderJob(self, job_id): self.deleted.append(job_id); self.jobs = [j for j in self.jobs if j["JobId"] != job_id]; return True
    def StartRendering(self, *args): self.started.append(args); return True


def configured(root: Path):
    flags = dict(DEFAULT_FLAGS); flags["CAP_RENDER"] = True
    return CreativeConfig(root / "config", root / "assets", root / "renders", root / "state.json",
                          root / "audit.jsonl", dict(DEFAULT_PALETTE), flags,
                          frozenset(), frozenset(), "mp4", "H264", workstation_id="PC_PERSONALE")


def stored_batch(registry: Registry):
    batch = create_render_batch(*fixtures(), "ARPHE_PROJECT", ("ARPHE_MAIN",),
                                ("ARPHE_OUTPUT",), "PC_PERSONALE")
    registry.save_render_batch(batch)
    return batch


class RenderBatchPreparationTests(unittest.TestCase):
    def test_prepare_never_calls_start_rendering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); registry = Registry(root / "state.json"); batch = stored_batch(registry)
            project = FakeRenderProject()
            result = prepare_render_batch(project, configured(root), registry, batch.batch_id)
            self.assertTrue(result["ok"])
            self.assertEqual([], project.started)

    def test_existing_jobs_remain_untouched_and_outside_created_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); registry = Registry(root / "state.json"); batch = stored_batch(registry)
            project = FakeRenderProject()
            result = prepare_render_batch(project, configured(root), registry, batch.batch_id)
            self.assertEqual(["new-job-1"], result["created_job_ids"])
            self.assertEqual("old-job", project.jobs[0]["JobId"])
            self.assertNotIn("old-job", result["created_job_ids"])

    def test_duplicate_or_missing_new_job_id_rolls_back_created_jobs_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); registry = Registry(root / "state.json"); batch = stored_batch(registry)
            project = FakeRenderProject()
            project.AddRenderJob = lambda: "old-job"
            with self.assertRaises(ValidationError):
                prepare_render_batch(project, configured(root), registry, batch.batch_id)
            self.assertEqual([], project.deleted)

    def test_partial_settings_failure_restores_original_timeline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); registry = Registry(root / "state.json"); batch = stored_batch(registry)
            project = FakeRenderProject(); original = project.timeline
            project.SetRenderSettings = lambda _settings: False
            with self.assertRaises(ValidationError):
                prepare_render_batch(project, configured(root), registry, batch.batch_id)
            self.assertIs(original, project.timeline)

    def test_prepare_uses_batch_staging_not_delivery_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); registry = Registry(root / "state.json"); batch = stored_batch(registry)
            project = FakeRenderProject()
            prepare_render_batch(project, configured(root), registry, batch.batch_id)
            prepared = registry.render_batch(batch.batch_id)
            self.assertEqual((configured(root).render_root / "staging" / batch.batch_id).resolve(),
                             Path(prepared.staging_directory).resolve())

    def test_prepare_records_duration_and_h264_high_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); registry = Registry(root / "state.json"); batch = stored_batch(registry)
            project = FakeRenderProject(); prepare_render_batch(project, configured(root), registry, batch.batch_id)
            prepared = registry.render_batch(batch.batch_id)
            self.assertEqual("High", project.settings["EncodingProfile"])
            self.assertEqual("1001/100", prepared.evidence["expected_durations"]["ARPHE_OUTPUT.mp4"])


def approved_batch(root: Path, project: FakeRenderProject):
    registry = Registry(root / "state.json"); batch = stored_batch(registry)
    prepare_render_batch(project, configured(root), registry, batch.batch_id)
    approved = approve_render_batch(registry, batch.batch_id, "SEGRETERIA")
    return registry, approved


class RenderBatchExecutionTests(unittest.TestCase):
    def test_start_passes_only_approved_created_ids_and_never_old_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            project = FakeRenderProject(); registry, batch = approved_batch(Path(directory), project)
            result = start_render_batch(project, registry, batch.batch_id, batch.approval_token)
            self.assertTrue(result["ok"])
            self.assertEqual([((list(batch.created_job_ids)), False)], project.started)
            self.assertNotIn("old-job", project.started[0][0])

    def test_queue_change_after_approval_is_rejected_as_stale(self):
        with tempfile.TemporaryDirectory() as directory:
            project = FakeRenderProject(); registry, batch = approved_batch(Path(directory), project)
            project.jobs.append({"JobId": "foreign-job"})
            with self.assertRaisesRegex(ValidationError, "coda"):
                start_render_batch(project, registry, batch.batch_id, batch.approval_token)
            self.assertEqual([], project.started)

    def test_unavailable_selective_start_fails_without_start_all_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            project = FakeRenderProject(); registry, batch = approved_batch(Path(directory), project)
            project.StartRendering = lambda *_args: False
            result = start_render_batch(project, registry, batch.batch_id, batch.approval_token)
            self.assertFalse(result["ok"])

    def test_active_foreign_render_blocks_start_and_cancel(self):
        with tempfile.TemporaryDirectory() as directory:
            project = FakeRenderProject(); registry, batch = approved_batch(Path(directory), project)
            project.IsRenderingInProgress = lambda: True
            with self.assertRaisesRegex(ValidationError, "attivo"):
                start_render_batch(project, registry, batch.batch_id, batch.approval_token)

    def test_cancel_prepared_deletes_only_batch_jobs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); project = FakeRenderProject(); registry = Registry(root / "state.json")
            batch = stored_batch(registry); prepare_render_batch(project, configured(root), registry, batch.batch_id)
            result = cancel_render_batch(project, registry, batch.batch_id, "TECNICO")
            self.assertTrue(result["ok"])
            self.assertEqual(["new-job-1"], project.deleted)
            self.assertEqual("old-job", project.jobs[0]["JobId"])

    def test_cancel_owned_render_transitions_to_cancelled(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); project = FakeRenderProject(); registry, batch = approved_batch(root, project)
            start_render_batch(project, registry, batch.batch_id, batch.approval_token)
            project.StopRendering = lambda: True
            result = cancel_render_batch(project, registry, batch.batch_id, "ALESSIO")
            self.assertEqual("CANCELLED", result["status"])


if __name__ == "__main__":
    unittest.main()
