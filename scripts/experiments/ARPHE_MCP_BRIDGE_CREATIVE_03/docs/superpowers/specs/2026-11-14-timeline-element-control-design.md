# Generic timeline element control design

## Intent

Allow chat-driven editing to inspect, disable, re-enable, and—only when ownership is proven—remove one exact DaVinci Resolve timeline element through the ARPHE bridge. This replaces fragile screen interaction for routine element control without introducing arbitrary Resolve execution or commands dedicated to a single video.

The bridge-restart capability is explicitly deferred. This design neither installs nor changes a Windows service and does not attempt to restart the running bridge.

## Goals

- Identify one current-timeline item with an opaque `element_id` and a read-back fingerprint.
- Disable and re-enable an unambiguous item reversibly.
- Remove one item non-ripple only when the bridge can prove it owns that item.
- Reject stale handles after any relevant project, timeline, track, range, media, name, or enabled-state change.
- Keep PC_PERSONALE and PC_SEGRETERIA state isolated by `workstation_id`.
- Audit every inspection and mutation without disclosing unrestricted filesystem paths.
- Expose only generic, typed MCP tools.

## Non-goals

- Restarting the bridge or Resolve.
- Deleting timelines, projects, tracks, source media, or Drive files.
- Ripple deletion or moving neighbouring clips.
- Removing arbitrary user-created timeline items.
- Treating an `ARPHE_` name, track number, clip colour, or metadata string alone as ownership proof.
- Adding commands for one named project, timeline, clip, or video.

## Approaches considered

### Selected: opaque handles plus a workstation-scoped ownership registry

Inspection creates short-lived opaque handles bound to the exact live Resolve item and its fingerprint. A separate local registry records bridge-created elements at creation time. Disable/enable accepts any unambiguous inspected item. Removal requires both a fresh handle and a matching ownership record.

This adds a small amount of persistent state, but it provides explicit ownership, stale-write protection, auditability, and safe behaviour across both workstations.

### Rejected: identify ownership from names and timeline placement

This would be simpler and could cover historical elements immediately, but names and positions are editable and can collide. It cannot safely authorize deletion.

### Rejected: expose raw Resolve timeline-item methods

This would be flexible but would violate the bridge contract: arbitrary mutation, weak validation, no workflow boundary, and no reliable stale-state protection.

## Public tool contract

### `inspect_timeline_elements`

Read-only. Operates only on the current allowed ARPHE project and current allowed timeline. Optional bounded filters may select media type, track index, or frame window. It returns sanitized records containing:

- `element_id`: random opaque handle, never a Resolve object or filesystem path;
- `fingerprint`: SHA-256 of the immutable inspection snapshot;
- media type, track index, start/end frames, duration, sanitized display name, enabled state;
- `bridge_owned`: true only after exact ownership-registry validation;
- permitted actions: `DISABLE`, `ENABLE`, and conditionally `REMOVE`.

Ambiguous duplicate candidates remain separate because track, range, media identity, and a bridge-local handle are all bound together. Handles expire after a short configured lifetime and are scoped to one workstation.

### `set_timeline_element_enabled`

Idempotent reversible write. Inputs: `element_id`, `fingerprint`, and `enabled`.

Before calling Resolve, the bridge must re-read the current project, timeline, track, range, media identity, item name, and current enabled state. Any identity mismatch returns a stale-target error without mutation. The write uses the supported clip-enabled API and verifies the requested state by read-back. Repeating an already-satisfied request succeeds idempotently.

This action is available for an inspected user-created item because it is reversible, but only on an allowed current project/timeline and only for the exact fresh handle.

One handle controls exactly one Resolve `TimelineItem`. Linked audio/video peers are reported as sanitized related elements but are never mutated implicitly. A caller that wants both sides must inspect and act on each exact item separately; this prevents a visual-overlay operation from unexpectedly muting or deleting programme audio.

### `prepare_timeline_element_removal`

Read-only preparation. Inputs: `element_id` and `fingerprint`.

The bridge revalidates the live item and requires an exact ownership-registry record for the current workstation, project, timeline, media type, track, range, and bridge creation record. It persists a single-use removal proposal containing the expected item fingerprint and returns a `removal_id`, proposal fingerprint, and a sanitized preview. It performs no Resolve mutation.

### `execute_timeline_element_removal`

Irreversible non-ripple write. Inputs: `removal_id`, proposal fingerprint, and an allowed operator role.

