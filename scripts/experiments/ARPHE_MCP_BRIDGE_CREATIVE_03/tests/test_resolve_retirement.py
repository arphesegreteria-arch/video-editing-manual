from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bridge.config import CreativeConfig, DEFAULT_FLAGS, DEFAULT_PALETTE
from bridge.registry import Registry
from bridge.resolve_retirement import (
    ResolveRetirementStore,
    approve_retirement,
    execute_retirement,
    inspect_retirements,
    prepare_retirement,
    recover_retirement,
)
from bridge.safety import ValidationError


UTC = timezone.utc
NOW = datetime(2026, 10, 8, 10, 0, tzinfo=UTC)


def config_for(root: Path) -> CreativeConfig:
    return CreativeConfig(
        path=root / "creative.json", asset_root=root / "assets", render_root=root / "renders",
        state_path=root / "state.json", audit_log_path=root / "audit.jsonl",
        palette=dict(DEFAULT_PALETTE), flags=dict(DEFAULT_FLAGS),
        allowed_projects=frozenset(), allowed_timelines=frozenset(),
        render_format="mp4", render_codec="H264", workstation_id="PC_PERSONALE",
        artifact_registry_path=root / "artifact-registry.json",
        runtime_log_root=root / "runtime-logs",
    )


class Timeline:
    def __init__(self, name: str):
        self.name = name

    def GetName(self):
        return self.name


class MediaPool:
    def __init__(self, project):
        self.project = project
        self.deleted = []

    def DeleteTimelines(self, timelines):
        self.deleted.extend(timelines)
        self.project.timelines = [item for item in self.project.timelines if item not in timelines]
        return True


class Project:
    def __init__(self, name="ARPHE_TEST_PROJECT"):
        self.name = name
        self.timelines = [Timeline("ARPHE_KEEP"), Timeline("ARPHE_RETIRE")]
        self.current = self.timelines[0]
        self.pool = MediaPool(self)

    def GetName(self):
        return self.name

    def GetCurrentTimeline(self):
        return self.current

    def GetTimelineCount(self):
        return len(self.timelines)

    def GetTimelineByIndex(self, index):
        return self.timelines[index - 1]

    def GetMediaPool(self):
        return self.pool


class Manager:
    def __init__(self, root: Path, project: Project):
        self.root = root
        self.project = project
        self.projects = [project.name]
        self.modified = 100
        self.exported = []
        self.closed = []
        self.deleted = []
        self.imported = []

    def SaveProject(self):
        return True

    def ExportProject(self, name, destination, with_stills):
        self.exported.append((name, destination, with_stills))
        Path(destination).write_bytes(b"DRP\0verified")
        return True

    def GetProjectLastModifiedTime(self, name):
        return self.modified

    def GetProjectListInCurrentFolder(self):
        return list(self.projects)

    def GetCurrentProject(self):
        return self.project

    def CloseProject(self, project):
        self.closed.append(project.GetName())
        self.project = None
        return True

    def DeleteProject(self, name):
        if self.project is not None and self.project.GetName() == name:
            return False
        self.deleted.append(name)
        self.projects.remove(name)
        return True

    def LoadProject(self, name):
        return None

    def ImportProject(self, archive, name):
        if name in self.projects:
            return False
        self.imported.append((archive, name))
        self.projects.append(name)
        return True


def setup(root: Path):
    config = config_for(root)
    config = replace(
        config,
        resolve_archive_root=root / "resolve-archives",
        resolve_retirement_registry_path=root / "resolve-retirements.json",
    )
    registry = Registry(config.state_path)
    registry.add_project("ARPHE_TEST_PROJECT")
    registry.add_timeline("ARPHE_TEST_PROJECT", "ARPHE_KEEP")
    registry.add_timeline("ARPHE_TEST_PROJECT", "ARPHE_RETIRE")
    project = Project()
    manager = Manager(root, project)
    store = ResolveRetirementStore(config.resolve_retirement_registry_path, "PC_PERSONALE")
    return config, registry, project, manager, store


