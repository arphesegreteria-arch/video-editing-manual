# ARPHÈ Podcast Reel Editorial Selection and Learning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan.

**Goal:** Add a resumable, approval-bound workflow that proposes strong excerpts from an ARPHÈ podcast, marks them on the original Resolve timeline, accepts one complete human review, creates only the approved Reel timelines, and learns from explained decisions without leaking editorial data between workstations.

**Architecture:** Keep semantic selection and natural-language interpretation in ChatGPT. Add deterministic bridge modules for the versioned contract, transcript-anchor validation, workstation-local jobs, Resolve markers/cuts, audio provenance, and redacted learning. Expose a small end-to-end MCP surface behind `CAP_EDITORIAL_SELECTION`; reuse the existing workflow registry, format contract, longform append logic, state lock, audit conventions, and Windows profile installer rather than adding new generic primitives.

**Tech Stack:** Python 3 standard library, `unittest`, FastMCP tool decorators, DaVinci Resolve Python API fakes, JSON contracts, PowerShell installer tests.

**Spec:** `docs/superpowers/specs/2026-10-08-editorial-selection-learning-design.md`

## Global Constraints

- Scope is only `ARPHE_PODCAST_REELS_CTA`; reject every other workflow ID.
- Never infer editorial meaning inside the bridge. Inputs to bridge writes are structured and fingerprint-bound.
- Final Reel duration, CTA included, is `<= 180.0` seconds with no override.
- Candidate count is quality-driven: `1..20`, with no target of six.
- Mark the original timeline; do not duplicate, cut, retime, or change settings during marking.
- Keep `PC_PERSONALE` and `PC_SEGRETERIA` state, flags, journals, validation evidence, and rollout gates independent.
- Detailed reasons, quotes, transcript anchors, media paths, names, and job IDs stay out of repository-tracked learning data.
- All mutating routes fail closed when `CAP_EDITORIAL_SELECTION` is false; read-only inspection stays available.
- Use TDD for every task and commit after each green unit.
- Run bridge `python -m unittest ...` commands from `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03`; run Windows and repository validators from the repository root.

## File Structure

New focused modules:

- `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/editorial_selection_contract.py` — immutable payload types, strict JSON loaders, canonical fingerprints.
- `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/editorial_selection.py` — transcript anchor resolution and pure candidate validation.
- `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/editorial_jobs.py` — per-workstation job store and lifecycle transitions.
- `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/editorial_markers.py` — all-or-nothing marker ownership and cleanup.
- `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/editorial_review.py` — structured review validation, instructions, and review fingerprint.
- `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/audio_provenance.py` — source/output/hash/sync manifest verification.
- `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/editorial_cut_workflow.py` — per-candidate, resumable Resolve mutations and verification.
- `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/editorial_learning.py` — local metrics plus redacted profile proposals.
- `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/editorial_selection_contract.json` — versioned workflow constants.
- `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/editorial_preferences.json` — versioned, aggregate-only shared profile.

Existing files to extend:

- `bridge/config.py`, `bridge/feature_flags.py`, `bridge/audio_tools.py`, `bridge/audio_worker.py`, `bridge/longform_tools.py`, `bridge/server.py`, `bridge/tool_catalog.py`.
- `creative_config.example.json`, `install_on_segreteria.ps1`, `set_feature_flag.ps1`.
- `docs/04_LONGFORM_WORKFLOW.md`, `docs/18_EDITORIAL_WORKFLOWS_AND_RENDER_DELIVERY.md`, `CURRENT_STATE.md`, `CHANGELOG.md`, `EXPERIMENT_LOG.md`.
- `validation/editorial-selection-ledger.json` and `scripts/validate_editorial_selection.py`.

## Review Focus

Five failure/input classes are most likely to escape ordinary happy-path testing. Each is pinned to an owning task below:

1. Same phrase occurs more than once near a boundary, or transcript timestamps sit on an FPS rounding edge — Task 2.
2. Marker creation fails halfway or collides with a pre-existing marker — Task 4.
3. A review payload is complete syntactically but stale, duplicated, or refers to an ambiguous modified anchor — Task 5.
4. A retry follows partial Resolve success and encounters an existing foreign timeline with the expected name — Task 7.
5. A shared-profile proposal is privacy-safe but based on a stale prior digest or presented by the wrong role/workstation — Task 8.

---

### Task 1: Define the strict selection contract and shipped preference profile

