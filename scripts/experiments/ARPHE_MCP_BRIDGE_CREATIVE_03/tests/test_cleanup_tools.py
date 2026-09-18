from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.cleanup_tools import apply_publish_cleanup, preview_publish_cleanup  # noqa: E402
from bridge.config import CreativeConfig, DEFAULT_FLAGS, DEFAULT_PALETTE  # noqa: E402
from bridge.registry import Registry  # noqa: E402
from bridge.safety import ValidationError  # noqa: E402


class Api:
    pass


def setup(root: Path):
    flags = dict(DEFAULT_FLAGS)
    flags["CAP_CLEANUP"] = True
    cfg = CreativeConfig(
        path=root / "config.json", asset_root=root, render_root=root,
        state_path=root / "state.json", audit_log_path=root / "audit.jsonl",
        palette=dict(DEFAULT_PALETTE), flags=flags, allowed_projects=frozenset(),
        allowed_timelines=frozenset(), render_format="mp4", render_codec="H264",
        media_roots=(root,), transcript_root=root, audio_root=root, audio_jobs_root=root,
    )
    registry = Registry(cfg.state_path)
    registry.add_project("ARPHE_CLEANUP_TEST")
    names = ("ARPHE_KEEP", "ARPHE_EXPERIMENT")
    timelines = []
    for name in names:
        timeline = Api()
        timeline.GetName = lambda value=name: value
        timelines.append(timeline)
        registry.add_timeline("ARPHE_CLEANUP_TEST", name)
    deleted = []
    pool = Api()
    pool.CreateEmptyTimeline = lambda *_: True
    pool.DeleteTimelines = lambda values: deleted.extend(values) or True
    project = Api()
    project.GetName = lambda: "ARPHE_CLEANUP_TEST"
    project.GetMediaPool = lambda: pool
    project.GetCurrentTimeline = lambda: timelines[0]
    project.GetTimelineCount = lambda: len(timelines)
    project.GetTimelineByIndex = lambda index: timelines[index - 1]
    project.GetSetting = lambda *_: "30"
    project.SetSetting = lambda *_: True
    project.SetCurrentTimeline = lambda *_: True
    manager = Api()
    for name in ("CreateProject", "LoadProject", "GetCurrentProject", "GetProjectListInCurrentFolder"):
        setattr(manager, name, lambda *_: True)
    manager.SaveProject = lambda: True
    manager.DeleteProject = lambda *_: True
    manager.GetProjectListInCurrentFolder = lambda: ["ARPHE_CLEANUP_TEST", "ARPHE_OLD_TEST"]
    return cfg, registry, manager, project, deleted


class CleanupTests(unittest.TestCase):
    def test_preview_is_read_only_and_token_is_bound_to_exact_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cfg, registry, manager, project, _ = setup(root)
            source = root / "original.mp4"
            source.write_bytes(b"1234")
            result = preview_publish_cleanup(manager, project, cfg, registry, ["ARPHE_KEEP"],
                                             ["ARPHE_EXPERIMENT"], [], [str(source)])
            self.assertFalse(result["writes_performed"])
            self.assertEqual(4, result["reclaimable_bytes"])
            self.assertEqual(16, len(result["confirmation_token"]))
            self.assertTrue(source.exists())

    def test_current_timeline_cannot_be_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cfg, registry, manager, project, _ = setup(root)
            with self.assertRaises(ValidationError):
                preview_publish_cleanup(manager, project, cfg, registry, ["ARPHE_EXPERIMENT"],
                                        ["ARPHE_KEEP"], [], [])

    def test_apply_requires_preview_token_then_saves(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cfg, registry, manager, project, deleted = setup(root)
            source = root / "original.mp4"
            source.write_bytes(b"1234")
            args = (["ARPHE_KEEP"], ["ARPHE_EXPERIMENT"], [], [str(source)])
            preview = preview_publish_cleanup(manager, project, cfg, registry, *args)
            with patch("bridge.cleanup_tools._send_to_recycle_bin") as recycle:
                result = apply_publish_cleanup(manager, project, cfg, registry, *args,
                                               preview["confirmation_token"])
            self.assertTrue(result["ok"])
            self.assertEqual(1, len(deleted))
            recycle.assert_called_once_with(source.resolve())


if __name__ == "__main__":
    unittest.main()
