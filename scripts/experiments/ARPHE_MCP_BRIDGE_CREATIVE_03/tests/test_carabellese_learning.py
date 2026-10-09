from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.carabellese_contract import (  # noqa: E402
    WORKFLOW_ID,
    load_carabellese_preferences,
)
from bridge.carabellese_jobs import new_carabellese_job  # noqa: E402
from bridge.carabellese_learning import (  # noqa: E402
    append_carabellese_outcome,
    approve_carabellese_profile_proposal,
    compile_carabellese_profile_proposal,
    inspect_carabellese_metrics,
)
from bridge.config import CreativeConfig, DEFAULT_FLAGS, DEFAULT_PALETTE  # noqa: E402
from bridge.safety import ValidationError  # noqa: E402


SHARED_PATH = ROOT / "carabellese_preferences.json"


def config(root: Path, workstation: str = "PC_PERSONALE") -> CreativeConfig:
    return CreativeConfig(
        path=root / "config.json", asset_root=root / "assets", render_root=root / "renders",
        state_path=root / "state.json", audit_log_path=root / "audit.jsonl",
        palette=dict(DEFAULT_PALETTE), flags=dict(DEFAULT_FLAGS),
        allowed_projects=frozenset(), allowed_timelines=frozenset(),
        render_format="mp4", render_codec="H264", workstation_id=workstation,
        carabellese_journal_path=root / "carabellese_journal.jsonl",
        carabellese_profile_overlay_path=root / "carabellese_profile_overlay.json",
        carabellese_profile_proposals_path=root / "carabellese_profile_proposals.json",
    )


def closed_job(workstation: str = "PC_PERSONALE"):
    candidates = (
        {"candidate_id": "P01", "kind": "PAUSE_REDUCE", "start_seconds": 2.0,
         "end_seconds": 3.4, "context_before": "testo privato paziente"},
        {"candidate_id": "P02", "kind": "PAUSE_CONTEXTUAL", "start_seconds": 4.0,
         "end_seconds": 4.8, "context_after": "nome privato"},
        {"candidate_id": "B01", "kind": "BOUNDARY_START", "start_seconds": 0.0,
         "end_seconds": 1.0, "reason": "indicazione privata"},
        {"candidate_id": "C01", "kind": "EDITORIAL_CUE", "start_seconds": 7.0,
         "end_seconds": 8.0, "context_before": "questo lo eliminiamo"},
    )
    job = new_carabellese_job(
        workstation_id=workstation, workflow_version=1,
        project_name="Studio Carabellese Alessio", timeline_name="C:/privato/podcast.mov",
        timeline_identity="resolve:timeline-private", timeline_fingerprint="1" * 64,
        source_fingerprint="2" * 64, transcript_fingerprint="3" * 64,
        contract_fingerprint="4" * 64, proposal_fingerprint="5" * 64,
        candidates=candidates,
    )
    decisions = (
        {"candidate_id": "P01", "outcome": "SHORTEN", "reason": "ritmo di Alessio",
         "start_seconds": 2.0, "end_seconds": 3.4, "residual_seconds": 0.7},
        {"candidate_id": "P02", "outcome": "KEEP", "reason": "respiro del paziente",
         "start_seconds": 4.0, "end_seconds": 4.8, "residual_seconds": 0.7},
        {"candidate_id": "B01", "outcome": "MODIFY", "reason": "attacco più pulito",
         "start_seconds": 0.2, "end_seconds": 0.9},
        {"candidate_id": "C01", "outcome": "REMOVE", "reason": "istruzione seria",
         "start_seconds": 7.0, "end_seconds": 8.0},
    )
    return replace(
        job, state="CLOSED", review_fingerprint="6" * 64,
        checkpoint_fingerprint="7" * 64,
        checkpoint_manifest={"path": "C:/privato/checkpoint.drt"},
        decisions=decisions,
    )


class CarabelleseLearningTests(unittest.TestCase):
    def test_only_closed_local_jobs_append_once_without_private_content(self):
        with tempfile.TemporaryDirectory() as raw_root:
            cfg = config(Path(raw_root)); job = closed_job()
            with self.assertRaisesRegex(ValidationError, "CLOSED"):
                append_carabellese_outcome(cfg, replace(job, state="VERIFIED"))
            with self.assertRaisesRegex(ValidationError, "workstation"):
                append_carabellese_outcome(cfg, closed_job("PC_SEGRETERIA"))
            first = append_carabellese_outcome(cfg, job)
            replay = append_carabellese_outcome(cfg, job)
            raw = cfg.carabellese_journal_path.read_text(encoding="utf-8")

        self.assertEqual(first, replay)
        self.assertEqual(4, first["recorded"])
        for private in (job.carabellese_job_id, "Alessio", "paziente", "C:/privato",
                        "ritmo di", "questo lo eliminiamo"):
            self.assertNotIn(private, raw)
        self.assertIn(WORKFLOW_ID, raw)

    def test_metrics_and_proposal_aggregate_only_supported_dimensions(self):
        with tempfile.TemporaryDirectory() as raw_root:
            cfg = config(Path(raw_root)); shared = load_carabellese_preferences(SHARED_PATH)
            append_carabellese_outcome(cfg, closed_job())
            metrics = inspect_carabellese_metrics(cfg)
            proposal = compile_carabellese_profile_proposal(
                cfg, shared, minimum_samples=4)

        self.assertEqual({"CONTEXTUAL", "LONG"}, set(metrics["pause_bands"]))
        self.assertEqual([0.7], metrics["residual_durations_seconds"])
        self.assertEqual({"median_start": 0.2, "median_end": -0.1},
                         metrics["boundary_shifts_seconds"])
        self.assertEqual({"PAUSE_CONTEXTUAL": 1}, metrics["false_positive_categories"])
        self.assertEqual(
            {"pause_band_approval_rates", "preferred_residual_pause_seconds",
             "boundary_adjustments_seconds", "false_positive_categories"},
            set(proposal["aggregate_preferences"]),
        )
        encoded = json.dumps(proposal, ensure_ascii=False)
        for private in ("Alessio", "paziente", "C:/privato", "carabellese_", "P01"):
            self.assertNotIn(private, encoded)

    def test_minimum_digest_role_and_workflow_isolation_are_enforced(self):
        with tempfile.TemporaryDirectory() as raw_root:
            cfg = config(Path(raw_root)); shared = load_carabellese_preferences(SHARED_PATH)
            append_carabellese_outcome(cfg, closed_job())
            with self.assertRaisesRegex(ValidationError, "campioni"):
                compile_carabellese_profile_proposal(cfg, shared, minimum_samples=5)
            proposal = compile_carabellese_profile_proposal(cfg, shared, minimum_samples=4)
            for role in ("SEGRETERIA", "EDITOR"):
                with self.assertRaisesRegex(ValidationError, "tecnico"):
                    approve_carabellese_profile_proposal(
                        cfg, proposal["proposal_id"], role, proposal["prior_profile_digest"])
            with self.assertRaisesRegex(ValidationError, "stale"):
                approve_carabellese_profile_proposal(
                    cfg, proposal["proposal_id"], "ALESSIO", "f" * 64)
            approved = approve_carabellese_profile_proposal(
                cfg, proposal["proposal_id"], "TECNICO", proposal["prior_profile_digest"])
            overlay = json.loads(cfg.carabellese_profile_overlay_path.read_text(encoding="utf-8"))

        self.assertTrue(approved["ok"])
        self.assertEqual(WORKFLOW_ID, overlay["workflow_id"])
        self.assertNotIn("PODCAST_REELS", json.dumps(overlay))


if __name__ == "__main__":
    unittest.main()
