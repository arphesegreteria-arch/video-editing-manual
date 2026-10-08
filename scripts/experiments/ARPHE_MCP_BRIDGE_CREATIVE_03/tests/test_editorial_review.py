from __future__ import annotations

import copy
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.editorial_jobs import EditorialJobStore, new_editorial_job  # noqa: E402
from bridge.editorial_review import secretary_instructions, submit_structured_review  # noqa: E402
from bridge.editorial_selection_contract import canonical_digest, load_selection_contract  # noqa: E402
from bridge.safety import ValidationError  # noqa: E402


CONTRACT = load_selection_contract(ROOT / "editorial_selection_contract.json")
TRANSCRIPT_FINGERPRINT = "b" * 64


def timed_transcript() -> dict[str, object]:
    words = [
        {"word": "lontano", "start": 0.0, "end": 0.5},
        {"word": "fuori", "start": 0.5, "end": 1.0},
        {"word": "inizio1", "start": 10.0, "end": 10.5},
        {"word": "fine1", "start": 13.5, "end": 14.0},
        {"word": "inizio2", "start": 100.0, "end": 100.5},
        {"word": "nuovo", "start": 101.0, "end": 101.3},
        {"word": "inizio", "start": 101.3, "end": 101.6},
        {"word": "ripetuto", "start": 102.0, "end": 102.3},
        {"word": "qui", "start": 102.3, "end": 102.6},
        {"word": "ripetuto", "start": 103.0, "end": 103.3},
        {"word": "qui", "start": 103.3, "end": 103.6},
        {"word": "nuova", "start": 105.7, "end": 105.9},
        {"word": "fine", "start": 105.9, "end": 106.0},
        {"word": "fine2", "start": 109.5, "end": 110.0},
        {"word": "inizio3", "start": 200.0, "end": 200.5},
        {"word": "fine3", "start": 203.5, "end": 204.0},
    ]
    return {
        "schema": "ARPHE_TRANSCRIPT_V1", "status": "complete",
        "source": {"fingerprint": "a" * 64, "duration_seconds": 240.0},
        "segments": [{"start": 0.0, "end": 240.0, "text": "transcript test", "words": words}],
        "_pinned_fingerprint": TRANSCRIPT_FINGERPRINT,
    }


def candidate(index: int, start: float, end: float) -> dict[str, object]:
    return {
        "candidate_id": f"R{index:02d}",
        "thesis": f"Tesi {index}",
        "start_anchor": {"text": f"inizio{index}"},
        "end_anchor": {"text": f"fine{index}"},
        "indispensable_context": f"Contesto {index}",
        "source_start_seconds": start,
        "source_end_seconds": end,
        "source_in_frame": int(start * 24),
        "source_out_frame_exclusive": int(end * 24),
        "speech_duration_seconds": end - start,
        "cta_duration_seconds": 5.0,
        "final_duration_seconds": end - start + 5.0,
        "uniqueness_evidence": f"Unico {index}",
        "quality_rationale": f"Forte {index}",
    }


def three_candidates() -> tuple[dict[str, object], ...]:
    return (candidate(1, 10.0, 14.0), candidate(2, 100.0, 110.0), candidate(3, 200.0, 204.0))


def marked_job(store: EditorialJobStore, candidates=None, *, fingerprint: str | None = None):
    selected = tuple(candidates or three_candidates())
    actual_fingerprint = canonical_digest({"candidates": list(selected)})
    job = store.create(new_editorial_job(
        workstation_id="PC_PERSONALE", workflow_version=1,
        project_name="ARPHE_TEST_PROJECT", timeline_name="ARPHE_SOURCE",
        timeline_identity="resolve:timeline-123", source_fingerprint="a" * 64,
        transcript_fingerprint=TRANSCRIPT_FINGERPRINT,
        candidate_fingerprint=fingerprint or actual_fingerprint,
        candidates=selected,
    ))
    return store.save(
        __import__("dataclasses").replace(
            job, state="MARKED",
            markers=({"name": "ARPHE_R01_IN", "frame": 240},),
        ),
        job.revision,
    )


def complete_decisions() -> list[dict[str, object]]:
    return [
        {"candidate_id": "R01", "outcome": "APPROVE", "reason": "chiaro e diretto"},
        {"candidate_id": "R02", "outcome": "MODIFY", "reason": "parte lentamente",
         "start_anchor": {"text": "nuovo inizio"},
         "end_anchor": {"text": "nuova fine"}},
        {"candidate_id": "R03", "outcome": "REJECT", "reason": "ripete il primo"},
    ]


