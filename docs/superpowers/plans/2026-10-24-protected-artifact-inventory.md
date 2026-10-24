# Protected Artifact Inventory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Register new audio/Colorist evidence as protected and add safe read-only inventory, dry-run maintenance and real in-process periodic checks with purge disabled.

**Architecture:** Extend the existing registry backwards-compatibly, keep producer registration in a focused helper module, and add a pure simulation layer above the current quarantine engine. The runtime scheduler loops in-process but the offline branch is not installed or enabled.

**Tech Stack:** Python 3, PyAV-independent filesystem metadata, `unittest`, atomic JSON stores.

**Spec:** `docs/superpowers/specs/2026-10-24-protected-artifact-inventory-design.md`

## Global Constraints

- Unknown means protected; no extension/age bulk classification.
- No live move, quarantine, purge, scheduler installation, Resolve write, push or merge.
- `purge_enabled` is false and cannot be enabled by configuration in this proposal.
- Producer paths must remain inside configured roots and reject symlinks/reparse points.

## Review Focus

- Concurrent producer registration cannot lose an existing registry update.
- A crash-left lock fails closed without being auto-removed.
- Hash drift and symlink substitution block every proposal.
- Active jobs and pending human review keep dependencies protected.
- Legacy discovery remains a dry-run and cannot create a registry.

---

### Task 1: Protected registry records and purge gate

**Files:**
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/artifact_records.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/artifact_retention.json`
- Test: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_artifact_records.py`

**Interfaces:**
- Produces: `register_protected_path(...)`, dependency/review fields, fail-closed registration lock, `ArtifactPolicy.purge_enabled=False`.

- [ ] Write failing tests for protected round-trip, dependencies, symlink rejection, concurrent lock and crash-left lock.
- [ ] Run the focused tests and confirm the intended failures.
- [ ] Implement the minimum backwards-compatible record and lock changes.
- [ ] Run focused tests green.

### Task 2: Producer registration

**Files:**
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/artifact_producers.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/audio_tools.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/timeline_dialogue_cleanup.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/colorist_jobs.py`
- Test: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_artifact_producers.py`

**Interfaces:**
- Consumes: protected registration from Task 1.
- Produces: idempotent registration for completed audio bundles and mutable Colorist state with opaque dependencies and review holds.

- [ ] Write failing tests for audio A/V5/manifest relationships, Colorist review holds and active-job refusal.
- [ ] Run and verify RED.
- [ ] Implement helpers and wire only post-save/post-completion producer points.
- [ ] Run focused producer and existing audio/Colorist tests green.

### Task 3: Root inventory, dry-run and migration proposal

**Files:**
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/artifact_planning.py`
- Test: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_artifact_planning.py`

**Interfaces:**
- Produces: `inventory_roots(config)`, `scan_artifacts(...)`, `simulate_maintenance(...)`, `plan_legacy_migration(...)`.

- [ ] Write failing tests for unknown protection, size/category simulation, dependencies, active jobs, hash drift, symlinks and migration immutability.
- [ ] Run and verify RED.
- [ ] Implement the pure read-only planners.
- [ ] Run focused tests green.

### Task 4: Periodic in-process scheduling and purge-disabled enforcement

**Files:**
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/maintenance_scheduler.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/artifact_hygiene.py`
- Test: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_maintenance_scheduler.py`
- Test: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_artifact_hygiene.py`

**Interfaces:**
- Produces: repeating daemon check with stop event; expired quarantine reports `PURGE_DISABLED` and never calls deletion.

- [ ] Write failing tests for repeated due checks, offline/time jump behavior, lock failure and purge-disabled boundary.
- [ ] Run and verify RED.
- [ ] Implement periodic checks and the hard purge gate.
- [ ] Run focused and full suites green.

### Task 5: Offline evidence and review

**Files:**
- Create: `docs/24_PROTECTED_ARTIFACT_INVENTORY.md`

- [ ] Run a read-only inventory against configured roots and record only counts/categories/protected proposals.
- [ ] Run `git diff --check` and the complete Creative suite.
- [ ] Review the branch against the spec, fix Critical/Important findings, and commit locally without push.
