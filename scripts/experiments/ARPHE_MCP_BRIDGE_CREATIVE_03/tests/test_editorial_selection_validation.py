from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

from scripts.validate_editorial_selection import validate_editorial_selection_ledger  # noqa: E402


CHECKS = {
    "marker_pairs", "complete_review", "cut_outputs", "partial_failure_resume",
    "duration_limit", "cleanup", "rollback_flag",
}


def pending_gate(workstation: str) -> dict:
    return {
        "workstation_id": workstation, "status": "PENDING",
        "checks": {name: "PENDING" for name in sorted(CHECKS)},
        "evidence": [],
        "limitations": ["Live gate not run on this workstation."],
    }


def valid_ledger() -> dict:
    return {
        "schema_version": 1,
        "workflow_id": "ARPHE_PODCAST_REELS_CTA",
        "capability_default": False,
        "automated_evidence": {
            "result": "PASS", "observed_at": "2026-10-08T10:00:00+02:00",
            "repository_commit": "a" * 40, "contract_digest": "b" * 64,
            "test_results": ["bridge automated tests passed", "Windows automated tests passed"],
            "limitations": ["Automated checks do not validate either workstation."],
        },
        "workstation_gates": {
            "PC_PERSONALE": pending_gate("PC_PERSONALE"),
            "PC_SEGRETERIA": pending_gate("PC_SEGRETERIA"),
        },
    }


class EditorialSelectionValidationTests(unittest.TestCase):
    def validate(self, payload: dict) -> list[str]:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            return validate_editorial_selection_ledger(path)

    def test_accepts_automated_pass_with_two_independent_pending_gates(self):
        self.assertEqual([], self.validate(valid_ledger()))

    def test_requires_both_exact_workstation_gates(self):
        payload = valid_ledger(); del payload["workstation_gates"]["PC_SEGRETERIA"]
        self.assertTrue(any("workstation_gates" in error for error in self.validate(payload)))

    def test_live_evidence_cannot_validate_another_workstation(self):
        payload = valid_ledger(); gate = payload["workstation_gates"]["PC_PERSONALE"]
        gate["status"] = "VALIDATED"; gate["checks"] = {name: "PASS" for name in CHECKS}
        gate["evidence"] = [{
            "evidence_id": "personal-live-1", "workstation_id": "PC_SEGRETERIA",
            "observed_at": "2026-10-08T11:00:00+02:00", "result": "PASS",
            "checks": sorted(CHECKS), "limitations": ["Synthetic disposable project."],
        }]
        errors = self.validate(payload)
        self.assertTrue(any("another workstation" in error for error in errors))

    def test_rejects_unsupported_status_and_incomplete_validated_gate(self):
        payload = valid_ledger(); gate = payload["workstation_gates"]["PC_PERSONALE"]
        gate["status"] = "DONE"
        self.assertTrue(any("status" in error for error in self.validate(payload)))
        gate["status"] = "VALIDATED"; gate["checks"]["marker_pairs"] = "PASS"
        self.assertTrue(any("VALIDATED" in error for error in self.validate(payload)))

    def test_rejects_sensitive_content_recursively(self):
        for key, value in (
            ("human_reason", "parte lentamente"),
            ("start_anchor", "frase esatta"),
            ("source_path", "C:/Users/alessio/podcast.mov"),
            ("details", {"nested": "editorial_0123456789abcdef"}),
        ):
            with self.subTest(key=key):
                payload = valid_ledger()
                payload["automated_evidence"][key] = value
                self.assertTrue(any("sensitive" in error for error in self.validate(payload)))

    def test_rejects_fake_future_timestamp(self):
        payload = valid_ledger()
        payload["automated_evidence"]["observed_at"] = "2099-01-01T00:00:00+00:00"
        self.assertTrue(any("future" in error for error in self.validate(payload)))


if __name__ == "__main__":
    unittest.main()