class EditorialReviewTests(unittest.TestCase):
    def test_secretary_instructions_are_compact_specific_and_copyable(self):
        with tempfile.TemporaryDirectory() as raw_root:
            store = EditorialJobStore(Path(raw_root) / "jobs.json", "PC_PERSONALE")
            job = marked_job(store)
            result = secretary_instructions(job)

        self.assertEqual("ARPHE_TEST_PROJECT", result["project"])
        self.assertEqual("ARPHE_SOURCE", result["timeline"])
        self.assertEqual(3, result["candidate_count"])
        self.assertEqual(3, len(result["steps"]))
        self.assertIn("R01 OK", result["example"])
        self.assertIn("MODIFICA", result["example"])
        self.assertIn("RIFIUTA", result["example"])

    def test_complete_review_binds_approve_modify_reject_and_fingerprint(self):
        with tempfile.TemporaryDirectory() as raw_root:
            store = EditorialJobStore(Path(raw_root) / "jobs.json", "PC_PERSONALE")
            marked = marked_job(store)
            reviewed = submit_structured_review(
                store, marked, complete_decisions(), timed_transcript(), CONTRACT
            )

        self.assertEqual("REVIEWED", reviewed.state)
        self.assertRegex(reviewed.review_fingerprint, r"^[0-9a-f]{64}$")
        self.assertEqual(["APPROVE", "MODIFY", "REJECT"],
                         [decision["outcome"] for decision in reviewed.decisions])
        self.assertEqual(101.0, reviewed.decisions[1]["source_start_seconds"])
        self.assertEqual(106.0, reviewed.decisions[1]["source_end_seconds"])
        self.assertEqual("parte lentamente", reviewed.decisions[1]["reason"])

    def test_missing_reason_candidate_or_duplicate_leaves_job_marked(self):
        invalids = []
        missing_reason = complete_decisions()
        missing_reason[0]["reason"] = " "
        invalids.append(missing_reason)
        invalids.append(complete_decisions()[:-1])
        duplicate = complete_decisions()
        duplicate[2]["candidate_id"] = "R02"
        invalids.append(duplicate)

        for decisions in invalids:
            with self.subTest(decisions=decisions), tempfile.TemporaryDirectory() as raw_root:
                store = EditorialJobStore(Path(raw_root) / "jobs.json", "PC_PERSONALE")
                marked = marked_job(store)
                with self.assertRaises(ValidationError):
                    submit_structured_review(store, marked, decisions, timed_transcript(), CONTRACT)
                self.assertEqual("MARKED", store.get(marked.editorial_job_id, "PC_PERSONALE").state)

    def test_ambiguous_modified_anchor_performs_no_transition(self):
        decisions = complete_decisions()
        decisions[1]["start_anchor"] = {"text": "ripetuto qui"}
        with tempfile.TemporaryDirectory() as raw_root:
            store = EditorialJobStore(Path(raw_root) / "jobs.json", "PC_PERSONALE")
            marked = marked_job(store)
            with self.assertRaisesRegex(ValidationError, "ambigu"):
                submit_structured_review(store, marked, decisions, timed_transcript(), CONTRACT)
            self.assertEqual("MARKED", store.get(marked.editorial_job_id, "PC_PERSONALE").state)

    def test_anchor_outside_candidate_neighborhood_is_rejected(self):
        decisions = complete_decisions()
        decisions[1]["start_anchor"] = {"text": "lontano fuori"}
        with tempfile.TemporaryDirectory() as raw_root:
            store = EditorialJobStore(Path(raw_root) / "jobs.json", "PC_PERSONALE")
            marked = marked_job(store)
            with self.assertRaises(ValidationError):
                submit_structured_review(store, marked, decisions, timed_transcript(), CONTRACT)

    def test_stale_transcript_or_candidate_fingerprint_is_rejected(self):
        with tempfile.TemporaryDirectory() as raw_root:
            store = EditorialJobStore(Path(raw_root) / "jobs.json", "PC_PERSONALE")
            marked = marked_job(store)
            changed_transcript = timed_transcript()
            changed_transcript["_pinned_fingerprint"] = "d" * 64
            with self.assertRaisesRegex(ValidationError, "transcript"):
                submit_structured_review(store, marked, complete_decisions(), changed_transcript, CONTRACT)

        with tempfile.TemporaryDirectory() as raw_root:
            store = EditorialJobStore(Path(raw_root) / "jobs.json", "PC_PERSONALE")
            marked = marked_job(store, fingerprint="e" * 64)
            with self.assertRaisesRegex(ValidationError, "candidate"):
                submit_structured_review(store, marked, complete_decisions(), timed_transcript(), CONTRACT)

    def test_modified_final_duration_over_180_seconds_is_rejected(self):
        source = timed_transcript()
        source["segments"][0]["words"].extend([
            {"word": "limiteinizio", "start": 80.0, "end": 80.5},
            {"word": "limitefine", "start": 89.5, "end": 90.0},
            {"word": "estremoinizio", "start": 0.0, "end": 0.5},
            {"word": "estremofine", "start": 175.5, "end": 176.0},
        ])
        source["segments"][0]["words"].sort(key=lambda item: item["start"])
        selected = (candidate(1, 80.0, 90.0),)
        selected[0]["start_anchor"] = {"text": "limiteinizio"}
        selected[0]["end_anchor"] = {"text": "limitefine"}
        decisions = [{
            "candidate_id": "R01", "outcome": "MODIFY", "reason": "serve tutto",
            "start_anchor": {"text": "estremoinizio"},
            "end_anchor": {"text": "estremofine"},
        }]
        with tempfile.TemporaryDirectory() as raw_root:
            store = EditorialJobStore(Path(raw_root) / "jobs.json", "PC_PERSONALE")
            marked = marked_job(store, selected)
            with self.assertRaisesRegex(ValidationError, "180"):
                submit_structured_review(store, marked, decisions, source, CONTRACT)


if __name__ == "__main__":
    unittest.main()
