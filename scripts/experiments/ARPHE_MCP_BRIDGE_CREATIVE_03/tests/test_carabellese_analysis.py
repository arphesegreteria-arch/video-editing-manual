from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge.carabellese_analysis import (  # noqa: E402
    cleanup_candidate_fingerprint,
    derive_pause_candidates,
    load_carabellese_inputs,
    validate_cleanup_candidates,
)
from bridge.carabellese_contract import load_carabellese_contract  # noqa: E402
from bridge.config import CreativeConfig, DEFAULT_FLAGS, DEFAULT_PALETTE  # noqa: E402
from bridge.safety import ValidationError  # noqa: E402


CONTRACT = load_carabellese_contract(ROOT / "carabellese_cleanup_contract.json")


def words(gaps: list[float], speakers: list[str] | None = None) -> list[dict[str, object]]:
    result = []
    cursor = 0.0
    for index in range(len(gaps) + 1):
        result.append({"word": f"w{index}", "start": cursor, "end": cursor + 0.4,
                       "speaker": (speakers or ["A"] * (len(gaps) + 1))[index]})
        if index < len(gaps):
            cursor += 0.4 + gaps[index]
    return result


def transcript(source_fingerprint: str = "a" * 64) -> dict[str, object]:
    timed = words([1.0, 2.0])
    return {"schema": "ARPHE_TRANSCRIPT_V1", "status": "complete",
            "source": {"fingerprint": source_fingerprint, "duration_seconds": 10.0},
            "segments": [{"start": 0.0, "end": 4.2, "text": "w0 w1 w2", "words": timed}]}


def raw_candidate(candidate_id: str = "C01", kind: str = "EDITORIAL_CUE",
                  start: float = 1.4, end: float = 2.0) -> dict[str, object]:
    return {"candidate_id": candidate_id, "kind": kind, "start_seconds": start,
            "end_seconds": end, "start_anchor": {"text": "w1"},
            "end_anchor": {"text": "w1"}, "context_before": "w0",
            "context_after": "w2", "reason": "indicazione da verificare",
            "review_required": False, "residual_seconds": None, "speaker_turn": False}


class PauseDerivationTests(unittest.TestCase):
    def test_thresholds_protect_short_gap_contextualize_mid_gap_and_reduce_long_gap(self):
        timed = words([0.69, 1.0, 2.0])
        silences = ({"start": 0.4, "end": 1.09}, {"start": 1.49, "end": 2.49},
                    {"start": 2.89, "end": 4.89})
        candidates = derive_pause_candidates(timed, silences, CONTRACT)

        self.assertEqual(2, len(candidates))
        self.assertEqual(["PAUSE_CONTEXTUAL", "PAUSE_REDUCE"], [item.kind for item in candidates])
        self.assertTrue(candidates[0].review_required)
        self.assertFalse(candidates[1].review_required)
        self.assertAlmostEqual(0.7, candidates[1].residual_seconds, places=3)
        self.assertGreaterEqual(candidates[1].start_seconds, 2.89 + 0.1)
        self.assertLessEqual(candidates[1].end_seconds, 4.89 - 0.1)

    def test_speaker_turn_and_unverified_silence_are_protected(self):
        turn = derive_pause_candidates(
            words([2.0], speakers=["A", "B"]), ({"start": 0.4, "end": 2.4},), CONTRACT
        )
        outside = derive_pause_candidates(
            words([2.0]), ({"start": 0.8, "end": 2.0},), CONTRACT
        )
        self.assertEqual((), turn)
        self.assertEqual((), outside)


