# Artifact Hygiene and Seven-Day Quarantine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add policy-bound inventory, seven-day quarantine, restore and automatic purge for bridge-owned technical files without touching user files or Resolve objects.

**Architecture:** A versioned retention policy and per-workstation artefact store feed a filesystem lifecycle engine. Creative producers register diagnostics and render staging; the Windows runtime emits validated sidecars for rotated logs. Three narrow MCP tools expose inspection, maintenance and one-item restore, while a profile-gated lazy runner performs at most one cycle per 24 hours.

**Tech Stack:** Python 3.12/3.13-compatible standard library, MCP Python server, PowerShell 5.1 installers, `unittest`, Windows filesystem.

**Spec:** `docs/superpowers/specs/2026-10-08-artifact-hygiene-quarantine-design.md`

## Global Constraints

- Quarantine is exactly seven complete days (`604800` seconds) in production policy.
- Only explicitly registered bridge artefacts or valid runtime-log producer sidecars are mutable.
- Desktop, Documents, Downloads, OneDrive, repositories, source media and Resolve objects are outside managed roots.
- Source, asset, review, master, publishable, config, secret, state, audit and active-log files are always protected.
- `PC_PERSONALE` and `PC_SEGRETERIA` use separate registry, quarantine, lock and evidence paths.
- Unknown existing files are `UNCLASSIFIED` and report-only.
- No second Scheduled Task and no generic path/list/move/delete MCP tool.
- Production retention is never shortened for live validation.
- Keep `CAP_CLEANUP` accepted for existing configs but retire its old public delete tools; the new gate is `CAP_ARTIFACT_MAINTENANCE`.

## Review Focus

- An old JPEG with a valid-looking ARPHE name but no registry record remains `UNCLASSIFIED` and untouched.
- A symlink, junction or resolved-path escape beneath a managed directory is rejected before inventory mutation.
- Staging tied to `DRAFT`, `CONFIRMED`, `PREPARED`, `APPROVED`, `RENDERING` or `VERIFYING` remains protected regardless of age.
- Restore into an occupied original path returns `RESTORE_COLLISION` without changing either item.
- A corrupt registry, changed digest or backwards clock fails closed and never shortens a deadline.

---

## File Structure

- `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/artifact_retention.json`: canonical production policy.
- `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/artifact_records.py`: policy types, artefact records and atomic per-PC store.
- `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/artifact_hygiene.py`: inventory, quarantine, restore, purge and reporting.
- `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/maintenance_scheduler.py`: profile-gated once-per-day background runner.
- `scripts/windows_bridge/artifact_log_handler.py`: unique rotated logs and producer sidecars.
- `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_artifact_records.py`: policy/store tests.
- `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_artifact_hygiene.py`: lifecycle and path-safety tests.
- `scripts/windows_bridge/tests/test_artifact_log_handler.py`: rotation/sidecar tests.
- `docs/19_ARTIFACT_HYGIENE_AND_QUARANTINE.md`: operator behaviour and per-PC live gates.

### Task 1: Define policy, configuration and the per-workstation artefact store

**Files:**
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/artifact_retention.json`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/artifact_records.py`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_artifact_records.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/config.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/feature_flags.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/creative_config.example.json`

**Interfaces:**
- Produces `load_artifact_policy(path: Path) -> ArtifactPolicy`.
- Produces immutable `ArtifactRecord` values and `ArtifactStore(path: Path, workstation_id: str)`.
- Produces `artifact_store_for(config: CreativeConfig) -> ArtifactStore` so existing bridge operations do not accept arbitrary registry paths.
- Produces `ArtifactStore.register_path(path, kind, category, producer, *, batch_id=None)`, `records()`, `replace(record)`, `maintenance_state()` and `set_maintenance_state(...)`.
- `kind` is `file` or `directory`; active directories may omit a digest until their terminal contents are frozen by maintenance.
- Adds `CreativeConfig.artifact_policy_path`, `artifact_registry_path`, `runtime_log_root` and `CAP_ARTIFACT_MAINTENANCE=false`.

- [ ] **Step 1: Write failing policy and store tests**

Test exact category retention (`86400` or `604800` active seconds and `604800` quarantine seconds), rejection of unknown categories/protection classes, atomic persistence, workstation mismatch, corrupt-registry failure and UTC deadline preservation when a supplied clock moves backwards.

```python
def test_production_policy_uses_full_seven_day_quarantine():
    assert policy.rules["DIAGNOSTIC_CAPTURE"].quarantine_seconds == 604800

