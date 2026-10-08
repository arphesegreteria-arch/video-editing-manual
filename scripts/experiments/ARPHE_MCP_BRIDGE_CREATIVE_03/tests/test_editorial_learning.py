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

from bridge.config import CreativeConfig, DEFAULT_FLAGS, DEFAULT_PALETTE  # noqa: E402
from bridge.editorial_jobs import EditorialJob, new_editorial_job  # noqa: E402
from bridge.editorial_learning import (  # noqa: E402
    append_local_outcome,
    approve_profile_proposal,
    compile_profile_proposal,
    inspect_local_metrics,
    load_effective_preferences,
    validate_profile_proposal_privacy,
)
from bridge.editorial_selection_contract import load_preference_profile  # noqa: E402
from bridge.safety import ValidationError  # noqa: E402


SHARED_PATH = ROOT / "editorial_preferences.json"


def config(root: Path, workstation: str = "PC_PERSONALE") -> CreativeConfig:
    return CreativeConfig(
        path=root / "config.json", asset_root=root / "assets", render_root=root / "renders",
        state_path=root / "state.json", audit_log_path=root / "audit.jsonl",
        palette=dict(DEFAULT_PALETTE), flags=dict(DEFAULT_FLAGS),
        allowed_projects=frozenset(), allowed_timelines=frozenset(),
        render_format="mp4", render_codec="H264", workstation_id=workstation,
        editorial_journal_path=root / "editorial_journal.jsonl",
        editorial_profile_overlay_path=root / "editorial_profile_overlay.json",
        editorial_profile_proposals_path=root / "editorial_profile_proposals.json",
    )


def verified_job(index: int = 1, workstation: str = "PC_PERSONALE") -> EditorialJob:
    candidates = (
        {"candidate_id": "R01", "source_start_seconds": 10.0, "source_end_seconds": 30.0,
         "final_duration_seconds": 25.0, "thesis": "Testo privato"},
        {"candidate_id": "R02", "source_start_seconds": 40.0, "source_end_seconds": 70.0,
         "final_duration_seconds": 35.0, "thesis": "Altro testo privato"},
        {"candidate_id": "R03", "source_start_seconds": 80.0, "source_end_seconds": 100.0,
         "final_duration_seconds": 25.0, "thesis": "Terzo testo privato"},
    )
    job = new_editorial_job(
        workstation_id=workstation, workflow_version=1,
        project_name=f"Podcast Alessio {index}", timeline_name="C:/privato/podcast.mov",
        timeline_identity=f"resolve:source-{index}", source_fingerprint=f"{index:064x}",
        transcript_fingerprint="b" * 64, candidate_fingerprint="c" * 64,
        candidates=candidates,
    )
    decisions = (
        {"candidate_id": "R01", "outcome": "APPROVE", "reason": "Chiaro e diretto",
         "normalized_reason_tags": ["chiaro_diretto"],
         "proposed_start_seconds": 10.0, "proposed_end_seconds": 30.0,
         "source_start_seconds": 10.0, "source_end_seconds": 30.0,
         "final_duration_seconds": 25.0},
        {"candidate_id": "R02", "outcome": "MODIFY", "reason": "Parte lentamente",
         "normalized_reason_tags": ["apertura_lenta"],
         "proposed_start_seconds": 40.0, "proposed_end_seconds": 70.0,
         "source_start_seconds": 45.0, "source_end_seconds": 68.0,
         "final_duration_seconds": 28.0},
        {"candidate_id": "R03", "outcome": "REJECT", "reason": "Ripete il primo",
         "normalized_reason_tags": ["tesi_ripetuta"],
         "proposed_start_seconds": 80.0, "proposed_end_seconds": 100.0,
         "source_start_seconds": 80.0, "source_end_seconds": 100.0,
         "final_duration_seconds": 25.0},
    )
    return replace(
        job, state="VERIFIED", review_fingerprint="d" * 64, decisions=decisions,
        operations=({"candidate_id": "R01", "status": "VERIFIED"},),
        state_timestamps={
            "ANALYZED": "2026-10-08T08:50:00Z", "MARKED": "2026-10-08T09:00:00Z",
            "REVIEWED": "2026-10-08T09:05:30Z", "VERIFIED": "2026-10-08T09:08:00Z",
        },
    )


