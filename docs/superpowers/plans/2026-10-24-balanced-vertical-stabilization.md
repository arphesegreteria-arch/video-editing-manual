# Balanced Vertical Stabilization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add generic, explicit position keyframes to the existing ARPHE `REFRAME` action and validate them on the `peeling` test without altering or saving the source project.

**Architecture:** Extend the existing reframe validator and Fusion adapter rather than creating a timeline-specific command. The bridge accepts caller-supplied `center_keys`, converts absolute action frames to clip-local frames, stores them in Resolve-owned splines, and reads every key back before recording verified evidence.

**Tech Stack:** Python 3, DaVinci Resolve/Fusion scripting API, `unittest`, PowerShell deployment scripts.

**Spec:** `docs/superpowers/specs/2026-10-24-balanced-vertical-stabilization-design.md`

## Global Constraints

- Operate only through ARPHE Resolve Personale on `PC_PERSONALE`.
- Keep source media, existing timelines and existing projects unchanged.
- Use only explicit measured frames and coordinates; no automatic subject or horizon recognition.
- Preserve one linked audio copy and all 732 source frames.
- Start the live trial at zoom `1.08`; increase only after visual evidence of exposed borders.
- Create a new provisional timeline and do not save the Resolve project before human review.
- Do not access or update `PC_SEGRETERIA`.

## Review Focus

- Reject Boolean, NaN, infinite and out-of-safe-range center coordinates before any Resolve mutation; Task 1 tests each class.
- Reject missing endpoint anchors, duplicate frames and unordered frames; Task 1 tests each condition.
- Normalize absolute action frames against a non-zero Resolve timeline origin without shifting key timing; Task 1 and Task 2 cover this.
- Treat silent Fusion key rejection or mismatched read-back as failure; Task 2 tests mismatched point values.
- Preserve legacy static-center actions and existing rotation-only actions unchanged; Task 1 and Task 2 include compatibility tests.

---

### Task 1: Validate and normalize explicit center keyframes

**Files:**
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/vertical_social_reframe.py`
- Test: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_vertical_social_reframe.py`

**Interfaces:**
- Consumes: existing `validate_reframe_action(action: dict[str, Any], total_frames: int) -> dict[str, Any]` and `reframe_transform_plan(action: dict[str, Any], output_width: int, output_height: int) -> dict[str, Any]`.
- Produces: `_center_keys(action: dict[str, Any], start: int, end: int) -> list[tuple[int, float, float]]`; validated output key `center_keys`; transform-plan key `center_keys` with clip-local frames.

- [ ] **Step 1: Write failing validation tests**

Add tests named `test_reframe_normalizes_explicit_center_keys_to_clip_local_frames`, `test_reframe_rejects_center_keys_without_both_range_anchors`, `test_reframe_rejects_unsafe_center_key_values`, and `test_static_center_reframe_remains_compatible`. Assert first/last anchoring at frames `0` and `731`, local-frame normalization from a non-zero action range, strict ordering, finite numeric `x/y`, and safe normalized bounds `0.1..0.9`.

- [ ] **Step 2: Run the focused tests and confirm RED**

Run: `C:\ARPHE\MCP\runtimes\PC_PERSONALE\venv\Scripts\python.exe -m unittest tests.test_vertical_social_reframe -v`

Expected: the new tests fail because `center_keys` is not validated or returned.

- [ ] **Step 3: Implement `_center_keys` and expose normalized keys**

Implement `_center_keys(action, start, end)` in `vertical_social_reframe.py`. Accept an omitted field as legacy static behavior; otherwise require at least two ordered entries, exact range endpoints, integer non-Boolean frames, finite non-Boolean numeric coordinates inside `0.1..0.9`, and return `(frame, x, y)` tuples. Add the validated list to `validate_reframe_action` and clip-local dictionaries to `reframe_transform_plan`.

- [ ] **Step 4: Run the focused tests and confirm GREEN**

Run the Task 1 command.

Expected: all `test_vertical_social_reframe` tests pass.

- [ ] **Step 5: Commit Task 1**

Commit message: `feat: validate explicit reframe center keys`

### Task 2: Apply Resolve-owned position splines with exact read-back