def test_corrupt_existing_registry_fails_closed():
    path.write_text("{")
    with self.assertRaises(ValueError):
        ArtifactStore(path, "PC_PERSONALE").records()
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `py -3 -m unittest scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_artifact_records -v`

Expected: FAIL because policy/store/config fields do not exist.

- [ ] **Step 3: Implement the production policy and atomic store**

Use schema version 1, `datetime` UTC ISO-8601 values, opaque UUID artefact IDs and temporary-file plus `os.replace`. Preserve a corrupt expected registry instead of recreating it. Store only managed-root-relative display values in reports; retain canonical paths internally.

- [ ] **Step 4: Run policy/store and config regressions**

Run: `py -3 -m unittest scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_artifact_records scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_feature_flags -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/artifact_retention.json scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/artifact_records.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/config.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/feature_flags.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/creative_config.example.json scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_artifact_records.py
git commit -m "feat: define workstation artifact retention"
```

### Task 2: Build read-only inventory and eligibility reporting

**Files:**
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/artifact_hygiene.py`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_artifact_hygiene.py`

**Interfaces:**
- Consumes `ArtifactPolicy`, `ArtifactStore`, `CreativeConfig` and `Registry.render_batch(batch_id)`.
- Produces `inspect_artifacts(config, artifact_store, project_registry, policy, now_utc) -> dict[str, Any]`.
- Produces `validate_managed_path(path, root, *, allow_directory=False) -> Path`.
- Produces only counts, bytes, relative names, opaque IDs, deadlines, policy version and workstation ID.

- [ ] **Step 1: Write failing inventory tests**

Cover registered diagnostics, all protected path classes, the six active render states, the five terminal states, a retry-linked failed staging directory, shallow legacy discovery and report redaction. Add the Review Focus regressions for an unregistered ARPHE JPEG and symlink/junction/resolved escape.

```python
def test_unregistered_arphe_jpeg_is_report_only():
    report = inspect_artifacts(...)
    assert report["unclassified_count"] == 1
    assert jpeg.exists()

def test_active_batch_staging_is_protected_regardless_of_age():
    assert item_for("PREPARED", age_days=90)["state"] == "PROTECTED"
```

- [ ] **Step 2: Run inventory tests and verify failure**

Run: `py -3 -m unittest scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_artifact_hygiene -v`

Expected: FAIL because the lifecycle engine is absent.

- [ ] **Step 3: Implement allowlisted inventory and eligibility**

Inspect only `diagnostics`, exact registered staging roots, `render_root/technical-preview` and the exact runtime rotated-log pattern. Use `Path.resolve`, `os.path.commonpath`, symlink checks and Windows reparse-point checks. Do not mutate the store or filesystem during inspection.

- [ ] **Step 4: Run inventory tests**

Run: `py -3 -m unittest scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_artifact_hygiene -v`

Expected: PASS for inventory tests; mutation tests remain absent until Task 3.

- [ ] **Step 5: Commit**

```bash
git add scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/artifact_hygiene.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_artifact_hygiene.py
git commit -m "feat: inventory bridge-owned artifacts"
```

### Task 3: Implement quarantine, restore, purge and crash reconciliation

**Files:**
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/artifact_records.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/artifact_hygiene.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_artifact_hygiene.py`

**Interfaces:**
- Produces `run_maintenance(config, artifact_store, project_registry, policy, now_utc) -> dict[str, Any]`.
- Produces `restore_artifact(config, artifact_store, artifact_id, now_utc) -> dict[str, Any]`.
- Produces write-ahead operations `MOVE_TO_QUARANTINE`, `RESTORE` and `PURGE` reconciled by exact source, destination and digest.
- Uses one `.arphe-quarantine` directory per managed root and a profile-owned lock.

- [ ] **Step 1: Write failing lifecycle tests**

Test exact 24-hour/7-day boundaries, full seven days in quarantine, digest/size drift, fully owned versus mixed staging directories, one-item purge, restore success, `RESTORE_COLLISION`, concurrent-lock refusal, failed moves, failed registry save after move, write-ahead reconciliation and backwards-clock preservation.

```python
def test_purge_requires_seven_complete_days():
    assert run_at(quarantined_at + timedelta(days=7) - epsilon)["purged"] == []
    assert run_at(quarantined_at + timedelta(days=7))["purged"] == [artifact_id]

