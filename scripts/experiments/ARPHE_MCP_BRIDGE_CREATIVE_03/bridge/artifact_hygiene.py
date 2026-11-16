from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import base64
import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
from typing import Any

from .artifact_records import (ArtifactPolicy, ArtifactRecord, ArtifactStore,
                               KNOWN_CATEGORIES, RegistrationLockedError, _reject_links,
                               artifact_signature, sha256_file)
from .config import CreativeConfig


UTC = timezone.utc
ACTIVE_BATCH_STATES = frozenset({"DRAFT", "CONFIRMED", "PREPARED", "APPROVED", "RENDERING", "VERIFYING"})
FAILED_BATCH_STATES = frozenset({"FAILED_RENDER", "FAILED_VERIFY"})


def _producer_activity_hold(config: CreativeConfig) -> bool:
    active = {"QUEUED", "RUNNING", "RENDERING", "PROCESSING", "APPLYING",
              "PREPARED", "APPROVED"}
    if config.audio_jobs_root.is_dir():
        for path in config.audio_jobs_root.rglob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                return True
            if isinstance(payload, dict) and str(payload.get("status") or "").upper() in active:
                return True
    if config.colorist_jobs_path.exists():
        try:
            payload = json.loads(config.colorist_jobs_path.read_text(encoding="utf-8-sig"))
            jobs = payload.get("jobs", {}) if isinstance(payload, dict) else {}
            return any(str(value.get("state") or "").upper() in active
                       for value in jobs.values() if isinstance(value, dict))
        except (OSError, json.JSONDecodeError):
            return True
    return False


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Timestamp inventario privo di timezone")
    return value.astimezone(UTC)


def _is_reparse(path: Path) -> bool:
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def validate_managed_path(path: Path, root: Path, *, allow_directory: bool = False) -> Path:
    _reject_links(root)
    _reject_links(path)
    root_resolved = root.resolve(strict=False)
    selected = path if path.is_absolute() else root_resolved / path
    selected_resolved = selected.resolve(strict=False)
    try:
        common = Path(os.path.commonpath((str(root_resolved), str(selected_resolved))))
    except ValueError as exc:
        raise ValueError("Percorso fuori dal managed root") from exc
    if common != root_resolved:
        raise ValueError("Percorso fuori dal managed root")
    current = selected.absolute()
    while True:
        if current.is_symlink() or _is_reparse(current):
            raise ValueError("Percorso symlink o reparse non consentito")
        if current.resolve(strict=False) == root_resolved:
            break
        parent = current.parent
        if parent == current:
            raise ValueError("Percorso fuori dal managed root")
        current = parent
    resolved = selected_resolved
    if resolved.exists():
        if allow_directory and not resolved.is_dir():
            raise ValueError("Artefatto directory atteso")
        if not allow_directory and not resolved.is_file():
            raise ValueError("Artefatto file atteso")
    return resolved


def _roots(config: CreativeConfig) -> dict[str, Path]:
    return {
        "render_root": config.render_root.resolve(),
        "profile_root": config.artifact_registry_path.parent.resolve(),
        "runtime_log_root": config.runtime_log_root.resolve(),
        "audio_root": config.audio_root.resolve(),
        "audio_jobs_root": config.audio_jobs_root.resolve(),
    }


def _display(path: Path, root_id: str, root: Path) -> str:
    return f"{root_id}:{path.relative_to(root).as_posix()}"


def _record_item(record: ArtifactRecord, config: CreativeConfig, project_registry: Any,
                 policy: ArtifactPolicy, now: datetime) -> dict[str, Any]:
    roots = _roots(config)
    root = roots.get(record.managed_root_id)
    item = {
        "artifact_id": record.artifact_id,
        "category": record.category,
        "state": record.state,
        "display_path": f"{record.managed_root_id}:invalid",
        "bytes": record.size_bytes or 0,
        "eligible_at": None if record.eligible_at is None else record.eligible_at.isoformat(),
        "purge_after": None if record.purge_after is None else record.purge_after.isoformat(),
    }
    if root is None:
        item["state"] = "ERROR"
        item["error_code"] = "UNKNOWN_MANAGED_ROOT"
        return item
    try:
        if record.quarantine_path:
            path = _payload(config, record)
            item["display_path"] = _display(path, "artifact_quarantine_root", _quarantine_root(config, record))
        else:
            path = validate_managed_path(Path(record.path), root,
                                         allow_directory=record.kind == "directory")
            item["display_path"] = _display(path, record.managed_root_id, root)
    except ValueError:
        item["state"] = "ERROR"
        item["error_code"] = "PATH_OUTSIDE_MANAGED_ROOT"
        return item
    if record.state in {"QUARANTINE_COPYING", "QUARANTINED", "PURGE_PENDING", "PURGED", "ERROR", "REVIEW_REQUIRED"}:
        return item
    if record.protection_class == "PROTECTED":
        item["state"] = "PROTECTED"
        return item
    rule = policy.rules[record.category]
    if record.batch_id:
        batch = project_registry.render_batch(record.batch_id)
        if batch is None:
            item["state"] = "ERROR"
            item["error_code"] = "BATCH_NOT_FOUND"
            return item
        if batch.status in ACTIVE_BATCH_STATES:
            item["state"] = "PROTECTED"
            return item
        if batch.status not in set(rule.terminal_batch_states):
            if not (record.category == "FAILED_RENDER_STAGING" and batch.status in FAILED_BATCH_STATES):
                item["state"] = "AWAITING_TERMINAL_SNAPSHOT" if batch.status in FAILED_BATCH_STATES else "ERROR"
                return item
        if record.terminal_observed_at is None or record.eligible_at is None:
            item["state"] = "AWAITING_TERMINAL_SNAPSHOT"
            return item
        item["state"] = "ELIGIBLE" if now >= record.eligible_at else "ACTIVE"
        return item
    eligible_at = record.eligible_at or record.created_at + timedelta(seconds=rule.active_seconds)
    item["eligible_at"] = eligible_at.isoformat()
    item["state"] = "ELIGIBLE" if now >= eligible_at else record.state
    return item


