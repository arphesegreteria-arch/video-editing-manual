# Editorial Workflows and Safe Render Batches Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every ARPHE edit and delivery use an explicit editorial workflow, verified project/playback format and an approved render batch that cannot start old jobs.

**Architecture:** Two versioned registries define editorial workflows and render profiles. A local brief resolves one immutable format contract; a persistent render-batch state machine owns only the jobs and staging files it creates, separates prepare/approve/start, verifies media with PyAV and promotes only conforming output.

**Tech Stack:** Python 3.12/3.13, Python stdlib dataclasses/JSON/hashlib/fractions, PyAV, MCP 2.x, unittest, DaVinci Resolve Studio scripting API.

**Spec:** `docs/superpowers/specs/2026-10-07-editorial-workflows-render-batches-design.md`

## Global Constraints

- `PC_PERSONALE` and `PC_SEGRETERIA` share source code but never runtime state, config, logs or batch evidence.
- `workflow_id` is explicit before the first Resolve write; ChatGPT may suggest it but the bridge never infers it.
- Project frame rate, timeline frame rate and playback frame rate are identical and read back before editing.
- `ARPHE_PODCAST_REELS_CTA` preserves source resolution/rate and delivers MP4/H.264 High/AAC 48 kHz.
- `ARPHE_VERTICAL_SOCIAL` is 1080x1920/30 and separates ProRes 422 HQ master from H.264/AAC social delivery.
- `CARABELLESE_YOUTUBE_CLEANUP` is 1920x1080, preserves the supported source rate and delivers MP4/H.264 High/AAC 48 kHz.
- `ARPHE_LONGFORM_EDITORIAL` requires explicit format fields and begins as `EDITOR_LED`.
- Preparing a batch never calls `StartRendering`; starting requires a non-stale approval fingerprint.
- Pre-existing Resolve jobs are never started or deleted by a new batch.
- No output enters a delivery directory before media verification passes.
- `SEGRETERIA` may approve standard final renders; overrides and technical recovery require `TECNICO` or `ALESSIO`.
- No Git update deploys automatically to a workstation; live gates remain separate per PC.

## Review Focus

- Mixed-rate sources: standard flow stops and requests a confirmed primary rate instead of choosing or rounding one.
- Duplicate, missing or reused Resolve job IDs: preparation/start fails closed and never broad-starts the queue.
- Queue mutation after approval: the token becomes stale even when approved jobs still exist.
- Process restart during render or verification: the persisted batch can be inspected/recovered without recreating jobs or promoting partial files.
- Fractional rates and missing audio streams: verification compares rational rates correctly and rejects a delivery that lacks required audio.

---

## File Structure

- `bridge/editorial_workflows.py`: load workflow/profile registries, validate briefs and resolve format/profile compatibility.
- `editorial_workflows.json`: four approved production-line definitions and question schemas.
- `render_profiles.json`: explicit review/master/publishable delivery definitions.
- `bridge/format_contract.py`: source-format resolution, Resolve project/timeline/playback apply and read-back.
- `bridge/render_batches.py`: manifest schema, fingerprint, state transitions, role gates and registry persistence helpers.
- `bridge/render_tools.py`: Resolve queue preparation, selective start/cancel and compatibility wrappers.
- `bridge/media_verification.py`: PyAV probing, contract verification and staging promotion.
- `bridge/registry.py`: persisted briefs, batches, render lock and attempts.
- `bridge/server.py` and `bridge/tool_catalog.py`: closed MCP surface.
- `tests/test_editorial_workflows.py`: registry, brief and format-profile compatibility tests.
- `tests/test_format_contract.py`: project/timeline/playback invariants.
- `tests/test_render_batches.py`: lifecycle, approval, queue isolation, rollback and recovery.
- `tests/test_media_verification.py`: output checks and promotion.
- `docs/18_EDITORIAL_WORKFLOWS_AND_RENDER_DELIVERY.md`: operator/technical runbook.

