# Branded Longform Editorial Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a safe, profile-isolated longform editing workflow with conservative cleanup, OBS multicamera support and approved adaptive editorial proposals.

**Architecture:** Add a dedicated contract and profile registry, then layer source-package validation, cleanup planning and editorial proposal/application on existing job, timeline, marker, checkpoint and feature-flag primitives.  Keep Resolve writes behind a default-off capability and expose typed server tools rather than free-form Resolve commands.

**Tech Stack:** Python 3.13, existing DaVinci Resolve scripting bridge, JSON contracts, unittest.

**Spec:** `docs/superpowers/specs/2026-10-10-branded-longform-editorial-design.md`

## Global Constraints

- Workflow ID is `BRANDED_LONGFORM_EDITORIAL`; profiles are `ARPHE_LONGFORM_EDITORIAL` and `CARABELLESE_LONGFORM_EDITORIAL`.
- `PROGRAM` provides the only final audio; camera audio is synchronization guide only.
- Preserve `ORIGINAL -> _CLEANUP -> _EDITORIAL`; never mutate the original timeline.
- `CARABELLESE_LONGFORM_EDITORIAL` remains `kit_status=PENDING` and may not apply ARPHE graphics.
- Only typed, fingerprint-bound batches approved by `ALESSIO` or `TECNICO` can write editorial interventions.
- `CAP_BRANDED_LONGFORM_EDITORIAL` defaults to false; PC_SEGRETERIA is out of scope.

## Review Focus

- A multicamera package with mismatched rates or no guide audio must remain review-only, never claim synchronization (Task 2).
- A changed original/contract/profile after approval must reject the write before any derived timeline change (Task 3).
- Ambiguous editorial cues and low-confidence filler detection must yield review markers, not auto-cuts (Task 3).
- A pending Carabellese kit must reject graphic application while still permitting cleanup/proposals (Task 4).
- A natural-language batch with a rejected or modified item must apply only its typed approved subset once (Task 5).

---

### Task 1: Branded longform contract and profile registry

**Files:**
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/branded_longform_contract.json`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/branded_longform_contract.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/editorial_workflows.json`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/editorial_workflows.py`
- Test: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_branded_longform_contract.py`

**Interfaces:**
- Produces `BrandedLongformContract`, `BrandProfile`, `load_branded_longform_contract(path: Path) -> BrandedLongformContract`, `profile_for(contract, profile_id) -> BrandProfile`, and `branded_longform_fingerprint(contract, profile) -> str`.
- Consumes `ValidationError` and the existing strict JSON loader conventions.

- [ ] **Step 1: Write failing contract tests** for ARPHE `READY`, Carabellese `PENDING`, unknown keys, duplicate profile IDs and the prohibition on graphic operations for a pending kit.
- [ ] **Step 2: Run** `python -m unittest scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_branded_longform_contract -q` **and verify failure** because the contract module is absent.
- [ ] **Step 3: Implement strict contract parsing** with source modes `SINGLE`/`OBS_MULTICAM`, profile kit status, allowed asset classes, semantic classes and cleanup confidence thresholds; register `BRANDED_LONGFORM_EDITORIAL` without deleting the existing legacy ARPHE longform entry.
- [ ] **Step 4: Re-run the focused test** and verify it passes.
- [ ] **Step 5: Commit** `feat: add branded longform contract`.

### Task 2: OBS package inspection and synchronization plan

**Files:**
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/branded_longform_media.py`
- Test: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_branded_longform_media.py`

**Interfaces:**
- Consumes `BrandedLongformContract` and `BrandProfile` from Task 1.
- Produces `LongformSourcePackage`, `CameraSource`, `inspect_longform_sources(raw: dict[str, object], contract: BrandedLongformContract) -> LongformSourcePackage`, and `build_sync_plan(package: LongformSourcePackage) -> dict[str, object]`.

- [ ] **Step 1: Write failing tests** for a valid single source, valid `PROGRAM` + two cameras, duplicate camera labels, missing PROGRAM, inconsistent rates and absent guide audio.
- [ ] **Step 2: Run** `python -m unittest scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_branded_longform_media -q` **and verify failure**.
- [ ] **Step 3: Implement immutable package records and validation.** Mark no-guide-audio packages `REVIEW_REQUIRED`; mark guide-aligned packages `READY_FOR_NATIVE_SYNC`; expose PROGRAM as `final_audio_source` unconditionally.
- [ ] **Step 4: Re-run the focused test** and verify it passes.
- [ ] **Step 5: Commit** `feat: validate branded longform sources`.

### Task 3: Cleanup plan, job state and derived timeline safety

**Files:**
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/branded_longform_cleanup.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/feature_flags.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/timeline_tools.py`
- Test: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_branded_longform_cleanup.py`

**Interfaces:**
- Consumes Task 1 profile fingerprint and Task 2 package/sync result.
- Produces `BrandedLongformJob`, `CleanupCandidate`, `create_cleanup_job(...) -> BrandedLongformJob`, `plan_cleanup(job, transcript) -> tuple[CleanupCandidate, ...]`, `prepare_cleanup_timeline(...) -> dict[str, object]`, and `verify_cleanup_preconditions(...) -> None`.

