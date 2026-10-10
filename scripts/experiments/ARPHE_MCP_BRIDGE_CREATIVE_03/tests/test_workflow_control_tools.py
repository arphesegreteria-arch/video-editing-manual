from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.config import DEFAULT_FLAGS  # noqa: E402
from bridge.control_plane import WorkflowJobStore, new_workflow_job  # noqa: E402
import bridge.server as server  # noqa: E402


class WorkflowControlToolTests(unittest.TestCase):
    def test_prepare_binds_exact_native_review_fingerprint(self):
        with tempfile.TemporaryDirectory() as raw:
            flags = dict(DEFAULT_FLAGS)
            flags["CAP_WORKFLOW_CONTROL_PLANE"] = True
            cfg = SimpleNamespace(workstation_id="PC_PERSONALE", flags=flags,
                                  workflow_control_jobs_path=Path(raw) / "jobs.json")
            target = {"project_name": "ARPHE", "timeline_name": "MASTER"}
            native = SimpleNamespace(workstation_id="PC_PERSONALE", state="REVIEWED",
                                     project_name="ARPHE", timeline_name="MASTER",
                                     candidate_fingerprint="b" * 64, review_fingerprint="c" * 64)
            with patch("bridge.server.load_config", return_value=cfg), \
                 patch("bridge.server.load_native_binding", return_value=native):
                first = server.prepare_workflow_job("PODCAST_REELS", "editorial_1", target)
                same = server.prepare_workflow_job("PODCAST_REELS", "editorial_1", target)
                native.review_fingerprint = "d" * 64
                changed = server.prepare_workflow_job("PODCAST_REELS", "editorial_1", target)
            self.assertTrue(first["ok"])
            self.assertTrue(same["idempotent"])
            self.assertEqual(first["workflow_job_id"], same["workflow_job_id"])
            self.assertNotEqual(first["plan_fingerprint"], changed["plan_fingerprint"])
            self.assertNotEqual(first["workflow_job_id"], changed["workflow_job_id"])

    def test_snapshot_is_useful_offline_and_performs_no_write(self):
        with tempfile.TemporaryDirectory() as raw:
            cfg = SimpleNamespace(workstation_id="PC_PERSONALE", flags=dict(DEFAULT_FLAGS),
                                  workflow_control_jobs_path=Path(raw) / "jobs.json")
            with patch("bridge.server.load_config", return_value=cfg), \
                 patch("bridge.server._runtime", return_value=(None, None, None, None, cfg, None, {"ok": False, "error": "offline"})):
                card = server.inspect_workstation_control_plane()
            self.assertEqual("PC_PERSONALE", card["workstation_id"])
            self.assertFalse(card["resolve"]["connected"])
            self.assertFalse((Path(raw) / "jobs.json").exists())

    def test_mutation_rejects_disabled_flag_before_runtime(self):
        cfg = SimpleNamespace(workstation_id="PC_PERSONALE", flags=dict(DEFAULT_FLAGS))
        with patch("bridge.server.load_config", return_value=cfg), \
             patch("bridge.server._runtime", side_effect=AssertionError("runtime touched")):
            result = server.prepare_workflow_job("PODCAST_REELS", "editorial_0123456789abcdef", {"project_name": "A", "timeline_name": "T"})
        self.assertFalse(result["ok"])
        self.assertIn("CAP_WORKFLOW_CONTROL_PLANE", result["error"])
        delivery = server.approve_workflow_delivery(
            "workflow_0123456789abcdef", "a" * 64, "SECRETARY")
        self.assertFalse(delivery["ok"])
        self.assertIn("CAP_WORKFLOW_CONTROL_PLANE", delivery["error"])

    def test_delivery_rejects_non_hex_fingerprint(self):
        with tempfile.TemporaryDirectory() as raw:
            flags = dict(DEFAULT_FLAGS)
            flags["CAP_WORKFLOW_CONTROL_PLANE"] = True
            path = Path(raw) / "jobs.json"
            job = new_workflow_job(
                "PC_PERSONALE", "PODCAST_REELS", "editorial_1",
                {"project_name": "ARPHE", "timeline_name": "MASTER"}, "a" * 64)
            WorkflowJobStore(path, "PC_PERSONALE").create(job)
            cfg = SimpleNamespace(workstation_id="PC_PERSONALE", flags=flags,
                                  workflow_control_jobs_path=path)
            with patch("bridge.server.load_config", return_value=cfg):
                result = server.approve_workflow_delivery(
                    job.workflow_job_id, "z" * 64, "SECRETARY")
            self.assertFalse(result["ok"])
            self.assertIn("non valida", result["error"])

    def test_inspect_job_is_read_only_and_approve_is_flag_gated(self):
        cfg = SimpleNamespace(workstation_id="PC_PERSONALE", flags=dict(DEFAULT_FLAGS),
                              workflow_control_jobs_path=Path("unused.json"))
        with patch("bridge.server.load_config", return_value=cfg), \
             patch("bridge.server._runtime", side_effect=AssertionError("runtime touched")):
            approved = server.approve_workflow_job("workflow_0123456789abcdef", "a" * 64, "SECRETARY")
        self.assertFalse(approved["ok"])
        self.assertIn("CAP_WORKFLOW_CONTROL_PLANE", approved["error"])

    def test_native_dispatch_refuses_missing_human_review(self):
        job = SimpleNamespace(workflow_family="PODCAST_REELS", native_reference="editorial_1")
        native = SimpleNamespace(state="MARKED", editorial_job_id="editorial_1",
                                 review_fingerprint=None)
        result = server._dispatch_control_native(job, native)
        self.assertFalse(result["ok"])
        self.assertEqual("SUBMIT_REVIEW", result["next_safe_action"])

    def test_native_dispatch_routes_reviewed_podcast_to_exact_apply(self):
        job = SimpleNamespace(workflow_family="PODCAST_REELS", native_reference="editorial_1")
        native = SimpleNamespace(state="REVIEWED", editorial_job_id="editorial_1",
                                 review_fingerprint="b" * 64)
        with patch("bridge.server.apply_podcast_reel_selection",
                   return_value={"ok": True, "state": "VERIFIED"}) as apply:
            result = server._dispatch_control_native(job, native)
        self.assertTrue(result["ok"])
        apply.assert_called_once_with("editorial_1", "b" * 64)

    def test_native_dispatch_routes_verified_carabellese_to_close(self):
        job = SimpleNamespace(workflow_family="CARABELLESE_CLEANUP", native_reference="carabellese_1")
        native = SimpleNamespace(state="VERIFIED", carabellese_job_id="carabellese_1")
        with patch("bridge.server.close_carabellese_cleanup",
                   return_value={"ok": True, "state": "CLOSED"}) as close:
            result = server._dispatch_control_native(job, native)
        self.assertTrue(result["ok"])
        close.assert_called_once_with("carabellese_1")

    def test_native_dispatch_routes_blocked_podcast_to_guarded_resume(self):
        job = SimpleNamespace(workflow_family="PODCAST_REELS", native_reference="editorial_1")
        native = SimpleNamespace(state="BLOCKED", editorial_job_id="editorial_1",
                                 review_fingerprint="b" * 64)
        with patch("bridge.server.apply_podcast_reel_selection",
                   return_value={"ok": True, "state": "VERIFIED"}) as apply:
            result = server._dispatch_control_native(job, native)
        self.assertTrue(result["ok"])
        apply.assert_called_once_with("editorial_1", "b" * 64)

    def test_native_dispatch_routes_approved_branded_to_apply(self):
        job = SimpleNamespace(workflow_family="BRANDED_LONGFORM", native_reference="job-1")
        native = SimpleNamespace(state="APPROVED", job_id="job-1")
        with patch("bridge.server.apply_branded_longform_batch",
                   return_value={"ok": True, "state": "APPLIED"}) as apply:
            result = server._dispatch_control_native(job, native)
        self.assertTrue(result["ok"])
        apply.assert_called_once_with("job-1")

    def test_native_dispatch_routes_vertical_next_cut_with_plan_fingerprint(self):
        action = SimpleNamespace(action_type="CUT")
        native = SimpleNamespace(plan_id="vertical_1", actions=(), action=lambda value: action)
        job = SimpleNamespace(workflow_family="VERTICAL_SOCIAL", native_reference="vertical_1")
        cfg = SimpleNamespace(vertical_social_plans_path=Path("plans.json"), workstation_id="PC_PERSONALE")
        with patch("bridge.server.do_inspect_vertical_social_plan",
                   return_value={"next_action": "cut-1"}), \
             patch("bridge.server.apply_vertical_social_cuts",
                   return_value={"ok": True, "state": "VERIFIED"}) as apply, \
             patch("bridge.vertical_social_jobs.plan_fingerprint", return_value="d" * 64):
            result = server._dispatch_control_native(job, native, cfg)
        self.assertTrue(result["ok"])
        apply.assert_called_once_with("vertical_1", "d" * 64)


if __name__ == "__main__":
    unittest.main()