def test_restore_collision_changes_nothing():
    result = restore_artifact(...)
    assert result["error_code"] == "RESTORE_COLLISION"
    assert original.read_bytes() == new_content
    assert quarantined.exists()
```

- [ ] **Step 2: Run lifecycle tests and verify failure**

Run: `py -3 -m unittest scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_artifact_hygiene -v`

Expected: FAIL because mutation and reconciliation are not implemented.

- [ ] **Step 3: Implement fail-closed lifecycle operations**

Revalidate category, terminal state, containment, size, digest and lock immediately before each move. Move on the same volume with `os.replace`; never copy across roots. Persist a write-ahead record before mutation and clear it only after the new lifecycle record is durable. When maintenance first observes a terminal render batch, freeze a sorted descendant manifest, record `terminal_observed_at` and calculate retention from that conservative timestamp. A directory is one artefact only when every descendant belongs to the same registered batch.

- [ ] **Step 4: Run lifecycle and store tests**

Run: `py -3 -m unittest scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_artifact_hygiene scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_artifact_records -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/artifact_records.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/artifact_hygiene.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_artifact_hygiene.py
git commit -m "feat: quarantine and restore technical artifacts"
```

### Task 4: Register diagnostic captures and render staging

**Files:**
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/diagnostic_tools.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/render_tools.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/media_verification.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_safety.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_render_batches.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_media_verification.py`

**Interfaces:**
- `capture_timeline_frames(...)` keeps its public signature and obtains the store through `artifact_store_for(config)`; it calls `register_path(kind="file", category="DIAGNOSTIC_CAPTURE", ...)` only after every requested JPEG exists.
- `prepare_render_batch(...)` keeps its public signature and registers the exact batch staging directory as `RENDER_STAGING` through `artifact_store_for(config)` after the batch has a durable `staging_directory`.
- Inventory derives staging eligibility from the current render-batch state; publishable targets are never registered as disposable.

- [ ] **Step 1: Write failing producer tests**

Assert every successful JPEG is registered, a registration failure removes only newly created JPEGs, the old 64-file hard-delete path is absent, staging is registered once, `FAILED_PREPARE` becomes eligible after 24 hours, failed verification retains seven-day diagnostic staging and promoted output remains protected.

- [ ] **Step 2: Run focused producer tests and verify failure**

Run: `py -3 -m unittest scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_safety scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_render_batches scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_media_verification -v`

Expected: FAIL because producers do not register artefacts and diagnostics still delete directly.

- [ ] **Step 3: Integrate the store without changing render semantics**

Remove `MAX_DIAGNOSTIC_FILES` and `_prune_diagnostics`. Keep existing scoped rollback for producer failures. Do not register delivery files, source media or Resolve objects. Preserve all batch transitions and selective render behaviour.

- [ ] **Step 4: Run producer and render suites**

Run: `py -3 -m unittest scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_safety scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_render_batches scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_media_verification -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/diagnostic_tools.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/render_tools.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/media_verification.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_safety.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_render_batches.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_media_verification.py
git commit -m "feat: register diagnostic and staging artifacts"
```

### Task 5: Replace hidden runtime-log deletion with registered rotation

**Files:**
- Create: `scripts/windows_bridge/artifact_log_handler.py`
- Create: `scripts/windows_bridge/tests/test_artifact_log_handler.py`
- Modify: `scripts/windows_bridge/arphe_bridge_runtime.py`
- Modify: `scripts/windows_bridge/tests/test_runtime.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/artifact_hygiene.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_artifact_hygiene.py`

**Interfaces:**
- Produces `ArtifactRotatingFileHandler(path, workstation_id, max_bytes)`.
- A rotation creates `runtime_log_root/rotated/runtime.<UTC>.<opaque-id>/` containing `runtime.log` plus atomic `artifact.json` with schema, workstation, `ROTATED_LOG`, size, digest and created UTC.
- Inventory accepts only a complete producer directory under that exact `rotated` root, then persists the directory in the central store during maintenance.

- [ ] **Step 1: Write failing rotation and sidecar tests**

Assert unique non-shifting directories, no `backupCount` deletion, secret redaction before rotation, valid digest/size, workstation binding, incomplete/forged/orphan producer directories reported as errors and no adoption outside the exact log root.

- [ ] **Step 2: Run Windows/log tests and verify failure**

Run: `py -3 -m unittest scripts.windows_bridge.tests.test_artifact_log_handler scripts.windows_bridge.tests.test_runtime -v`

Expected: FAIL because the handler and producer sidecars do not exist.

