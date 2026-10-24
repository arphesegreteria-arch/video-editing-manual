from __future__ import annotations

from pathlib import Path
import json
import multiprocessing
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge import server  # noqa: E402
from bridge.config import CreativeConfig, DEFAULT_FLAGS, DEFAULT_PALETTE  # noqa: E402
from bridge.safety import ValidationError  # noqa: E402
from bridge.voice_isolation import (  # noqa: E402
    VoiceIsolationStore, capture_track, apply_voice_isolation, restore_voice_isolation,
)


class FakeTimeline:
    def __init__(self):
        self.state = {1: {"isEnabled": False, "amount": 0}}
        self.name = "ARPHE Audio"
        self.uid = "timeline-1"
        self.set_calls = []
        self.mutate_on_set = True

    def GetName(self): return self.name
    def GetUniqueId(self): return self.uid
    def GetTrackCount(self, kind): return 1 if kind == "audio" else 0
    def GetTrackName(self, kind, index): return "Dialogue" if kind == "audio" and index == 1 else ""
    def GetVoiceIsolationState(self, index): return dict(self.state[index])
    def SetVoiceIsolationState(self, index, state):
        self.set_calls.append((index, dict(state)))
        if self.mutate_on_set:
            self.state[index] = dict(state)
        return True


class FakeProject:
    def GetName(self): return "ARPHE_TEST"


def _prepare_in_process(ledger_path: str, ready: multiprocessing.synchronize.Event,
                        start: multiprocessing.synchronize.Event,
                        output: multiprocessing.queues.Queue) -> None:
    store = VoiceIsolationStore(Path(ledger_path), "PC_PERSONALE")
    card = capture_track(FakeProject(), FakeTimeline(), 1)
    ready.set()
    start.wait(10)
    try:
        output.put(("ok", store.prepare(card, 60)["job_id"]))
    except Exception as exc:
        output.put(("error", type(exc).__name__, str(exc)))


def _apply_in_process(ledger_path: str, job_id: str, entered: multiprocessing.queues.Queue,
                      release: multiprocessing.synchronize.Event,
                      output: multiprocessing.queues.Queue) -> None:
    store = VoiceIsolationStore(Path(ledger_path), "PC_PERSONALE")
    try:
        def operation(_job):
            entered.put("entered")
            release.wait(10)
            return "written"
        output.put(("ok", store.apply(job_id, operation)))
    except Exception as exc:
        output.put(("error", type(exc).__name__, str(exc)))


def _config(root: Path, enabled: bool) -> CreativeConfig:
    flags = dict(DEFAULT_FLAGS)
    flags["CAP_VOICE_ISOLATION"] = enabled
    return CreativeConfig(
        root / "config.json", root / "assets", root / "renders", root / "state.json",
        root / "audit.jsonl", dict(DEFAULT_PALETTE), flags, frozenset(), frozenset(), "mp4", "H264",
        workstation_id="PC_PERSONALE",
    )


