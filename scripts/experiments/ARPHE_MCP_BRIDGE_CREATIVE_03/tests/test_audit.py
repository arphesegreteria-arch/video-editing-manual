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


if __name__ == "__main__":
    unittest.main()