class CandidateValidationTests(unittest.TestCase):
    def test_all_editorial_cue_tones_require_individual_review(self):
        source = transcript()
        reasons = ("serio", "ambiguo", "citazione", "ironico")
        for reason in reasons:
            with self.subTest(reason=reason):
                raw = raw_candidate()
                raw["reason"] = reason
                validated = validate_cleanup_candidates([raw], source, CONTRACT, 10.0)
                self.assertTrue(validated[0].review_required)

    def test_boundary_and_manual_candidates_require_anchors_and_context(self):
        source = transcript()
        for kind in ("BOUNDARY_START", "BOUNDARY_END", "MANUAL"):
            with self.subTest(kind=kind):
                raw = raw_candidate(kind=kind)
                self.assertTrue(validate_cleanup_candidates([raw], source, CONTRACT, 10.0)[0].review_required)
                raw["context_before"] = ""
                with self.assertRaisesRegex(ValidationError, "context"):
                    validate_cleanup_candidates([raw], source, CONTRACT, 10.0)

    def test_malformed_overlapping_and_out_of_duration_ranges_fail(self):
        source = transcript()
        malformed = raw_candidate()
        malformed.pop("reason")
        non_boolean = raw_candidate()
        non_boolean["review_required"] = "false"
        overlap = [raw_candidate("C01", start=1.4, end=2.0),
                   raw_candidate("C02", start=1.8, end=2.2)]
        outside = raw_candidate(end=10.1)
        for batch in ([malformed], [non_boolean], overlap, [outside]):
            with self.subTest(batch=batch), self.assertRaises(ValidationError):
                validate_cleanup_candidates(batch, source, CONTRACT, 10.0)

    def test_fingerprint_is_deterministic_and_order_sensitive(self):
        source = transcript()
        first = validate_cleanup_candidates([raw_candidate()], source, CONTRACT, 10.0)
        self.assertRegex(cleanup_candidate_fingerprint(first), r"^[0-9a-f]{64}$")
        self.assertEqual(cleanup_candidate_fingerprint(first), cleanup_candidate_fingerprint(first))


class ProvenanceTests(unittest.TestCase):
    def test_load_inputs_rejects_transcript_or_audio_from_another_source(self):
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            for name in ("media", "transcripts", "audio", "audio_jobs"):
                (root / name).mkdir()
            flags = dict(DEFAULT_FLAGS)
            cfg = CreativeConfig(
                path=root / "config.json", asset_root=root / "assets", render_root=root / "renders",
                state_path=root / "state.json", audit_log_path=root / "audit.jsonl",
                palette=dict(DEFAULT_PALETTE), flags=flags, allowed_projects=frozenset(),
                allowed_timelines=frozenset(), render_format="mp4", render_codec="H264",
                media_roots=(root / "media",), transcript_root=root / "transcripts",
                audio_root=root / "audio", audio_jobs_root=root / "audio_jobs",
            )
            source_fp = "a" * 64
            tx_path = cfg.transcript_root / "tx.json"
            tx_path.write_text(json.dumps(transcript(source_fp)), encoding="utf-8")
            tx_fp = hashlib.sha256(tx_path.read_bytes()).hexdigest()
            wav = cfg.audio_root / "clean.wav"
            wav.write_bytes(b"RIFF")
            manifest = {"schema": "ARPHE_AUDIO_JOB_V2", "job_id": "audio_0123456789abcdef",
                        "status": "COMPLETED", "preset": "NATURAL", "source_fingerprint": source_fp,
                        "output_path": str(wav), "output_sha256": hashlib.sha256(b"RIFF").hexdigest(),
                        "source_duration_seconds": 10.0, "output_duration_seconds": 10.0,
                        "sync_delta_seconds": 0.0, "sample_rate": 48000, "channels": 2,
                        "silence_windows": [{"start": 0.4, "end": 1.4}]}
            (cfg.audio_jobs_root / "audio_0123456789abcdef.json").write_text(
                json.dumps(manifest), encoding="utf-8")

            loaded = load_carabellese_inputs(cfg, tx_path, tx_fp, "audio_0123456789abcdef", source_fp)
            self.assertEqual(source_fp, loaded.source_fingerprint)
            self.assertEqual(((0.4, 1.4),), loaded.silence_windows)
            with self.assertRaisesRegex(ValidationError, "sorgente"):
                load_carabellese_inputs(cfg, tx_path, tx_fp, "audio_0123456789abcdef", "b" * 64)


if __name__ == "__main__":
    unittest.main()
