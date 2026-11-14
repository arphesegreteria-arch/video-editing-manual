# Timeline Element Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add generic, typed bridge tools to inspect and reversibly enable/disable one exact Resolve timeline item, plus two-phase non-ripple removal restricted to proven bridge-owned items.

**Architecture:** A focused workstation-scoped JSON store persists short-lived inspection handles, bridge ownership records, removal proposals, and durable removal intents. Live Resolve items are always re-matched and fingerprinted immediately before mutation; server wrappers execute under the existing Resolve access lock and expose no raw names, paths, or arbitrary properties.

**Tech Stack:** Python 3.12, FastMCP, DaVinci Resolve scripting API, `unittest`, atomic JSON files using `tempfile`/`os.replace`.

**Spec:** `docs/superpowers/specs/2026-11-14-timeline-element-control-design.md`

## Global Constraints

- Do not implement bridge restart, Resolve restart, or a Windows service.
- One handle controls exactly one `TimelineItem`; linked audio/video peers are reported but never mutated implicitly.
- Disable/enable may target any fresh, unambiguous item on the current allowed project/timeline.
- Removal is non-ripple and is allowed only for an exact active ownership record created by the bridge.
- Historical or duplicated items without exact ownership proof remain disable/re-enable only.
- Every write is refused on a picture-locked workflow in this first release.
- No tool accepts project name, timeline name, item name, path, raw Resolve ID, or arbitrary property as a mutation selector.
- State and ownership never cross `workstation_id` boundaries.
- No dependency additions and no per-video command names.

## Review Focus

- Resolve returns two indistinguishable items in one track/range: inspection may list them, but mutation must fail closed on ambiguous rematch; Task 2 pins this.
- A handle expires between inspection and mutation: the operation must fail without calling Resolve; Task 2 pins this.
- `DeleteClips` succeeds and the process loses its response before commit: recovery must finalize the same receipt rather than delete another item; Task 3 pins this.
- A duplicated or renamed clip resembles a bridge-owned item: name/range similarity must not grant removal; Task 3 pins this.
- A workflow becomes picture-locked after inspection: every later write must re-check the live lock and refuse; Task 2 and Task 3 pin this.

---

### Task 1: Timeline element records and atomic workstation store

**Files:**
- Create: `bridge/timeline_element_control.py`
- Create: `tests/test_timeline_element_control.py`

**Interfaces:**
- Produces: `TimelineElementSnapshot`, `TimelineElementStore`, `snapshot_fingerprint`, `store_for_config`, ownership/handle/proposal persistence methods used by all later tasks.
- Consumes: `ValidationError` from `bridge.safety` and `safe_call` from `bridge.resolve_connection`.

- [ ] **Step 1: Write failing record and store tests**

Add tests named:

- `test_snapshot_fingerprint_is_deterministic_and_changes_for_every_identity_field`
- `test_store_rejects_foreign_workstation_file`
- `test_handle_expires_and_cannot_be_reused_as_live`
- `test_ownership_requires_exact_project_timeline_track_range_and_media_identity`
- `test_proposal_is_single_use_and_persists_durable_intent`
- `test_atomic_store_preserves_previous_file_when_replace_fails`

Assert that a snapshot contains exactly workstation, project, timeline, media type, track, start/end, duration, sanitized name, media identity, and enabled state; persisted records never contain a source filesystem path.

- [ ] **Step 2: Run the focused tests and verify failure**

Run: `python -m unittest tests.test_timeline_element_control -v`

Expected: FAIL because `bridge.timeline_element_control` does not exist.

- [ ] **Step 3: Implement the immutable snapshot and fingerprint API**

In `bridge/timeline_element_control.py`, add:

```python
@dataclass(frozen=True)
class TimelineElementSnapshot: ...

def snapshot_fingerprint(snapshot: TimelineElementSnapshot) -> str: ...
def capture_item_snapshot(workstation_id: str, project: object, timeline: object,
                          media_type: str, track_index: int, item: object) -> TimelineElementSnapshot: ...
```

Use canonical sorted JSON and SHA-256. Derive media identity from documented Resolve media metadata/ID through `safe_call`; sanitize display names and never persist paths.

- [ ] **Step 4: Implement the atomic store**

Add:

```python
class TimelineElementStore:
    def __init__(self, path: Path, workstation_id: str,
                 handle_ttl_seconds: int = 300, removal_ttl_seconds: int = 600): ...
    def issue_handle(self, snapshot: TimelineElementSnapshot, related: tuple[str, ...] = ()) -> dict[str, object]: ...
    def require_handle(self, element_id: str, fingerprint: str, now: datetime) -> dict[str, object]: ...
    def register_ownership(self, snapshot: TimelineElementSnapshot,
                           action: str, native_reference: str) -> dict[str, object]: ...
    def matching_ownership(self, snapshot: TimelineElementSnapshot) -> dict[str, object] | None: ...
    def prepare_removal(self, handle: dict[str, object], ownership: dict[str, object],
                        now: datetime) -> dict[str, object]: ...
    def begin_removal(self, removal_id: str, proposal_fingerprint: str,
                      operator_role: str, now: datetime) -> dict[str, object]: ...
    def complete_removal(self, removal_id: str, receipt: dict[str, object], now: datetime) -> dict[str, object]: ...
```