def _unclassified(config: CreativeConfig, known_paths: set[Path]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    locations = (
        ("render_root", config.render_root / "diagnostics"),
        ("render_root", config.render_root / "technical-preview"),
        ("render_root", config.render_root / "staging"),
    )
    render_root = config.render_root.resolve()
    for root_id, directory in locations:
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir(), key=lambda item: item.name.casefold()):
            try:
                resolved = validate_managed_path(path, render_root, allow_directory=path.is_dir())
            except ValueError:
                continue
            if resolved in known_paths or any(known in resolved.parents for known in known_paths):
                continue
            try:
                size = resolved.stat().st_size if resolved.is_file() else 0
            except OSError:
                size = 0
            result.append({
                "artifact_id": None,
                "category": "UNCLASSIFIED",
                "state": "UNCLASSIFIED",
                "display_path": _display(resolved, root_id, render_root),
                "bytes": size,
                "eligible_at": None,
                "purge_after": None,
            })
    return result


def _rotated_log_metadata(config: CreativeConfig, producer: Path) -> tuple[datetime, int, str]:
    root = config.runtime_log_root.resolve()
    selected = validate_managed_path(producer, root, allow_directory=True)
    if selected.parent != (root / "rotated").resolve() or not selected.name.startswith("runtime."):
        raise ValueError("Cartella produttore log fuori dalla radice esatta")
    if {item.name for item in selected.iterdir()} != {"runtime.log", "artifact.json"}:
        raise ValueError("Unità log incompleta o con contenuti inattesi")
    log = validate_managed_path(selected / "runtime.log", root)
    metadata_path = validate_managed_path(selected / "artifact.json", root)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8-sig"))
    expected_keys = {
        "schema_version", "workstation_id", "category", "log_file",
        "created_at", "size_bytes", "sha256",
    }
    if not isinstance(metadata, dict) or set(metadata) != expected_keys:
        raise ValueError("Metadata log non valida")
    if (metadata.get("schema_version") != 1 or
            metadata.get("workstation_id") != config.workstation_id or
            metadata.get("category") != "ROTATED_LOG" or
            metadata.get("log_file") != "runtime.log"):
        raise ValueError("Identità metadata log non valida")
    created = datetime.fromisoformat(str(metadata["created_at"]))
    created = _utc(created)
    size = log.stat().st_size
    digest = sha256_file(log)
    if metadata.get("size_bytes") != size or metadata.get("sha256") != digest:
        raise ValueError("Integrità log non valida")
    return created, size, digest


def _rotated_log_findings(config: CreativeConfig, known_paths: set[Path]) -> list[dict[str, Any]]:
    rotated = config.runtime_log_root / "rotated"
    if not rotated.is_dir():
        return []
    findings: list[dict[str, Any]] = []
    for producer in sorted(rotated.iterdir(), key=lambda item: item.name.casefold()):
        resolved = producer.resolve(strict=False)
        if resolved in known_paths:
            continue
        item = {
            "artifact_id": None,
            "category": "ROTATED_LOG",
            "state": "PENDING_IMPORT",
            "display_path": f"runtime_log_root:rotated/{producer.name}",
            "bytes": 0,
            "eligible_at": None,
            "purge_after": None,
        }
        try:
            _, size, _ = _rotated_log_metadata(config, producer)
            item["bytes"] = size
        except (OSError, ValueError, json.JSONDecodeError):
            item["state"] = "ERROR"
            item["error_code"] = "INVALID_ROTATED_LOG_METADATA"
        findings.append(item)
    return findings


def _import_rotated_logs(config: CreativeConfig, store: ArtifactStore,
                         policy: ArtifactPolicy) -> None:
    rotated = config.runtime_log_root / "rotated"
    if not rotated.is_dir():
        return
    known = {Path(record.path).resolve(strict=False) for record in store.records() if record.state != "PURGED"}
    for producer in sorted(rotated.iterdir(), key=lambda item: item.name.casefold()):
        if producer.resolve(strict=False) in known:
            continue
        try:
            created, _, _ = _rotated_log_metadata(config, producer)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        record = store.register_path(
            producer,
            kind="directory",
            category="ROTATED_LOG",
            producer="windows_runtime_log_rotation",
            managed_root_id="runtime_log_root",
            created_at=created,
            policy_version=policy.policy_version,
        )
        with store.registration_guard():
            record = _record_by_id(store, record.artifact_id)
            _owned_record(config, store, record)
            if _disposable(record) and record.state in {"ACTIVE", "ELIGIBLE", "RESTORED"}:
                size, digest, _ = _directory_signature(producer)
                store.replace(replace(record, size_bytes=size, sha256=digest))
        known.add(producer.resolve())


