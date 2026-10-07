# Motion and Longform Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Make entry/exit animations semantically correct and deterministic, and reject longform intervals that collapse to no frames.

**Architecture:** Motion planning creates independent deterministic channel keys. The animation writer merges a new phase with existing keys instead of replacing a prior phase. Longform validation checks rounded frame intervals before Resolve receives a plan.

**Tech Stack:** Python, Resolve/Fusion API fakes, pytest/unittest.

**Spec:** docs/superpowers/specs/2026-10-07-brand-content-state-motion-workstation-design.md

## Global Constraints

- Do not modify render/profile or cleanup semantics.
- Motion tests prove values and frame ranges without live Resolve.
- A live Resolve check is a separately logged workstation gate.
- Preserve public tool names and existing supported presets.

## Review Focus

- An exit at the composition boundary ends opacity at zero at its final frame.
- Entry followed by exit keeps both key ranges.
- ease_out midpoint differs numerically from linear midpoint.
- A legal one-frame clip remains valid; only zero/negative rounded spans fail.
- Unsupported fractional FPS retains current rejection behavior.

---

## File Structure

- scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/motion_presets.py: deterministic phase key generation.
- scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/creative_tools.py: apply/merge Fusion keys.
- scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/longform_tools.py: rounded-frame validation.
- scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_safety.py: fake Fusion motion regression checks.
- scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_longform_tools.py: interval regressions.
- validation/validation-ledger.json: later manual evidence; no PASS before observation.

### Task 1: Specify and test motion channel semantics

**Files:**
- Modify: scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_safety.py
- Modify: scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/motion_presets.py
- Modify: scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/creative_tools.py

**Interfaces:**
- Produces exit_motion_plan(preset, start_frame, duration_frames, direction, easing, settle) -> dict.
- Changes _animate(comp, record, plan, phase: Literal["entry", "exit"]) -> bool to merge per channel.

- [ ] **Step 1: Write failing exit, preservation and easing tests**

~~~python
def test_exit_starts_visible_and_ends_transparent_offscreen():
    keys = exit_motion_plan("ARPHE_SOFT_DROP", 82, 18, direction="right", easing="linear")
    assert keys[0]["opacity"] == 1.0
    assert keys[-1]["opacity"] == 0.0
    assert keys[-1]["x"] > 0.0

def test_exit_keeps_existing_entry_keys():
    apply_entry_then_exit(fake_comp)
    assert fake_comp.frames_for("Center") == {0, 18, 82, 100}

def test_ease_out_midpoint_differs_from_linear():
    assert midpoint("ease_out") != midpoint("linear")
~~~

- [ ] **Step 2: Run focused safety tests to verify they fail**

Run: py -3 -m pytest scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_safety.py -k "exit or easing or animate" -v

Expected: FAIL because reversed writing currently creates an entrance at the end and replaces splines.

- [ ] **Step 3: Implement phase-aware plans and channel-key merge**

Entry finishes at the resting state; exit begins at resting state and finishes offscreen/transparent. Preserve keys outside the new phase range. Generate deterministic intermediate samples for ease_out; linear remains affine.

- [ ] **Step 4: Run full motion safety tests**

Run: py -3 -m pytest scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_safety.py -v

Expected: PASS, including existing stack/preset behavior.

- [ ] **Step 5: Commit**

~~~bash
git add scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/motion_presets.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/creative_tools.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_safety.py
git commit -m "fix: preserve semantic entry and exit motion"
~~~

### Task 2: Reject zero-frame longform intervals

**Files:**
- Modify: scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_longform_tools.py
- Modify: scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/longform_tools.py

**Interfaces:**
- Maintains validate_plan(clips: list[dict[str, Any]], fps: float = 30.0).
- Raises ValidationError naming the clip when source_out_frame_exclusive <= source_in_frame.

- [ ] **Step 1: Write the failing rounded-frame regression test**

~~~python
def test_validate_plan_rejects_interval_that_rounds_to_zero_frames():
    with pytest.raises(ValidationError, match="zero frames"):
        validate_plan([{"clip_id": "ZERO", "start_second": 1.0, "end_second": 1.001}], 30.0)
~~~

- [ ] **Step 2: Run it to verify current behavior is wrong**

Run: py -3 -m pytest scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_longform_tools.py -k zero_frames -v

Expected: FAIL because the current validator returns duration_frames == 0.

- [ ] **Step 3: Check rounded frames before normalized output**

Raise ValidationError including clip_id, source times and rounded frames. Keep a one-frame interval valid.

- [ ] **Step 4: Run longform test module**

Run: py -3 -m pytest scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_longform_tools.py -v

Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/longform_tools.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_longform_tools.py
git commit -m "fix: reject zero-frame longform ranges"
~~~

### Task 3: Register a pending live motion gate

**Files:**
- Modify: validation/validation-ledger.json
- Modify: CHANGELOG.md

**Interfaces:**
- Consumes a human-observed Resolve frame capture and named workstation/profile.
- Produces a LOCAL_MANUAL or END_TO_END evidence record; no capture leaves result PENDING.

- [ ] **Step 1: Add pending gate record**

Name entry, exit, ease-out and entry-plus-exit observations, but set result PENDING and make no PASS claim.

- [ ] **Step 2: Run ledger validation**

Run: py -3 scripts/validate_validation_ledger.py --ledger validation/validation-ledger.json --current-state CURRENT_STATE.md

Expected: PASS; pending records require no invented live evidence.

- [ ] **Step 3: Commit**

~~~bash
git add validation/validation-ledger.json CHANGELOG.md
git commit -m "docs: add pending motion validation gate"
~~~

