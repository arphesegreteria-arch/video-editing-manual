from __future__ import annotations

from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.editorial_selection import (  # noqa: E402
    TranscriptAnchor,
    load_pinned_transcript,
    resolve_anchor,
    validate_candidate_batch,
)
from bridge.editorial_selection_contract import load_selection_contract  # noqa: E402
from bridge.safety import ValidationError  # noqa: E402


CONTRACT = load_selection_contract(ROOT / "editorial_selection_contract.json")


def transcript(count: int = 20, *, clip_seconds: float = 4.0) -> dict[str, object]:
    segments = []
    for index in range(1, count + 1):
        start = (index - 1) * 10.0
        end = start + clip_seconds
        segments.append({
            "start": start,
            "end": end,
            "text": f"apertura {index} contenuto chiusura {index}",
            "words": [
                {"word": f"apertura{index}", "start": start, "end": start + 0.5},
                {"word": "contenuto", "start": start + 0.5, "end": end - 0.5},
                {"word": f"chiusura{index}", "start": end - 0.5, "end": end},
            ],
        })
    return {
        "schema": "ARPHE_TRANSCRIPT_V1",
        "status": "complete",
        "source": {"fingerprint": "s" * 64, "duration_seconds": count * 10.0},
        "segments": segments,
    }


def candidate(index: int, *, clip_seconds: float = 4.0, thesis: str | None = None,
              candidate_id: str | None = None) -> dict[str, object]:
    start = (index - 1) * 10.0
    end = start + clip_seconds
    return {
        "candidate_id": candidate_id or f"R{index:02d}",
        "thesis": thesis or f"Tesi editoriale {index}",
        "start_anchor": {"text": f"apertura{index}"},
        "end_anchor": {"text": f"chiusura{index}"},
        "indispensable_context": f"Contesto necessario {index}",
        "source_start_seconds": start,
        "source_end_seconds": end,
        "speech_duration_seconds": clip_seconds,
        "cta_duration_seconds": 5.0,
        "final_duration_seconds": clip_seconds + 5.0,
        "uniqueness_evidence": f"Argomento distinto {index}",
        "quality_rationale": f"Passaggio autosufficiente {index}",
    }


