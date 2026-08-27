# Resolve Studio Capability Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish, with repeatable tests, which DaVinci Resolve Studio operations ARPHE can drive reliably from external Python and document the supported automation surface.

**Architecture:** Build a small non-destructive audit harness that connects to a running Resolve Studio instance, executes one capability probe at a time against a disposable test project/timeline, records structured results, and never mutates production timelines. Keep long-form V4.3 work independent and running in parallel.

**Tech Stack:** Python 3, DaVinci Resolve Studio scripting API/Fusion scripting, JSON/Markdown test reports, existing repository conventions.

**Spec:** `docs/TRAINING_ROADMAP.md`

## Global Constraints

- Tests must run only against a disposable audit project/timeline.
- No capability is marked `SUPPORTED` from documentation alone; it must pass an execution probe.
- Results use exactly `SUPPORTED`, `PARTIAL`, or `MANUAL`.
- Failures must capture the operation, exception/error text, Resolve version, platform, and test timestamp.
- Existing long-form V4.3 files remain untouched unless a finding directly requires a documented compatibility note.

---

### Task 1: External connection and environment report

**Files:**
- Create: `scripts/studio_audit/connectivity_probe.py`
- Create: `scripts/studio_audit/audit_result.py`
- Create: `tests/studio_audit/test_audit_result.py`
- Create: `docs/RESOLVE_STUDIO_CAPABILITIES.md`

**Interfaces:**
- Produces: `AuditResult(capability: str, status: str, detail: str, metadata: dict)` and a CLI probe that exits `0` on successful Resolve connection, non-zero otherwise.

- [ ] **Step 1: Write a unit test for allowed status values and report serialization.**
- [ ] **Step 2: Run the test and verify it fails before implementation.**
- [ ] **Step 3: Implement the minimal `AuditResult` model and JSON serialization.**
- [ ] **Step 4: Implement a connectivity probe that imports the Resolve scripting module, connects to the running application, and reports Resolve version/project context without editing anything.**
- [ ] **Step 5: Run unit tests and the live connectivity probe against Resolve Studio.**
- [ ] **Step 6: Record the first capability row in `docs/RESOLVE_STUDIO_CAPABILITIES.md`.**
- [ ] **Step 7: Commit as `test: add Resolve Studio connectivity audit`.**

---

### Task 2: Project, Media Pool and timeline probes

**Files:**
- Create: `scripts/studio_audit/project_timeline_probe.py`
- Create: `tests/studio_audit/test_probe_guards.py`
- Modify: `docs/RESOLVE_STUDIO_CAPABILITIES.md`

**Interfaces:**
- Consumes: `AuditResult` from Task 1.
- Produces: capability results for project inspection, Media Pool import, timeline creation, clip placement and safe cleanup.

- [ ] **Step 1: Add tests that refuse to run destructive probes unless the project/timeline name matches the audit-only naming convention.**
- [ ] **Step 2: Run tests and verify the guard fails before implementation.**
- [ ] **Step 3: Implement the audit-only guard.**
- [ ] **Step 4: Add live probes for project inspection, media import, timeline creation and clip placement using disposable media.**
- [ ] **Step 5: Execute each probe independently and record `SUPPORTED`, `PARTIAL`, or `MANUAL`.**
- [ ] **Step 6: Update the capability matrix with exact observations and limitations.**
- [ ] **Step 7: Commit as `test: audit Resolve project and timeline controls`.**

---

### Task 3: Edit primitives and Fusion probes

**Files:**
- Create: `scripts/studio_audit/edit_fusion_probe.py`
- Modify: `docs/RESOLVE_STUDIO_CAPABILITIES.md`

**Interfaces:**
- Consumes: disposable timeline from the audit harness.
- Produces: results for cut/trim behavior, clip transforms, Fusion composition creation/readback and parameter mutation.