**Files:**

- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/editorial_selection_contract.py`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/editorial_selection_contract.json`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/editorial_preferences.json`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_editorial_selection_contract.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class SelectionContract:
    schema_version: int
    workflow_id: str
    max_candidates: int
    max_final_seconds: float
    marker_color: str
    cta_duration_seconds: float
    modified_anchor_window_seconds: float

@dataclass(frozen=True)
class PreferenceProfile:
    schema_version: int
    profile_version: int
    workflow_id: str
    aggregate_preferences: dict[str, object]
    sample_counts: dict[str, int]
    digest: str

def load_selection_contract(path: Path) -> SelectionContract: ...
def load_preference_profile(path: Path) -> PreferenceProfile: ...
def canonical_digest(payload: Mapping[str, object]) -> str: ...
```

- Contract values: workflow `ARPHE_PODCAST_REELS_CTA`, max candidates `20`, max final seconds `180.0`, marker color chosen from Resolve-supported point-marker colors, no minimum candidate quota.
- The shipped preference profile starts at version `1`, contains only documented aggregate keys, zero sample counts, and a digest computed without its own `digest` field.
- Reject unknown keys, wrong primitive types, unsupported schema versions, duplicate aggregate keys, non-zero counts without an explicit aggregate, and any string value that looks like a path, quoted transcript excerpt, media name, reviewer name, or job ID.

- [ ] Write tests that load the two shipped JSON files and fail for every invalid case above.
- [ ] Run `python -m unittest tests.test_editorial_selection_contract -v`; verify RED because the module/files do not exist.
- [ ] Implement the dataclasses, strict loaders, canonical JSON normalization, and baseline JSON files.
- [ ] Re-run the focused test; verify GREEN.
- [ ] Commit: `git add ... && git commit -m "feat: define editorial selection contract"`.

### Task 2: Validate candidates and resolve transcript anchors deterministically

**Files:**

- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/editorial_selection.py`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_editorial_selection.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class TranscriptAnchor:
    text: str
    occurrence: int | None = None

@dataclass(frozen=True)
class CandidateProposal:
    candidate_id: str
    thesis: str
    start_anchor: TranscriptAnchor
    end_anchor: TranscriptAnchor
    indispensable_context: str
    source_start_seconds: float
    source_end_seconds: float
    speech_duration_seconds: float
    cta_duration_seconds: float
    final_duration_seconds: float
    uniqueness_evidence: str
    quality_rationale: str

@dataclass(frozen=True)
class ResolvedCandidate:
    proposal: CandidateProposal
    source_in_frame: int
    source_out_frame_exclusive: int
    transcript_start_seconds: float
    transcript_end_seconds: float

def load_pinned_transcript(path: Path, expected_fingerprint: str) -> dict[str, object]: ...
def resolve_anchor(transcript: Mapping[str, object], anchor: TranscriptAnchor,
                   *, near_seconds: tuple[float, float] | None = None) -> float: ...
def validate_candidate_batch(raw: Sequence[Mapping[str, object]], *, transcript: Mapping[str, object],
                             fps: Fraction, contract: SelectionContract) -> tuple[ResolvedCandidate, ...]: ...
```

- Candidate IDs must be exactly `R01` through `R20`, unique and sequential in submitted ranking order.
- Resolve full phrase matches over transcript word/segment data; `occurrence` disambiguates only when it identifies exactly one occurrence.
- Derive frames from pinned transcript times using the same explicit `Fraction` rate used by the source timeline; start rounds down, exclusive end rounds up.
- Reject empty text fields, duplicate/consolidatable thesis keys, materially overlapping duplicate proposals, time/anchor disagreement beyond the contract tolerance, reversed/empty ranges, and final duration above 180 seconds including CTA.

- [ ] Add tests for 1, 6, 10, and 20 candidates; duplicate IDs/theses; overlap; 179.99/180.0/180.01 final seconds; 24/25/30 FPS boundaries; repeated phrase with no occurrence; invalid occurrence; and transcript fingerprint mismatch. This owns Review Focus item 1.
- [ ] Run `python -m unittest tests.test_editorial_selection -v`; verify RED.
- [ ] Implement only the pure resolver and validation code; do not import Resolve.
- [ ] Re-run focused tests; verify GREEN.
- [ ] Commit: `git commit -am "feat: validate podcast reel candidates"`.

### Task 3: Add a workstation-bound editorial job state machine

