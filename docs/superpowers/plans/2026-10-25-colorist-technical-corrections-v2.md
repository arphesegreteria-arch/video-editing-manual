# ARPHE Colorist Technical Corrections V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add fingerprint-bound per-clip technical corrections and honest multicamera matching semantics to the guarded ARPHE Colorist workflow.

**Architecture:** Extend the pure model with closed technical-observation validation, evolve Colorist jobs to a backward-readable V2 payload, and make the Resolve adapter apply one approved CDL directly per clip. Keep all Resolve writes behind the existing local-version, approval, rollback and review gates.

**Tech Stack:** Python 3.12+, standard library, MCP Python SDK, DaVinci Resolve Studio 21 scripting API, `unittest`.

**Spec:** `docs/superpowers/specs/2026-10-25-colorist-technical-corrections-v2-design.md`

## Global Constraints

- Do not connect to Resolve, install runtimes, restart bridges, save projects, render, or touch media.
- `CAP_COLORIST` remains disabled by default.
- V2 never calls `CopyGrades`; every selected clip receives its fingerprint-bound CDL directly.
- Existing V1 records remain readable and retain their original fingerprint semantics.
- All Resolve writes remain approval-bound and use new local color versions with rollback/read-back.
- Signature ADV looks are out of scope for this plan.

## Review Focus

- A V1 APPLIED record pending review must still load, preview and complete review without fingerprint drift.
- Per-clip maps with missing, extra or reordered keys must fail or remain fingerprint-stable as appropriate.
- Observation values containing bool, NaN, infinity, invalid percentile ordering or too many frame samples must fail before persistence.
- A V2 partial apply must restore every previously active version and never fall back to `CopyGrades`.
- Apply evidence with a CDL digest belonging to a different clip must be rejected.

---

### Task 1: Closed technical observations and per-clip CDL construction

**Files:**
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/colorist_model.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_colorist_model.py`

**Interfaces:**
- Produces: `build_clip_corrections(clip_ids, adjustments, adjustments_by_clip, observations_by_clip, preset_name, presets) -> tuple[str, dict, dict, dict]` and `cdl_digest(cdl) -> str`.

- [ ] **Step 1: Write failing tests** for exact clip coverage, mutually exclusive global/per-clip adjustments, closed observations, numeric boundaries, percentile ordering, stable map order, and literal CDL digests.
- [ ] **Step 2: Run focused tests** with expected failures caused by the missing interfaces.
- [ ] **Step 3: Implement the minimal validators and builders** using the existing bounded `build_cdl` mapping.
- [ ] **Step 4: Run focused tests green.**
- [ ] **Step 5: Commit** with message `feat: add measured per-clip color corrections`.

### Task 2: Backward-readable V2 job schema and evidence

**Files:**
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/colorist_jobs.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_colorist_jobs.py`

**Interfaces:**
- Consumes: per-clip adjustments, observations, CDLs and digests from Task 1.
- Produces: V2 `ColoristJob` persistence/fingerprinting plus V1 decode and original-fingerprint verification.

- [ ] **Step 1: Write failing tests** for V2 fingerprint coverage, evidence digest validation, V1 terminal-record round-trip/review, and refusal to apply legacy PREPARED/APPROVED records as V2.
- [ ] **Step 2: Run focused tests red.**
- [ ] **Step 3: Implement plan-schema-aware payload, validation and serialization** without rewriting existing registry files on read.
- [ ] **Step 4: Run focused tests green.**
- [ ] **Step 5: Commit** with message `feat: version colorist plans for per-clip grading`.

### Task 3: Direct per-clip Resolve application

**Files:**
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/colorist_resolve.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_colorist_resolve.py`

**Interfaces:**
- Consumes: V2 job `cdl_by_clip` and `matching_strategy` from Task 2.
- Produces: direct per-clip `SetCDL`, optional per-clip DRX, digest-bound evidence, and unchanged rollback/read-back behavior.

- [ ] **Step 1: Write failing tests** proving different CDLs reach different clips, V2 never invokes `CopyGrades`, optional DRX applies per clip, digest evidence is exact, and partial failure restores all prior versions.
- [ ] **Step 2: Run focused tests red.**
- [ ] **Step 3: Implement V2 direct apply** while retaining the isolated legacy adapter path for persisted V1 jobs.
- [ ] **Step 4: Run focused tests green.**
- [ ] **Step 5: Commit** with message `feat: apply color corrections per clip`.

### Task 4: MCP contract, documentation and offline verification

**Files:**
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/server.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_colorist_tools.py`
- Modify: `docs/23_COLORIST_MODULE.md`
- Modify: `docs/RESOLVE_STUDIO_CAPABILITIES.md`
- Modify: `CURRENT_STATE.md`

**Interfaces:**
- Consumes: Tasks 1-3.
- Produces: expanded closed `prepare_colorist_plan` contract and operator-visible V2 strategy/evidence.

- [ ] **Step 1: Write failing tool tests** for the two optional closed maps, exact target coverage, no Resolve calls on invalid evidence, V2 inspection fields and default-off apply.
- [ ] **Step 2: Run focused tests red.**
- [ ] **Step 3: Wire preparation and inspection** to the V2 model/job interfaces.
- [ ] **Step 4: Run focused tests green.**
- [ ] **Step 5: Document** V2 semantics, V1 compatibility, honest matching limits, human review and pending native gate.
- [ ] **Step 6: Run all Colorist tests and the complete bridge suite.**
- [ ] **Step 7: Commit** with message `docs: define colorist technical correction v2`.