class ResolveRetirementTests(unittest.TestCase):
    def test_prepare_timeline_exports_verified_drp_without_deleting(self):
        with tempfile.TemporaryDirectory() as directory:
            config, registry, project, manager, store = setup(Path(directory))
            result = prepare_retirement(manager, project, config, registry, store,
                                        "timeline", project.name, "ARPHE_RETIRE", NOW)
            self.assertEqual("PREPARED", result["status"])
            self.assertEqual([], project.pool.deleted)
            self.assertTrue(manager.exported[0][2])
            record = store.get(result["retirement_id"])
            self.assertGreater(record["archive_size_bytes"], 0)
            self.assertEqual(64, len(record["archive_sha256"]))

    def test_prepare_uses_project_attributes_when_direct_last_modified_is_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            config, registry, project, manager, store = setup(Path(directory))
            manager.GetProjectLastModifiedTime = lambda _name: None
            manager.GetProjectAttributesInCurrentFolder = lambda: {
                project.name: {"lastModifiedDate": "2026-10-08T10:00:00+02:00"}
            }
            result = prepare_retirement(manager, project, config, registry, store,
                                        "timeline", project.name, "ARPHE_RETIRE", NOW)
            self.assertEqual("PREPARED", result["status"])
            self.assertEqual("2026-10-08T10:00:00+02:00",
                             store.get(result["retirement_id"])["project_last_modified"])

    def test_prepare_rejects_current_timeline_and_active_render_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            config, registry, project, manager, store = setup(Path(directory))
            with self.assertRaises(ValidationError):
                prepare_retirement(manager, project, config, registry, store,
                                   "timeline", project.name, "ARPHE_KEEP", NOW)
            registry.acquire_render_lock(project.name, "batch-active")
            with self.assertRaises(ValidationError):
                prepare_retirement(manager, project, config, registry, store,
                                   "timeline", project.name, "ARPHE_RETIRE", NOW)

    def test_execute_requires_technical_approval_and_unchanged_project(self):
        with tempfile.TemporaryDirectory() as directory:
            config, registry, project, manager, store = setup(Path(directory))
            prepared = prepare_retirement(manager, project, config, registry, store,
                                          "timeline", project.name, "ARPHE_RETIRE", NOW)
            with self.assertRaises(ValidationError):
                execute_retirement(manager, project, config, registry, store,
                                   prepared["retirement_id"], NOW)
            with self.assertRaises(ValidationError):
                approve_retirement(store, prepared["retirement_id"], "editor", NOW)
            approve_retirement(store, prepared["retirement_id"], "technical", NOW)
            manager.modified += 1
            with self.assertRaises(ValidationError):
                execute_retirement(manager, project, config, registry, store,
                                   prepared["retirement_id"], NOW)
            self.assertEqual([], project.pool.deleted)

    def test_archive_tamper_blocks_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            config, registry, project, manager, store = setup(Path(directory))
            prepared = prepare_retirement(manager, project, config, registry, store,
                                          "timeline", project.name, "ARPHE_RETIRE", NOW)
            approve_retirement(store, prepared["retirement_id"], "alessio", NOW)
            Path(store.get(prepared["retirement_id"])["archive_path"]).write_bytes(b"tampered")
            with self.assertRaises(ValidationError):
                execute_retirement(manager, project, config, registry, store,
                                   prepared["retirement_id"], NOW)
            self.assertEqual([], project.pool.deleted)

    def test_timeline_execution_is_exact_verified_and_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            config, registry, project, manager, store = setup(Path(directory))
            prepared = prepare_retirement(manager, project, config, registry, store,
                                          "timeline", project.name, "ARPHE_RETIRE", NOW)
            approve_retirement(store, prepared["retirement_id"], "technical", NOW)
            first = execute_retirement(manager, project, config, registry, store,
                                       prepared["retirement_id"], NOW)
            second = execute_retirement(manager, project, config, registry, store,
                                        prepared["retirement_id"], NOW)
            self.assertEqual("EXECUTED", first["status"])
            self.assertTrue(second["idempotent"])
            self.assertEqual(["ARPHE_RETIRE"], [item.GetName() for item in project.pool.deleted])
            self.assertFalse(registry.timeline_allowed(project.name, "ARPHE_RETIRE"))

    def test_executing_timeline_reconciles_after_delete_before_save_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            config, registry, project, manager, store = setup(Path(directory))
            prepared = prepare_retirement(manager, project, config, registry, store,
                                          "timeline", project.name, "ARPHE_RETIRE", NOW)
            approve_retirement(store, prepared["retirement_id"], "technical", NOW)
            manager.SaveProject = lambda: False
            with self.assertRaises(RuntimeError):
                execute_retirement(manager, project, config, registry, store,
                                   prepared["retirement_id"], NOW)
            self.assertEqual("EXECUTING", store.get(prepared["retirement_id"])["status"])
            reconciled = execute_retirement(manager, project, config, registry, store,
                                            prepared["retirement_id"], NOW)
            self.assertEqual("EXECUTED", reconciled["status"])
            self.assertFalse(registry.timeline_allowed(project.name, "ARPHE_RETIRE"))

    def test_executing_retry_still_blocks_if_target_exists_and_project_changed(self):
        with tempfile.TemporaryDirectory() as directory:
            config, registry, project, manager, store = setup(Path(directory))
            prepared = prepare_retirement(manager, project, config, registry, store,
                                          "timeline", project.name, "ARPHE_RETIRE", NOW)
            approve_retirement(store, prepared["retirement_id"], "technical", NOW)
            project.pool.DeleteTimelines = lambda _items: False
            with self.assertRaises(RuntimeError):
                execute_retirement(manager, project, config, registry, store,
                                   prepared["retirement_id"], NOW)
            manager.modified += 1
            with self.assertRaises(ValidationError):
                execute_retirement(manager, project, config, registry, store,
                                   prepared["retirement_id"], NOW)

    def test_project_execution_closes_then_deletes_and_recovery_never_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            config, registry, project, manager, store = setup(Path(directory))
            prepared = prepare_retirement(manager, project, config, registry, store,
                                          "project", project.name, None, NOW)
            approve_retirement(store, prepared["retirement_id"], "technical", NOW)
            execute_retirement(manager, project, config, registry, store,
                               prepared["retirement_id"], NOW)
            self.assertEqual([project.name], manager.closed)
            self.assertEqual([project.name], manager.deleted)
            recovered = recover_retirement(manager, config, store,
                                           prepared["retirement_id"], NOW)
            self.assertTrue(recovered["recovery_project"].startswith("ARPHE_RECOVERY_"))
            self.assertNotEqual(project.name, recovered["recovery_project"])
            self.assertEqual("RECOVERED", store.get(prepared["retirement_id"])["status"])

    def test_inspection_keeps_last_three_and_all_archives_younger_than_30_days(self):
        with tempfile.TemporaryDirectory() as directory:
            config, registry, project, manager, store = setup(Path(directory))
            ids = []
            for days in (100, 90, 80, 70, 1):
                result = prepare_retirement(manager, project, config, registry, store,
                                            "timeline", project.name, "ARPHE_RETIRE",
                                            NOW - timedelta(days=days))
                ids.append(result["retirement_id"])
            report = inspect_retirements(config, store, NOW)
            states = {item["retirement_id"]: item["archive_retention"] for item in report["items"]}
            self.assertEqual("CANDIDATE", states[ids[0]])
            self.assertEqual("CANDIDATE", states[ids[1]])
            self.assertEqual("RETAIN", states[ids[2]])
            self.assertEqual("RETAIN", states[ids[3]])
            self.assertEqual("RETAIN", states[ids[4]])
            self.assertNotIn(str(Path(directory)), str(report))


if __name__ == "__main__":
    unittest.main()