**Files:**

- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/editorial_jobs.py`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_editorial_jobs.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/config.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/creative_config.example.json`

**Interfaces:**

```python
JOB_STATES = frozenset({"ANALYZED", "MARKED", "REVIEWED", "CUT", "VERIFIED", "CLOSED",
                        "STALE", "BLOCKED", "FAILED_RECOVERABLE"})

@dataclass(frozen=True)
class EditorialJob:
    editorial_job_id: str
    workstation_id: str
    workflow_id: str
    workflow_version: int
    state: str
    project_name: str
    timeline_name: str
    timeline_identity: str
    source_fingerprint: str
    transcript_fingerprint: str
    candidate_fingerprint: str
    review_fingerprint: str | None
    resume_state: str | None
    candidates: tuple[dict[str, object], ...]
    markers: tuple[dict[str, object], ...]
    decisions: tuple[dict[str, object], ...]
    operations: tuple[dict[str, object], ...]

class EditorialJobStore:
    def create(self, job: EditorialJob) -> EditorialJob: ...
    def get(self, job_id: str, workstation_id: str) -> EditorialJob: ...
    def save(self, job: EditorialJob, expected_revision: int) -> EditorialJob: ...
    def active_for_timeline(self, timeline_identity: str) -> EditorialJob | None: ...
```

- Add `editorial_jobs_path`, `editorial_journal_path`, `editorial_profile_overlay_path`, and `editorial_profile_proposals_path` to `CreativeConfig`; defaults live beside the workstation-owned `state_path`.
- Use atomic replace, monotonically increasing revision, random IDs matching `editorial_[0-9a-f]{16}`, and strict transition validation.
- The normal path is `ANALYZED -> MARKED -> REVIEWED -> CUT -> VERIFIED -> CLOSED`. Any non-closed state may fail to `BLOCKED`, `FAILED_RECOVERABLE`, or `STALE`; `BLOCKED` may return only to its recorded `resume_state` after the precondition is revalidated, `FAILED_RECOVERABLE` may resume only the recorded cut operation, and `STALE` requires a new job.
- Bind every read/write to `workstation_id`; a foreign workstation returns a validation error, never data.
- Enforce at most one non-closed marker-owning job per timeline; terminal exceptional states retain recoverable data.

- [ ] Add tests for every valid/invalid transition, stale revision, idempotent replay, corrupt JSON, wrong workstation, and concurrent active timeline ownership.
- [ ] Run `python -m unittest tests.test_editorial_jobs -v`; verify RED.
- [ ] Implement the store and config fields without changing the general `Registry` schema.
- [ ] Re-run focused tests; verify GREEN.
- [ ] Commit: `git commit -am "feat: add resumable editorial job store"`.

### Task 4: Implement all-or-nothing markers on the original timeline

**Files:**

- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/editorial_markers.py`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_editorial_markers.py`

**Interfaces:**

```python
def marker_specs(job: EditorialJob, contract: SelectionContract) -> tuple[dict[str, object], ...]: ...
def mark_candidates(timeline: object, store: EditorialJobStore, job: EditorialJob,
                    contract: SelectionContract) -> EditorialJob: ...
def verify_job_markers(timeline: object, job: EditorialJob) -> dict[str, object]: ...
def cleanup_verified_markers(timeline: object, store: EditorialJobStore,
                             job: EditorialJob) -> EditorialJob: ...
```

- Use Resolve `GetMarkers`, `AddMarker`, and exact-frame deletion/read-back. Marker names are `ARPHE_Rxx_IN/OUT`; notes contain no transcript quote, only thesis/context/duration on IN and candidate ID on OUT.
- Snapshot all pre-existing markers before mutation. A collision blocks before writes where possible; any mid-write failure deletes only markers created in that attempt and proves the snapshot is unchanged.
- Require current project/timeline identity to match the job. Do not call any cut, setting, track, or duplication method.
- Cleanup is legal only from `VERIFIED`, targets registered `(frame, name)` pairs, verifies foreign markers unchanged, and transitions to `CLOSED`.

- [ ] Build strict fakes that log every Resolve call. Test 1/20 candidates, pre-existing unrelated markers, exact-frame collision, failure on marker N, read-back mismatch, repeated marking, wrong timeline, and cleanup before verification. This owns Review Focus item 2.
- [ ] Run `python -m unittest tests.test_editorial_markers -v`; verify RED.
- [ ] Implement marker creation/rollback/verification/cleanup.
- [ ] Re-run focused tests; verify GREEN and assert no forbidden calls occurred.
- [ ] Commit: `git commit -am "feat: mark editorial candidates safely"`.

