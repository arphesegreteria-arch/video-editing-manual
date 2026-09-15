from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.config import CreativeConfig, DEFAULT_FLAGS, DEFAULT_PALETTE  # noqa: E402
from bridge.registry import Registry  # noqa: E402
from bridge.render_tools import queue_longform_exports, start_longform_exports  # noqa: E402


class Api:
    pass


def setup(root: Path):
    flags = dict(DEFAULT_FLAGS)
    flags.update(CAP_LONGFORM=True, CAP_RENDER=True)
    cfg = CreativeConfig(
        path=root / "config.json", asset_root=root / "assets", render_root=root / "renders",
        state_path=root / "state.json", audit_log_path=root / "audit.jsonl",
        palette=dict(DEFAULT_PALETTE), flags=flags, allowed_projects=frozenset(),
        allowed_timelines=frozenset(), render_format="mp4", render_codec="H264",
        media_roots=(root,), transcript_root=root, audio_root=root, audio_jobs_root=root,
    )
    registry = Registry(cfg.state_path)
    registry.add_project("ARPHE_LONGFORM_TEST")
    registry.add_timeline("ARPHE_LONGFORM_TEST", "ARPHE_CLIP_01")
    registry.add_timeline("ARPHE_LONGFORM_TEST", "ARPHE_CLIP_02")
    registry.set_longform_batch("ARPHE_LONGFORM_TEST", "ARPHE_MASTER",
                                ["ARPHE_CLIP_01", "ARPHE_CLIP_02"])
    timelines = []
    for name in ("ARPHE_CLIP_01", "ARPHE_CLIP_02"):
        timeline = Api()
        timeline.GetName = lambda value=name: value
        timelines.append(timeline)
    pool = Api()
    pool.CreateEmptyTimeline = lambda *_: True
    pool.ImportMedia = lambda *_: True
    pool.AppendToTimeline = lambda *_: True
    project = Api()
    project.GetName = lambda: "ARPHE_LONGFORM_TEST"
    project.GetMediaPool = lambda: pool
    project.GetCurrentTimeline = lambda: timelines[0]
    project.GetTimelineCount = lambda: 2
    project.GetTimelineByIndex = lambda index: timelines[index - 1]
    project.GetSetting = lambda *_: "30"
    project.SetSetting = lambda *_: True
    project.SetCurrentTimeline = lambda *_: True
    project.SetCurrentRenderFormatAndCodec = lambda *_: True
    project.SetRenderSettings = lambda *_: True
    queued = []
    project.AddRenderJob = lambda: queued.append(f"job-{len(queued)+1}") or queued[-1]
    project.StartRendering = lambda ids: ids == ["job-1", "job-2"]
    manager = Api()
    for name in ("CreateProject", "LoadProject", "SaveProject", "GetCurrentProject",
                 "GetProjectListInCurrentFolder"):
        setattr(manager, name, lambda *_: True)
    return cfg, registry, manager, project


class LongformExportTests(unittest.TestCase):
    def test_queue_creates_one_job_per_clip_and_does_not_start(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg, registry, manager, project = setup(Path(directory))
            starts = []
            project.StartRendering = lambda ids: starts.append(ids) or True
            result = queue_longform_exports(manager, project, cfg, registry)
            self.assertTrue(result["ok"])
            self.assertEqual(2, result["job_count"])
            self.assertFalse(result["render_started"])
            self.assertEqual([], starts)

    def test_start_runs_only_prepared_batch_jobs(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg, registry, manager, project = setup(Path(directory))
            queue_longform_exports(manager, project, cfg, registry)
            result = start_longform_exports(project, cfg, registry)
            self.assertTrue(result["ok"])
            self.assertEqual(2, result["job_count"])


if __name__ == "__main__":
    unittest.main()