### Task 1: Versioned workflow and render-profile registries

**Files:**
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/editorial_workflows.json`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/render_profiles.json`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/editorial_workflows.py`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_editorial_workflows.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/creative_config.example.json`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/config.py`

**Interfaces:**
- Produces: `load_workflow_registry(path: Path) -> WorkflowRegistry`.
- Produces: `load_render_profile_registry(path: Path) -> RenderProfileRegistry`.
- Produces: `validate_editorial_brief(raw: dict[str, Any], workflows: WorkflowRegistry) -> EditorialBrief`.
- Produces: `resolve_delivery_profile(brief: EditorialBrief, profile_id: str, profiles: RenderProfileRegistry) -> RenderProfile`.
- `EditorialBrief` exposes `brief_id`, `workflow_id`, `workflow_version`, `operator_role`, `primary_source`, `requested_outputs`, `format_request` and `unresolved_questions`.

- [ ] **Step 1: Write failing registry tests**

Add tests named:

```python
def test_four_workflows_load_with_unique_ids_and_required_questions(): ...
def test_standard_secretary_brief_resolves_only_allowed_profiles(): ...
def test_ambiguous_or_incomplete_brief_keeps_unresolved_questions(): ...
def test_mixed_source_rates_require_confirmed_primary_rate(): ...
def test_new_registry_entry_loads_without_render_engine_branch(): ...
```

Assert the four exact IDs and contracts from the spec, including Carabellese 1920x1080 with
source-derived rate and vertical 1080x1920/30. Reject unknown keys, unsupported automation levels,
duplicate IDs and a non-technical override.

- [ ] **Step 2: Run the focused tests and confirm RED**

Run: `python -m unittest scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_editorial_workflows -v`

Expected: FAIL because registries/module do not exist.

- [ ] **Step 3: Implement immutable registry and brief types**

Use frozen dataclasses and strict JSON validation. Store registry paths in `CreativeConfig` with
package-file defaults; retain `render_format`/`render_codec` only as deprecated compatibility
fields and do not consult them from the new engine.

- [ ] **Step 4: Run focused tests and existing config/safety tests**

Run: `python -m unittest scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_editorial_workflows scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_safety -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/editorial_workflows.json scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/render_profiles.json scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/creative_config.example.json scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/editorial_workflows.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/config.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_editorial_workflows.py
git commit -m "feat: define editorial workflows and render profiles"
```

### Task 2: Resolve and verify project, timeline and playback format

**Files:**
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/format_contract.py`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_format_contract.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/timeline_tools.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/longform_tools.py`

**Interfaces:**
- Consumes: `EditorialBrief` and workflow format contract from Task 1.
- Produces: frozen `SourceFormat(width: int, height: int, frame_rate: Fraction)`.
- Produces: frozen `ResolvedFormat(width: int, height: int, project_rate: Fraction, playback_rate: Fraction)`.
- Produces: `resolve_format_contract(brief: EditorialBrief, sources: list[SourceFormat]) -> ResolvedFormat`.
- Produces: `apply_project_format(project: Any, contract: ResolvedFormat) -> dict[str, str]`.
- Produces: `verify_timeline_format(project: Any, timeline: Any, contract: ResolvedFormat) -> None`.

- [ ] **Step 1: Write failing format-invariant tests**

```python
def test_arphe_podcast_preserves_source_dimensions_and_rate(): ...
def test_carabellese_forces_1080p_and_preserves_fractional_source_rate(): ...
def test_vertical_forces_1080x1920_30_and_playback_30(): ...
def test_project_rejecting_playback_rate_stops_before_timeline_create(): ...
def test_readback_mismatch_raises_before_editing(): ...
```

Use fake Resolve objects that record `SetSetting` order. Assert format/playback calls occur before
timeline creation and that 30000/1001 remains rationally equivalent rather than becoming 30.

- [ ] **Step 2: Run tests and confirm RED**

Run: `python -m unittest scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_format_contract -v`

Expected: FAIL because `format_contract.py` is absent.

- [ ] **Step 3: Implement the format contract and route existing creators through it**

Resolve source-derived fields before project/timeline creation. Use explicit Resolve project
setting keys for timeline and playback rates, then read back project and timeline values. An
unsupported rate or mixed-rate brief without a confirmed primary source raises `ValidationError`.

- [ ] **Step 4: Run format, project/timeline and long-form tests**

Run: `python -m unittest scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_format_contract scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_project_timeline_tools scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_longform_tools -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/format_contract.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/timeline_tools.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/longform_tools.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_format_contract.py
git commit -m "fix: enforce project timeline and playback format"
```

### Task 3: Persistent render-batch manifest and approval state machine

**Files:**
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/render_batches.py`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_render_batches.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/registry.py`

**Interfaces:**
- Consumes: `EditorialBrief`, `RenderProfile`, `ResolvedFormat` from Tasks 1-2.
- Produces: `create_render_batch(brief: EditorialBrief, profile: RenderProfile, resolved_format: ResolvedFormat, project_name: str, timeline_names: tuple[str, ...], output_names: tuple[str, ...], workstation_id: str, attempt: int = 1, previous_batch_id: str | None = None) -> RenderBatch` in state `DRAFT` or `CONFIRMED`.
- Produces: `batch_fingerprint(batch: RenderBatch) -> str` using canonical JSON excluding volatile timestamps/status.
- Produces: `approve_render_batch(batch: RenderBatch, operator_role: str) -> RenderBatch` in `APPROVED` with bound token.
- Produces: `transition_batch(batch_id: str, expected: str, target: str, evidence: dict[str, Any]) -> RenderBatch`.
- Extends `Registry` with `save_brief`, `brief`, `save_render_batch`, `render_batch`, `list_render_batches`, `acquire_render_lock` and `release_render_lock`.

- [ ] **Step 1: Write failing lifecycle tests**

```python
def test_batch_transitions_are_monotonic_and_persist_across_registry_reload(): ...
def test_secretary_can_approve_standard_final_but_not_override(): ...
def test_manifest_change_invalidates_approval_token(): ...
def test_retry_creates_new_attempt_linked_to_failed_batch(): ...
def test_process_restart_reads_existing_render_lock_and_batch(): ...
```

Also reject unknown states, invalid transition edges and duplicate active locks for one project.

- [ ] **Step 2: Run lifecycle tests and confirm RED**

Run: `python -m unittest scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_render_batches.RenderBatchStateTests -v`

Expected: FAIL because batch interfaces do not exist.

- [ ] **Step 3: Implement manifest, canonical fingerprint and atomic persistence**

Add top-level `briefs`, `render_batches` and `render_locks` keys with `setdefault` migration from
registry schema v1. Keep atomic temp-file replacement. Approval tokens contain no secret and are
valid only when recomputed fingerprint and recorded token match.

- [ ] **Step 4: Run lifecycle and existing registry-dependent tests**

Run: `python -m unittest scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_render_batches scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_cleanup_tools scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_longform_tools -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/render_batches.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/registry.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_render_batches.py
git commit -m "feat: persist approved render batch lifecycle"
```

### Task 4: Prepare jobs without starting and isolate old queue entries

**Files:**
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/render_tools.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_render_batches.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_longform_exports.py`