### Task 5: Bind complete human review to exact candidates and anchors

**Files:**

- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/editorial_review.py`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_editorial_review.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class ReviewDecision:
    candidate_id: str
    outcome: str  # APPROVE | MODIFY | REJECT
    reason: str
    start_anchor: TranscriptAnchor | None = None
    end_anchor: TranscriptAnchor | None = None
    normalized_reason_tags: tuple[str, ...] = ()

def secretary_instructions(job: EditorialJob) -> dict[str, object]: ...
def submit_structured_review(store: EditorialJobStore, job: EditorialJob,
                             raw_decisions: Sequence[Mapping[str, object]],
                             transcript: Mapping[str, object],
                             contract: SelectionContract) -> EditorialJob: ...
```

- Instructions return exact project/timeline/count, three compact steps, and the copyable `R01 OK/MODIFICA/RIFIUTA — motivo` example.
- Require one and only one decision plus a non-empty original reason for every candidate. `MODIFY` requires both anchors and resolves them only inside the configured neighborhood of the original candidate.
- Submission is all-or-nothing: any missing, duplicate, stale, ambiguous, or over-duration decision leaves the job `MARKED` and creates no output.
- Fingerprint the canonical complete review and store it on transition to `REVIEWED`.

- [ ] Test the compact instructions, all three outcomes, missing reason for APPROVE, missing candidate, duplicate candidate, ambiguous modified phrase, anchors outside the neighborhood, changed transcript/candidate fingerprint, and 180-second post-modification limit. This owns Review Focus item 3.
- [ ] Run `python -m unittest tests.test_editorial_review -v`; verify RED.
- [ ] Implement validation and fingerprinting; keep free-text parsing out of the bridge.
- [ ] Re-run focused tests; verify GREEN.
- [ ] Commit: `git commit -am "feat: bind complete editorial reviews"`.

### Task 6: Upgrade audio jobs to verifiable provenance manifests

**Files:**

- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/audio_provenance.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/audio_tools.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/audio_worker.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_audio_pipeline.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class VerifiedAudio:
    path: Path
    audio_job_id: str
    preset: str
    source_fingerprint: str
    output_sha256: str
    output_duration_seconds: float
    sync_delta_seconds: float

def media_fingerprint(path: Path) -> str: ...
def file_sha256(path: Path) -> str: ...
def verify_audio_manifest(config: CreativeConfig, audio_job_id: str,
                          expected_source_fingerprint: str) -> VerifiedAudio: ...
```

- Replace the private path/size/mtime hash with one shared fingerprint function and preserve backward reading only for inspection, not editorial mutation.
- On worker completion record schema `ARPHE_AUDIO_JOB_V2`, source fingerprint, output SHA-256, source duration, output duration, sync delta, sample rate, channels, preset, and job ID.
- Verification requires COMPLETED V2 manifest, allowlisted WAV, matching source fingerprint, current output hash, `abs(sync_delta_seconds) <= 1/30`, and consistent job ID/path.
- Existing `allowed_audio` remains a path gate; editorial cutting must call the stronger verifier. No A/B tracks are added here.

- [ ] Extend audio tests for valid V2, foreign source, changed WAV, excessive sync delta, incomplete/legacy manifest, wrong job ID, and missing file. Assert every invalid case fails before any supplied mutation callback.
- [ ] Run `python -m unittest tests.test_audio_pipeline -v`; verify RED.
- [ ] Implement manifest generation and verification.
- [ ] Re-run focused tests; verify GREEN.
- [ ] Commit: `git commit -am "feat: verify enhanced audio provenance"`.

### Task 7: Create and resume approved Reel timelines candidate by candidate

**Files:**

- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/editorial_cut_workflow.py`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_editorial_cut_workflow.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/longform_tools.py`

**Interfaces:**

```python
def apply_or_resume_editorial_cuts(resolve: object, manager: object, config: CreativeConfig,
                                   store: EditorialJobStore, job_id: str,
                                   expected_review_fingerprint: str,
                                   *, audio_job_id: str | None = None) -> EditorialJob: ...
def verify_editorial_outputs(project: object, job: EditorialJob,
                             contract: SelectionContract) -> EditorialJob: ...
