# Workflow Control Plane Implementation Plan

> For agentic workers: REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Add one workstation-scoped control plane that coordinates existing Creative Bridge workflows as approval-bound, resumable jobs with a compact operator-facing status card.

**Architecture:** bridge/control_plane.py owns only the common envelope and atomic local registry. bridge/workflow_control.py adapts existing specialized job records; it never migrates their registries nor executes arbitrary commands. server.py exposes a small card-oriented API and revalidates its explicit target under the Resolve lock before delegating a write.

**Tech Stack:** Python 3.12/3.13-compatible stdlib, dataclasses, JSON/SHA-256, FastMCP, unittest and fake Resolve API objects.

**Spec:** docs/superpowers/specs/2026-10-10-workflow-control-plane-design.md

## Global Constraints

- Keep PC_PERSONALE and PC_SEGRETERIA flags, state, evidence and registries separate.
- Add CAP_WORKFLOW_CONTROL_PLANE, default false; inspection remains read-only while disabled.
- Never migrate/delete/overwrite specialized workflow registries.
- Writes require the persisted approved-plan fingerprint and target revalidation under RESOLVE_ACCESS_LOCK.
- No generic natural-language executor, generic auto-render/publish, or cross-workstation recovery.
- Use a profile's declared venv interpreter, never a generic python or py PATH alias.

## Review Focus

- Late current-project/timeline change blocks before native write: Task 4 fake-Resolve test.
- Duplicate advance returns recorded evidence, never creates a second native output: Task 3.
- Foreign-workstation native reference is rejected: Task 1.
- Offline snapshot is useful and makes no write: Task 4.
- Disabled feature gate rejects before runtime/Resolve is touched: Task 4.

---

## File structure

| Path | Responsibility |
| --- | --- |
| bridge/control_plane.py | Envelope, approval digest, transitions, atomic per-workstation store. |
| bridge/workflow_control.py | Native adapters, state mapping, cards, target comparison and advance dispatch. |
| bridge/config.py, bridge/feature_flags.py | Default-off capability and profile-local registry path. |
| bridge/server.py, bridge/tool_catalog.py | Read-only snapshot and six narrow MCP tools. |
| tests/test_control_plane.py | Pure registry, state and fingerprint contract. |
| tests/test_workflow_control.py | Adapter mapping, reconciliation and idempotency. |
| tests/test_workflow_control_tools.py | Server feature gates and fake-Resolve target checks. |
| docs/21_WORKFLOW_CONTROL_PLANE.md | Secretary/technical guide and rollout evidence template. |

### Task 1: Control-plane model, store and default-off configuration

**Files:**
- Create: scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/control_plane.py
- Create: scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_control_plane.py
- Modify: scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/config.py
- Modify: scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/feature_flags.py
- Modify: scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_feature_flags.py
- Modify: scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/creative_config.example.json

**Interfaces:**
- Produces frozen WorkflowJob, WorkflowJobStore, workflow_job_fingerprint(job), approve_workflow_job(store, workflow_job_id, plan_fingerprint, operator_role), and transition_workflow_job(store, workflow_job_id, expected_revision, next_state, evidence).
- WorkflowJob fields: workflow_job_id, workstation_id, workflow_family, native_reference, target, plan_fingerprint, approved_plan_fingerprint, state, revision, resume_state, evidence, created_at, updated_at.
- Adds CAP_WORKFLOW_CONTROL_PLANE and workflow_control_jobs_path.

- [ ] **Step 1: Write RED contract tests**
  - same immutable job creates idempotently; same ID with a different target raises ValidationError containing contenuto differente;
  - approval with 64 zeroes raises fingerprint error; foreign workstation store cannot load it;
  - corrupt registry raises ValidationError and does not replace the file.

- [ ] **Step 2: Verify RED**
  - Run: the explicit Personal venv Python, module unittest tests.test_control_plane -v.
  - Expected: FAIL because bridge.control_plane is absent.

- [ ] **Step 3: Implement the contract**
  - Allow only PODCAST_REELS, VERTICAL_SOCIAL, CARABELLESE_CLEANUP, BRANDED_LONGFORM.
  - Use sorted canonical JSON and SHA-256.
  - Persist schema/workstation_id/jobs through temporary file plus os.replace; corrupt data fails closed.
  - Implement the common state graph from the spec; BLOCKED, STALE and FAILED_RECOVERABLE require a valid active resume state.