**Interfaces:**
- Consumes: confirmed brief/batch and registries from Tasks 1-3.
- Produces: `prepare_render_batch(project: Any, config: CreativeConfig, registry: Registry, batch_id: str) -> dict[str, Any]`.
- Produces internal `_render_job_ids(project: Any) -> tuple[str, ...]` that rejects missing/duplicate IDs.
- Updates only the named batch to `PREPARED` with `queue_before`, `created_job_ids`, expected outputs and staging directory.

- [ ] **Step 1: Add failing queue-isolation tests**

```python
def test_prepare_never_calls_start_rendering(): ...
def test_existing_jobs_remain_untouched_and_outside_created_ids(): ...
def test_duplicate_or_missing_new_job_id_rolls_back_created_jobs_only(): ...
def test_partial_settings_failure_restores_original_timeline(): ...
def test_prepare_uses_batch_staging_not_delivery_directory(): ...
```

Fake Resolve must expose `GetRenderJobList`, `AddRenderJob`, `DeleteRenderJob`, timeline selection
and call logs. Include one harmless old job in every happy-path fixture.

- [ ] **Step 2: Run queue tests and confirm RED**

Run: `python -m unittest scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_render_batches.RenderBatchPreparationTests -v`

Expected: FAIL because the generic preparer is absent/current preview starts immediately.