```

- Extract narrowly reusable media import/range append helpers from `longform_tools.py`; retain old tool behavior and tests.
- Under the existing Resolve access lock, preflight workstation/workflow/state/fingerprints, source timeline identity, output names, source format, CTA asset/length, and optional audio provenance before the first mutation.
- For APPROVE/MODIFY create one timeline named `ARPHE_<job-suffix>_Rxx`; REJECT creates none. Append approved source interval, then existing standard CTA, using explicit source width/height/FPS/playback FPS.
- After each candidate, read back boundaries, CTA presence, format, and final duration; atomically record the operation before proceeding.
- On candidate failure set `FAILED_RECOVERABLE` with next operation index and keep markers. On retry, validate registered successes and resume. An expected name with no matching registered identity is a foreign collision and blocks rather than adopts/overwrites it.
- Transition `CUT` only when all requested outputs exist, then `VERIFIED` only after aggregate re-verification. Marker cleanup remains a separate explicit call.

- [ ] Add strict order-log tests for APPROVE/MODIFY/REJECT, CTA-inclusive 180.0/180.01, source-format preservation, stale review fingerprint, wrong source/timeline, optional foreign audio, failure on candidate four after three successes, idempotent resume, tampered prior output, and foreign expected-name collision. This owns Review Focus item 4.
- [ ] Run `python -m unittest tests.test_editorial_cut_workflow tests.test_longform_tools -v`; verify RED only in the new expectations.
- [ ] Implement extraction plus workflow orchestrator.
- [ ] Re-run focused tests; verify GREEN.
- [ ] Commit: `git commit -am "feat: apply resumable editorial reel cuts"`.

### Task 8: Record local metrics and compile approval-bound shared learning

**Files:**

- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/editorial_learning.py`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_editorial_learning.py`

**Interfaces:**

```python
def append_local_outcome(config: CreativeConfig, job: EditorialJob) -> dict[str, object]: ...
def inspect_local_metrics(config: CreativeConfig) -> dict[str, object]: ...
def compile_profile_proposal(config: CreativeConfig, shared: PreferenceProfile,
                             *, minimum_samples: int = 5) -> dict[str, object]: ...
def approve_profile_proposal(config: CreativeConfig, proposal_id: str, operator_role: str,
                             expected_prior_digest: str) -> dict[str, object]: ...
def load_effective_preferences(config: CreativeConfig,
                               shared: PreferenceProfile) -> dict[str, object]: ...
```

- Append detailed local JSONL records only after `VERIFIED`; include boundaries, decisions, human reasons, normalized tags, deltas, timestamps, and first-proposal acceptance.
- Compute candidate/job metrics specified by the design. Label wall-clock value `review_latency_seconds`, never active labor.
- Compile only aggregate whitelisted keys and sample counts. Run a recursive privacy validator before saving a proposal; no auto-edit, Git action, or push.
- Alessio-only approval writes the approved aggregate to the workstation-local overlay/export with both prior and proposed digests. Repository `editorial_preferences.json` changes remain an explicit reviewed patch after approval.
- Effective preferences are deterministic `shared base + local overlay`; never read another workstation path.

- [ ] Test metrics, minimum samples, redaction of quotes/paths/names/job IDs, recursive nested leakage, no repository write, wrong role, wrong workstation, stale prior digest, double approval, and deterministic merge. This owns Review Focus item 5.
- [ ] Run `python -m unittest tests.test_editorial_learning -v`; verify RED.
- [ ] Implement local journal, metrics, compiler, privacy validator, and approval.
- [ ] Re-run focused tests; verify GREEN.
- [ ] Commit: `git commit -am "feat: learn from editorial review outcomes"`.

### Task 9: Expose a small, gated end-to-end MCP surface

**Files:**

- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/config.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/feature_flags.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/server.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/tool_catalog.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_feature_flags.py`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_editorial_selection_tools.py`

**Public tools:**

```text
inspect_editorial_selection
prepare_podcast_reel_selection
inspect_editorial_selection_job
submit_podcast_reel_review
apply_podcast_reel_selection
close_podcast_reel_selection
inspect_editorial_learning
compile_editorial_profile_proposal
approve_editorial_profile_proposal
```

- Add `CAP_EDITORIAL_SELECTION` to capability names/defaults/status. Default is false and technical availability requires the focused modules plus the Resolve methods needed by the requested operation.
- `inspect_*` routes remain read-only while disabled. All prepare/mark/review/cut/close/compile/approve writes require the new capability and exact workstation binding.
- `prepare_podcast_reel_selection` accepts already structured candidates, creates the ANALYZED job, and marks it in one idempotent workflow call.
- `inspect_editorial_selection_job` returns compact secretary instructions in MARKED state and recovery instructions in exceptional states.
- Public tool schemas do not accept raw shell/code, arbitrary paths outside existing allowlists, timecode-only modifications, or override of workflow/duration/workstation.

- [ ] Write async MCP tests for tool catalog exposure, default-off reads, every default-off write, wrong workflow/workstation, repeated identical calls, compact instructions, state-specific responses, and proof Resolve fakes receive zero calls on preflight failure.
- [ ] Run `python -m unittest tests.test_feature_flags tests.test_editorial_selection_tools tests.test_safety -v`; verify RED.
- [ ] Wire the orchestrators and annotations without exposing their primitives.
- [ ] Re-run focused tests; verify GREEN.
- [ ] Commit: `git commit -am "feat: expose editorial selection workflow"`.

### Task 10: Preserve workstation isolation in Windows installation and upgrades

**Files:**

- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/creative_config.example.json`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/install_on_segreteria.ps1`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/set_feature_flag.ps1`
- Modify: `scripts/windows_bridge/tests/test_profile_installer.py`
- Modify: `scripts/windows_bridge/tests/test_profile_config.py`