- [ ] **Step 4: Add profile-owned configuration/reporting**
  - Set the new capability false by default; add a sibling state path beside editorial registries.
  - Report implemented/technically available only when the module and read-only context are available.
  - Preserve profiles omitting the new JSON fields.

- [ ] **Step 5: Verify GREEN**
  - Run the explicit Personal venv Python against tests.test_control_plane and tests.test_feature_flags.
  - Expected: PASS without real Resolve or user-profile state writes.

- [ ] **Step 6: Commit**
  - Stage model, config, flag, example config and unit tests.
  - Commit message: feat: add workflow control-plane registry.

### Task 2: Native adapters and normalized job cards

**Files:**
- Create: scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/workflow_control.py
- Create: scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_workflow_control.py
- Modify: scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/control_plane.py

**Interfaces:**
- Consumes Task 1 plus EditorialJob, CarabelleseJob, VerticalSocialPlan, BrandedLongformJob.
- Produces load_native_binding(config, workflow_family, native_reference), prepare_workflow_envelope(config, workflow_family, native_reference, target), workflow_job_card(job, native), reconcile_workflow_job(store, job, native), next_safe_action(workflow_family, native_state, approved).

- [ ] **Step 1: Write RED adapter tests**
  - Editorial MARKED maps to REVIEW_READY and SUBMIT_REVIEW.
  - A foreign native record or changed target raises a workstation/target ValidationError.
  - A workflow without verified delivery reports NONE rather than a fabricated delivery action.

- [ ] **Step 2: Verify RED**
  - Run the explicit Personal venv Python against tests.test_workflow_control -v.
  - Expected: FAIL because bridge.workflow_control is absent.

- [ ] **Step 3: Implement read-only mapping**
  - Use only four exact public family names.
  - Load native records read-only; require same workstation and use their authoritative identifiers/fingerprints.
  - Centralize native-to-common state mapping and return exactly one safe action or NONE.

- [ ] **Step 4: Cover reconciliation**
  - Test a native VERIFIED result observed after interruption: envelope reconciliation advances without a native write.
  - Test changed native fingerprint sets STALE while preserving earlier evidence.

- [ ] **Step 5: Verify GREEN**
  - Run the explicit Personal venv Python against tests.test_workflow_control, test_editorial_jobs, test_carabellese_jobs, test_vertical_social_jobs and test_branded_longform_jobs.

- [ ] **Step 6: Commit**
  - Stage adapter, model amendment and tests.
  - Commit message: feat: adapt native workflows to control-plane jobs.

### Task 3: Approval-bound safe advance

**Files:**
- Modify: scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/workflow_control.py
- Modify: scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/control_plane.py
- Modify: scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_workflow_control.py

**Interfaces:**
- Produces advance_workflow_job(config, resolve, manager, project, timeline, store, workflow_job_id, approved_plan_fingerprint) returning a dict with workflow_job_id, normalized state, next_safe_action, native reference and redacted evidence.

- [ ] **Step 1: Write RED advance tests**
  - advance without persisted exact approval raises an approval error and fake delegate is never called;
  - calling advance twice after success returns the same recorded evidence and fake delegate call count remains one.

- [ ] **Step 2: Verify RED**
  - Run the explicit Personal venv Python against tests.test_workflow_control -v.

- [ ] **Step 3: Implement narrow dispatch**
  - Persist EXECUTING with optimistic revision before delegation.
  - Dispatch only the adapter-declared next action to existing typed functions, never a user-provided tool name.
  - Re-read native evidence and persist normalized state.
  - Native errors become FAILED_RECOVERABLE only where evidence proves safe resume; otherwise BLOCKED with a redacted error code.

- [ ] **Step 4: Cover interrupted native success**
  - For a Podcast and Carabellese fake, persist native success before envelope save.
  - Assert the next inspection reconciles it and no second native call runs.

- [ ] **Step 5: Verify GREEN**
  - Run explicit Personal venv Python for test_workflow_control, test_editorial_cut_workflow, test_carabellese_apply, test_vertical_social_workflow and test_branded_longform_workflow.

- [ ] **Step 6: Commit**
  - Stage adapter/model/tests.
  - Commit message: feat: require approval-bound workflow advancement.

### Task 4: Status card, target revalidation and public MCP tools

**Files:**
- Modify: scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/server.py
- Modify: scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/tool_catalog.py
- Create: scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_workflow_control_tools.py
- Modify: scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_entrypoint.py