- [ ] **Step 3: Implement registered size-based rotation**

Keep the 2,000,000-byte threshold. Create the unique producer directory, close and atomically move the active log into it, hash it, write `artifact.json`, then reopen the active log. On metadata failure keep the rotated directory as an error/unclassified item; never delete it. Update `configure_logging(log_dir, secret, workstation_id)`.

- [ ] **Step 4: Import valid sidecars during maintenance**

Extend maintenance—not read-only inspection—to register each complete producer directory as one lifecycle unit. Purge removes that exact directory after quarantine. Add the corresponding Creative lifecycle tests.

- [ ] **Step 5: Run Windows and Creative lifecycle tests**

Run: `py -3 -m unittest scripts.windows_bridge.tests.test_artifact_log_handler scripts.windows_bridge.tests.test_runtime scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_artifact_hygiene -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/windows_bridge/artifact_log_handler.py scripts/windows_bridge/arphe_bridge_runtime.py scripts/windows_bridge/tests/test_artifact_log_handler.py scripts/windows_bridge/tests/test_runtime.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/artifact_hygiene.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_artifact_hygiene.py
git commit -m "feat: retain rotated logs through quarantine"
```

### Task 6: Expose narrow tools, lazy maintenance and retire legacy deletion

**Files:**
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/maintenance_scheduler.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/server.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/tool_catalog.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_safety.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_artifact_hygiene.py`
- Delete: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/cleanup_tools.py`
- Delete: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_cleanup_tools.py`

**Interfaces:**
- Exposes `inspect_artifact_hygiene()` as read-only.
- Exposes `run_artifact_maintenance()` with both destructive and idempotent annotations for a fixed policy cycle.
- Exposes `restore_quarantined_artifact(artifact_id: str)` as a scoped write.
- Produces `start_lazy_maintenance(config_loader, delay_seconds=5) -> threading.Thread | None` and `run_if_due(...)`.
- Removes public `preview_publish_cleanup` and `apply_publish_cleanup`; `CAP_CLEANUP` remains config-compatible but has no public destructive path.

- [ ] **Step 1: Write failing MCP and scheduler tests**

Assert exact tool names/annotations, no path argument, output redaction, disabled gate blocks mutation but not inspection, one run per 24 hours, one concurrent lock, background failure does not stop `mcp.run`, and old cleanup tools are absent.

- [ ] **Step 2: Run safety/lifecycle tests and verify failure**

Run: `py -3 -m unittest scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_safety scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_artifact_hygiene -v`

Expected: FAIL because the tools and scheduler are absent and legacy deletion remains exposed.

- [ ] **Step 3: Implement the narrow MCP surface and lazy runner**

The background thread starts before `mcp.run`, waits five seconds, loads only the selected profile and runs only when `CAP_ARTIFACT_MAINTENANCE=true` and the last attempt is at least 24 hours old. Exceptions update maintenance state and are swallowed after redacted audit; they do not touch Resolve or readiness.

- [ ] **Step 4: Remove legacy arbitrary cleanup exposure**

Remove imports, decorators, catalog entries and the obsolete module/tests. Do not add a generic compatibility wrapper that accepts paths or Resolve project/timeline names.

- [ ] **Step 5: Run complete Creative suite**

Run: `py -3 -m unittest discover -s scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests -v`

Expected: PASS with no old cleanup tools exposed.

- [ ] **Step 6: Commit**

```bash
git add scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/maintenance_scheduler.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/server.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/tool_catalog.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_safety.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_artifact_hygiene.py
git rm scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/cleanup_tools.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_cleanup_tools.py
git commit -m "feat: expose safe artifact maintenance"
```

### Task 7: Install, document and validate the personal-PC rollout

**Files:**
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/install_on_segreteria.ps1`
- Modify: `scripts/windows_bridge/install_autostart.ps1`
- Modify: `scripts/windows_bridge/profile_config.py`
- Modify: `scripts/windows_bridge/bridge_config.example.json`
- Modify: `scripts/windows_bridge/tests/test_profile_installer.py`
- Modify: `scripts/windows_bridge/tests/test_profile_config.py`
- Create: `docs/19_ARTIFACT_HYGIENE_AND_QUARANTINE.md`
- Modify: `CURRENT_STATE.md`
- Modify: `CHANGELOG.md`
- Modify: `INDEX.md`
- Modify: `START_HERE.md`
- Modify: `validation/validation-ledger.json`

