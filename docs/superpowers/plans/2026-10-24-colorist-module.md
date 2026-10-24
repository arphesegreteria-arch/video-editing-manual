# ARPHE Colorist Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a guarded, non-destructive Colorist workflow for the ARPHE Resolve bridge.

**Architecture:** A pure planning layer validates bounded corrections and creates immutable fingerprints; a local state machine stores prepare/approve/apply/review evidence; a narrow Resolve adapter creates local color versions and applies only CDL, allowlisted DRX, or reference-grade copies. MCP wrappers expose the closed workflow behind `CAP_COLORIST`.

**Tech Stack:** Python 3.13, standard library, MCP Python SDK, DaVinci Resolve Studio 21 scripting API, `unittest`.

**Spec:** `docs/superpowers/specs/2026-10-24-colorist-module-design.md`

## Global Constraints

- No call may connect to or modify the live Resolve session during implementation or offline tests.
- `CAP_COLORIST` defaults to `false` and status `PENDING`.
- No public tool accepts an arbitrary file path, CDL map, node index, or generic Resolve operation.
- All Resolve writes require an approved fingerprint and exact context revalidation.
- Existing grades and versions are never overwritten or deleted.

## Review Focus

- A clip ID disappears or resolves twice between prepare and apply: fail before any write.
- Version creation succeeds for one clip and a later operation fails: restore previous active versions and report partial evidence.
- Numeric inputs include bool, NaN, infinity, or boundary values: reject malformed values and accept documented limits.
- A plan or approval from another workstation/project/timeline is replayed: reject as stale or foreign.
- A DRX registry entry escapes the configured asset root: reject during configuration or prepare.

---

### Task 1: Pure correction model and preset registry

**Files:**
- Create: `bridge/colorist_model.py`
- Create: `colorist_presets.json`
- Test: `tests/test_colorist_model.py`

**Interfaces:**
- Produces: `build_cdl(adjustments, preset) -> dict[str, str]`, `load_colorist_presets(path) -> dict`, `plan_fingerprint(payload) -> str`.

- [ ] Write failing tests for exact bounded mappings, invalid numbers, registry schema, unknown presets, and fingerprint stability.
- [ ] Run the focused tests and verify the failures are caused by missing production code.
- [ ] Implement the minimal pure model and registry loader.
- [ ] Run focused tests green.

### Task 2: Fingerprint-bound plan lifecycle

**Files:**
- Create: `bridge/colorist_jobs.py`
- Test: `tests/test_colorist_jobs.py`

**Interfaces:**
- Consumes: `plan_fingerprint` from Task 1.
- Produces: `ColoristJob`, `ColoristJobStore`, `new_colorist_job`, `approve_colorist_job`, `record_colorist_apply`, `record_colorist_review`.

- [ ] Write failing tests for prepare/approve/apply/review, stale revisions, foreign workstation, wrong fingerprint, rejection, and corrupt state.
- [ ] Run focused tests red.
- [ ] Implement the atomic workstation-local store and transitions.
- [ ] Run focused tests green.

### Task 3: Narrow Resolve adapter

**Files:**
- Create: `bridge/colorist_resolve.py`
- Test: `tests/test_colorist_resolve.py`

**Interfaces:**
- Consumes: approved `ColoristJob` and CDL from Tasks 1-2.
- Produces: `inspect_colorist_context`, `apply_colorist_job`, `preview_colorist_version`, `restore_colorist_preview`.

- [ ] Write failing fake-Resolve tests for clip resolution, context binding, collision-free local versions, CDL payload, optional DRX, reference copying, partial failure restoration, and preview restoration.
- [ ] Run focused tests red.
- [ ] Implement the adapter using only documented Resolve 21 methods.
- [ ] Run focused tests green.

### Task 4: Configuration, capability, and MCP surface

**Files:**
- Modify: `bridge/config.py`
- Modify: `bridge/feature_flags.py`
- Modify: `bridge/tool_catalog.py`
- Modify: `bridge/server.py`
- Modify: `creative_config.example.json`
- Test: `tests/test_colorist_tools.py`
- Test: `tests/test_feature_flags.py`
- Test: `tests/test_safety.py`

**Interfaces:**
- Consumes: workflow functions from Tasks 1-3.
- Produces: closed tools `inspect_colorist_context`, `prepare_colorist_plan`, `inspect_colorist_plan`, `approve_colorist_plan`, `apply_colorist_plan`, `preview_colorist_version`, `restore_colorist_preview`, `submit_colorist_review`.

- [ ] Write failing tests for disabled-by-default capability, actual API availability, exact tool signatures, annotations, no arbitrary paths, and guarded workflow calls.
- [ ] Run focused tests red.
- [ ] Wire configuration, capability reporting, catalog, and MCP wrappers.
- [ ] Run focused tests green.

### Task 5: Documentation and offline verification

**Files:**
- Modify: `docs/RESOLVE_STUDIO_CAPABILITIES.md`
- Create: `docs/23_COLORIST_MODULE.md`
- Modify: `CURRENT_STATE.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: verified behavior and exact test evidence from Tasks 1-4.
- Produces: operator/developer documentation and native gate checklist.

- [ ] Document supported APIs, approximations, failure behavior, human review, installation boundary, and disposable-project native gate.
- [ ] Run all Colorist tests, then the complete bridge suite.
- [ ] Record the pre-existing environmental baseline failure separately from regressions.