- [ ] **Step 3: Implement queue snapshot/diff, staging and scoped rollback**

Apply the explicit `RenderProfile`, not global config format/codec. After every `AddRenderJob`,
read the queue and prove exactly one new unique ID appeared. On failure call `DeleteRenderJob`
only for IDs proven new; if deletion fails, store them as orphaned and block approval/start.

- [ ] **Step 4: Migrate legacy preparation wrappers**

Make `queue_longform_exports`, `render_preview` and `queue_publish_package_exports` prepare a
batch only. Remove `start_render` from the public publish-package path; wrappers return
`render_started: false`, `batch_id` and next action `approve_render_batch`.

- [ ] **Step 5: Run batch and long-form export tests**

Run: `python -m unittest scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_render_batches scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_longform_exports -v`

Expected: PASS and no preparation test records a `StartRendering` call.

- [ ] **Step 6: Commit**

```bash
git add scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/render_tools.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_render_batches.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_longform_exports.py
git commit -m "fix: prepare isolated render jobs without starting"
```

### Task 5: Selective start, status and cancellation

**Files:**
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/render_tools.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/render_batches.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_render_batches.py`

**Interfaces:**
- Produces: `start_render_batch(project: Any, registry: Registry, batch_id: str, approval_token: str) -> dict[str, Any]`.
- Produces: `get_render_batch_status(project: Any, registry: Registry, batch_id: str) -> dict[str, Any]`.
- Produces: `cancel_render_batch(project: Any, registry: Registry, batch_id: str, operator_role: str) -> dict[str, Any]`.

- [ ] **Step 1: Add failing start/cancel tests**

```python
def test_start_passes_only_approved_created_ids_and_never_old_ids(): ...
def test_queue_change_after_approval_is_rejected_as_stale(): ...
def test_unavailable_selective_start_fails_without_start_all_fallback(): ...
def test_active_foreign_render_blocks_start_and_cancel(): ...
def test_cancel_prepared_deletes_only_batch_jobs(): ...
```

Assert the exact call is `StartRendering(created_job_ids, False)` and that no zero-argument or
whole-queue call occurs.

- [ ] **Step 2: Run start/cancel tests and confirm RED**

Run: `python -m unittest scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_render_batches.RenderBatchExecutionTests -v`

Expected: FAIL because selective execution interfaces are absent.

- [ ] **Step 3: Implement approval revalidation, lock and selective start**

Compare current queue IDs and job settings with the approved manifest. Reject any addition,
deletion or settings change. Acquire the project lock before start, persist `RENDERING`, and
release only on terminal state/recovery. Never call broad `StartRendering()`.

- [ ] **Step 4: Implement safe cancel/status**

Prepared cancellation deletes only batch jobs. Rendering cancellation may call Resolve stop only
when the bridge owns the lock and no foreign active job exists; otherwise return a technical
recovery response without stopping.

- [ ] **Step 5: Run batch execution tests**

Run: `python -m unittest scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_render_batches -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/render_tools.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/render_batches.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_render_batches.py
git commit -m "feat: start only approved render batch jobs"
```

### Task 6: Media verification and delivery promotion

**Files:**
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/media_verification.py`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_media_verification.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/render_tools.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_render_batches.py`

**Interfaces:**
- Produces: frozen `MediaProbe(container: str, video_codec: str, width: int, height: int, frame_rate: Fraction, duration_seconds: Fraction, audio_codec: str | None, audio_sample_rate: int | None)`.
- Produces: frozen `RenderExpectation(container: str, video_codec: str, width: int, height: int, frame_rate: Fraction, duration_seconds: Fraction, audio_required: bool, audio_codec: str | None, audio_sample_rate: int | None)` derived from the approved batch, never from current defaults.
- Produces: `probe_media(path: Path) -> MediaProbe` using PyAV.
- Produces: `verify_media(probe: MediaProbe, expected: RenderExpectation) -> list[str]`.
- Produces: `expectation_from_batch(batch: RenderBatch) -> RenderExpectation`.
- Produces: `verify_and_promote_batch(project: Any, config: CreativeConfig, registry: Registry, batch_id: str) -> dict[str, Any]`.

- [ ] **Step 1: Write failing verification tests**

```python
def test_probe_reads_existing_video_fixture_without_decoding_frames(): ...
def test_fractional_frame_rate_compares_rationally(): ...
def test_wrong_resolution_codec_duration_or_missing_audio_blocks_delivery(): ...
def test_failed_verify_retains_staging_and_marks_batch_failed(): ...
def test_verified_file_moves_atomically_and_collision_is_rejected(): ...
def test_restart_can_verify_existing_rendering_batch_without_requeue(): ...
```

Use the tracked carrier video only for real metadata probing; use constructed `MediaProbe`
values for each failure class. Create temporary staging/delivery files for promotion tests.

- [ ] **Step 2: Run verification tests and confirm RED**

Run: `python -m unittest scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_media_verification -v`

Expected: FAIL because media verification module is absent.

- [ ] **Step 3: Implement PyAV probe and contract comparison**

Read stream metadata only. Compare frame rates as `Fraction`; duration tolerance is at most one
expected frame. Required-audio profiles reject absent audio and non-48-kHz sample rate.

- [ ] **Step 4: Implement terminal transition and promotion**

Require Resolve job completion, verify every expected file, then atomically move within the
profile render root. On cross-filesystem fallback, copy, hash-verify, then retire staging. Any
failure leaves evidence and files in staging and records `FAILED_VERIFY`.

- [ ] **Step 5: Run media and batch tests**

Run: `python -m unittest scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_media_verification scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_render_batches -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/media_verification.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/render_tools.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_media_verification.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_render_batches.py
git commit -m "feat: verify and promote render batch outputs"
```

### Task 7: Closed MCP workflow and render-batch surface

**Files:**
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/audit.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/server.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/tool_catalog.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_audit.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_safety.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_longform_exports.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/README.md`

