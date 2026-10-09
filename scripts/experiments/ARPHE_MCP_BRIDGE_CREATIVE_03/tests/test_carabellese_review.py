from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.carabellese_contract import (  # noqa: E402
    carabellese_contract_fingerprint,
    load_carabellese_contract,
)
from bridge.carabellese_jobs import CarabelleseJobStore, new_carabellese_job  # noqa: E402
from bridge.carabellese_review import (  # noqa: E402
    carabellese_secretary_instructions,
    submit_carabellese_review,
)
from bridge.safety import ValidationError  # noqa: E402


CONTRACT = load_carabellese_contract(ROOT / "carabellese_cleanup_contract.json")
TX_FP = "2" * 64


def candidates() -> tuple[dict[str, object], ...]:
    base = {"context_before": "prima", "context_after": "dopo", "reason": "proposta",
            "residual_seconds": None, "speaker_turn": False}
    return (
        dict(base, candidate_id="B01", kind="BOUNDARY_START", start_seconds=0.0,
             end_seconds=1.0, start_anchor="intro", end_anchor="primo", review_required=True),
        dict(base, candidate_id="P01", kind="PAUSE_REDUCE", start_seconds=1.6,
             end_seconds=1.9, start_anchor="primo", end_anchor="mezzo", review_required=False,
             residual_seconds=0.7),
        dict(base, candidate_id="C01", kind="EDITORIAL_CUE", start_seconds=2.0,
             end_seconds=3.5, start_anchor="mezzo", end_anchor="ultimo", review_required=False),
    )