class VoiceIsolationTests(unittest.TestCase):
    def test_prepare_blocks_target_while_restore_is_interrupted(self):
        with tempfile.TemporaryDirectory() as root:
            store = VoiceIsolationStore(Path(root) / "jobs.json", "PC_PERSONALE")
            capture = capture_track(FakeProject(), FakeTimeline(), 1)
            job = store.prepare(capture, 60)
            store.transition(job["job_id"], "PREPARED", "RESTORING")
            with self.assertRaisesRegex(ValidationError, "attivo"):
                store.prepare(capture, 40)

    def test_apply_refuses_state_drift_before_write(self):
        timeline = FakeTimeline()
        capture = capture_track(FakeProject(), timeline, 1)
        timeline.state[1] = {"isEnabled": True, "amount": 35}
        with self.assertRaisesRegex(ValidationError, "cambiato"):
            apply_voice_isolation(FakeProject(), timeline, capture, 60)
        self.assertEqual([], timeline.set_calls)
    def test_capture_requires_typed_getter_and_stable_audio_target(self):
        card = capture_track(FakeProject(), FakeTimeline(), 1)
        self.assertEqual("timeline-1", card.target.timeline_id)
        self.assertEqual("Dialogue", card.target.track_name)
        self.assertFalse(card.initial.is_enabled)
        self.assertEqual(0, card.initial.amount)

    def test_apply_validates_amount_before_writing(self):
        timeline = FakeTimeline()
        card = capture_track(FakeProject(), timeline, 1)
        with self.assertRaisesRegex(ValidationError, "amount"):
            apply_voice_isolation(FakeProject(), timeline, card, 101)
        self.assertEqual([], timeline.set_calls)

    def test_apply_reads_back_exact_requested_state(self):
        timeline = FakeTimeline()
        card = capture_track(FakeProject(), timeline, 1)
        result = apply_voice_isolation(FakeProject(), timeline, card, 65)
        self.assertEqual({"isEnabled": True, "amount": 65}, result.current.as_dict())
        self.assertEqual([(1, {"isEnabled": True, "amount": 65})], timeline.set_calls)

    def test_apply_refuses_changed_timeline_before_writing(self):
        timeline = FakeTimeline()
        card = capture_track(FakeProject(), timeline, 1)
        timeline.uid = "other-timeline"
        with self.assertRaisesRegex(ValidationError, "cambiato"):
            apply_voice_isolation(FakeProject(), timeline, card, 40)
        self.assertEqual([], timeline.set_calls)

    def test_restore_requires_expected_current_state_and_reads_back_initial(self):
        timeline = FakeTimeline()
        card = capture_track(FakeProject(), timeline, 1)
        applied = apply_voice_isolation(FakeProject(), timeline, card, 70)
        restored = restore_voice_isolation(FakeProject(), timeline, card, applied.current)
        self.assertEqual({"isEnabled": False, "amount": 0}, restored.current.as_dict())

    def test_restore_refuses_concurrent_change(self):
        timeline = FakeTimeline()
        card = capture_track(FakeProject(), timeline, 1)
        applied = apply_voice_isolation(FakeProject(), timeline, card, 70)
        timeline.state[1] = {"isEnabled": True, "amount": 35}
        with self.assertRaisesRegex(ValidationError, "concorrente"):
            restore_voice_isolation(FakeProject(), timeline, card, applied.current)

    def test_write_true_without_readback_is_failure(self):
        timeline = FakeTimeline()
        timeline.mutate_on_set = False
        card = capture_track(FakeProject(), timeline, 1)
        with self.assertRaisesRegex(RuntimeError, "read-back"):
            apply_voice_isolation(FakeProject(), timeline, card, 50)

    def test_ledger_persists_prepare_and_excludes_second_active_job(self):
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            store = VoiceIsolationStore(Path(root) / "jobs.json", "PC_PERSONALE")
            card = capture_track(FakeProject(), FakeTimeline(), 1)
            job = store.prepare(card, 60)
            self.assertEqual("PREPARED", VoiceIsolationStore(Path(root) / "jobs.json", "PC_PERSONALE").get(job["job_id"])["state"])
            with self.assertRaisesRegex(ValidationError, "attivo"):
                store.prepare(card, 61)

    def test_ledger_allows_apply_restore_transitions_and_keeps_interrupted_apply_recoverable(self):
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            store = VoiceIsolationStore(Path(root) / "jobs.json", "PC_PERSONALE")
            job = store.prepare(capture_track(FakeProject(), FakeTimeline(), 1), 60)
            self.assertEqual("APPLYING", store.transition(job["job_id"], "PREPARED", "APPLYING")["state"])
            self.assertEqual("APPLYING", VoiceIsolationStore(
                Path(root) / "jobs.json", "PC_PERSONALE").get(job["job_id"])["state"])

    def test_ledger_prepare_is_atomic_across_two_contending_processes(self):
        with tempfile.TemporaryDirectory() as root:
            context = multiprocessing.get_context("spawn")
            ready, start, output = context.Event(), context.Event(), context.Queue()
            processes = [context.Process(target=_prepare_in_process,
                                         args=(str(Path(root) / "jobs.json"), ready, start, output))
                         for _ in range(2)]
            for process in processes: process.start()
            for process in processes: self.assertTrue(ready.wait(10))
            start.set()
            results = [output.get(timeout=10) for _ in processes]
            for process in processes:
                process.join(10)
                self.assertEqual(0, process.exitcode)
            self.assertEqual(1, sum(result[0] == "ok" for result in results))
            self.assertEqual(1, sum(result[0] == "error" and result[1] == "ValidationError" for result in results))
            ledger = json.loads((Path(root) / "jobs.json").read_text(encoding="utf-8"))
            self.assertEqual(1, len(ledger["jobs"]))

    def test_ledger_apply_lock_serializes_the_entire_mutation_across_processes(self):
        with tempfile.TemporaryDirectory() as root:
            ledger_path = Path(root) / "jobs.json"
            job = VoiceIsolationStore(ledger_path, "PC_PERSONALE").prepare(
                capture_track(FakeProject(), FakeTimeline(), 1), 60)
            context = multiprocessing.get_context("spawn")
            entered, release, output = context.Queue(), context.Event(), context.Queue()
            processes = [context.Process(target=_apply_in_process,
                                         args=(str(ledger_path), job["job_id"], entered, release, output))
                         for _ in range(2)]
            for process in processes: process.start()
            self.assertEqual("entered", entered.get(timeout=10))
            self.assertTrue(entered.empty())
            release.set()
            results = [output.get(timeout=10) for _ in processes]
            for process in processes:
                process.join(10)
                self.assertEqual(0, process.exitcode)
            self.assertEqual(1, sum(result[0] == "ok" for result in results))
            self.assertEqual(1, sum(result[0] == "error" and result[1] == "ValidationError" for result in results))

    def test_restore_recovers_interrupted_apply_only_when_requested_state_is_still_present(self):
        with tempfile.TemporaryDirectory() as root:
            store = VoiceIsolationStore(Path(root) / "jobs.json", "PC_PERSONALE")
            timeline = FakeTimeline()
            capture = capture_track(FakeProject(), timeline, 1)
            job = store.prepare(capture, 60)
            store.transition(job["job_id"], "PREPARED", "APPLYING")
            apply_voice_isolation(FakeProject(), timeline, capture, 60)
            recovered = store.get(job["job_id"])
            self.assertEqual("APPLYING", recovered["state"])
            restored = restore_voice_isolation(FakeProject(), timeline, capture,
                                               type(capture.initial)(True, 60))
            self.assertEqual({"isEnabled": False, "amount": 0}, restored.current.as_dict())

    def test_endpoints_fail_closed_when_gate_is_disabled_before_runtime(self):
        config = _config(Path("unused"), enabled=False)
        with patch("bridge.server.load_config", return_value=config), \
             patch("bridge.server._runtime", side_effect=AssertionError("runtime touched")):
            prepared = server.prepare_voice_isolation(1, 60)
            applied = server.apply_voice_isolation_job("voice_x")
            restored = server.restore_voice_isolation_job("voice_x")
        for result in (prepared, applied, restored):
            self.assertFalse(result["ok"])
            self.assertIn("CAP_VOICE_ISOLATION", result["error"])

    def test_inspect_endpoint_is_read_only_while_gate_is_disabled(self):
        with tempfile.TemporaryDirectory() as root:
            config = _config(Path(root), enabled=False)
            project, timeline = FakeProject(), FakeTimeline()
            runtime = (object(), object(), project, timeline, config, object(), None)
            with patch("bridge.server._runtime", return_value=runtime):
                inspected = server.inspect_voice_isolation(1)
            self.assertTrue(inspected["ok"])
            self.assertFalse(inspected["capability_enabled"])
            self.assertEqual({"isEnabled": False, "amount": 0}, inspected["current"])
            self.assertEqual([], timeline.set_calls)

    def test_endpoint_apply_rejects_target_drift_and_keeps_recovery_ledger(self):
        with tempfile.TemporaryDirectory() as root:
            config = _config(Path(root), enabled=True)
            project, timeline = FakeProject(), FakeTimeline()
            runtime = (object(), object(), project, timeline, config, object(), None)
            with patch("bridge.server.load_config", return_value=config), \
                 patch("bridge.server._runtime", return_value=runtime):
                prepared = server.prepare_voice_isolation(1, 60)
                timeline.uid = "different-timeline"
                applied = server.apply_voice_isolation_job(prepared["voice_job_id"])
            self.assertFalse(applied["ok"])
            self.assertIn("cambiato", applied["error"])
            self.assertEqual([], timeline.set_calls)
            self.assertEqual("APPLYING", VoiceIsolationStore(
                config.state_path.parent / "voice_isolation_jobs.json", "PC_PERSONALE"
            ).get(prepared["voice_job_id"])["state"])

    def test_endpoint_apply_readback_failure_preserves_recoverable_ledger(self):
        with tempfile.TemporaryDirectory() as root:
            config = _config(Path(root), enabled=True)
            project, timeline = FakeProject(), FakeTimeline()
            timeline.mutate_on_set = False
            runtime = (object(), object(), project, timeline, config, object(), None)
            with patch("bridge.server.load_config", return_value=config), \
                 patch("bridge.server._runtime", return_value=runtime):
                prepared = server.prepare_voice_isolation(1, 60)
                applied = server.apply_voice_isolation_job(prepared["voice_job_id"])
            self.assertFalse(applied["ok"])
            self.assertIn("read-back", applied["error"])
            self.assertEqual("APPLYING", VoiceIsolationStore(
                config.state_path.parent / "voice_isolation_jobs.json", "PC_PERSONALE"
            ).get(prepared["voice_job_id"])["state"])

    def test_endpoint_restore_recovers_after_apply_crash_without_overwriting_external_change(self):
        with tempfile.TemporaryDirectory() as root:
            config = _config(Path(root), enabled=True)
            project, timeline = FakeProject(), FakeTimeline()
            runtime = (object(), object(), project, timeline, config, object(), None)
            with patch("bridge.server.load_config", return_value=config), \
                 patch("bridge.server._runtime", return_value=runtime):
                prepared = server.prepare_voice_isolation(1, 60)
                with patch("bridge.server.apply_voice_isolation", side_effect=KeyboardInterrupt):
                    with self.assertRaises(KeyboardInterrupt):
                        server.apply_voice_isolation_job(prepared["voice_job_id"])
                timeline.state[1] = {"isEnabled": True, "amount": 60}
                restored = server.restore_voice_isolation_job(prepared["voice_job_id"])
                self.assertEqual({"isEnabled": False, "amount": 0}, timeline.state[1])
                timeline.state[1] = {"isEnabled": True, "amount": 35}
                blocked = server.restore_voice_isolation_job(prepared["voice_job_id"])
            self.assertTrue(restored["ok"])
            self.assertTrue(blocked["ok"])
            self.assertTrue(blocked["idempotent"])

    def test_endpoint_restore_refuses_external_change_and_retains_job(self):
        with tempfile.TemporaryDirectory() as root:
            config = _config(Path(root), enabled=True)
            project, timeline = FakeProject(), FakeTimeline()
            runtime = (object(), object(), project, timeline, config, object(), None)
            with patch("bridge.server.load_config", return_value=config), \
                 patch("bridge.server._runtime", return_value=runtime):
                prepared = server.prepare_voice_isolation(1, 60)
                self.assertTrue(server.apply_voice_isolation_job(prepared["voice_job_id"])["ok"])
                timeline.state[1] = {"isEnabled": True, "amount": 35}
                restored = server.restore_voice_isolation_job(prepared["voice_job_id"])
            self.assertFalse(restored["ok"])
            self.assertIn("concorrente", restored["error"])
            self.assertEqual({"isEnabled": True, "amount": 35}, timeline.state[1])
            self.assertEqual("RESTORING", VoiceIsolationStore(
                config.state_path.parent / "voice_isolation_jobs.json", "PC_PERSONALE"
            ).get(prepared["voice_job_id"])["state"])

    def test_endpoint_restore_crash_leaves_applied_job_for_safe_retry(self):
        with tempfile.TemporaryDirectory() as root:
            config = _config(Path(root), enabled=True)
            project, timeline = FakeProject(), FakeTimeline()
            runtime = (object(), object(), project, timeline, config, object(), None)
            with patch("bridge.server.load_config", return_value=config), \
                 patch("bridge.server._runtime", return_value=runtime):
                prepared = server.prepare_voice_isolation(1, 60)
                self.assertTrue(server.apply_voice_isolation_job(prepared["voice_job_id"])["ok"])
                with patch("bridge.server.restore_voice_isolation", side_effect=KeyboardInterrupt):
                    with self.assertRaises(KeyboardInterrupt):
                        server.restore_voice_isolation_job(prepared["voice_job_id"])
                retried = server.restore_voice_isolation_job(prepared["voice_job_id"])
            self.assertTrue(retried["ok"])
            self.assertEqual("RESTORED", VoiceIsolationStore(
                config.state_path.parent / "voice_isolation_jobs.json", "PC_PERSONALE"
            ).get(prepared["voice_job_id"])["state"])

    def test_endpoint_restore_recovers_when_crash_happens_after_resolve_write(self):
        with tempfile.TemporaryDirectory() as root:
            config = _config(Path(root), enabled=True)
            project, timeline = FakeProject(), FakeTimeline()
            runtime = (object(), object(), project, timeline, config, object(), None)
            with patch("bridge.server.load_config", return_value=config), \
                 patch("bridge.server._runtime", return_value=runtime):
                prepared = server.prepare_voice_isolation(1, 60)
                self.assertTrue(server.apply_voice_isolation_job(prepared["voice_job_id"])["ok"])
                def crash_after_write(_project, live_timeline, capture, expected):
                    live_timeline.state[capture.target.track_index] = capture.initial.as_dict()
                    raise KeyboardInterrupt
                with patch("bridge.server.restore_voice_isolation", side_effect=crash_after_write):
                    with self.assertRaises(KeyboardInterrupt):
                        server.restore_voice_isolation_job(prepared["voice_job_id"])
                retried = server.restore_voice_isolation_job(prepared["voice_job_id"])
            self.assertTrue(retried["ok"])
            self.assertEqual("RESTORED", VoiceIsolationStore(
                config.state_path.parent / "voice_isolation_jobs.json", "PC_PERSONALE"
            ).get(prepared["voice_job_id"])["state"])


if __name__ == "__main__":
    unittest.main()