- [ ] **Step 1: Write failing tests** for high-confidence filler/restart removal, meaningful silence/ambiguous cue review markers, immutable original naming, stale fingerprint rejection and `CAP_BRANDED_LONGFORM_EDITORIAL=false` rejection.
- [ ] **Step 2: Run** `python -m unittest scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_branded_longform_cleanup -q` **and verify failure**.
- [ ] **Step 3: Implement job revisions, cleanup candidates and `_CLEANUP` creation.** Reuse existing lock/checkpoint/timeline helpers; keep camera-selection reasons explicit and never choose a camera merely for cadence.
- [ ] **Step 4: Re-run the focused test** and verify it passes.
- [ ] **Step 5: Commit** `feat: add conservative longform cleanup`.

### Task 4: Semantic proposal engine and profile/asset guard

**Files:**
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/branded_longform_editorial.py`
- Test: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_branded_longform_editorial.py`

**Interfaces:**
- Consumes `BrandedLongformJob`, `BrandProfile` and cleanup markers from Task 3.
- Produces `EditorialProposal`, `ProposalCard`, `propose_editorial(job, segments, profile) -> ProposalCard`, `validate_asset_for_proposal(proposal, profile, asset) -> None`, and `proposal_fingerprint(card) -> str`.

- [ ] **Step 1: Write failing tests** for each semantic class, three-item list proposal, personal-story restraint, camera-cut preference, low-confidence fallback, supplied B-roll acceptance, stock/generated proposal-only status and Carabellese pending-kit graphic rejection.
- [ ] **Step 2: Run** `python -m unittest scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_branded_longform_editorial -q` **and verify failure**.
- [ ] **Step 3: Implement deterministic classification/proposal policy and one compact card projection.** Each proposal must include ID, time range, kind, rationale, asset/copy requirement, profile and pacing impact.
- [ ] **Step 4: Re-run the focused test** and verify it passes.
- [ ] **Step 5: Commit** `feat: add adaptive longform proposals`.

### Task 5: Batch approval, editorial timeline application and verification

**Files:**
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/branded_longform_apply.py`
- Test: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_branded_longform_apply.py`

**Interfaces:**
- Consumes `ProposalCard`/fingerprint from Task 4 and cleanup timeline from Task 3.
- Produces `ApprovalDecision`, `approve_proposal_batch(card, decisions, operator_role) -> tuple[ApprovalDecision, ...]`, `apply_branded_editorial(...) -> dict[str, object]`, and `verify_branded_editorial(...) -> dict[str, object]`.

- [ ] **Step 1: Write failing tests** for one natural-language-normalized batch where only approved typed items apply; duplicate retry; stale approval; source/timeline tamper; unresolved asset; font/safe-area/overflow verification failure.
- [ ] **Step 2: Run** `python -m unittest scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_branded_longform_apply -q` **and verify failure**.
- [ ] **Step 3: Implement typed batch approval and `_EDITORIAL` timeline creation.** Use the existing graphics/readability primitives only after profile and asset provenance checks; journal verification per proposal and preserve verified cleanup on partial failure.
- [ ] **Step 4: Re-run the focused test** and verify it passes.
- [ ] **Step 5: Commit** `feat: apply approved branded longform edits`.

### Task 6: Server surface, documentation, validation ledger and personal rollout gate

**Files:**
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/server.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/tool_catalog.py`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/scripts/native_gate_branded_longform.py`
- Create: `scripts/validate_branded_longform.py`
- Create: `validation/branded-longform-ledger.json`
- Modify: `docs/18_EDITORIAL_WORKFLOWS_AND_RENDER_DELIVERY.md`
- Modify: `CURRENT_STATE.md`
- Modify: `CHANGELOG.md`
- Test: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_entrypoint.py`

**Interfaces:**
- Consumes the Task 1–5 public functions.
- Produces bridge tools `inspect_branded_longform`, `create_branded_longform_cleanup`, `propose_branded_longform_editorial`, `approve_branded_longform_batch`, `apply_branded_longform_batch` and `verify_branded_longform_job`.

- [ ] **Step 1: Write failing entrypoint/catalog tests** for complete tool exposure, default-off capability, role denial and a status response that names workstation, profile, kit readiness, selected project/timeline and source mode.
- [ ] **Step 2: Run the focused tests** and verify failure before registration.
- [ ] **Step 3: Wire safe server handlers and tool descriptions.** Handlers must return the single compact card for ordinary operators and full evidence only on technical request.
- [ ] **Step 4: Implement validator/ledger and native gate.** The gate uses only a disposable PC_PERSONALE project, verifies cleanup/marker/approval/rollback, restores source state and returns the capability to false; it never addresses PC_SEGRETERIA.
- [ ] **Step 5: Run** `python -m unittest discover -s scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests -q` **and** `python scripts/validate_branded_longform.py`; record exact results in the ledger.
- [ ] **Step 6: Commit** `feat: expose branded longform workflow`.

## Execution Handoff

Plan complete.  This should be executed natively in one controlled worktree because Tasks 1–5 share strict contracts and state-machine interfaces; finish with an independent whole-branch review before any PR or rollout.