def _inventory_fingerprint(items: list[dict[str, Any]]) -> str:
    encoded = json.dumps(items, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _inspection_cursor(fingerprint: str, offset: int) -> str:
    payload = json.dumps({"fingerprint": fingerprint, "offset": offset},
                         sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _inspection_offset(cursor: str, fingerprint: str) -> int:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        if payload.get("fingerprint") != fingerprint or type(payload.get("offset")) is not int:
            raise ValueError
        offset = payload["offset"]
        if offset < 0:
            raise ValueError
        return offset
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("Inspection cursor stale or invalid") from exc


def inspect_artifacts(config: CreativeConfig, artifact_store: ArtifactStore, project_registry: Any,
                      policy: ArtifactPolicy, now_utc: datetime, *, cursor: str | None = None,
                      limit: int = 0) -> dict[str, Any]:
    now = _utc(now_utc)
    records = artifact_store.records()
    items = [_record_item(record, config, project_registry, policy, now) for record in records]
    known_paths = {Path(record.path).resolve(strict=False) for record in records if record.state != "PURGED"}
    items.extend(_unclassified(config, known_paths))
    items.extend(_rotated_log_findings(config, known_paths))
    items.sort(key=lambda item: (str(item.get("display_path", "")).casefold(),
                                 str(item.get("artifact_id") or "")))
    summary: dict[str, dict[str, int]] = {}
    for item in items:
        bucket = summary.setdefault(item["state"], {"count": 0, "bytes": 0})
        bucket["count"] += 1
        bucket["bytes"] += int(item.get("bytes") or 0)
    fingerprint = _inventory_fingerprint(items)
    result = {
        "ok": True,
        "action": "inspect_artifact_hygiene",
        "workstation_id": config.workstation_id,
        "policy_version": policy.policy_version,
        "summary": summary,
        "item_count": len(items),
        "inventory_fingerprint": fingerprint,
    }
    if cursor is None and limit <= 0:
        return result
    page_limit = min(50, max(1, int(limit or 50)))
    offset = _inspection_offset(cursor, fingerprint) if cursor is not None else 0
    if offset > len(items):
        raise ValueError("Inspection cursor stale or invalid")
    page = items[offset:offset + page_limit]
    next_offset = offset + len(page)
    return {**result, "items": page,
            "next_cursor": (_inspection_cursor(fingerprint, next_offset)
                            if next_offset < len(items) else None)}


def _directory_signature(path: Path) -> tuple[int, str, tuple[str, ...]]:
    return artifact_signature(path, "directory")


def _signature(path: Path, kind: str) -> tuple[int, str, tuple[str, ...]]:
    return artifact_signature(path, kind)


def _lock_path(store: ArtifactStore) -> Path:
    return store.path.with_suffix(store.path.suffix + ".maintenance.lock")


def _acquire_lock(store: ArtifactStore) -> int | None:
    path = _lock_path(store)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        return os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return None


def _release_lock(store: ArtifactStore, descriptor: int) -> None:
    os.close(descriptor)
    _lock_path(store).unlink(missing_ok=True)


def _record_by_id(store: ArtifactStore, artifact_id: str) -> ArtifactRecord:
    for record in store.records():
        if record.artifact_id == artifact_id:
            return record
    raise KeyError(artifact_id)


def _mark_error(store: ArtifactStore, record: ArtifactRecord, code: str) -> None:
    store.replace(replace(record, state="ERROR", last_error=code))


def _review(store, record, code):
    updated = replace(record, state="REVIEW_REQUIRED", last_error=code)
    store.replace(updated)
    return updated


def _owned_record(config, store, record):
    if store.workstation_id != config.workstation_id or record.workstation_id != config.workstation_id:
        raise ValueError("Artifact workstation mismatch")
    if store.path != config.artifact_registry_path.resolve():
        raise ValueError("Artifact registry mismatch")
    _reject_links(store.path)
    if _record_by_id(store, record.artifact_id) != record:
        raise ValueError("Artifact record changed")
    if not record.artifact_id or Path(record.artifact_id).name != record.artifact_id or record.artifact_id in {".", ".."}:
        raise ValueError("Invalid artifact identity")


def _disposable(record):
    return (record.protection_class == "DISPOSABLE" and record.category in KNOWN_CATEGORIES
            and not record.hold_reasons and not record.dependencies)


def _original(config, record):
    root = _roots(config).get(record.managed_root_id)
    if root is None:
        raise ValueError("Unknown managed root")
    path = validate_managed_path(Path(record.path), root, allow_directory=record.kind == "directory")
    if path == root or ".arphe-quarantine" in path.relative_to(root).parts:
        raise ValueError("Invalid artifact source")
    if record.original_path and Path(record.original_path) != path:
        raise ValueError("Original artifact path changed")
    return path


def _quarantine_root(config, record):
    root = config.artifact_quarantine_root
    # Compatibility with manually constructed profiles predating absolute retention paths.
    if not root.is_absolute():
        root = _roots(config)[record.managed_root_id] / ".arphe-quarantine"
    _reject_links(root)
    return root


def _payload(config, record, *, legacy=False):
    root = _quarantine_root(config, record)
    if legacy:
        root = _roots(config)[record.managed_root_id] / ".arphe-quarantine"
    expected = root / record.artifact_id / "payload"
    selected = Path(record.quarantine_path) if record.quarantine_path else expected
    if selected != expected:
        raise ValueError("Quarantine payload path mismatch")
    return validate_managed_path(selected, root, allow_directory=record.kind == "directory")


def _check_overlap(store, record, path):
    for other in store.records():
        if other.artifact_id == record.artifact_id or other.state == "PURGED":
            continue
        if other.workstation_id != store.workstation_id:
            raise ValueError("Inventory ownership ambiguous")
        for candidate in (other.path, other.quarantine_path):
            if candidate:
                other_path = Path(candidate).resolve()
                if path == other_path or path in other_path.parents or other_path in path.parents:
                    raise ValueError("Overlapping registered artifact")


def _verified(path, record):
    if not path.exists():
        raise ValueError("PAYLOAD_MISSING")
    size, digest, _ = _signature(path, record.kind)
    if record.size_bytes != size or record.sha256 != digest:
        raise ValueError("CONTENT_CHANGED")


def _remove_verified(path, record):
    # The caller checks exact target, ownership, state/time and authorization first.
    _reject_links(path)
    _verified(path, record)
    if record.kind == "directory":
        shutil.rmtree(path)
    else:
        path.unlink()


def _flush_payload(path, kind):
    files = [path] if kind == "file" else [item for item in path.rglob("*") if item.is_file()]
    for file in files:
        with file.open("r+b") as handle:
            handle.flush()
            os.fsync(handle.fileno())
    if os.name != "nt":
        directories = [path.parent]
        if kind == "directory":
            directories += [item for item in path.rglob("*") if item.is_dir()] + [path]
        for directory in directories:
            descriptor = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)


def _copy_durable(source, destination, kind):
    if kind == "directory":
        shutil.copytree(source, destination, copy_function=shutil.copyfile)
    else:
        shutil.copyfile(source, destination)
    _flush_payload(destination, kind)


def _complete_quarantine(store, record, operation):
    at = _utc(datetime.fromisoformat(operation["at"]))
    updated = replace(record, state="QUARANTINED", original_path=operation["source"],
                      quarantine_path=operation["destination"], quarantined_at=at,
                      purge_after=at + timedelta(seconds=1296000), last_error=None)
    store.replace(updated)
    store.clear_pending_operation()
    return updated


def _reconcile_pending(config, store, policy, now):
    operation = store.pending_operation()
    if operation is None:
        return
    record = _record_by_id(store, str(operation.get("artifact_id", "")))
    try:
        _owned_record(config, store, record)
        if not _disposable(record) or record.state == "REVIEW_REQUIRED":
            raise ValueError("PENDING_OPERATION_REQUIRES_REVIEW")
        original = _original(config, record)
        action = operation.get("type")
        if action in {"MOVE_TO_QUARANTINE", "RESTORE"}:
            # Legacy journals name source=original and destination=quarantine for both actions.
            payload = _payload(config, record, legacy=operation.get("version") is None)
            if Path(operation["source"]) != original or Path(operation["destination"]) != payload:
                raise ValueError("PENDING_PATH_MISMATCH")
            _check_overlap(store, record, original)
            _check_overlap(store, record, payload)
            if action == "RESTORE":
                if original.exists() and payload.exists() and operation.get("phase") in {"COPYING", "VERIFIED"}:
                    _verified(original, record)
                    _verified(payload, record)
                    _flush_payload(original, record.kind)
                    store.update_pending_operation({**operation, "phase": "VERIFIED"})
                    _verified(original, record)
                    _remove_verified(payload, record)
                if original.exists() and not payload.exists():
                    _verified(original, record)
                    if record.state != "RESTORED":
                        # Recovery completes the restore now; an old intent must
                        # not consume the restored artifact's new active period.
                        eligible_at = now + timedelta(seconds=policy.rules[record.category].active_seconds)
                        restored = replace(record, state="RESTORED", path=str(original),
                            original_path=str(original), quarantine_path=None, quarantined_at=None,
                            purge_after=None, eligible_at=eligible_at, last_error=None)
                        if operation.get("keep_after_restore") is True:
                            # A crash after moving bytes must finish the keep transaction, not
                            # downgrade it into an ordinary eligible restore. This save also
                            # clears the journal, so a write failure leaves it for retry.
                            requested_at = operation.get("keep_requested_at")
                            event_at = (_utc(datetime.fromisoformat(requested_at))
                                        if isinstance(requested_at, str) else now)
                            try:
                                store.complete_restore_with_keep(record, restored, event_at)
                            except (OSError, ValueError, RegistrationLockedError):
                                # Do not replace the quarantined record or consume the journal;
                                # the next guarded reconciliation retries the same held commit.
                                return
                            return
                        store.replace(restored)
                elif payload.exists() and not original.exists():
                    _verified(payload, record)
                else:
                    raise ValueError("RESTORE_AMBIGUOUS")
                store.clear_pending_operation()
                return
            if original.exists() and not payload.exists():
                _verified(original, record)
                if record.state == "QUARANTINE_COPYING":
                    store.replace(replace(record, state="ACTIVE", last_error=None))
                store.clear_pending_operation()
                return
            if payload.exists():
                _verified(payload, record)
                if record.state != "QUARANTINED":
                    # A recovered transfer starts its complete retention period now.
                    operation = {**operation, "at": max(now, _utc(datetime.fromisoformat(operation["at"]))).isoformat()}
                if original.exists():
                    if operation.get("phase") not in {"COPYING", "VERIFIED"}:
                        raise ValueError("QUARANTINE_AMBIGUOUS")
                    _verified(original, record)
                    _flush_payload(payload, record.kind)
                    operation = {**operation, "phase": "VERIFIED"}
                    store.update_pending_operation(operation)
                    _verified(payload, record)
                    _remove_verified(original, record)
                _complete_quarantine(store, record, operation)
                return
            raise ValueError("PAYLOAD_MISSING")
        if action == "PURGE":
            payload = _payload(config, record)
            if Path(operation["source"]) != payload:
                raise ValueError("PENDING_PATH_MISMATCH")
            if record.state == "PURGED" and operation.get("phase") == "DELETED" and not payload.exists():
                store.clear_pending_operation()
                return
            if not payload.exists():
                if operation.get("phase") != "DELETED" or record.state != "PURGE_PENDING":
                    raise ValueError("PURGE_OUTCOME_UNKNOWN")
                store.replace(replace(record, state="PURGED", last_error=None))
            else:
                _verified(payload, record)
                store.replace(replace(record, state="QUARANTINED", last_error=None))
            store.clear_pending_operation()
            return
        raise ValueError("UNKNOWN_PENDING_OPERATION")
    except (OSError, ValueError, KeyError) as exc:
        _review(store, record, str(exc))
        store.clear_pending_operation()


def _freeze_terminal(record: ArtifactRecord, store: ArtifactStore, project_registry: Any,
                     policy: ArtifactPolicy, now: datetime) -> ArtifactRecord:
    batch = project_registry.render_batch(record.batch_id)
    if batch is None:
        _mark_error(store, record, "BATCH_NOT_FOUND")
        return _record_by_id(store, record.artifact_id)
    if batch.status in ACTIVE_BATCH_STATES:
        return record
    category = "FAILED_RENDER_STAGING" if batch.status in FAILED_BATCH_STATES else "RENDER_STAGING"
    rule = policy.rules[category]
    if batch.status not in set(rule.terminal_batch_states):
        _mark_error(store, record, "UNEXPECTED_BATCH_STATE")
        return _record_by_id(store, record.artifact_id)
    path = Path(record.path)
    try:
        size, digest, names = _signature(path, record.kind)
    except (OSError, ValueError):
        _mark_error(store, record, "STAGING_NOT_READABLE")
        return _record_by_id(store, record.artifact_id)
    expected = set(getattr(batch, "expected_outputs", ()) or ())
    unexpected = set(names) - expected
    if unexpected:
        _mark_error(store, record, "UNEXPECTED_STAGING_CONTENT")
        return _record_by_id(store, record.artifact_id)
    frozen = replace(
        record,
        category=category,
        terminal_observed_at=now,
        eligible_at=now + timedelta(seconds=rule.active_seconds),
        size_bytes=size,
        sha256=digest,
        policy_version=policy.policy_version,
    )
    store.replace(frozen)
    return frozen


def quarantine_artifact(config: CreativeConfig, store: ArtifactStore, record: ArtifactRecord,
                        policy: ArtifactPolicy, now_utc: datetime) -> ArtifactRecord:
    now = _utc(now_utc)
    if type(policy.quarantine_seconds) is not int or policy.quarantine_seconds != 1296000:
        raise ValueError("Quarantine must last 1296000 seconds")
    with store.registration_guard():
        _owned_record(config, store, record)
        if store.pending_operation() is not None:
            raise ValueError("Pending operation requires reconciliation")
        if not _disposable(record) or record.state not in {"ACTIVE", "ELIGIBLE", "RESTORED"}:
            return record
        if record.batch_id and (record.terminal_observed_at is None or record.eligible_at is None):
            return record
        eligible_at = record.eligible_at or record.created_at + timedelta(seconds=policy.rules[record.category].active_seconds)
        if now < eligible_at or _producer_activity_hold(config):
            return record
        try:
            source = _original(config, record)
            destination = _payload(config, record)
            _check_overlap(store, record, source)
            _check_overlap(store, record, destination)
            _verified(source, record)
            if destination.exists() or destination.is_symlink():
                raise ValueError("QUARANTINE_COLLISION")
            if destination.parent.exists() and any(destination.parent.iterdir()):
                raise ValueError("QUARANTINE_CONTAINER_NOT_EMPTY")
        except (OSError, ValueError) as exc:
            if str(exc) == "CONTENT_CHANGED":
                _mark_error(store, record, "CONTENT_CHANGED")
                return _record_by_id(store, record.artifact_id)
            return _review(store, record, str(exc))
        operation = {"version": 2, "type": "MOVE_TO_QUARANTINE", "phase": "INTENT",
            "artifact_id": record.artifact_id, "source": str(source), "destination": str(destination),
            "at": now.isoformat(), "purge_after": (now + timedelta(seconds=1296000)).isoformat()}
        store.set_pending_operation(operation)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            _owned_record(config, store, record)
            _original(config, record)
            _payload(config, record)
            _verified(source, record)
            if destination.exists() or destination.is_symlink():
                raise ValueError("QUARANTINE_COLLISION")
        except (OSError, ValueError) as exc:
            return _review(store, record, str(exc))
        try:
            os.replace(source, destination)
        except OSError as exc:
            if exc.errno != errno.EXDEV and getattr(exc, "winerror", None) != 17:
                return _review(store, record, "QUARANTINE_MOVE_FAILED")
            copying = replace(record, state="QUARANTINE_COPYING")
            operation = {**operation, "phase": "COPYING"}
            store.update_pending_operation(operation, copying)
            try:
                _copy_durable(source, destination, record.kind)
                _verified(destination, record)
                _verified(source, record)
                operation = {**operation, "phase": "VERIFIED"}
                store.update_pending_operation(operation)
                _check_overlap(store, copying, source)
                _check_overlap(store, copying, destination)
                _payload(config, copying)
                _verified(destination, record)
                _remove_verified(source, record)
            except (OSError, ValueError) as exc:
                return _review(store, copying, "QUARANTINE_COPY_FAILED: " + str(exc))
        return _complete_quarantine(store, record, operation)


def _activation_evidence(config, store, activation_store, policy):
    from .retention_activation import activation_allows_purge, inventory_fingerprint, policy_fingerprint
    if activation_store.workstation_id != config.workstation_id or activation_store.path != config.retention_activation_path.resolve():
        return None
    try:
        registry_bytes = store.path.read_bytes()
        policy_hash = policy_fingerprint(policy)
        inventory_hash = inventory_fingerprint(config, store)
        if registry_bytes != store.path.read_bytes():
            return None
        if not activation_allows_purge(activation_store, config.workstation_id, policy_hash, inventory_hash):
            return None
        return registry_bytes, policy_hash, inventory_hash
    except (OSError, ValueError, KeyError, TypeError):
        return None


def purge_artifact(config: CreativeConfig, store: ArtifactStore, activation_store,
                   record: ArtifactRecord, policy: ArtifactPolicy, now_utc: datetime) -> ArtifactRecord:
    now = _utc(now_utc)
    if type(policy.quarantine_seconds) is not int or policy.quarantine_seconds != 1296000:
        raise ValueError("Quarantine must last 1296000 seconds")
    _owned_record(config, store, record)
    if not _disposable(record) or record.state != "QUARANTINED":
        return record
    evidence = _activation_evidence(config, store, activation_store, policy)
    with store.registration_guard():
        current = _record_by_id(store, record.artifact_id)
        if current != record:
            return _review(store, current, "INVENTORY_CHANGED")
        if store.pending_operation() is not None:
            raise ValueError("Pending operation requires reconciliation")
        try:
            original = _original(config, record)
            payload = _payload(config, record)
            _check_overlap(store, record, original)
            _check_overlap(store, record, payload)
            if original.exists():
                raise ValueError("QUARANTINE_AMBIGUOUS")
            _verified(payload, record)
            if record.quarantined_at is None or record.purge_after != record.quarantined_at + timedelta(seconds=1296000):
                raise ValueError("INVALID_PURGE_TIME")
        except (OSError, ValueError) as exc:
            return _review(store, record, str(exc))
        if now < record.purge_after or _producer_activity_hold(config) or evidence is None:
            return record
        registry_bytes, policy_hash, inventory_hash = evidence
        if store.path.read_bytes() != registry_bytes:
            return _review(store, record, "INVENTORY_CHANGED")
        from .retention_activation import activation_allows_purge, inventory_fingerprint
        try:
            current_inventory_hash = inventory_fingerprint(config, store)
        except (OSError, ValueError, KeyError, TypeError):
            return _review(store, record, "INVENTORY_CHANGED")
        if current_inventory_hash != inventory_hash or store.path.read_bytes() != registry_bytes:
            return _review(store, record, "INVENTORY_CHANGED")
        if not activation_allows_purge(activation_store, config.workstation_id, policy_hash, current_inventory_hash):
            return record
        operation = {"version": 2, "type": "PURGE", "phase": "INTENT",
            "artifact_id": record.artifact_id, "source": str(payload), "destination": "",
            "policy_fingerprint": policy_hash, "inventory_fingerprint": inventory_hash,
            "at": now.isoformat()}
        store.set_pending_operation(operation)
        pending = replace(record, state="PURGE_PENDING")
        store.update_pending_operation(operation, pending)
        try:
            _owned_record(config, store, pending)
            _payload(config, pending)
            _check_overlap(store, pending, payload)
            if _original(config, pending).exists():
                raise ValueError("QUARANTINE_AMBIGUOUS")
            if not activation_allows_purge(activation_store, config.workstation_id, policy_hash, inventory_hash):
                store.replace(record)
                store.clear_pending_operation()
                return record
            _remove_verified(payload, pending)
        except (OSError, ValueError) as exc:
            return _review(store, pending, "PURGE_FAILED: " + str(exc))
        operation = {**operation, "phase": "DELETED"}
        store.update_pending_operation(operation)
        purged = replace(record, state="PURGED", last_error=None)
        store.replace(purged)
        store.clear_pending_operation()
        return purged


def run_maintenance(config: CreativeConfig, artifact_store: ArtifactStore, project_registry: Any,
                    policy: ArtifactPolicy, now_utc: datetime, activation_store=None) -> dict[str, Any]:
    now = _utc(now_utc)
    descriptor = _acquire_lock(artifact_store)
    if descriptor is None:
        return {"ok": False, "action": "run_artifact_maintenance",
                "error_code": "MAINTENANCE_LOCKED", "quarantined": [], "purged": []}
    quarantined: list[str] = []
    purged: list[str] = []
    purge_blocked: list[str] = []
    reviews: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    try:
        if policy.quarantine_seconds != 1296000:
            raise ValueError("Quarantine must last 1296000 seconds")
        with artifact_store.registration_guard():
            before = {record.artifact_id: record.state for record in artifact_store.records()}
            _reconcile_pending(config, artifact_store, policy, now)
            for record in artifact_store.records():
                if record.state != before.get(record.artifact_id):
                    if record.state == "QUARANTINED" and before.get(record.artifact_id) != "PURGE_PENDING":
                        quarantined.append(record.artifact_id)
                    elif record.state == "PURGED":
                        purged.append(record.artifact_id)
        _import_rotated_logs(config, artifact_store, policy)
        if activation_store is None:
            from .retention_activation import RetentionActivationStore
            activation_store = RetentionActivationStore(config.retention_activation_path, config.workstation_id)
        producer_hold = _producer_activity_hold(config)
        for record in artifact_store.records():
            if record.state in {"ERROR", "PURGED", "REVIEW_REQUIRED"} or not _disposable(record) or producer_hold:
                continue
            _owned_record(config, artifact_store, record)
            if record.batch_id and record.terminal_observed_at is None:
                with artifact_store.registration_guard():
                    # Producers may promote to Resolve protection after the loop
                    # snapshot. Never freeze/save that stale disposable record.
                    record = _record_by_id(artifact_store, record.artifact_id)
                    _owned_record(config, artifact_store, record)
                    if not _disposable(record) or record.state not in {"ACTIVE", "ELIGIBLE", "RESTORED"}:
                        continue
                    record = _freeze_terminal(record, artifact_store, project_registry, policy, now)
            if record.state in {"ACTIVE", "ELIGIBLE", "RESTORED"}:
                if record.batch_id:
                    batch = project_registry.render_batch(record.batch_id)
                    if batch is None or batch.status in ACTIVE_BATCH_STATES or record.eligible_at is None:
                        continue
                updated = quarantine_artifact(config, artifact_store, record, policy, now)
                if updated.state == "QUARANTINED" and record.artifact_id not in quarantined:
                    quarantined.append(record.artifact_id)
            elif record.state == "QUARANTINED":
                updated = purge_artifact(config, artifact_store, activation_store, record, policy, now)
                if updated.state == "PURGED":
                    purged.append(record.artifact_id)
                elif record.quarantined_at is not None and now >= record.quarantined_at + timedelta(seconds=1296000):
                    purge_blocked.append(record.artifact_id)
            if artifact_store.pending_operation() is not None:
                break
        for record in artifact_store.records():
            if record.state == "REVIEW_REQUIRED":
                reviews.append({"artifact_id": record.artifact_id, "code": record.last_error})
            elif record.state == "ERROR":
                errors.append({"artifact_id": record.artifact_id, "code": record.last_error})
        artifact_store.set_maintenance_state(last_attempt_at=now, last_result="ok")
        return {"ok": True, "action": "run_artifact_maintenance",
                "workstation_id": config.workstation_id,
                "policy_version": policy.policy_version,
                "quarantined": quarantined, "purged": purged,
                "purge_blocked": purge_blocked, "review_required": reviews, "errors": errors}
    except RegistrationLockedError:
        return {"ok": False, "action": "run_artifact_maintenance",
                "error_code": "REGISTRATION_LOCKED", "quarantined": quarantined,
                "purged": purged, "purge_blocked": purge_blocked, "review_required": reviews, "errors": errors}
    except Exception as exc:
        try:
            artifact_store.set_maintenance_state(last_attempt_at=now, last_result="error")
        except Exception:
            pass
        return {"ok": False, "action": "run_artifact_maintenance",
                "error_code": type(exc).__name__, "quarantined": quarantined,
                "purged": purged, "purge_blocked": purge_blocked, "review_required": reviews,
                "errors": errors + [{"code": type(exc).__name__, "detail": str(exc)}]}
    finally:
        _release_lock(artifact_store, descriptor)


def _restore_artifact(config: CreativeConfig, artifact_store: ArtifactStore, artifact_id: str,
                     policy: ArtifactPolicy, now_utc: datetime, *, keep_after_restore: bool = False) -> dict[str, Any]:
    now = _utc(now_utc)
    descriptor = _acquire_lock(artifact_store)
    if descriptor is None:
        return {"ok": False, "action": "restore_quarantined_artifact", "error_code": "MAINTENANCE_LOCKED"}
    try:
        _reconcile_pending(config, artifact_store, policy, now)
        record = _record_by_id(artifact_store, artifact_id)
        _owned_record(config, artifact_store, record)
        if record.state != "QUARANTINED" or not _disposable(record) or not record.quarantine_path or not record.original_path:
            return {"ok": False, "action": "restore_quarantined_artifact", "error_code": "NOT_QUARANTINED"}
        source = _payload(config, record)
        destination = _original(config, record)
        if destination.exists() or destination.is_symlink():
            return {"ok": False, "action": "restore_quarantined_artifact", "error_code": "RESTORE_COLLISION"}
        _check_overlap(artifact_store, record, source)
        _check_overlap(artifact_store, record, destination)
        size, digest, _ = _signature(source, record.kind)
        if record.size_bytes != size or record.sha256 != digest:
            _mark_error(artifact_store, record, "QUARANTINE_CONTENT_CHANGED")
            return {"ok": False, "action": "restore_quarantined_artifact",
                    "error_code": "QUARANTINE_CONTENT_CHANGED"}
        destination.parent.mkdir(parents=True, exist_ok=True)
        eligible_at = now + timedelta(seconds=policy.rules[record.category].active_seconds)
        operation = {
            "version": 2,
            "type": "RESTORE",
            "phase": "INTENT",
            "artifact_id": record.artifact_id,
            "source": str(destination),
            "destination": str(source),
            "eligible_at": eligible_at.isoformat(),
        }
        if keep_after_restore:
            operation["keep_after_restore"] = True
            operation["keep_requested_at"] = now.isoformat()
        artifact_store.set_pending_operation(operation)
        # A producer can have created a collision while the journal was flushed.
        if destination.exists() or destination.is_symlink():
            artifact_store.clear_pending_operation()
            return {"ok": False, "action": "restore_quarantined_artifact", "error_code": "RESTORE_COLLISION"}
        _original(config, record)
        _payload(config, record)
        _verified(source, record)
        try:
            os.replace(source, destination)
        except OSError as exc:
            if exc.errno != errno.EXDEV and getattr(exc, "winerror", None) != 17:
                raise
            operation = {**operation, "phase": "COPYING"}
            artifact_store.update_pending_operation(operation)
            try:
                _copy_durable(source, destination, record.kind)
                _verified(destination, record)
                _verified(source, record)
                artifact_store.update_pending_operation({**operation, "phase": "VERIFIED"})
                _original(config, record)
                _payload(config, record)
                _verified(destination, record)
                _remove_verified(source, record)
            except (OSError, ValueError) as exc:
                _review(artifact_store, record, "RESTORE_COPY_FAILED: " + str(exc))
                raise
        restored = replace(
            record,
            state="RESTORED",
            path=str(destination),
            original_path=str(destination),
            quarantine_path=None,
            quarantined_at=None,
            purge_after=None,
            eligible_at=eligible_at,
            last_error=None,
        )
        if keep_after_restore:
            try:
                restored = artifact_store.complete_restore_with_keep(record, restored, now)
            except (OSError, ValueError, RegistrationLockedError):
                # The registry still names the quarantined payload. Restore that exact state
                # before returning a failed keep, never exposing an unheld eligible artifact.
                try:
                    if source.exists() or source.is_symlink():
                        raise ValueError("RESTORE_ROLLBACK_COLLISION")
                    os.replace(destination, source)
                    artifact_store.clear_pending_operation()
                except (OSError, ValueError):
                    pass
                raise
        else:
            artifact_store.replace(restored)
            artifact_store.clear_pending_operation()
        try:
            source.parent.rmdir()
        except OSError:
            pass
        return {"ok": True, "action": "restore_quarantined_artifact",
                "artifact_id": artifact_id, "state": "RESTORED"}
    except (OSError, ValueError) as exc:
        return {"ok": False, "action": "restore_quarantined_artifact", "error_code": str(exc)}
    finally:
        _release_lock(artifact_store, descriptor)


def restore_artifact(config: CreativeConfig, artifact_store: ArtifactStore, artifact_id: str,
                     policy: ArtifactPolicy, now_utc: datetime, *, keep_after_restore: bool = False) -> dict[str, Any]:
    try:
        with artifact_store.registration_guard():
            return _restore_artifact(config, artifact_store, artifact_id, policy, now_utc,
                                     keep_after_restore=keep_after_restore)
    except RegistrationLockedError:
        return {"ok": False, "action": "restore_quarantined_artifact", "error_code": "REGISTRATION_LOCKED"}


def keep_artifact(config: CreativeConfig, store: ArtifactStore, artifact_id: str,
                  policy: ArtifactPolicy, now_utc: datetime) -> dict[str, Any]:
    """Keep an exact local artifact; quarantined content is restored before the hold."""
    try:
        now = _utc(now_utc)
        record = _record_by_id(store, artifact_id)
        _owned_record(config, store, record)
        restored = False
        if record.state == "QUARANTINED":
            outcome = restore_artifact(config, store, artifact_id, policy, now, keep_after_restore=True)
            if not outcome.get("ok"):
                return {"ok": False, "action": "keep_artifact", "artifact_id": artifact_id,
                        "error_code": outcome.get("error_code", "RESTORE_FAILED")}
            restored = True
        elif record.state not in {"ACTIVE", "ELIGIBLE", "RESTORED"}:
            # Let the store durably record a sanitized local refusal before returning.
            try:
                store.keep_artifact(artifact_id, now)
            except (OSError, ValueError, RegistrationLockedError):
                pass
            return {"ok": False, "action": "keep_artifact", "artifact_id": artifact_id,
                    "error_code": "STATE_REJECTED"}
        updated = _record_by_id(store, artifact_id) if restored else store.keep_artifact(artifact_id, now)
        return {"ok": True, "action": "keep_artifact", "artifact_id": artifact_id,
                "state": updated.state, "hold_reasons": updated.hold_reasons,
                "restore_performed": restored}
    except (KeyError, OSError, ValueError, RegistrationLockedError):
        return {"ok": False, "action": "keep_artifact", "artifact_id": artifact_id,
                "error_code": "KEEP_REFUSED"}
