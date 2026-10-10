# ARPHÈ Vertical Social Assistant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the safe, resumable plan-and-action foundation for the `ARPHE_VERTICAL_SOCIAL` editing assistant.

**Architecture:** A machine-readable contract defines action vocabulary, phases, capabilities and runtime rules. A workstation-local plan store persists versioned, fingerprint-bound plans and action-level state. Server tools expose only structured plan lifecycle operations and runtime status; no free-form Resolve command or unvalidated creative action is executed.

**Tech Stack:** Python 3.10+, FastMCP bridge, dataclasses, JSON registries and `unittest`.

**Spec:** `docs/superpowers/specs/2026-10-09-arphe-vertical-social-assistant-design.md`

## Global Constraints

- Keep `PC_PERSONALE` and `PC_SEGRETERIA` state, learning and rollout isolated.
- Default every newly introduced capability to `false`; no installer enables it.
- Retain the existing workflow registry as the format/render authority.
- Use only semantic, schema-validated action types; never expose arbitrary Resolve properties or code.
- Bind approval and execution eligibility to an exact plan fingerprint and version.
- Caption execution is prohibited before picture lock and remains unavailable in this slice.
- Any failure affects only the action concerned; verified earlier work must remain resumable.
- Normal operator output is one compact card; technical evidence stays separately inspectable.

## Review Focus

- Same `plan_id` with modified actions or target must invalidate approval via a different fingerprint; Task 2 pins this.
- A caption action before picture lock or without a validated capability must remain blocked, never queued for Resolve; Task 1 and Task 3 pin this.
- A retry of a previously applied action must be idempotent and not create a second transition; Task 2 pins this.
- A plan from another workstation must be rejected before status or mutation is returned; Task 2 pins this.
- An unknown action, invalid dependency or illegal phase transition must be rejected without partially writing the plan; Task 1 and Task 2 pin this.

---

## File structure

- `vertical_social_contract.json`: versioned, distributable contract for the workflow.
- `bridge/vertical_social_contract.py`: strict contract loading and action/phase validation.
- `bridge/vertical_social_jobs.py`: workstation-local plan persistence, fingerprints and legal state transitions.
- `bridge/vertical_social_workflow.py`: compact-card projection, plan preparation, approval, phase progression and safe resume decisions.
- `bridge/config.py`: adds the closed-by-default Vertical Social capability and state locations.
- `bridge/server.py`: narrow MCP tools delegating to the workflow module and reporting contract/status.
- `creative_config.example.json` and `install_on_segreteria.ps1`: distributable defaults and isolated local paths.
- `tests/test_vertical_social_contract.py`, `tests/test_vertical_social_jobs.py`, `tests/test_vertical_social_workflow.py`, `tests/test_vertical_social_tools.py`: behavior and server-surface tests.
- `docs/18_EDITORIAL_WORKFLOWS_AND_RENDER_DELIVERY.md`, `CURRENT_STATE.md`, `CHANGELOG.md`, `validation/vertical-social-ledger.json`: operator documentation and rollout evidence schema.

### Task 1: Vertical Social contract and capability registry

**Files:**
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/vertical_social_contract.json`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/vertical_social_contract.py`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_vertical_social_contract.py`

**Interfaces:**
- Produces: `VerticalSocialContract`, `VerticalSocialActionSpec`, `load_vertical_social_contract(path: Path) -> VerticalSocialContract`, `validate_action_request(contract, action: dict, picture_locked: bool) -> VerticalSocialActionSpec`.
- Consumed by: Tasks 2–4.

- [ ] **Step 1: Write failing contract tests**

Cover exact schema version, unique action IDs, phase ordering, unknown action rejection, dependency validation, and rejection of `CAPTIONS` before picture lock or when its capability is not `VALIDATED`.

- [ ] **Step 2: Run the new tests to verify failure**

Run: `python -m unittest tests.test_vertical_social_contract -v` from `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03`.

Expected: FAIL because the contract loader and validator do not exist.

- [ ] **Step 3: Add the strict JSON contract and loader**

Define actions `CUT`, `REFRAME`, `B_ROLL`, `GRAPHIC`, `CTA`, `MUSIC_DUCK`, `CAPTIONS` and `GENERATIVE_SHOT`, each with its permitted phase, required capability and initial availability. Make caption capability explicitly `PARTIAL` and non-executable. Reject unknown keys and invalid transitions.

- [ ] **Step 4: Run contract tests to verify pass**

Run: `python -m unittest tests.test_vertical_social_contract -v`.

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/vertical_social_contract.json scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/vertical_social_contract.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_vertical_social_contract.py
git commit -m "feat: add vertical social action contract"
```

