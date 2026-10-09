# Studio Carabellese YouTube Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a gated, resumable Studio Carabellese workflow that transcribes one YouTube podcast timeline, proposes moderate pause/boundary/editorial-cue edits, obtains one complete review, checkpoints the timeline and applies the approved cleanup with isolated learning.

**Architecture:** Add a Carabellese-specific contract, job model and public workflow on top of the bridge's shared workstation, provenance, marker, locking and approval patterns. Keep the current timeline canonical, use a verified `.drt` checkpoint before destructive work, and isolate all state, learning and rollout evidence from Podcast Reels.

**Tech Stack:** Python 3.12+, standard library, DaVinci Resolve Studio 21.1.1 scripting API, JSON contracts, `unittest`, PowerShell installers.

**Spec:** `docs/superpowers/specs/2026-10-09-carabellese-youtube-cleanup-design.md`

## Global Constraints

- `CARABELLESE_YOUTUBE_CLEANUP` remains 1920×1080 with project, timeline and playback equal to the pinned source FPS.
- Add no CTA, caption, Graphic Kit asset, title, reframing, music or automatic render.
- `CAP_CARABELLESE_CLEANUP=false` by default and validation remains per workstation.
- Show one canonical visible timeline; internal recovery/staging objects must not survive successful completion.
- Spoken editorial cues never authorize automatic removal, regardless of confidence.
- Every review group or exception requires an explicit outcome and reason.
- Verify a source-bound transcript, plan fingerprint and `.drt` checkpoint before the first destructive timeline write.
- Keep Carabellese job state, raw outcomes and approved preferences separate from Podcast Reels.
- Do not commit transcripts, media, raw review text, names, private paths or live job identifiers.
- In this worktree, use `C:\ARPHE\MCP\runtimes\PC_PERSONALE\venv\Scripts\python.exe` as `<PYTHON>` for test commands.

## File Structure

- `bridge/carabellese_contract.py`: strict contract and preference loaders plus canonical fingerprints.
- `carabellese_cleanup_contract.json`: versioned thresholds, format and marker policy.
- `carabellese_preferences.json`: redacted approved baseline specific to Carabellese.
- `bridge/carabellese_jobs.py`: isolated job schema, transitions, optimistic revisions and workstation ownership.
- `bridge/carabellese_transcription.py`: allowlisted asynchronous transcription jobs and status recovery.
- `bridge/transcription_worker.py`: shared checkpointed faster-whisper implementation used by the bridge and CLI.
- `bridge/carabellese_analysis.py`: transcript/audio provenance, pause/boundary/cue candidate validation and fingerprints.
- `bridge/carabellese_markers.py`: concise boundary/exception markers and foreign-marker preservation.
- `bridge/carabellese_review.py`: one-response structured review, reasons and operator instructions.
- `bridge/carabellese_checkpoint.py`: `.drt` export, hash verification and technical restore.
- `bridge/carabellese_apply.py`: source/timeline preflight, same-timeline edit execution, verification and recoverable failure.
- `bridge/carabellese_learning.py`: local redacted aggregates and approved workflow-specific overlay.
- `bridge/server.py` and `bridge/tool_catalog.py`: public inspection, prepare, review, apply, recover, close and learning tools.
- `bridge/config.py`, `bridge/feature_flags.py`, installer/config JSON: default-off capability and isolated paths.
- `scripts/validate_carabellese_cleanup.py` and `validation/carabellese-cleanup-ledger.json`: automated and per-PC evidence.

## Review Focus

- A transcription worker is interrupted or handed an out-of-root source: resume only its owned manifest or reject before process creation (Task 3).
- A transcript belongs to a different source or changes after proposal: reject before markers, checkpoint or cuts (Task 4).
- Resolve cannot verify `.drt` export or safe same-timeline staging on the installed API: return an explicit unsupported/preflight result and leave the timeline unchanged (Tasks 7–8).
- A serious-sounding phrase is actually quoted or ironic: force individual review and never auto-remove it (Tasks 4–6).
- A partial apply, app restart or operator timeline change occurs: preserve the verified checkpoint, stop later operations and require verified recovery or a new review (Tasks 8–9).