**Interfaces:**
- Exposes: `list_editorial_workflows`, `validate_editorial_brief`, `prepare_render_batch`, `approve_render_batch`, `start_render_batch`, `get_render_batch_status`, `verify_render_batch`, `cancel_render_batch`.
- Removes public immediate-start semantics from `render_preview` and `queue_publish_package_exports`.
- Does not expose arbitrary render settings, queue deletion or start-all tools.

- [ ] **Step 1: Add failing catalog and annotation tests**

```python
def test_render_tools_expose_closed_prepare_approve_start_verify_surface(): ...
def test_no_tool_has_start_render_default_or_arbitrary_render_settings(): ...
def test_prepare_and_approve_are_safe_writes_start_and_cancel_are_explicit_writes(): ...
def test_workflow_listing_contains_no_local_brief_or_media_content(): ...
def test_batch_audit_records_role_transition_fingerprint_and_job_ids_but_no_paths_or_content(): ...
```

Update catalog parity assertions so missing/extra MCP functions fail.

- [ ] **Step 2: Run safety tests and confirm RED**

Run: `python -m unittest scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_audit scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_safety scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_longform_exports -v`

Expected: FAIL until the MCP surface is migrated.

- [ ] **Step 3: Implement thin server adapters and compatibility responses**

