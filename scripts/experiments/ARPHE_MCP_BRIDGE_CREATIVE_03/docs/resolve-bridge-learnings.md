# Resolve bridge learnings

## Generic timeline element control

Use one generic workflow for timeline-item control. Never add an MCP command, preset, project name, timeline name, or video identifier dedicated to a single edit.

1. Call `inspect_timeline_elements` on the current allowlisted project and timeline. Optional filters may restrict media type, track, or frame range. The result contains short-lived opaque handles; it does not expose source paths or raw Resolve IDs.
2. For a reversible change, call `set_timeline_element_enabled` with exactly the returned `element_id` and fingerprint. One handle affects one TimelineItem only. Linked audio/video peers are reported but are never changed implicitly.
3. For permanent removal, call `prepare_timeline_element_removal`, then `execute_timeline_element_removal` with the opaque proposal and an allowlisted operator role. Execution is always `DeleteClips([item], False)` and verifies target absence plus unchanged neighbouring ranges.

Permanent removal is available only when the bridge recorded exact ownership after a successful creation read-back. Historical items, manually created items, renamed lookalikes, and generic duplicates are not retroactively owned; they remain eligible only for disable/re-enable. Duplication does not propagate ownership unless a future workflow proves an exact one-to-one mapping.

Every mutation revalidates the current project, timeline, track, range, media identity, display name, state, handle lifetime, workstation, and picture-lock status. Any ambiguity or drift fails closed. A resumed durable removal intent may finalize the original receipt only when the original target is absent and neighbour invariants still match; it never retries against a replacement.

`CAP_TIMELINE_ELEMENT_CONTROL` gates all writes and defaults to `false`. The repository example does not activate it. Deployment, workstation-specific activation, and bridge restart are separate operator steps: validate PC_PERSONALE first on a disposable bridge-owned overlay, then validate PC_SEGRETERIA independently.