Use schema `ARPHE_TIMELINE_ELEMENT_CONTROL_V1`, random opaque UUID-based IDs, allowlisted roles already used by bridge approval flows, atomic `os.replace`, and the existing per-path locking convention or a focused equivalent.

- [ ] **Step 5: Run the focused tests**

Run: `python -m unittest tests.test_timeline_element_control -v`

Expected: all Task 1 tests PASS.

- [ ] **Step 6: Commit the core store**

```bash
git add bridge/timeline_element_control.py tests/test_timeline_element_control.py
git commit -m "feat: add timeline element control store"
```

### Task 2: Live inspection and reversible enable state

**Files:**
- Modify: `bridge/timeline_element_control.py`
- Modify: `tests/test_timeline_element_control.py`

**Interfaces:**
- Consumes: Task 1 snapshots, fingerprints, and `TimelineElementStore`.
- Produces: `inspect_elements`, `set_element_enabled`, `timeline_is_picture_locked`, and exact live rematching for Task 3 and server wrappers.

- [ ] **Step 1: Write failing live-operation tests**

Add Resolve fakes and tests named:

- `test_inspection_returns_opaque_handles_and_sanitized_fields_for_each_track_item`
- `test_inspection_reports_linked_peer_without_grouping_mutations`
- `test_disable_and_enable_are_idempotent_and_verified_by_readback`
- `test_repeat_request_accepts_only_enabled_state_drift_to_the_requested_value`
- `test_mutation_rejects_expired_handle_before_set_clip_enabled`
- `test_mutation_rejects_ambiguous_live_rematch`
- `test_mutation_rejects_changed_project_timeline_track_range_media_name_or_enabled_state`
- `test_mutation_rechecks_picture_lock_after_inspection`
- `test_inspection_does_not_grant_remove_from_arphe_name_alone`

The fake item must expose `GetStart`, `GetEnd`, `GetDuration`, `GetName`, `GetMediaPoolItem`, `GetClipEnabled`, and `SetClipEnabled`.

- [ ] **Step 2: Run the new tests and verify failure**

Run: `python -m unittest tests.test_timeline_element_control.TimelineElementLiveTests -v`

Expected: FAIL because the live functions are absent.

- [ ] **Step 3: Implement inspection and exact rematching**

Add:

```python
def inspect_elements(project: object, timeline: object, config: CreativeConfig,
                     registry: Registry, store: TimelineElementStore,
                     media_type: str | None = None, track_index: int | None = None,
                     start_frame: int | None = None, end_frame: int | None = None,
                     now: datetime | None = None) -> dict[str, object]: ...

def rematch_live_item(project: object, timeline: object,
                      handle: dict[str, object]) -> tuple[object, TimelineElementSnapshot]: ...
```

Validate current project/timeline with the existing allowlist logic. Bound media type to `video|audio`, track to a positive integer, and frame filters to a valid ordered range. Search only the bound track and require one exact snapshot match for mutation.

- [ ] **Step 4: Implement picture-lock detection and reversible mutation**

Add:

```python
def timeline_is_picture_locked(config: CreativeConfig, project_name: str,
                               timeline_name: str) -> bool: ...

def set_element_enabled(project: object, timeline: object, config: CreativeConfig,
                        registry: Registry, store: TimelineElementStore,
                        element_id: str, fingerprint: str, enabled: bool,
                        now: datetime | None = None) -> dict[str, object]: ...
```

Revalidate handle and lock immediately before mutation. Treat already-satisfied state as idempotent success only when every identity field still matches and the sole fingerprint drift is `enabled == requested`; any other state drift is stale. Otherwise call only `SetClipEnabled(bool)`, read back `GetClipEnabled`, and fail if unsupported or mismatched.

- [ ] **Step 5: Run focused tests**

Run: `python -m unittest tests.test_timeline_element_control.TimelineElementLiveTests -v`

Expected: all Task 2 tests PASS.

- [ ] **Step 6: Commit inspection and reversible control**

```bash
git add bridge/timeline_element_control.py tests/test_timeline_element_control.py
git commit -m "feat: inspect and toggle timeline elements"
```

### Task 3: Ownership-gated two-phase non-ripple removal

**Files:**
- Modify: `bridge/timeline_element_control.py`
- Modify: `tests/test_timeline_element_control.py`