Adapters load config/registry/registries, validate input and delegate. Old queue tools may return a
deprecation note plus prepared `batch_id`, but they may not accept `start_render` or start jobs.
Extend the existing sanitized audit writer with batch ID, action, actor role, transition,
fingerprint and Resolve job IDs; never log media paths, brief text, review text, secrets or tokens.
Update README with the required app-schema refresh.

- [ ] **Step 4: Run the complete Creative suite**

Run: `python -m unittest discover -s scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests -v`

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/audit.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/server.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/tool_catalog.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_audit.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_safety.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_longform_exports.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/README.md
git commit -m "feat: expose approved render batch workflow"
```

### Task 8: Operator documentation and pending live gates

**Files:**
- Create: `docs/18_EDITORIAL_WORKFLOWS_AND_RENDER_DELIVERY.md`
- Modify: `docs/04_LONGFORM_WORKFLOW.md`
- Modify: `docs/11_CREATIVE_BRIDGE_AND_E09.md`
- Modify: `docs/16_INSTAGRAM_REVIEW_REEL_STANDARD.md`
- Modify: `CURRENT_STATE.md`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Documents: recognition/confirmation, nine common questions, role boundaries, four workflows,
  playback FPS invariant, prepare/approve/start/verify commands and rollback outcomes.
- Records: code tests separately from `PC_PERSONALE` and `PC_SEGRETERIA` live evidence.

- [ ] **Step 1: Write the operator and technical runbook**

Include one secretary example per workflow and one ambiguous-request menu example. Use “playback
FPS” for Resolve playback and “review render” for a file; never use bare “preview” for both.

- [ ] **Step 2: Document migration and rollback**

Mark immediate-start examples obsolete. Document `FAILED_PREPARE`, `FAILED_RENDER`,
`FAILED_VERIFY`, orphaned-job recovery, staging retention and the rule against clearing the full
queue.

- [ ] **Step 3: Add PENDING per-PC acceptance checklist**

For each PC, require: profile identity, format/playback read-back, harmless old queue job,
prepare, approval, selective start, media verification and proof the old job remained untouched.
Do not mark either workstation PASS from automated tests.

- [ ] **Step 4: Run final automated verification**

Run:

```bash
python -m unittest discover -s scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests -v
python -m unittest discover -s scripts/windows_bridge/tests -v
git diff --check
```

Expected: all Creative tests pass; Windows suite passes with only the known CurrentUser DPAPI
environment skip if the sandbox token still lacks that profile; diff check is clean.

- [ ] **Step 5: Perform whole-branch review**

Review from the spec commit to `HEAD`, focusing on implicit defaults, broad queue operations,
stale approval, partial cleanup and claims of unperformed workstation validation. Fix every
Critical/Important finding and rerun Step 4.

- [ ] **Step 6: Commit**

```bash
git add docs/18_EDITORIAL_WORKFLOWS_AND_RENDER_DELIVERY.md docs/04_LONGFORM_WORKFLOW.md docs/11_CREATIVE_BRIDGE_AND_E09.md docs/16_INSTAGRAM_REVIEW_REEL_STANDARD.md CURRENT_STATE.md CHANGELOG.md
git commit -m "docs: standardize editorial render operations"
```

## Completion Boundary

The implementation is complete in code when Tasks 1-8 pass and review findings are resolved.
Real rollout remains incomplete until each workstation independently records its PENDING gates.
Do not install, restart tasks, refresh the ChatGPT app schema or run a live render without a
separate explicit workstation action.