---

### Task 1: Contract, preferences and default-off capability

**Files:**
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/carabellese_cleanup_contract.json`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/carabellese_preferences.json`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/carabellese_contract.py`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_carabellese_contract.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/config.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/feature_flags.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/creative_config.example.json`

**Interfaces:**
- Produces: `CarabelleseContract`, `CarabellesePreferences`, `load_carabellese_contract(path: Path)`, `load_carabellese_preferences(path: Path)`, `carabellese_contract_fingerprint(contract) -> str`.
- Produces config paths: `carabellese_jobs_path`, `carabellese_journal_path`, `carabellese_profile_overlay_path`, `carabellese_profile_proposals_path`, `carabellese_checkpoint_root`.

- [ ] **Step 1: Write failing strict-loader and feature-flag tests**

Add tests asserting workflow ID, 1920×1080, `frame_rate_mode="source"`, pause bounds `0.7/1.5`, residual range `0.6–0.8`, cue review always true, unknown keys rejected, preferences workflow isolation, and `CAP_CARABELLESE_CLEANUP` default false.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `<PYTHON> -m unittest scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_carabellese_contract scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_feature_flags`

Expected: FAIL because the loader and capability do not exist.

- [ ] **Step 3: Implement the minimal contract, preference and config support**

Use frozen dataclasses, strict exact-key validation and canonical SHA-256 JSON fingerprints. Add the capability to `CAPABILITY_NAMES`, `DEFAULT_FLAGS`, reporting and technical availability without activating it.

- [ ] **Step 4: Run focused tests and verify GREEN**

Expected: all focused tests PASS.

- [ ] **Step 5: Commit**

```text
git commit -m "feat: define Carabellese cleanup contract"
```

### Task 2: Isolated resumable job store

**Files:**
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/carabellese_jobs.py`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_carabellese_jobs.py`

**Interfaces:**
- Consumes: contract version and workstation-local paths from Task 1.
- Produces: `CarabelleseJob`, `CarabelleseJobStore`, `new_carabellese_job(...) -> CarabelleseJob`.
- States: `ANALYZED`, `MARKED`, `REVIEWED`, `CHECKPOINTED`, `APPLYING`, `VERIFIED`, `FAILED_RECOVERABLE`, `BLOCKED`, `STALE`, `CLOSED`.

- [ ] **Step 1: Write failing lifecycle, isolation and concurrency tests**

Cover every valid edge, invalid skips, stale revision, idempotent create/save, corrupt JSON, wrong workstation, one active job per timeline and rejection of `ARPHE_PODCAST_REELS_CTA` records.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `<PYTHON> -m unittest scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_carabellese_jobs`

- [ ] **Step 3: Implement the strict job schema and atomic store**

Persist source, timeline, transcript, contract, proposal, review and checkpoint fingerprints plus candidates, decisions, markers and operations. Use optimistic revisions and atomic replace.

- [ ] **Step 4: Run focused tests and verify GREEN**

- [ ] **Step 5: Commit**

```text
git commit -m "feat: add resumable Carabellese jobs"
```

### Task 3: Managed local transcription