**Interfaces:**
- Consumes: Task 2 `rematch_live_item`, `timeline_is_picture_locked`, and Task 1 store transactions.
- Produces: `prepare_element_removal`, `execute_element_removal`, and crash-recovery receipts.

- [ ] **Step 1: Write failing removal tests**

Add tests named:

- `test_prepare_removal_requires_exact_active_ownership_not_name_similarity`
- `test_prepare_removal_refuses_historical_and_duplicated_unregistered_items`
- `test_execute_removal_rechecks_picture_lock_and_live_fingerprint`
- `test_execute_removal_calls_delete_clips_once_with_one_item_and_ripple_false`
- `test_execute_removal_verifies_target_absent_and_neighbour_ranges_unchanged`
- `test_execute_removal_does_not_consume_proposal_when_resolve_delete_fails`
- `test_execute_removal_recovers_committed_delete_after_lost_response`
- `test_execute_removal_never_redirects_to_replacement_item`
- `test_completed_removal_returns_same_idempotent_receipt`

- [ ] **Step 2: Run removal tests and verify failure**

Run: `python -m unittest tests.test_timeline_element_control.TimelineElementRemovalTests -v`

Expected: FAIL because removal functions are absent.

- [ ] **Step 3: Implement preparation**

Add:

```python
def prepare_element_removal(project: object, timeline: object, config: CreativeConfig,
                            registry: Registry, store: TimelineElementStore,
                            element_id: str, fingerprint: str,
                            now: datetime | None = None) -> dict[str, object]: ...
```

Require fresh exact rematch, no picture lock, and exact active ownership. Return only `removal_id`, proposal fingerprint, expiry, and sanitized preview; perform no Resolve write.

- [ ] **Step 4: Implement durable execution and recovery**

Add:

```python
def execute_element_removal(project: object, timeline: object, config: CreativeConfig,
                            registry: Registry, store: TimelineElementStore,
                            removal_id: str, proposal_fingerprint: str,
                            operator_role: str,
                            now: datetime | None = None) -> dict[str, object]: ...
```

Persist intent before calling `DeleteClips([item], False)`. Snapshot neighbouring items before deletion, then verify exact target absence and unchanged neighbour ranges. On a resumed intent, finalize the original receipt only when the target is absent and invariants match; ambiguous state becomes blocked and never retries against another item.

- [ ] **Step 5: Run focused removal tests**

Run: `python -m unittest tests.test_timeline_element_control.TimelineElementRemovalTests -v`

Expected: all Task 3 tests PASS.

- [ ] **Step 6: Commit two-phase removal**

```bash
git add bridge/timeline_element_control.py tests/test_timeline_element_control.py
git commit -m "feat: remove owned timeline elements safely"
```

### Task 4: Register ownership from reusable creation paths

**Files:**
- Modify: `bridge/timeline_element_control.py`
- Modify: `bridge/fusion_tools.py`
- Modify: `bridge/asset_tools.py`
- Modify: `bridge/vertical_social_captions.py`
- Modify: `bridge/vertical_social_broll.py`
- Modify: `tests/test_fusion_graph.py`
- Modify: `tests/test_asset_tools.py`
- Modify: `tests/test_vertical_social_captions.py`
- Modify: `tests/test_vertical_social_broll.py`
- Modify: `tests/test_timeline_element_control.py`

**Interfaces:**
- Consumes: Task 1 `TimelineElementStore.register_ownership` and snapshot capture.
- Produces: `register_created_item`, called only after successful Resolve read-back by generic bridge creation paths.

- [ ] **Step 1: Write failing ownership integration tests**

For each creation family, add an assertion that successful creation persists one exact ownership record with its generic action and native reference. Add failure tests proving no ownership is registered before read-back and registry-write failure never reports the element as removable.

Cover Fusion composition/carrier, image/video/logo assets and music bed where represented by an item, vertical-social caption overlay, and vertical-social B-roll insert.

- [ ] **Step 2: Run integration tests and verify failure**

Run: `python -m unittest tests.test_fusion_graph tests.test_asset_tools tests.test_vertical_social_captions tests.test_vertical_social_broll -v`

Expected: FAIL because creation paths do not register timeline ownership.

- [ ] **Step 3: Add the shared registration helper**

Add:

```python
def register_created_item(config: CreativeConfig, project: object, timeline: object,
                          media_type: str, track_index: int, item: object,
                          action: str, native_reference: str) -> dict[str, object]: ...
```

Construct the workstation store from config, capture the live item after creation, persist exact ownership, and return an opaque ownership ID for internal evidence only.

- [ ] **Step 4: Integrate registration after verified creation**

Call the helper only after each reusable creation path has obtained and read back the created item. Propagate registry persistence failure as a recoverable creation error so the result never claims a removable owned element. Do not infer ownership for pre-existing items and do not broaden any existing delete behaviour.

- [ ] **Step 5: Run ownership integration tests**