### Task 2: Versioned plan store and action journal

**Files:**
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/vertical_social_jobs.py`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_vertical_social_jobs.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/config.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/creative_config.example.json`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/install_on_segreteria.ps1`

**Interfaces:**
- Consumes: `VerticalSocialContract` and validated action specs from Task 1.
- Produces: `VerticalSocialPlan`, `VerticalSocialPlanStore`, `new_vertical_social_plan(...)`, `plan_fingerprint(plan) -> str`, `transition_action(store, plan_id, action_id, expected_state, next_state, evidence) -> VerticalSocialPlan`.
- Consumed by: Tasks 3–4.

- [ ] **Step 1: Write failing plan-store tests**

Cover deterministic content fingerprints, approval invalidation after a material revision, workstation ownership enforcement, legal per-action transitions, blocked-action evidence, idempotent replay, and resume after one action is blocked while another is verified.

- [ ] **Step 2: Run the new tests to verify failure**

Run: `python -m unittest tests.test_vertical_social_jobs -v`.

Expected: FAIL because the plan store does not exist.

- [ ] **Step 3: Implement local plan persistence and journal**

Persist only metadata, action intent and non-sensitive evidence under new workstation-local config paths. Ensure atomic replacement, append-only journal records, state-owner checks and exact fingerprint binding. Add `CAP_VERTICAL_SOCIAL` to known/default flags as `false`; installers create isolated empty state but never switch it on.

- [ ] **Step 4: Run plan-store tests to verify pass**

Run: `python -m unittest tests.test_vertical_social_jobs -v`.

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/vertical_social_jobs.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_vertical_social_jobs.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/config.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/creative_config.example.json scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/install_on_segreteria.ps1
git commit -m "feat: persist vertical social editing plans"
```

### Task 3: Plan lifecycle, compact review card and safe resume

**Files:**
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/vertical_social_workflow.py`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_vertical_social_workflow.py`

**Interfaces:**
- Consumes: Task 1 contract and Task 2 plan store.
- Produces: `prepare_vertical_social_plan(...)`, `approve_vertical_social_plan(...)`, `mark_vertical_social_picture_lock(...)`, `advance_vertical_social_action(...)`, `inspect_vertical_social_plan(...)`, `compact_vertical_social_card(plan) -> dict[str, object]`.
- Consumed by: Task 4.

- [ ] **Step 1: Write failing workflow tests**

Cover one-card projection, explicit approval against matching fingerprint, plan revision superseding an earlier approval, a local action failure yielding `BLOCKED` without changing a verified action, safe-resume selection, and caption phase denial until picture lock plus validated capability.

- [ ] **Step 2: Run the new tests to verify failure**

Run: `python -m unittest tests.test_vertical_social_workflow -v`.

Expected: FAIL because the lifecycle module does not exist.

- [ ] **Step 3: Implement the lifecycle without Resolve edits**

Prepare validates workflow ID, target metadata and actions; approval records the fingerprint; picture lock gates terminal actions; action progression records evidence through the store. Return compact normal cards and separate technical evidence. Do not add a Resolve write path in this task.

- [ ] **Step 4: Run workflow tests to verify pass**

Run: `python -m unittest tests.test_vertical_social_workflow -v`.

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/vertical_social_workflow.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_vertical_social_workflow.py
git commit -m "feat: add vertical social plan lifecycle"
```

### Task 4: Closed MCP surface and runtime discovery

**Files:**
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/server.py`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_vertical_social_tools.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_safety.py`

**Interfaces:**
- Consumes: Task 3 lifecycle API.
- Produces MCP tools: `inspect_vertical_social`, `prepare_vertical_social_plan`, `approve_vertical_social_plan`, `inspect_vertical_social_plan`, `mark_vertical_social_picture_lock`, `advance_vertical_social_action`.
- Consumed by: operators and later action executors.

- [ ] **Step 1: Write failing server-surface tests**

Cover tool registration, closed capability gate, no Resolve write for inspect/prepare/approve, explicit contract/workstation/project/timeline/FPS status, plan ownership enforcement and refusal to advance an unavailable action.

- [ ] **Step 2: Run the new tests to verify failure**

Run: `python -m unittest tests.test_vertical_social_tools tests.test_safety -v`.

Expected: FAIL because the tools do not exist.

- [ ] **Step 3: Add guarded MCP adapters**

Reuse existing runtime/config patterns. Status must surface the current workstation and existing project/timeline/FPS, then Vertical Social contract/capability status, active plan summary and next safe action. All mutations fail closed unless `CAP_VERTICAL_SOCIAL` is explicitly enabled; no adapter may directly invoke arbitrary Resolve methods.

- [ ] **Step 4: Run server-surface tests to verify pass**

Run: `python -m unittest tests.test_vertical_social_tools tests.test_safety -v`.

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/server.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_vertical_social_tools.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_safety.py
git commit -m "feat: expose guarded vertical social planning tools"
```