- Installer copies the two shipped read-only JSON registries, creates workstation-owned job/journal/overlay/proposal paths, and defaults the new flag false for fresh installs.
- Upgrade preserves an explicit local true/false value and existing local editorial state. It never copies personal state into segreteria or vice versa.
- Feature-flag script recognizes `CAP_EDITORIAL_SELECTION` through the selected profile, prints workstation/config target in dry-run, and does not use a generic Python alias.
- Foreign existing job/journal metadata blocks before any write, following the existing artifact/retirement ownership pattern.

- [ ] Add installer tests for both workstations, fresh default false, explicit true/false preservation, distinct paths, registry copy, foreign state rejection, dry-run, and no deletion/migration across profiles.
- [ ] From repository root run `python -m unittest discover -s scripts/windows_bridge/tests -p "test_profile*.py" -v`; verify RED in the new editorial-selection expectations.
- [ ] Implement PowerShell/config changes.
- [ ] Re-run focused tests; verify GREEN.
- [ ] Commit: `git commit -am "feat: isolate editorial selection rollout"`.

### Task 11: Document the operator flow and add machine-checkable validation evidence

**Files:**

- Create: `validation/editorial-selection-ledger.json`
- Create: `scripts/validate_editorial_selection.py`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_editorial_selection_validation.py`
- Modify: `docs/04_LONGFORM_WORKFLOW.md`
- Modify: `docs/18_EDITORIAL_WORKFLOWS_AND_RENDER_DELIVERY.md`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/README.md`
- Modify: `CURRENT_STATE.md`
- Modify: `CHANGELOG.md`
- Modify: `EXPERIMENT_LOG.md`

- Document the compact secretary interaction exactly: listen between paired markers, do not edit markers, reply once with decision and reason for every candidate. Include recovery and Alessio-only/technical actions separately.
- Ledger schema records automated evidence plus separate `PC_PERSONALE` and `PC_SEGRETERIA` gates. No workstation may become `VALIDATED` from another workstation's evidence.
- Validator requires marker/review/cut/recovery/duration/cleanup/rollback evidence for a live gate and rejects sensitive content in tracked fields.
- Initial repository state after automated tests is `PC_PERSONALE=PENDING`, `PC_SEGRETERIA=PENDING`, capability default false.

- [ ] Write validator tests for missing gates, cross-workstation evidence, unsupported status, sensitive fields, fake future timestamps, and a valid automated-only pending ledger.
- [ ] Run `python -m unittest tests.test_editorial_selection_validation -v`; verify RED.
- [ ] Implement validator, initial ledger, and operator docs.
- [ ] Run focused tests and `python scripts/validate_editorial_selection.py`; verify GREEN.
- [ ] Commit: `git commit -am "docs: define editorial selection rollout"`.

### Task 12: Run complete verification and repository privacy audit

**Files:** Review all files changed in Tasks 1–11.

- [ ] Run bridge suite from `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03`:

  `python -m unittest discover -s tests -v`