- [ ] **Step 1: Add a probe that changes a harmless clip transform and verifies the value can be read back.**
- [ ] **Step 2: Add a cut/trim probe using only the disposable timeline.**
- [ ] **Step 3: Add a Fusion probe that creates or inspects a composition, changes a known parameter and verifies readback.**
- [ ] **Step 4: Run all probes separately so one failure cannot hide the others.**
- [ ] **Step 5: Record each result and any API limitations in the capability matrix.**
- [ ] **Step 6: Commit as `test: audit Resolve edit and Fusion controls`.**

---

### Task 4: Tracking automation probe

**Files:**
- Create: `scripts/studio_audit/tracking_probe.py`
- Modify: `docs/RESOLVE_STUDIO_CAPABILITIES.md`

**Interfaces:**
- Produces: separate results for tracker creation/configuration, starting tracking programmatically, reading tracking data, and applying tracked motion.

- [ ] **Step 1: Use a short controlled talking-head clip in the disposable audit project.**
- [ ] **Step 2: Probe tracker creation/configuration independently from execution.**
- [ ] **Step 3: Probe whether Track Forward can be initiated programmatically in the installed Studio version.**
- [ ] **Step 4: Verify whether tracking data can be read after execution.**
- [ ] **Step 5: Mark each sub-capability independently; do not collapse a partially automated tracker into one `SUPPORTED` row.**
- [ ] **Step 6: Document whether the current manual Track Forward workaround can be retired.**
- [ ] **Step 7: Commit as `test: audit Resolve Studio tracking automation`.**

---

### Task 5: Captions, audio and render probes

**Files:**
- Create: `scripts/studio_audit/output_probe.py`
- Modify: `docs/RESOLVE_STUDIO_CAPABILITIES.md`

**Interfaces:**
- Produces: results for subtitle/caption creation and styling access, audio level automation relevant to music/ducking, render settings, render queue and export start/status.

- [ ] **Step 1: Probe subtitle/caption creation separately from styling.**
- [ ] **Step 2: Probe clip/track audio controls needed for background music and ducking.**
- [ ] **Step 3: Add a short disposable render job and verify queue creation.**
- [ ] **Step 4: Start the disposable render and verify status/output without touching production presets.**
- [ ] **Step 5: Record all results and limitations in the capability matrix.**
- [ ] **Step 6: Commit as `test: audit captions audio and render controls`.**

---

### Task 6: External execution, logging and final recommendation

**Files:**
- Create: `scripts/studio_audit/run_all.py`
- Create: `scripts/studio_audit/README.md`
- Modify: `docs/RESOLVE_STUDIO_CAPABILITIES.md`
- Modify: `CURRENT_STATE.md`

**Interfaces:**
- Consumes: all probe modules.
- Produces: one command that runs the safe audit suite, writes a timestamped JSON result, and a human-readable capability matrix/recommendation.

- [ ] **Step 1: Implement `run_all.py` so every probe reports independently and one failed probe does not abort the whole audit.**
- [ ] **Step 2: Write logs/results to a dedicated ignored output directory with timestamp and Resolve version metadata.**
- [ ] **Step 3: Document exact setup and execution commands in `scripts/studio_audit/README.md`.**
- [ ] **Step 4: Run the complete audit against Resolve Studio and inspect every result.**
- [ ] **Step 5: Update `docs/RESOLVE_STUDIO_CAPABILITIES.md` with the final `SUPPORTED` / `PARTIAL` / `MANUAL` matrix.**
- [ ] **Step 6: Update `CURRENT_STATE.md` with the architectural consequences: which old workarounds stay, which can be retired, and which next training phase starts.**
- [ ] **Step 7: Commit as `docs: finalize Resolve Studio capability audit`.**

## Completion gate

The audit is complete only when:

1. an external Python process can connect to Resolve Studio;
2. every roadmap-relevant capability has an execution-backed status;
3. tracking is broken down into configuration, execution and data readback instead of a single vague result;
4. a repeatable safe audit command exists;
5. `CURRENT_STATE.md` names the next primitive to train based on measured Studio capabilities.