The bridge revalidates the proposal, ownership, workstation, current project/timeline, and the live item fingerprint immediately before execution. It calls `DeleteClips([item], False)` for exactly one item, verifies that the exact item is absent while neighbouring items retain their ranges, marks the ownership record removed, consumes the proposal, and writes an audit receipt. Reuse is rejected or returned as an already-completed idempotent receipt; it can never target a replacement item.

## Ownership model

A new workstation-scoped registry stores bridge-created timeline elements with:

- schema version and workstation ID;
- random ownership ID;
- project and timeline identity;
- media type and track index;
- item start/end range and stable media identity where available;
- creating bridge action/job reference;
- creation fingerprint, current state, and timestamps.

Creation paths that are updated to register ownership must do so only after Resolve read-back succeeds. If registry persistence fails, the creation action reports a recoverable error and the item is not considered removable by the generic tool.

Historical items are not retroactively declared owned from naming conventions. They can be disabled/re-enabled after inspection, but generic removal remains unavailable unless an existing structured bridge record proves the exact item identity and a deliberate migration imports it.

Generic timeline duplication does not automatically propagate ownership. When a bridge-owned duplication workflow can read back a one-to-one source/destination mapping, that workflow may create new ownership records explicitly; otherwise duplicated items remain disable/re-enable only. This avoids granting deletion rights to ambiguous copies.

Registry writes use the bridge's existing atomic file-write and locking conventions. State is isolated between PC_PERSONALE and PC_SEGRETERIA.

## Safety and failure behaviour

- A dedicated `CAP_TIMELINE_ELEMENT_CONTROL` feature flag gates all writes; inspection may report the gate state.
- Existing project/timeline allowlisting remains mandatory.
- No tool accepts a project name, timeline name, item name, path, raw Resolve ID, or arbitrary property as a mutation selector.
- No delete-by-name, delete-by-track, delete-by-range, batch delete, track delete, or ripple mode is exposed.
- Every write is refused on a picture-locked workflow in the first release. There is no override token or implicit exception; a future workflow-specific unlock design is separate work.
- A Resolve API failure, missing read-back support, duplicate live match, stale fingerprint, expired handle, or ownership mismatch fails closed.
- Removal proposals expire, are single-use, and are invalidated by any live-item fingerprint change.
- Removal uses a durable intent record written before `DeleteClips`. After a crash or lost response, recovery re-reads the exact target: if it is absent and neighbouring invariants hold, the bridge finalizes the same idempotent receipt; if state is ambiguous it blocks automatic retry and requires reconciliation. It never redirects the proposal to a replacement item.
- Audit output is sanitized and records workstation, action, target fingerprint, result, and creating job reference without unrestricted paths.

## Integration

- Add a focused `timeline_element_control.py` module for handles, fingerprints, ownership records, proposals, and Resolve operations.
- Add typed wrappers in `server.py` under the existing global Resolve access lock.
- Add the four generic tool names to `tool_catalog.py`; keep `delete_timeline`, `delete_project`, raw item mutation, and generic batch deletion forbidden.
- Register ownership from reusable bridge creation paths, beginning with Fusion overlays, caption overlays, B-roll/image/video assets, logos, music beds, and other bridge-owned inserts covered by tests.
- Add a workstation-scoped registry path and handle/proposal TTLs to validated configuration.
- Document the generic workflow in bridge learnings; do not add per-video commands.

## Verification

- Unit-test fingerprint determinism, handle expiry, workstation isolation, atomic persistence, and proposal single use.
- Verify disable, repeated disable, enable, and repeated enable with Resolve fakes and state read-back.
- Verify stale rejection after changes to project, timeline, track, range, media identity, name, or enabled state.
- Verify user-created elements never receive `REMOVE` and cannot prepare removal.
- Verify name-only ownership spoofing is rejected.
- Verify removal calls exactly `DeleteClips([item], False)`, never ripple mode, and checks neighbouring items.
- Verify API failure and ambiguous matching produce no mutation.
- Verify the exposed-tool catalog exactly matches decorated tools and contains no generic arbitrary mutation.
- Run the complete bridge test suite before deployment.
- Deployment and production activation remain separate: deploy to one workstation, restart by the existing operator procedure, smoke-test on a disposable bridge-owned overlay, then repeat on the other workstation when available.

## Builder decisions left open

- Choose the exact small TTL values for inspection handles and removal proposals within a conservative range.
- Reuse the existing atomic JSON-store pattern or extract a shared helper if that reduces duplication without broad refactoring.
- Choose which already-structured creation records can be imported safely in the first release; anything uncertain remains non-removable.
