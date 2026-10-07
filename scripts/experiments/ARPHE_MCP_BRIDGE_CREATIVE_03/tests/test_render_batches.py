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
from bridge.render_batches import (  # noqa: E402
    approve_render_batch, batch_fingerprint, create_render_batch, transition_batch,
)
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


if __name__ == "__main__":
    unittest.main()