**Files:**
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/vertical_social_reframe.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/vertical_social_apply.py`
- Test: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_vertical_social_reframe.py`
- Test: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_vertical_social_apply.py`

**Interfaces:**
- Consumes: Task 1 `center_keys` dictionaries with clip-local frames.
- Produces: `apply_transform_parameters(tool: object, plan: dict[str, Any], comp: object | None = None) -> bool` writes and verifies a Resolve-owned Center spline; action evidence returns absolute `center_keys` exactly as approved.

- [ ] **Step 1: Write failing Fusion and executor tests**

Add `test_transform_applies_and_reads_back_center_spline`, `test_transform_rejects_silent_center_key_mismatch`, `test_reframe_evidence_preserves_absolute_center_keys`, and a rotation-only compatibility assertion. Fake spline storage must preserve point pairs at exact integer frames.

- [ ] **Step 2: Run focused tests and confirm RED**

Run: `C:\ARPHE\MCP\runtimes\PC_PERSONALE\venv\Scripts\python.exe -m unittest tests.test_vertical_social_reframe tests.test_vertical_social_apply -v`

Expected: the new spline/read-back and evidence tests fail.

- [ ] **Step 3: Implement Center spline application and evidence**

When `center_keys` is non-empty, replace the static Center input with a Resolve-owned spline, assign every local-frame point, and compare every returned `x/y` value within `1e-6`. Retain the current static `SetInput("Center", ...)` path when no center keys are supplied. Return the approved absolute list in `apply_reframe_action` evidence.

- [ ] **Step 4: Run focused and full suites**

Run the Task 2 focused command, then:

`C:\ARPHE\MCP\runtimes\PC_PERSONALE\venv\Scripts\python.exe -m unittest discover -s tests -v`

from `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03`, followed by the bundled Python full suite from `scripts/windows_bridge`.

Expected: 0 failures; existing static and rotation-only behavior remains green.

- [ ] **Step 5: Commit Task 2**

Commit message: `feat: apply verified position keyframes in Resolve`

### Task 3: Deploy only to PC_PERSONALE and validate the balanced live trial

**Files:**
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/README.md`
- Test: live Resolve bridge read-back and diagnostic captures; no source-file modification.

**Interfaces:**
- Consumes: generic `center_keys`, existing `rotation_keys`, zoom and provisional-plan workflow.
- Produces: a new unsaved provisional timeline with verified key evidence and a documented rollout note; no `PC_SEGRETERIA` mutation.

- [ ] **Step 1: Document the generic center-key contract**

Document required endpoint anchors, safe normalized bounds, Resolve-owned read-back and the rule that measurements are supplied explicitly by the caller.

- [ ] **Step 2: Install with the canonical installer on PC_PERSONALE only**

Create a new local backup, run the profile-specific installer with `WorkstationId PC_PERSONALE`, preserve the existing config and feature flags, restart the personal runtime, and verify `ping.workstation_id == "PC_PERSONALE"`.

- [ ] **Step 3: Calibrate Fusion Center direction with a minimal provisional trial**

Create a disposable generic plan using the existing rotation keys, zoom `1.08`, and a small equal endpoint Center-Y offset. Capture frames `0` and `731`; compare measured ceiling `CenterY` against the prior timeline to establish the sign and pixel-to-normalized response. Do not save or reuse the calibration provisional as the final result.

- [ ] **Step 4: Build the balanced explicit center-key list**

Use the 25 already measured one-second checkpoints. Target the ceiling near `48 px` with correction gain `0.75`, preserving 25% of natural vertical movement. Convert measured pixel corrections using the calibration result; keep `x=0.5`, retain the approved rotation keys, anchor frames `0` and `731`, and use zoom `1.08`.

- [ ] **Step 5: Create and apply a fresh final provisional plan**

Use a generic `REFRAME` action with no timeline-specific bridge code. Require action state `VERIFIED` and evidence that exactly matches all submitted rotation keys, center keys, range `[0,732]`, zoom and provisional timeline name.

- [ ] **Step 6: Verify Resolve structure and visuals**

Read back exactly one 732-frame V1 clip and one 732-frame A1 clip with the same source and no edit points. Capture all 25 one-second checkpoints plus frame `731`; measure angle and ceiling height, and visually inspect edges, deformation and subject framing.

Acceptance: no exposed image edge; no audio duplication; rotation remains within the current verified envelope; vertical range is materially below the current `40.69 px`; no source or prior timeline changes.

- [ ] **Step 7: Leave the project unsaved for human review**

Keep the new provisional current in Resolve, report exact measurements and remaining limitations, and do not call project save or render.

- [ ] **Step 8: Commit documentation and update the existing draft PR**

Commit message: `docs: record balanced reframe verification`

Push to `arphe/adv-caption-audio-20261022` and update draft PR #20 with fresh test and live read-back evidence.
