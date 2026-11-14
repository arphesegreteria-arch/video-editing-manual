from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.audit import write_audit  # noqa: E402


class AuditTests(unittest.TestCase):
    def test_audit_excludes_inputs_paths_and_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            write_audit(path, "add_review_card", {
                "ok": False, "stage": "validation", "error_type": "ValidationError",
                "text": "patient private text", "path": "C:/secret", "api_key": "SENSITIVE_MARKER",
            })
            raw = path.read_text(encoding="utf-8")
            record = json.loads(raw)
            self.assertEqual("add_review_card", record["action"])
            self.assertNotIn("patient", raw)
            self.assertNotIn("C:/", raw)
            self.assertNotIn("SENSITIVE_MARKER", raw)

    def test_batch_audit_records_role_transition_fingerprint_and_job_ids_but_no_paths_or_content(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            write_audit(path, "approve_render_batch", {
                "ok": True, "batch_id": "batch-1", "actor_role": "SEGRETERIA",
                "transition": "PREPARED->APPROVED", "fingerprint": "abc123",
                "job_ids": ["job-1"], "approval_token": "secret-token",
                "path": "C:/patients/private", "brief_text": "private review",
            })
            raw = path.read_text(encoding="utf-8")
            record = json.loads(raw)
            self.assertEqual(["job-1"], record["job_ids"])
            self.assertEqual("PREPARED->APPROVED", record["transition"])
            self.assertNotIn("secret-token", raw)
            self.assertNotIn("patients", raw)
            self.assertNotIn("private review", raw)

    def test_timeline_control_audit_keeps_only_opaque_ids_and_fingerprints(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            write_audit(path, "execute_timeline_element_removal", {
                "ok": True,
                "workstation_id": "PC_PERSONALE",
                "element_id": "element_opaque",
                "removal_id": "removal_opaque",
                "fingerprint": "a" * 64,
                "proposal_fingerprint": "b" * 64,
                "project": "PRIVATE_PROJECT",
                "timeline": "PRIVATE_TIMELINE",
                "display_name": "patient private overlay",
                "path": "C:/patients/private.mov",
            })
            raw = path.read_text(encoding="utf-8")
            record = json.loads(raw)
            self.assertEqual("PC_PERSONALE", record["workstation_id"])
            self.assertEqual("element_opaque", record["element_id"])
            self.assertEqual("removal_opaque", record["removal_id"])
            self.assertEqual("a" * 64, record["fingerprint"])
            self.assertEqual("b" * 64, record["proposal_fingerprint"])
            self.assertNotIn("PRIVATE", raw)
            self.assertNotIn("patient", raw)
            self.assertNotIn("C:/", raw)


if __name__ == "__main__":
    unittest.main()