class EditorialSelectionTests(unittest.TestCase):
    def test_accepts_quality_driven_candidate_counts_without_six_item_quota(self):
        source = transcript()
        for count in (1, 6, 10, 20):
            with self.subTest(count=count):
                resolved = validate_candidate_batch(
                    [candidate(index) for index in range(1, count + 1)],
                    transcript=source,
                    fps=Fraction(24, 1),
                    contract=CONTRACT,
                )
                self.assertEqual(count, len(resolved))
                self.assertEqual([f"R{i:02d}" for i in range(1, count + 1)],
                                 [item.proposal.candidate_id for item in resolved])

    def test_rejects_duplicate_or_nonsequential_ids_and_consolidatable_theses(self):
        source = transcript(3)
        invalid_batches = (
            [candidate(1), candidate(2, candidate_id="R01")],
            [candidate(1), candidate(2, candidate_id="R03")],
            [candidate(1, thesis="Una tesi"), candidate(2, thesis=" una   TESI ")],
        )
        for batch in invalid_batches:
            with self.subTest(batch=batch), self.assertRaises(ValidationError):
                validate_candidate_batch(batch, transcript=source, fps=Fraction(24), contract=CONTRACT)

    def test_rejects_materially_overlapping_duplicate_proposals(self):
        source = transcript(1)
        source["segments"] = [{
            "start": 0.0, "end": 4.25, "text": "due proposte quasi coincidenti",
            "words": [
                {"word": "apertura1", "start": 0.0, "end": 0.5},
                {"word": "secondaapertura", "start": 0.25, "end": 0.75},
                {"word": "contenuto", "start": 0.5, "end": 3.5},
                {"word": "chiusura1", "start": 3.5, "end": 4.0},
                {"word": "secondachiusura", "start": 3.75, "end": 4.25},
            ],
        }]
        second = candidate(2)
        second.update({
            "start_anchor": {"text": "secondaapertura"},
            "end_anchor": {"text": "secondachiusura"},
            "source_start_seconds": 0.25,
            "source_end_seconds": 4.25,
        })

        with self.assertRaisesRegex(ValidationError, "sovrapp"):
            validate_candidate_batch([candidate(1), second], transcript=source,
                                     fps=Fraction(24), contract=CONTRACT)

    def test_final_duration_limit_includes_cta(self):
        for final_seconds, accepted in ((179.99, True), (180.0, True), (180.01, False)):
            speech = final_seconds - 5.0
            source = transcript(1, clip_seconds=speech)
            raw = candidate(1, clip_seconds=speech)
            raw["final_duration_seconds"] = final_seconds
            if accepted:
                self.assertEqual(1, len(validate_candidate_batch(
                    [raw], transcript=source, fps=Fraction(25), contract=CONTRACT
                )))
            else:
                with self.assertRaisesRegex(ValidationError, "180"):
                    validate_candidate_batch([raw], transcript=source,
                                             fps=Fraction(25), contract=CONTRACT)

    def test_frame_conversion_floors_start_and_ceils_exclusive_end(self):
        source = transcript(1, clip_seconds=1.001)
        source["segments"][0]["words"][0].update(start=0.041, end=0.2)
        source["segments"][0]["words"][-1].update(start=0.8, end=1.001)
        raw = candidate(1, clip_seconds=0.96)
        raw.update(source_start_seconds=0.041, source_end_seconds=1.001,
                   speech_duration_seconds=0.96, final_duration_seconds=5.96)

        expected = {Fraction(24): (0, 25), Fraction(25): (1, 26), Fraction(30): (1, 31)}
        for fps, frames in expected.items():
            with self.subTest(fps=fps):
                item = validate_candidate_batch([raw], transcript=source, fps=fps, contract=CONTRACT)[0]
                self.assertEqual(frames, (item.source_in_frame, item.source_out_frame_exclusive))

    def test_repeated_phrase_requires_valid_one_based_occurrence(self):
        source = {
            "schema": "ARPHE_TRANSCRIPT_V1", "status": "complete",
            "source": {"fingerprint": "s" * 64, "duration_seconds": 12.0},
            "segments": [{
                "start": 0.0, "end": 12.0, "text": "frase ripetuta poi frase ripetuta",
                "words": [
                    {"word": "frase", "start": 1.0, "end": 1.3},
                    {"word": "ripetuta", "start": 1.3, "end": 2.0},
                    {"word": "poi", "start": 5.0, "end": 5.3},
                    {"word": "frase", "start": 9.0, "end": 9.3},
                    {"word": "ripetuta", "start": 9.3, "end": 10.0},
                ],
            }],
        }

        with self.assertRaisesRegex(ValidationError, "ambigu"):
            resolve_anchor(source, TranscriptAnchor("frase ripetuta"))
        self.assertEqual(9.0, resolve_anchor(source, TranscriptAnchor("frase ripetuta", 2)))
        with self.assertRaises(ValidationError):
            resolve_anchor(source, TranscriptAnchor("frase ripetuta", 3))

    def test_near_window_disambiguates_repeated_phrase(self):
        source = {
            "schema": "ARPHE_TRANSCRIPT_V1", "status": "complete",
            "source": {"fingerprint": "s" * 64, "duration_seconds": 20.0},
            "segments": [{"start": 0, "end": 20, "text": "x", "words": [
                {"word": "inizia", "start": 2.0, "end": 2.5},
                {"word": "qui", "start": 2.5, "end": 3.0},
                {"word": "inizia", "start": 15.0, "end": 15.5},
                {"word": "qui", "start": 15.5, "end": 16.0},
            ]}],
        }

        self.assertEqual(15.0, resolve_anchor(
            source, TranscriptAnchor("inizia qui"), near_seconds=(14.0, 17.0)
        ))

    def test_load_pinned_transcript_rejects_changed_file_fingerprint(self):
        with tempfile.TemporaryDirectory() as raw_root:
            path = Path(raw_root) / "transcript.json"
            path.write_text(json.dumps(transcript(1)), encoding="utf-8")
            expected = hashlib.sha256(path.read_bytes()).hexdigest()
            loaded = load_pinned_transcript(path, expected)
            self.assertEqual("complete", loaded["status"])
            path.write_text(json.dumps(transcript(2)), encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "fingerprint"):
                load_pinned_transcript(path, expected)

    def test_rejects_empty_evidence_and_anchor_time_disagreement(self):
        source = transcript(1)
        empty = candidate(1)
        empty["quality_rationale"] = " "
        shifted = candidate(1)
        shifted["source_start_seconds"] = 2.0

        for raw in (empty, shifted):
            with self.subTest(raw=raw), self.assertRaises(ValidationError):
                validate_candidate_batch([raw], transcript=source,
                                         fps=Fraction(24), contract=CONTRACT)


if __name__ == "__main__":
    unittest.main()