### Task 5: Operational documentation and rollout evidence

**Files:**
- Create: `validation/vertical-social-ledger.json`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_vertical_social_ledger.py`
- Modify: `docs/18_EDITORIAL_WORKFLOWS_AND_RENDER_DELIVERY.md`
- Modify: `CURRENT_STATE.md`
- Modify: `CHANGELOG.md`
- Modify: `INDEX.md`

**Interfaces:**
- Consumes: the final contract, lifecycle and tool names from Tasks 1–4.
- Produces: a validation ledger with independent PC_PERSONALE and PC_SEGRETERIA gates.

- [ ] **Step 1: Write a failing ledger/documentation validator test**

Add a test that rejects a ledger without separate workstation records, required automated checks, capability default state and a native Resolve gate placeholder.

- [ ] **Step 2: Run the validator test to verify failure**

Run: `python -m unittest tests.test_vertical_social_ledger -v`.

Expected: FAIL because the ledger/documentation artifacts do not exist.

- [ ] **Step 3: Document the operational contract and evidence schema**

Describe the compact-card interaction, picture-lock/caption ordering, no-free-form execution, partial-failure recovery, new state files and disabled-by-default rollout. Add the ledger with both workstations `PENDING`, no claims of native validation, and no customer content.

- [ ] **Step 4: Run targeted tests and static checks**

Run: `python -m unittest tests.test_vertical_social_contract tests.test_vertical_social_jobs tests.test_vertical_social_workflow tests.test_vertical_social_tools tests.test_vertical_social_ledger tests.test_safety -v` and `python -m compileall bridge`.

Expected: PASS; no native Resolve capability is enabled.

- [ ] **Step 5: Commit**

```bash
git add validation/vertical-social-ledger.json scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_vertical_social_ledger.py docs/18_EDITORIAL_WORKFLOWS_AND_RENDER_DELIVERY.md CURRENT_STATE.md CHANGELOG.md INDEX.md
git commit -m "docs: record vertical social assistant rollout"
```

### Task 6: Full regression, installation integrity and native rollout gate

**Files:**
- Modify only if verification reveals a defect in Tasks 1–5.
- Update: `validation/vertical-social-ledger.json` only with observed evidence.

**Interfaces:**
- Consumes: all prior tasks.
- Produces: a verified implementation branch and an evidence-backed decision whether to enable a single workstation gate.

- [ ] **Step 1: Run the complete automated suite and distributable integrity checks**

Run the package suite from `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03`, then compile all bridge modules and compare the installer’s expected package files. Record exact results in the ledger.

- [ ] **Step 2: Run an isolated PC_PERSONALE native gate only after automated checks pass**

Keep `CAP_VERTICAL_SOCIAL=false` until the test project is ready. Validate status/read-only discovery, prepare/approve/resume behaviour, target/workstation isolation and restoration. Do not attempt unimplemented creative actions or caption execution.

- [ ] **Step 3: Record observed outcome and keep PC_SEGRETERIA pending**

Store only non-sensitive evidence, flip no production capability automatically, and document any blocker precisely.

- [ ] **Step 4: Commit verified evidence**

```bash
git add validation/vertical-social-ledger.json CURRENT_STATE.md CHANGELOG.md
git commit -m "test: validate vertical social planning gate"
```

## Plan self-review

- **Spec coverage:** Task 1 covers the runtime contract and action vocabulary; Task 2 handles fingerprinted, workstation-local state; Task 3 covers phases, compact interaction and recovery; Task 4 exposes the controlled runtime status and tools; Tasks 5–6 cover documentation, tests and separate rollout.
- **Step scan:** Every task has a missing-behavior test, an observed failing run, a minimal implementation, a passing run and a narrow commit.
- **Type consistency:** Contract validation feeds the plan store; the store feeds lifecycle functions; lifecycle functions are the only server-tool backend.
- **Review focus:** Each listed failure mode is pinned to Tasks 1–4.
- **Proportion:** The plan deliberately stops before Resolve execution modules. CUT, B-roll, reframe and branded caption execution each need their own future validated slice.

## Execution handoff

Execute natively in this existing isolated worktree. The tasks share strict storage and lifecycle interfaces, so sequential implementation is safer and less expensive than parallel changes. After implementation, request one whole-branch review before any native capability rollout.