**Interfaces:**
- Creative installer copies `artifact_retention.json` and pins `artifact_policy_path`, profile-owned `artifact_registry_path` and workstation-specific `runtime_log_root`.
- Windows installer copies `artifact_log_handler.py` and keeps one existing supervisor task.
- Documentation records code tests separately from `PC_PERSONALE` and `PC_SEGRETERIA` live gates.

- [ ] **Step 1: Write failing installer/profile tests**

Assert both profiles resolve different registry/quarantine/log roots; installers copy policy and log handler; upgrades preserve existing config/secrets while adding missing fields; dry-run writes nothing; a foreign workstation registry/config is rejected.

- [ ] **Step 2: Run Windows tests and verify failure**

Run: `py -3 -m unittest discover -s scripts/windows_bridge/tests -v`

Expected: FAIL because payload/config migration is incomplete.

- [ ] **Step 3: Implement profile-safe installation and migration**

Add fields only inside the selected profile. Leave `CAP_ARTIFACT_MAINTENANCE=false` on install and preserve an existing explicit value. Do not deploy to or modify the other workstation.

- [ ] **Step 4: Write operator documentation and pending gates**

Document categories, exact retention, protected locations, unclassified files, restore collision, health warning and the fact that real purge cannot be marked PASS before seven days. Add `PENDING` gates separately for both PCs before rollout.

- [ ] **Step 5: Run full automated verification**

Run: `py -3 -m unittest discover -s scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests -v`

Run: `py -3 -m unittest discover -s scripts/windows_bridge/tests -v`

Run: `py -3 scripts/validate_validation_ledger.py --ledger validation/validation-ledger.json --current-state CURRENT_STATE.md`

Expected: all Creative and Windows tests PASS except the already documented environment-dependent DPAPI skip; ledger validation PASS.

- [ ] **Step 6: Perform whole-branch safety review**

Review from the spec commit through `HEAD`, focusing on unknown-file mutation, path escapes, active staging, hidden direct deletion, cross-workstation paths, shortened retention and sensitive report fields. Resolve every Critical/Important finding and rerun Step 5.

- [ ] **Step 7: Commit code-complete documentation**

```bash
git add scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/install_on_segreteria.ps1 scripts/windows_bridge/install_autostart.ps1 scripts/windows_bridge/profile_config.py scripts/windows_bridge/bridge_config.example.json scripts/windows_bridge/tests/test_profile_installer.py scripts/windows_bridge/tests/test_profile_config.py docs/19_ARTIFACT_HYGIENE_AND_QUARANTINE.md CURRENT_STATE.md CHANGELOG.md INDEX.md START_HERE.md validation/validation-ledger.json
git commit -m "docs: prepare artifact maintenance rollout"
```

- [ ] **Step 8: Roll out only to `PC_PERSONALE`**

Run the installer preflight, back up the personal profile, deploy the verified commit, enable `CAP_ARTIFACT_MAINTENANCE` only for `PC_PERSONALE`, restart its existing task and verify workstation ID, Creative03 active and `/readyz=ready`. Confirm `PC_SEGRETERIA` paths and task were not touched.

- [ ] **Step 9: Execute the disposable-file live gate**

Create new bridge-owned diagnostic/test artefacts and verify inventory at rollout. After 24 complete hours, quarantine one of those exact artefacts, restore it, re-quarantine it and confirm report/digest/path behaviour. Record quarantine/restore as `TIME_BOUND_PENDING` until that follow-up occurs, and record purge separately as `TIME_BOUND_PENDING` until the re-quarantined item has remained there for seven complete days. Never backdate evidence, shorten production policy or use editorial files.

- [ ] **Step 10: Record evidence and open the pull request**

Update the ledger and docs with exact commit, workstation, policy version, test counts, live gate result, limitations and rollback. Push the branch, attach the pull request and merge only after checks and review are clean.

## Self-Review Notes

- Every in-scope artefact category has a producer path or an explicitly future producer contract.
- The plan removes both existing hidden deletion paths: diagnostic overflow and rotating-log backup deletion.
- Render staging eligibility covers `FAILED_PREPARE`, `VERIFIED`, `CANCELLED`, `FAILED_RENDER` and `FAILED_VERIFY`; all non-terminal states are protected.
- The new tool surface has no arbitrary path or Resolve-object argument.
- Installer and live-gate work are profile-scoped; `PC_SEGRETERIA` remains untouched and `PENDING`.
- Real seven-day purge evidence is deliberately not claimed during same-day rollout.