class EditorialLearningTests(unittest.TestCase):
    def test_verified_outcome_records_local_details_and_metrics_once(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = config(Path(directory))
            job = verified_job()
            first = append_local_outcome(cfg, job)
            replay = append_local_outcome(cfg, job)
            metrics = inspect_local_metrics(cfg)
            records = [json.loads(line) for line in cfg.editorial_journal_path.read_text(
                encoding="utf-8").splitlines()]

        self.assertEqual(first, replay)
        self.assertEqual(3, len(records))
        self.assertEqual({"APPROVE", "MODIFY", "REJECT"}, {r["outcome"] for r in records})
        self.assertEqual("Parte lentamente", records[1]["human_reason"])
        self.assertEqual(["apertura_lenta"], records[1]["normalized_reason_tags"])
        self.assertEqual(5.0, records[1]["start_delta_seconds"])
        self.assertEqual(-2.0, records[1]["end_delta_seconds"])
        self.assertEqual(330.0, metrics["review_latency_seconds"])
        self.assertNotIn("active_labor", json.dumps(metrics))
        self.assertEqual(1 / 3, metrics["accepted_unchanged_rate"])
        self.assertEqual(1 / 3, metrics["modification_rate"])
        self.assertEqual(1 / 3, metrics["rejection_rate"])
        self.assertEqual(1, metrics["boundary_correction_count"])

    def test_nonverified_or_foreign_job_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = config(Path(directory))
            with self.assertRaisesRegex(ValidationError, "VERIFIED"):
                append_local_outcome(cfg, replace(verified_job(), state="REVIEWED"))
            with self.assertRaisesRegex(ValidationError, "workstation"):
                append_local_outcome(cfg, verified_job(workstation="PC_SEGRETERIA"))
            self.assertFalse(cfg.editorial_journal_path.exists())

    def test_compiler_requires_samples_is_redacted_and_never_writes_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = config(Path(directory))
            shared = load_preference_profile(SHARED_PATH)
            before = SHARED_PATH.read_bytes()
            append_local_outcome(cfg, verified_job())
            with self.assertRaisesRegex(ValidationError, "campioni"):
                compile_profile_proposal(cfg, shared, minimum_samples=4)
            proposal = compile_profile_proposal(cfg, shared, minimum_samples=3)
            after = SHARED_PATH.read_bytes()

        encoded = json.dumps(proposal, ensure_ascii=False)
        self.assertEqual(before, after)
        self.assertEqual(shared.digest, proposal["prior_profile_digest"])
        self.assertEqual(3, proposal["sample_count"])
        for secret in ("Chiaro e diretto", "Alessio", "C:/privato", "editorial_"):
            self.assertNotIn(secret, encoded)
        self.assertEqual(
            {"preferred_duration_seconds", "weak_opening_tags",
             "context_reduction_seconds", "unchanged_approval_tags"},
            set(proposal["aggregate_preferences"]),
        )

    def test_recursive_privacy_validator_rejects_nested_sensitive_values(self):
        sensitive = {
            "job_ids": ["editorial_0123456789abcdef"],
            "private_strings": ["Alessio", "frase esatta", "C:/Users/alessio/video.mov"],
        }
        for leaked in (
            {"nested": [{"value": "editorial_0123456789abcdef"}]},
            {"nested": {"value": "parere di Alessio"}},
            {"nested": ["C:/Users/alessio/video.mov"]},
            {"nested": {"quote": "frase esatta"}},
        ):
            with self.subTest(leaked=leaked), self.assertRaises(ValidationError):
                validate_profile_proposal_privacy(leaked, sensitive)

    def test_compiler_omits_unsupported_aggregates_instead_of_inventing_values(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = config(Path(directory))
            shared = load_preference_profile(SHARED_PATH)
            job = verified_job()
            approvals = tuple({
                **decision,
                "outcome": "APPROVE",
                "normalized_reason_tags": ["chiaro_diretto"],
                "source_start_seconds": decision["proposed_start_seconds"],
                "source_end_seconds": decision["proposed_end_seconds"],
                "final_duration_seconds": (
                    decision["proposed_end_seconds"] - decision["proposed_start_seconds"] + 5.0
                ),
            } for decision in job.decisions)
            append_local_outcome(cfg, replace(job, decisions=approvals))
            proposal = compile_profile_proposal(cfg, shared, minimum_samples=3)

        self.assertNotIn("context_reduction_seconds", proposal["aggregate_preferences"])
        self.assertNotIn("weak_opening_tags", proposal["aggregate_preferences"])
        self.assertEqual(set(proposal["aggregate_preferences"]), set(proposal["sample_counts"]))

    def test_approval_requires_alessio_current_digest_and_is_single_use(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = config(Path(directory))
            shared = load_preference_profile(SHARED_PATH)
            append_local_outcome(cfg, verified_job())
            proposal = compile_profile_proposal(cfg, shared, minimum_samples=3)
            proposal_id = proposal["proposal_id"]
            with self.assertRaisesRegex(ValidationError, "Alessio"):
                approve_profile_proposal(cfg, proposal_id, "SEGRETERIA", shared.digest)
            with self.assertRaisesRegex(ValidationError, "stale"):
                approve_profile_proposal(cfg, proposal_id, "ALESSIO", "f" * 64)
            approved = approve_profile_proposal(cfg, proposal_id, "ALESSIO", shared.digest)
            with self.assertRaisesRegex(ValidationError, "già approvata"):
                approve_profile_proposal(cfg, proposal_id, "ALESSIO", shared.digest)
            overlay = json.loads(cfg.editorial_profile_overlay_path.read_text(encoding="utf-8"))

        self.assertEqual(shared.digest, overlay["prior_profile_digest"])
        self.assertEqual(proposal["proposed_profile_digest"], overlay["proposed_profile_digest"])
        self.assertEqual(proposal_id, approved["proposal_id"])

    def test_foreign_proposal_store_blocks_and_effective_merge_is_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cfg = config(root)
            shared = load_preference_profile(SHARED_PATH)
            cfg.editorial_profile_proposals_path.write_text(json.dumps({
                "schema": "ARPHE_EDITORIAL_PROPOSALS_V1", "workstation_id": "PC_SEGRETERIA",
                "proposals": {},
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "workstation"):
                compile_profile_proposal(cfg, shared, minimum_samples=1)
            cfg.editorial_profile_proposals_path.unlink()
            append_local_outcome(cfg, verified_job())
            proposal = compile_profile_proposal(cfg, shared, minimum_samples=3)
            approve_profile_proposal(cfg, proposal["proposal_id"], "ALESSIO", shared.digest)
            first = load_effective_preferences(cfg, shared)
            second = load_effective_preferences(cfg, shared)

        self.assertEqual(first, second)
        self.assertEqual(proposal["aggregate_preferences"], first["aggregate_preferences"])
        self.assertEqual(proposal["sample_counts"], first["sample_counts"])
        self.assertEqual(shared.digest, first["shared_profile_digest"])
        self.assertEqual(proposal["proposed_profile_digest"], first["local_overlay_digest"])


if __name__ == "__main__":
    unittest.main()
