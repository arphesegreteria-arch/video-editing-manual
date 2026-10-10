# Astra review remediation implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Workflow Control Plane safe to deploy after the Astra review findings.

**Architecture:** Keep native workflow registries authoritative. Strengthen the common envelope with local transactional state, executable approval provenance, target identity checks and family-specific adapter state. Serialize every Resolve context-changing public operation with the existing lock.

**Tech Stack:** Python 3.12, MCPServer, DaVinci Resolve public scripting API, unittest, PowerShell installer.

**Spec:** `docs/superpowers/specs/2026-10-10-astra-review-remediation-design.md`

## Global Constraints

- `PC_SEGRETERIA` remains untouched and pending throughout this plan.
- Shipped `CAP_WORKFLOW_CONTROL_PLANE` values remain `false`.
- No generic delivery, render, publishing or natural-language executor is added.
- Existing native job registries remain the authority and are never migrated or deleted.
- Each behavior change begins with a failing test using the personal venv.

## Review Focus

- Two MCP worker threads prepare or approve distinct jobs at the same time; both updates must persist.
- A process ends after the native executor changed Resolve but before envelope completion; the next request must recover without a duplicate write.
- A project/timeline with the approved visible name but a different identity or source must be rejected before CUT.
- A generated Vertical Social UUID must progress from CUT to a later action using one owned provisional timeline name.
- A clean workstation installation must contain every contract imported by the bridge.

### Task 1: Transactional control-plane state and interruption recovery

**Files:**
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/control_plane.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/workflow_control.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_control_plane.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_workflow_control.py`

**Interfaces:**
- Produces an atomic `find_or_create_binding(...)` store operation and an `EXECUTING` recovery path which returns `FAILED_RECOVERABLE` without invoking its delegate.

- [ ] Write failing threaded create/revision tests and an interruption-after-claim test.
- [ ] Run the selected tests and observe lost state / rejected `EXECUTING` retry.
- [ ] Add path-scoped transaction locking, atomic binding lookup/create, persisted operation claim, and recovery transition.
- [ ] Run selected tests and the control-plane test group green.
- [ ] Commit with `fix: make control-plane state transactional`.

### Task 2: Bind approvals and targets to executable provenance

**Files:**
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/workflow_control.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/server.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_workflow_control.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_workflow_control_tools.py`

**Interfaces:**
- Produces normalized target provenance and a branded digest that changes when native approval decisions change.

- [ ] Write failing tests for changed branded decisions and same-name different-identity target.
- [ ] Run tests and observe the old approval/target is accepted.
- [ ] Implement provenance normalization, native binding checks and live identity checks under the Resolve lock.
- [ ] Run focused tests green.
- [ ] Commit with `fix: bind workflow approval to executable provenance`.

### Task 3: Repair adapter state and Vertical Social handoff

**Files:**
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/workflow_control.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/server.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/vertical_social_apply.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/vertical_social_cuts.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_workflow_control.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_workflow_control_tools.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_vertical_social_cuts.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_vertical_social_apply.py`

**Interfaces:**
- Produces family-aware cards and one shared `provisional_timeline_name(plan_id)`.

- [ ] Write failing tests for pending Vertical cards, blocked Podcast/Carabellese resume and UUID CUT-to-effect lookup.
- [ ] Run tests and observe `NONE`, dispatcher refusal, and name mismatch.
- [ ] Implement family-aware native state inspection, blocked routing and shared naming.
- [ ] Run adapter and Vertical Social test groups green.
- [ ] Commit with `fix: reconcile workflow adapters with native state`.

### Task 4: Serialize legacy context writes

**Files:**
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/server.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_workflow_control_tools.py`

**Interfaces:**
- Produces public Resolve selection/writes that cannot run concurrently with Control Plane target validation.

- [ ] Write a failing thread test in which `set_current_timeline` cannot complete while the Resolve lock is held.
- [ ] Run it and observe the current unprotected selection completes.
- [ ] Put all context-changing legacy public tools behind `RESOLVE_ACCESS_LOCK` without nesting behavior changes.
- [ ] Run focused tests green.
- [ ] Commit with `fix: serialize Resolve context-changing tools`.

### Task 5: Make a clean profile installation complete

**Files:**
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/install_on_segreteria.ps1`
- Modify: `scripts/windows_bridge/tests/test_profile_installer.py`
- Modify: `CURRENT_STATE.md`, `EXPERIMENT_LOG.md`, `CHANGELOG.md`, `docs/21_WORKFLOW_CONTROL_PLANE.md`

**Interfaces:**
- Produces a fresh Creative install containing all imported contracts and a truthful pending rollout record.

- [ ] Write a failing clean-install asset test for `branded_longform_contract.json`.
- [ ] Run it and observe the missing contract.
- [ ] Add the contract to the installer manifest and document remediation status without claiming a new gate yet.
- [ ] Run installer tests with Python 3.12 green.
- [ ] Commit with `fix: install branded longform contract`.

### Task 6: Whole-system verification and personal gate

**Files:**
- Modify: status documents only if verification produces new evidence.

- [ ] Run full Creative and Windows suites with explicit interpreters and `git diff --check`.
- [ ] Execute an isolated personal native gate only after the suites pass: interruption/recovery, same-name target block, Vertical CUT-to-effect, context restore and clean flag rollback.
- [ ] Record exact evidence and retain `PC_SEGRETERIA=PENDING`.
- [ ] Commit validation evidence with `docs: record control-plane remediation gate`.
- [ ] Produce a fresh review package and request an independent final review before merge.
