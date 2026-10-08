from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

from scripts.validate_review_readability_ledger import validate_readability_ledger  # noqa: E402


VIDEO_COMMIT = "f500179ef58aed2b706aa364bf4caa9c06983d4c"
GRAPHIC_COMMIT = "665ed816176bc76b6b10ca5f274b0054b2791437"
POLICY_DIGEST = "68b240d727e23707b4b64e5da069c47519e166a25bce94e33cc3de5ae005c0fe"
STATE_REFERENCE = "CURRENT_STATE.md#review-readability-guard"


def evidence(kind: str, result: str, workstation_id: str | None = None) -> dict:
    return {
        "evidence_id": f"readability-{kind.lower().replace('_', '-')}",
        "kind": kind,
        "workstation_id": workstation_id,
        "video_repository_commit": VIDEO_COMMIT,
        "graphic_kit_repository_commit": GRAPHIC_COMMIT,
        "policy_version": "ARPHE_VIDEO_READABILITY_V1",
        "policy_digest": POLICY_DIGEST,
        "observed_at": "2026-10-08T20:00:00+02:00",
        "result": result,
        "limitations": ["Live Resolve evidence not implied by automated checks."],
        "current_state_reference": STATE_REFERENCE,
        "validated_workstations": [workstation_id] if result == "PASS" and workstation_id else [],
    }


def valid_ledger() -> dict:
    return {
        "schema_version": 1,
        "evidence": [
            evidence("AUTOMATED", "PASS"),
            evidence("PC_PERSONALE_LIVE", "PENDING", "PC_PERSONALE"),
            evidence("PC_SEGRETERIA_LIVE", "PENDING", "PC_SEGRETERIA"),
        ],
    }


class ReadabilityValidationTests(unittest.TestCase):
    def validate(self, payload: dict, state: str = f'<a id="review-readability-guard"></a>\n{STATE_REFERENCE}'):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ledger = root / "ledger.json"
            current_state = root / "CURRENT_STATE.md"
            ledger.write_text(json.dumps(payload), encoding="utf-8")
            current_state.write_text(state, encoding="utf-8")
            return validate_readability_ledger(ledger, current_state)

    def test_accepts_automated_pass_and_two_explicitly_pending_workstations(self):
        self.assertEqual([], self.validate(valid_ledger()))

    def test_requires_exact_schema_evidence_fields_and_values(self):
        payload = valid_ledger()
        payload["schema_version"] = 2
        del payload["evidence"][0]["policy_digest"]
        payload["evidence"][1]["video_repository_commit"] = "short"
        payload["evidence"][2]["observed_at"] = "yesterday"
        errors = self.validate(payload)
        self.assertTrue(any("schema_version" in item for item in errors))
        self.assertTrue(any("policy_digest" in item for item in errors))
        self.assertTrue(any("video_repository_commit" in item for item in errors))
        self.assertTrue(any("observed_at" in item for item in errors))

    def test_rejects_raw_review_content_anywhere_in_evidence(self):
        payload = valid_ledger()
        payload["evidence"][0]["details"] = {"review_text": "testo che non deve essere salvato"}
        errors = self.validate(payload)
        self.assertTrue(any("raw review" in item.lower() for item in errors))

    def test_live_evidence_requires_matching_identity_and_cannot_validate_other_pc(self):
        payload = valid_ledger()
        payload["evidence"][1]["workstation_id"] = None
        payload["evidence"][2]["result"] = "PASS"
        payload["evidence"][2]["validated_workstations"] = ["PC_PERSONALE"]
        errors = self.validate(payload)
        self.assertTrue(any("workstation_id" in item for item in errors))
        self.assertTrue(any("cannot validate" in item.lower() for item in errors))

    def test_every_reference_must_point_into_current_state(self):
        errors = self.validate(valid_ledger(), state="# CURRENT STATE\nNo matching section.")
        self.assertTrue(any("current_state_reference" in item for item in errors))


if __name__ == "__main__":
    unittest.main()