**Interfaces:**
- Produces inspect_workstation_control_plane(), prepare_workflow_job(...), inspect_workflow_job(workflow_job_id), approve_workflow_job(...), advance_workflow_job(...), approve_workflow_delivery(...).
- Snapshot fields: bridge/workstation/Resolve version/current project/current timeline/resolution/edit FPS/playback FPS/capability report/active job cards.

- [ ] **Step 1: Write RED public-surface tests**
  - offline snapshot returns workstation identity, connected false, and no mutation;
  - mismatched current project/timeline makes advance fail under the lock and fake delegate call count stays zero;
  - disabled flag makes prepare/approve/advance fail before server runtime is touched.

- [ ] **Step 2: Verify RED**
  - Run the explicit Personal venv Python against tests.test_workflow_control_tools -v.

- [ ] **Step 3: Implement snapshot**
  - Inside RESOLVE_ACCESS_LOCK combine current runtime/capability/context.
  - Read timelineFrameRate and timelinePlaybackFrameRate separately; return null when unavailable and never set either.
  - Offline output still includes local runtime/workstation identity and connection block.

- [ ] **Step 4: Implement gates and exact target revalidation**
  - Prepare/approve/advance/delivery reject before _runtime when disabled.
  - Advance acquires RESOLVE_ACCESS_LOCK then compares current project/timeline identity and available fingerprints to the stored target before Task 3 delegate.
  - Add exactly six names to EXPOSED_TOOL_NAMES.
  - Delivery approval returns not_available unless an adapter exposes an existing verified delivery fingerprint.

- [ ] **Step 5: Verify GREEN**
  - Run explicit Personal venv Python for test_workflow_control_tools, test_feature_flags, test_entrypoint, test_editorial_selection_tools, test_carabellese_tools, test_vertical_social_tools and test_branded_longform_tools.

- [ ] **Step 6: Commit**
  - Stage server/catalog/tests.
  - Commit message: feat: expose guarded workflow control plane.

### Task 5: Documentation, profiles and honest rollout record

**Files:**
- Create: docs/21_WORKFLOW_CONTROL_PLANE.md
- Modify: scripts/windows_bridge/profiles/pc_personale.example.json
- Modify: scripts/windows_bridge/profiles/pc_segreteria.example.json
- Modify: scripts/windows_bridge/tests/test_profile_config.py
- Modify: CURRENT_STATE.md, CHANGELOG.md, EXPERIMENT_LOG.md

**Interfaces:**
- Documents compact secretary cards, recovery prompts and technical fields.
- Both profile examples keep new flag false and distinct local state paths.

- [ ] **Step 1: Write RED profile test**
  - normalized Personal and Segreteria examples retain CAP_WORKFLOW_CONTROL_PLANE false;
  - they do not share registry/config roots and carry no generic Python alias.

- [ ] **Step 2: Verify RED**
  - Run C:\Program Files\Python312\python.exe against scripts/windows_bridge/tests/test_profile_config.py -v.

- [ ] **Step 3: Document conservative rollout**
  - Write the secretary and technical recovery guides.
  - Record code/test status but mark both native gates PENDING until executed.
  - Explicitly state this code change does not touch the open Segreteria project, enable a flag, change Python or alter tunnels.

- [ ] **Step 4: Run full suites with explicit interpreters**
  - Personal venv: discover scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests.
  - Python312: discover scripts/windows_bridge/tests.
  - If an explicit executable is absent here, record the exact environmental limitation; do not install Python or alter a profile.

- [ ] **Step 5: Personal native gate only with explicit live authorization**
  - Use one small owned non-production target.
  - Prove snapshot, approval digest, wrong-target block, success, interruption/reconcile/resume, context restore and cleanup.
  - Do not execute on PC_SEGRETERIA or enable its flag.

- [ ] **Step 6: Commit**
  - Stage docs, profiles, profile test and status records.
  - Commit message: docs: record workflow control-plane rollout.

## Final verification and handoff

- [ ] Run git diff origin/main...HEAD --check and inspect a clean git status --short.
- [ ] Run both explicit-interpreter suites; do not substitute PATH aliases.
- [ ] Confirm EXPOSED_TOOL_NAMES contains exactly the six new control-plane tools.
- [ ] Check status docs contain no claim that PC_SEGRETERIA was installed, enabled or natively validated.
- [ ] Request code review before a PR. Do not merge or deploy without explicit user authorization.