- [ ] Run Windows suite from repository root:

  `python -m unittest discover -s scripts/windows_bridge/tests -v`

- [ ] Run focused validator:

  `python scripts/validate_editorial_selection.py`

- [ ] Run repository privacy searches and inspect every hit:

  `rg -n "editorial_[0-9a-f]{16}|[A-Z]:[/\\]|source_(name|path)|reviewer|human_reason|start_anchor|end_anchor" scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/editorial_preferences.json validation/editorial-selection-ledger.json`

- [ ] Run `git diff --check`, `git status --short`, and review `git diff --stat` plus the complete branch diff.
- [ ] Confirm no automated test edits a real Resolve project, no live evidence is claimed, both workstation flags default/preserve independently, and the segreteria open job is untouched.
- [ ] If any check fails, return to its owning task and add a regression test before fixing.
- [ ] Commit any verification-only corrections with a scoped message; do not squash evidence-generating commits yet.

### Task 13: Perform isolated `PC_PERSONALE` live gate and rollback drill

**Files:**

- Modify after evidence exists: `validation/editorial-selection-ledger.json`
- Modify after evidence exists: `CURRENT_STATE.md`, `CHANGELOG.md`, `EXPERIMENT_LOG.md`

- [ ] Confirm Resolve is available on `PC_PERSONALE`, no real editorial timeline is the test target, and `PC_SEGRETERIA` is not being operated.
- [ ] Install/upgrade the personal runtime with `CAP_EDITORIAL_SELECTION=false`; inspect status and paths.
- [ ] Use synthetic or explicitly approved non-sensitive media/transcript on a disposable project. Record source timeline marker snapshot.
- [ ] Enable the flag only on the personal profile and run a job containing at least one APPROVE, one MODIFY, and one REJECT decision with reasons.
- [ ] Verify marker pairs and compact instructions; inject a controlled failure after at least one successful output; resume and prove no duplicate timeline.
- [ ] Verify explicit source format/playback FPS, CTA presence, final duration `<=180s`, optional-audio provenance behavior, and cleanup preserving all foreign markers.
- [ ] Disable the flag and prove mutating tools fail closed; re-enable only if Alessio elects to keep the personal rollout active.
- [ ] Record exact commands/results/timestamps/workstation identity in the ledger. Keep `PC_SEGRETERIA=PENDING` and false.
- [ ] Run Task 12 verification again.
- [ ] Commit: `git commit -am "test: validate editorial selection on personal pc"`.

### Task 14: Review, PR, and merge without touching segreteria runtime

- [ ] Use `superpowers:requesting-code-review` for a fresh review against the spec, with special attention to the five Review Focus classes and zero-write preflights.
- [ ] Address findings with regression tests; repeat Task 12.
- [ ] Compare branch to `origin/main`; resolve only in-repo conflicts, never workstation runtime state.
- [ ] Push `codex/editorial-selection-learning`, open a PR summarizing design, automated results, personal evidence, rollback result, privacy boundary, and `PC_SEGRETERIA=PENDING`.
- [ ] After checks/review pass and Alessio authorizes merge, merge the PR.
- [ ] Do not install or enable the feature on `PC_SEGRETERIA`. Its later rollout requires a new isolated live gate after the current editorial work is no longer at risk.

## Plan Self-Review

- **Spec coverage:** Every design section maps to an owning task: contract/candidates (1–2), jobs (3), markers (4), review (5), audio (6), cuts/recovery/CTA/format (7), metrics/learning/privacy (8), public surface/flag (9), workstation isolation (10), docs/evidence (11), verification/live rollout (12–14).
- **Step scan:** Every implementation task begins with failing tests, names the focused command and expected RED/GREEN result, and ends with a scoped commit.
- **Type consistency:** `Fraction` is used for FPS; fingerprints are canonical SHA-256 strings; job state is persisted through one typed store; public tools exchange JSON-compatible dictionaries derived from immutable dataclasses.
- **Review Focus coverage:** Ambiguous anchors/rounding (Task 2), marker partial failure/collision (Task 4), stale/ambiguous complete reviews (Task 5), partial resume/foreign output (Task 7), and privacy-safe but stale/unauthorized profile updates (Task 8) each have explicit regression tests.
- **Proportion:** The plan adds focused modules around existing validated primitives instead of rewriting the bridge or expanding the operator UI. Live rollout remains isolated and default-off on segreteria.
