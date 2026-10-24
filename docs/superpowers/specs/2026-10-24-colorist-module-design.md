# ARPHE Colorist Module Design

## Intent

Add a guarded Colorist workflow to the ARPHE Resolve bridge so a human editor can prepare, approve, apply, compare, and review bounded color changes without overwriting the existing grade. The module is for technical normalization first and an optional ARPHE look second.

## Goals

- Work only on the current allowlisted ARPHE project and timeline.
- Preserve the existing grade in its current local color version.
- Express white balance, exposure, contrast, and saturation as bounded ASC-CDL values.
- Support multicamera matching by copying a reviewed reference grade to explicit target clip IDs.
- Offer allowlisted ARPHE presets and optional allowlisted DRX looks.
- Require a fingerprint-bound human approval before any Resolve write.
- Expose before/after version switching for human review without rendering or saving.
- Fail closed on stale project, timeline, clip set, plan, approval, or API capability.

## Non-goals

- Automatic scene understanding, skin-tone detection, or claims of objective white balance.
- Arbitrary node editing, LUT paths, DRX paths, filesystem access, render, or project save.
- Editing a live project during development or validation.
- Replacing a professional colorist or judging creative intent without human review.

## Constraints

- Resolve Studio 21.1.1 is currently live and being edited from another chat; development and automated tests must not connect to it.
- Native validation must happen later on a disposable ARPHE project with explicit consent.
- The installed Resolve 21 stubs confirm `TimelineItem.AddVersion`, `LoadVersionByName`, `GetVersionNameList`, `GetCurrentVersion`, `SetCDL`, `CopyGrades`, `GetNodeGraph`, `Graph.ApplyGradeFromDRX`, and `Timeline.GetCurrentClipThumbnailImage`.
- The public API does not expose Resolve's full primary-wheel or automatic color-match controls. White balance, exposure, and contrast are therefore conservative deterministic mappings into CDL, clearly reported as approximations.

## Chosen approach

### Considered

1. CDL-only: safest and portable, but cannot carry a richer authored look.
2. DRX-only: preserves authored node graphs, but is unsuitable for bounded technical normalization and depends on external assets.
3. CDL technical base plus optional allowlisted DRX look: selected because it separates correction from style and keeps DRX optional.

## Workflow

1. `inspect_colorist_context` lists supported API capabilities and stable clip IDs without writing.
2. `prepare_colorist_plan` validates explicit clip IDs, correction values, preset name, optional DRX preset role, and optional reference clip. It stores an immutable fingerprint-bound plan locally, including the relative path, byte size, and SHA-256 identity of an optional DRX asset.
3. `approve_colorist_plan` accepts the plan fingerprint and an allowed human role. It performs no Resolve write.
4. `apply_colorist_plan` revalidates workstation, registered/allowlisted project and timeline, clip IDs, current versions, plan fingerprint, optional DRX identity, and capability flag. It persists `APPLYING` before the first Resolve write. Each target receives a new collision-free local color version. CDL is applied on node 1; an optional configured DRX is then applied to that version. For matching, the reference grade is copied only to targets whose new versions were created successfully.
5. `preview_colorist_version` loads only the recorded before or after local version for one plan-owned clip. This is a reversible UI-visible write and never captures, renders, or saves.
6. `restore_colorist_preview` restores the persistent pre-preview version of one explicit clip, leaving every other clip unchanged.
7. `submit_colorist_review` records an explicit human accept/reject decision only after all tracked previews have been restored. It does not delete versions or save the project.

## Safety and recovery

- `CAP_COLORIST` is implemented but disabled by default and remains `PENDING` until a native disposable-project gate passes.
- Plans bind workstation, project name, timeline name and identity, clip IDs, current versions, exact adjustments, presets, optional DRX content identity, and fingerprint.
- ARPHE-looking names are not authorization. The project and timeline must be bridge-registered or explicitly allowlisted.
- No tool accepts a raw DRX or LUT path. DRX files come only from a configured registry under the allowlisted asset root.
- Version collisions stop before changing that clip; existing versions are never overwritten or deleted.
- Partial failure returns exact per-clip evidence and restores each clip's previously active version where possible. Complete restoration persists `FAILED_RECOVERABLE`; incomplete restoration persists `FAILED_MANUAL`. It never resets grades. An interrupted final persistence leaves the durable job in `APPLYING` for manual reconciliation rather than blind retry.
- Development tests use fakes and temporary files only.

## Presets

The initial preset registry contains three conservative, explicitly experimental looks: `ARPHE_CLEAN_NEUTRAL`, `ARPHE_WARM_PRESENCE`, and `ARPHE_SOFT_LUXURY`. Preset numbers remain data, not code. A preset is not promoted to production until visual review on controlled charts and representative ARPHE footage.

## Verification

- Unit tests validate numeric bounds, deterministic CDL mapping, canonical fingerprints, state transitions, stale-target rejection, collision handling, rollback, multicamera copying, preset allowlisting, and closed tool signatures.
- Offline integration tests exercise the MCP surface with fake Resolve objects.
- Native verification is a separate, consented gate on a disposable project; no live-project testing is part of this implementation.