**Files:**
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/transcription_worker.py`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/carabellese_transcription.py`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_carabellese_transcription.py`
- Modify: `scripts/experiments/ARPHE_LONGFORM_TRANSCRIBE_01.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/requirements.txt`

**Interfaces:**
- Consumes: allowlisted media/transcript roots and workstation identity from config.
- Produces: `start_carabellese_transcription(config, media_path, expected_source_fingerprint, model="small", language="it") -> dict[str, object]`, `get_carabellese_transcription_job(config, job_id) -> dict[str, object]`, and `transcribe_checkpointed(...)` shared with the existing CLI.

- [ ] **Step 1: Write failing job, interruption and path-safety tests**

Assert only allowlisted media is accepted; the source fingerprint is checked before process creation; job IDs and outputs are workstation-local; retry returns the owned running/complete job; interrupted manifests remain resumable; status never returns transcript content or private source paths; model/language are allowlisted rather than arbitrary command arguments.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `<PYTHON> -m unittest scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_carabellese_transcription`

- [ ] **Step 3: Extract the checkpointed worker and implement asynchronous orchestration**

Move the reusable transcription body out of `ARPHE_LONGFORM_TRANSCRIBE_01.py` without changing `ARPHE_TRANSCRIPT_V1`; keep the CLI as a thin wrapper. Launch only the installed worker with the current interpreter, explicit paths and no shell.

- [ ] **Step 4: Run focused tests and verify GREEN**

- [ ] **Step 5: Commit**

```text
git commit -m "feat: manage Carabellese transcription jobs"
```

### Task 4: Source-bound analysis and candidate validation

**Files:**
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/carabellese_analysis.py`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_carabellese_analysis.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/audio_provenance.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_audio_pipeline.py`

**Interfaces:**
- Consumes: the managed transcript from Task 3, `load_pinned_transcript`, verified audio manifests and the Task 1 contract.
- Produces: `CleanupCandidate`, `load_carabellese_inputs(...)`, `derive_pause_candidates(words, silence_windows, contract)`, `validate_cleanup_candidates(raw, transcript, contract, duration_seconds)`, `cleanup_candidate_fingerprint(candidates) -> str`.

- [ ] **Step 1: Write failing provenance, pause and review-focus tests**

Assert wrong-source transcript/audio rejection; protected sub-0.7 gaps; contextual 0.7–1.5 gaps; >1.5 gaps reduced into 0.6–0.8; speaker-turn protection; silence-safe blade bounds; serious, ambiguous, quoted and ironic cues all have `review_required=True`; malformed, overlapping and out-of-duration ranges fail.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `<PYTHON> -m unittest scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_carabellese_analysis scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_audio_pipeline`

- [ ] **Step 3: Implement validation and deterministic pause derivation**

Use timestamped words plus verified local silence windows. Normalize adjacent compatible pause removals only when the resulting residual pause remains inside contract bounds; reject every other overlap. Boundary/cue/manual candidates supplied by the assistant must anchor to transcript words and include context.

- [ ] **Step 4: Run focused tests and verify GREEN**

- [ ] **Step 5: Commit**

```text
git commit -m "feat: validate Carabellese cleanup candidates"
```

### Task 5: Concise markers on the canonical timeline

**Files:**
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/carabellese_markers.py`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_carabellese_markers.py`

**Interfaces:**
- Consumes: `CarabelleseJobStore`, validated candidates and timeline identity helper.
- Produces: `carabellese_marker_specs(job, contract)`, `mark_carabellese_review(timeline, store, job, contract)`, `verify_carabellese_markers(...)`, `cleanup_carabellese_markers(...)`.

- [ ] **Step 1: Write failing marker-scope and rollback tests**

Assert only boundaries and individually reviewed exceptions get markers; ordinary pauses do not; collisions block before writes; add failure rolls back owned markers; retries are idempotent; foreign markers stay byte-equivalent.

- [ ] **Step 2: Run focused test and verify RED**

- [ ] **Step 3: Implement namespaced markers and scoped rollback**

Use `CARABELLESE:<job_id>:<candidate_id>:IN|OUT` custom data and a marker colour from the contract.

- [ ] **Step 4: Run focused tests and verify GREEN**

- [ ] **Step 5: Commit**

```text
git commit -m "feat: mark Carabellese review exceptions"
```

### Task 6: One-response review and secretary instructions

**Files:**
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/carabellese_review.py`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_carabellese_review.py`

**Interfaces:**
- Produces: `carabellese_secretary_instructions(job) -> dict[str, object]`, `submit_carabellese_review(store, job, boundary_decisions, pause_decision, exception_decisions, contract) -> CarabelleseJob`.
- Review outcomes: `KEEP`, `REMOVE`, `SHORTEN`, `MODIFY` with non-empty `reason`.

- [ ] **Step 1: Write failing completeness and wording tests**

Assert one compact summary; one pause-batch decision; individual boundaries/cues; mandatory reasons; missing, duplicate or unknown IDs reject without state changes; modified spans revalidate against transcript anchors; cue confidence never bypasses review.

- [ ] **Step 2: Run focused test and verify RED**

- [ ] **Step 3: Implement canonical decisions and review fingerprint**

Sort decisions by stable candidate ID and fingerprint canonical JSON including contract and candidate fingerprints.

- [ ] **Step 4: Run focused tests and verify GREEN**

- [ ] **Step 5: Commit**

```text
git commit -m "feat: review Carabellese cleanup in one response"
```

### Task 7: Verified `.drt` checkpoint and restore

**Files:**
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/carabellese_checkpoint.py`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_carabellese_checkpoint.py`

**Interfaces:**
- Produces: `export_timeline_checkpoint(resolve, project, timeline, store, job, root) -> CarabelleseJob`, `verify_timeline_checkpoint(job) -> dict[str, object]`, `restore_timeline_checkpoint(resolve, project, store, job) -> CarabelleseJob`.

- [ ] **Step 1: Write failing export, hash and unsupported-API tests**

Assert export uses `resolve.EXPORT_DRT`; missing/empty/hash-mismatched output never reaches `CHECKPOINTED`; retry reuses a verified checkpoint; unsupported export is zero-write; restore imports under a temporary owned name, verifies identity/content evidence, removes the failed owned timeline only after verification and finishes with one canonical timeline.

- [ ] **Step 2: Run focused test and verify RED**

- [ ] **Step 3: Implement checkpoint manifest and scoped restore**

Store path only in workstation-local state; shared evidence records hash/result but no private path.

- [ ] **Step 4: Run focused tests and verify GREEN**

- [ ] **Step 5: Commit**

```text
git commit -m "feat: checkpoint Carabellese timelines"
```

### Task 8: Same-timeline application engine

**Files:**
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/carabellese_apply.py`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_carabellese_apply.py`

**Interfaces:**
- Consumes: reviewed job and verified checkpoint from Tasks 6–7.
- Produces: `inspect_carabellese_apply_support(resolve, project, timeline, job) -> dict[str, object]`, `apply_or_resume_carabellese_cleanup(resolve, manager, config, store, job_id, expected_review_fingerprint) -> CarabelleseJob`, `verify_carabellese_timeline(...) -> dict[str, object]`.

- [ ] **Step 1: Write failing zero-write preflight tests**

Cover wrong workstation/project/timeline/source/transcript/contract/review fingerprint; playback mismatch; changed timeline; absent checkpoint; unsupported timeline shape/API; and a `BLOCKED` job whose failed preflight remains persisted byte-equivalent.

- [ ] **Step 2: Write failing apply/idempotency tests**

Use a fake single-source linked AV timeline. Assert approved removals are ordered latest-first, safe handles remain, the canonical timeline name/identity policy holds, one final timeline remains, foreign tracks/markers are rejected rather than adopted, retry does not duplicate operations and verification checks final duration against the approved plan.

- [ ] **Step 3: Run focused test and verify RED**

- [ ] **Step 4: Implement the safest verified splice adapter supported by Resolve**

The adapter must first prove the required API surface on the installed version. It may use owned temporary tracks inside the same timeline while building kept segments, but it may not delete original timeline items until every staged segment reads back correctly. If transitions cannot be verified, preserve silence handles and return that limitation in verification evidence.

- [ ] **Step 5: Implement recoverable failure and resume**

On any post-checkpoint exception, persist `FAILED_RECOVERABLE`, stop later operations and preserve checkpoint plus completed-operation evidence. Never continue against a changed timeline fingerprint.

- [ ] **Step 6: Run focused tests and verify GREEN**

- [ ] **Step 7: Commit**

```text
git commit -m "feat: apply verified Carabellese cleanup"
```

### Task 9: Recovery and closure workflow

**Files:**
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/carabellese_apply.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/carabellese_markers.py`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_carabellese_recovery.py`

**Interfaces:**
- Produces: `recover_carabellese_cleanup(...) -> CarabelleseJob`, `close_carabellese_cleanup(...) -> CarabelleseJob`.

- [ ] **Step 1: Write failing partial-failure, restart and tamper tests**

Assert failure after one staged operation stops all later work; restart reads the journal; changed checkpoint/timeline blocks recovery; successful restore leaves one canonical timeline; close requires `VERIFIED`, removes only owned markers and preserves checkpoint retention metadata.

- [ ] **Step 2: Run focused tests and verify RED**

- [ ] **Step 3: Implement technical recovery and verified closure**

- [ ] **Step 4: Run focused tests and verify GREEN**

- [ ] **Step 5: Commit**

```text
git commit -m "feat: recover and close Carabellese cleanup"
```

### Task 10: Isolated Carabellese learning

**Files:**
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/carabellese_learning.py`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_carabellese_learning.py`

**Interfaces:**
- Produces: `append_carabellese_outcome(config, job)`, `inspect_carabellese_metrics(config)`, `compile_carabellese_profile_proposal(config, shared, minimum_samples)`, `approve_carabellese_profile_proposal(config, proposal_id, operator_role, expected_previous_digest)`.

- [ ] **Step 1: Write failing isolation and privacy tests**

Assert only `CLOSED` jobs append; reruns are idempotent; aggregates include pause bands, residual durations, boundary shifts and false-positive categories; raw transcript, reasons, names, paths, job IDs and Podcast-Reels data never enter proposals; wrong digest/role rejects.

- [ ] **Step 2: Run focused test and verify RED**

- [ ] **Step 3: Implement local journal, redacted proposal and approved overlay**

- [ ] **Step 4: Run focused tests and verify GREEN**

- [ ] **Step 5: Commit**

```text
git commit -m "feat: learn Carabellese cleanup preferences"
```

### Task 11: Public tools, server flow and concise operator response

**Files:**
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/server.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/tool_catalog.py`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_carabellese_tools.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_safety.py`

**Interfaces:**
- Produces public tools: `inspect_carabellese_cleanup`, `start_carabellese_transcription`, `get_carabellese_transcription_job`, `prepare_carabellese_cleanup`, `inspect_carabellese_job`, `submit_carabellese_review`, `apply_carabellese_cleanup`, `recover_carabellese_cleanup`, `close_carabellese_cleanup`, `inspect_carabellese_learning`, `compile_carabellese_profile_proposal`, `approve_carabellese_profile_proposal`.

- [ ] **Step 1: Write failing end-to-end fake-runtime tool tests**

Assert inspection works while disabled; writes require the capability; preparation pins current source/timeline/transcript and returns exact secretary instructions; stale/old job IDs cannot execute; no generic path or arbitrary Resolve mutation parameter is exposed.

- [ ] **Step 2: Run tool and safety tests and verify RED**

- [ ] **Step 3: Implement thin locked server wrappers and catalog entries**

Keep one `RESOLVE_ACCESS_LOCK` around each complete Resolve operation and return structured recoverable errors through the existing `_call` wrapper.

- [ ] **Step 4: Run focused tests and verify GREEN**

- [ ] **Step 5: Commit**

```text
git commit -m "feat: expose Carabellese cleanup workflow"
```

### Task 12: Installer, validation ledger and operating documentation

**Files:**
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/install_on_segreteria.ps1`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/set_feature_flag.ps1`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_feature_flags.py`
- Modify: `scripts/windows_bridge/tests/test_profile_installer.py`
- Create: `scripts/validate_carabellese_cleanup.py`
- Create: `validation/carabellese-cleanup-ledger.json`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_carabellese_validation.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/README.md`
- Modify: `docs/18_EDITORIAL_WORKFLOWS_AND_RENDER_DELIVERY.md`
- Modify: `CURRENT_STATE.md`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Produces strict per-workstation evidence with `PC_PERSONALE=PENDING` and `PC_SEGRETERIA=PENDING` until independent live gates pass.

- [ ] **Step 1: Write failing installer and ledger tests**

Assert installer preserves an explicit local flag and Carabellese state, rejects foreign workstation files before writes, copies both registries, and never copies state between PCs. Assert the validator rejects missing checks, inferred cross-PC PASS, private paths/content and enabled final flags.

- [ ] **Step 2: Run focused tests and verify RED**

- [ ] **Step 3: Implement installer/config migration and validator**

- [ ] **Step 4: Document exact secretary and technical flows**

State that no CTA/Graphic Kit/render is part of v1, one timeline is canonical, reasons are mandatory and threshold wording may be simplified during calibration.

- [ ] **Step 5: Run focused tests and verify GREEN**

- [ ] **Step 6: Commit**

```text
git commit -m "docs: define Carabellese cleanup rollout"
```

### Task 13: Full verification and isolated personal rollout

**Files:**
- Modify after evidence exists: `validation/carabellese-cleanup-ledger.json`
- Modify after evidence exists: `CURRENT_STATE.md`, `CHANGELOG.md`, `EXPERIMENT_LOG.md`

**Interfaces:**
- Produces automated evidence and a personal live-gate result without changing `PC_SEGRETERIA`.

- [ ] **Step 1: Run all automated suites**

Run:

```text
<PYTHON> -m unittest discover -s scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests -p "test_*.py"
<PYTHON> -m unittest discover -s scripts/windows_bridge/tests -p "test_*.py"
<PYTHON> scripts/validate_carabellese_cleanup.py
git diff --check
```

Expected: PASS with only previously documented environment skips.

- [ ] **Step 2: Review privacy and rollback surfaces**

Search tracked diffs for transcript excerpts, names, local paths, tunnel IDs, secrets and live job IDs. Review every write path for a read-only preflight, owned rollback and exact job/fingerprint requirement.

- [ ] **Step 3: Install only the `PC_PERSONALE` copy with the flag false**

Verify installed hashes, workstation identity, isolated state paths, task health and `/readyz`; do not touch `PC_SEGRETERIA`.

- [ ] **Step 4: Run a disposable Resolve capability probe before enabling the gate**

Prove `.drt` export/import, source-FPS/playback read-back, same-timeline staging and scoped removal on a synthetic project. If any required API cannot be verified, record `UNSUPPORTED`/`PENDING`, leave the flag false and stop without adapting the architecture silently.

- [ ] **Step 5: Run the personal live gate only if the capability probe passes**

Use synthetic dialogue with moderate/long pauses, a speaker turn, setup/closing tails, a serious delete cue and an ironic look-alike. Verify compact review, mandatory reasons, checkpoint, one canonical final timeline, partial failure/recovery, foreign marker preservation and rollback.

- [ ] **Step 6: Return the personal flag to false and clean synthetic artifacts**

Verify task `Running`, live supervisor PID, `/readyz=ready`, installed hash match, exact original project restoration and no remaining synthetic project/files/jobs except quarantined evidence allowed by policy.

- [ ] **Step 7: Record honest evidence and commit**

Promote only checks actually observed. Keep `PC_SEGRETERIA=PENDING` and explicitly state it was untouched.

```text
git commit -m "test: validate Carabellese cleanup on personal pc"
```

### Task 14: Final review and integration decision

**Files:**
- Review all branch changes against the spec and this plan.

- [ ] **Step 1: Perform a whole-branch correctness review**

Focus on zero-write preflights, same-timeline safety, unsupported Resolve API handling, transcript provenance, privacy, workstation isolation and default-off rollback.

- [ ] **Step 2: Fix findings test-first and rerun full verification**

- [ ] **Step 3: Present branch integration options**

Do not push, open a PR or merge until Alessio explicitly selects the integration action.