def proposal_fingerprint(items) -> str:
    encoded = json.dumps(list(items), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def transcript() -> dict[str, object]:
    return {"schema": "ARPHE_TRANSCRIPT_V1", "status": "complete",
            "source": {"fingerprint": "1" * 64, "duration_seconds": 5.0},
            "segments": [{"start": 0.0, "end": 5.0, "text": "intro primo mezzo ultimo dopo",
                          "words": [
                              {"word": "intro", "start": 0.0, "end": 0.5},
                              {"word": "primo", "start": 1.0, "end": 1.5},
                              {"word": "mezzo", "start": 2.0, "end": 2.5},
                              {"word": "ultimo", "start": 3.0, "end": 3.5},
                              {"word": "dopo", "start": 4.0, "end": 4.5},
                          ]}], "_pinned_fingerprint": TX_FP}


def marked_job(store: CarabelleseJobStore):
    items = candidates()
    created = store.create(new_carabellese_job(
        workstation_id="PC_PERSONALE", workflow_version=CONTRACT.version,
        project_name="STUDIO_CARABELLESE", timeline_name="PODCAST_YOUTUBE",
        timeline_identity="resolve:timeline", timeline_fingerprint="0" * 64,
        source_fingerprint="1" * 64, transcript_fingerprint=TX_FP,
        contract_fingerprint=carabellese_contract_fingerprint(CONTRACT),
        proposal_fingerprint=proposal_fingerprint(items), candidates=items,
    ))
    return store.save(replace(created, state="MARKED", markers=({"frame": 0},)), created.revision)


def boundaries():
    return [{"candidate_id": "B01", "outcome": "REMOVE", "reason": "inizio tecnico"}]


def pause():
    return {"outcome": "SHORTEN", "reason": "ritmo naturale"}


def exceptions():
    return [{"candidate_id": "C01", "outcome": "KEEP", "reason": "frase ironica"}]


class CarabelleseReviewTests(unittest.TestCase):
    def test_secretary_gets_one_compact_card_with_exact_reply_shape(self):
        with tempfile.TemporaryDirectory() as raw_root:
            store = CarabelleseJobStore(Path(raw_root) / "jobs.json", "PC_PERSONALE")
            card = carabellese_secretary_instructions(marked_job(store))
        self.assertEqual(1, card["card_count"])
        self.assertEqual(["B01"], card["boundary_ids"])
        self.assertEqual(["P01"], card["pause_ids"])
        self.assertEqual(["C01"], card["exception_ids"])
        self.assertIn("un solo messaggio", card["instruction"])
        self.assertIn("motivo", card["instruction"])

    def test_complete_review_expands_pause_batch_sorts_decisions_and_fingerprints(self):
        with tempfile.TemporaryDirectory() as raw_root:
            store = CarabelleseJobStore(Path(raw_root) / "jobs.json", "PC_PERSONALE")
            reviewed = submit_carabellese_review(
                store, marked_job(store), boundaries(), pause(), exceptions(), CONTRACT,
                transcript=transcript(),
            )
        self.assertEqual("REVIEWED", reviewed.state)
        self.assertEqual(["B01", "C01", "P01"], [item["candidate_id"] for item in reviewed.decisions])
        self.assertRegex(reviewed.review_fingerprint, r"^[0-9a-f]{64}$")
        self.assertEqual("SHORTEN", reviewed.decisions[2]["outcome"])

    def test_missing_duplicate_unknown_or_empty_reason_leaves_job_marked(self):
        invalids = (
            ([], pause(), exceptions()),
            (boundaries() * 2, pause(), exceptions()),
            (boundaries(), pause(), exceptions() + [{"candidate_id": "X99", "outcome": "KEEP", "reason": "x"}]),
            (boundaries(), {"outcome": "KEEP", "reason": " "}, exceptions()),
        )
        for boundary_input, pause_input, exception_input in invalids:
            with self.subTest(case=(boundary_input, pause_input, exception_input)), tempfile.TemporaryDirectory() as raw_root:
                store = CarabelleseJobStore(Path(raw_root) / "jobs.json", "PC_PERSONALE")
                marked = marked_job(store)
                with self.assertRaises(ValidationError):
                    submit_carabellese_review(store, marked, boundary_input, pause_input,
                                              exception_input, CONTRACT, transcript=transcript())
                self.assertEqual("MARKED", store.get(marked.carabellese_job_id, "PC_PERSONALE").state)

    def test_modify_revalidates_new_transcript_anchors(self):
        modified = [{"candidate_id": "C01", "outcome": "MODIFY", "reason": "taglio migliore",
                     "start_anchor": {"text": "primo"}, "end_anchor": {"text": "dopo"}}]
        with tempfile.TemporaryDirectory() as raw_root:
            store = CarabelleseJobStore(Path(raw_root) / "jobs.json", "PC_PERSONALE")
            reviewed = submit_carabellese_review(
                store, marked_job(store), boundaries(), pause(), modified, CONTRACT,
                transcript=transcript(),
            )
        decision = next(item for item in reviewed.decisions if item["candidate_id"] == "C01")
        self.assertEqual((1.0, 4.5), (decision["start_seconds"], decision["end_seconds"]))

    def test_unknown_modify_anchor_and_stale_transcript_do_not_transition(self):
        bad = [{"candidate_id": "C01", "outcome": "MODIFY", "reason": "x",
                "start_anchor": {"text": "inesistente"}, "end_anchor": {"text": "dopo"}}]
        for source in (transcript(), dict(transcript(), _pinned_fingerprint="9" * 64)):
            with self.subTest(source=source), tempfile.TemporaryDirectory() as raw_root:
                store = CarabelleseJobStore(Path(raw_root) / "jobs.json", "PC_PERSONALE")
                marked = marked_job(store)
                with self.assertRaises(ValidationError):
                    submit_carabellese_review(store, marked, boundaries(), pause(), bad, CONTRACT,
                                              transcript=source)
                self.assertEqual("MARKED", store.get(marked.carabellese_job_id, "PC_PERSONALE").state)

    def test_cue_requires_decision_even_when_candidate_confidence_flag_is_false(self):
        with tempfile.TemporaryDirectory() as raw_root:
            store = CarabelleseJobStore(Path(raw_root) / "jobs.json", "PC_PERSONALE")
            marked = marked_job(store)
            with self.assertRaisesRegex(ValidationError, "incompleta"):
                submit_carabellese_review(store, marked, boundaries(), pause(), [], CONTRACT,
                                          transcript=transcript())


if __name__ == "__main__":
    unittest.main()