Run: `python -m unittest tests.test_fusion_graph tests.test_asset_tools tests.test_vertical_social_captions tests.test_vertical_social_broll tests.test_timeline_element_control -v`

Expected: all targeted tests PASS.

- [ ] **Step 6: Commit ownership integration**

```bash
git add bridge/timeline_element_control.py bridge/fusion_tools.py bridge/asset_tools.py bridge/vertical_social_captions.py bridge/vertical_social_broll.py tests
git commit -m "feat: register bridge-owned timeline elements"
```

### Task 5: Configuration, MCP wrappers, catalog, audit, and full verification

**Files:**
- Modify: `bridge/config.py`
- Modify: `creative_config.example.json`
- Modify: `bridge/server.py`
- Modify: `bridge/tool_catalog.py`
- Modify: `bridge/audit.py`
- Create: `tests/test_config.py`
- Modify: `tests/test_project_timeline_tools.py`
- Modify: `tests/test_safety.py`
- Create: `docs/resolve-bridge-learnings.md`

**Interfaces:**
- Consumes: Tasks 1–4 public functions.
- Produces: four FastMCP tools: `inspect_timeline_elements`, `set_timeline_element_enabled`, `prepare_timeline_element_removal`, `execute_timeline_element_removal`.

- [ ] **Step 1: Write failing configuration and MCP contract tests**

Add tests asserting:

- `CAP_TIMELINE_ELEMENT_CONTROL` exists and defaults false;
- config provides `timeline_element_control_path`, handle TTL `300`, and proposal TTL `600`, rejecting booleans, non-integers, and values outside conservative bounds;
- the four names exist exactly once in `EXPOSED_TOOL_NAMES` and match decorated tools;
- wrappers hold `RESOLVE_ACCESS_LOCK`, call the typed module functions, and return sanitized errors;
- writes fail before Resolve access when the gate is false;
- destructive annotation is used only for execution, while preparation is read-only and enable state is idempotent write;
- audit includes only opaque `element_id`/`removal_id`, target fingerprint, action result, and workstation—not names or paths.

- [ ] **Step 2: Run contract tests and verify failure**

Run: `python -m unittest tests.test_config tests.test_project_timeline_tools tests.test_safety -v`

Expected: FAIL because config, wrappers, catalog entries, and audit fields are absent.

- [ ] **Step 3: Add validated configuration**

Extend `CreativeConfig`, `CAPABILITY_NAMES`, `DEFAULT_FLAGS`, loader validation, and the example config with the new gate, workstation-scoped JSON path, and fixed bounded TTL settings. Keep the gate false in the repository example.

- [ ] **Step 4: Add the four server wrappers and annotations**

Each wrapper obtains the current runtime under `RESOLVE_ACCESS_LOCK`, enforces existing project/timeline allowlisting and the new gate for writes, constructs the store from config, calls one typed operation, and routes the result through the existing sanitized `_call`/`_error` and audit path.

- [ ] **Step 5: Update the catalog, forbidden set, and audit metadata**

Add the four generic names to `EXPOSED_TOOL_NAMES`. Add raw/batch variants such as `delete_clip`, `delete_clips`, `remove_timeline_item`, and `set_any_clip_property` to `FORBIDDEN_GENERIC_TOOLS`. Extend the audit allowlist only with opaque timeline-control identifiers and fingerprints.

- [ ] **Step 6: Document the generic workflow**

In `docs/resolve-bridge-learnings.md`, document inspect → reversible toggle or prepare → execute, ownership limitations for historical/duplicated elements, picture-lock refusal, and the fact that no per-video commands are allowed.

- [ ] **Step 7: Run focused and full verification**

Run:

```bash
python -m unittest tests.test_timeline_element_control tests.test_config tests.test_project_timeline_tools tests.test_safety -v
python -m unittest discover -s tests -p "test_*.py" -v
```

Expected: all tests PASS; decorated tool names exactly match the catalog; no repository default enables the new write gate.

- [ ] **Step 8: Review the diff for forbidden scope**

Run: `git diff --check` and `git diff --stat HEAD~4..HEAD`.

Expected: no whitespace errors; no restart/service implementation, no per-video command, no arbitrary item mutation, and no production configuration change.

- [ ] **Step 9: Commit bridge exposure and documentation**

```bash
git add bridge/config.py creative_config.example.json bridge/server.py bridge/tool_catalog.py bridge/audit.py tests docs/resolve-bridge-learnings.md
git commit -m "feat: expose safe timeline element controls"
```

## Deployment boundary

Implementation completion means the repository code and tests are ready. Production mirroring, gate activation, and bridge restart are intentionally excluded while the operator is away. Later deployment must activate and smoke-test PC_PERSONALE first on a disposable bridge-owned overlay, then repeat independently on PC_SEGRETERIA.
