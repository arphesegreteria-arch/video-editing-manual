# ARPHE Colorist Technical Corrections V2 Design

## Intent

Replace the misleading single-grade multicamera path with an auditable technical-normalization
workflow. Each selected clip receives its own bounded correction, derived from explicit human or
offline measurements, while Resolve writes remain approval-bound, reversible local color versions.

## Goals

- Preserve the existing non-destructive prepare, approve, apply, preview, restore and review flow.
- Bind white-balance, exposure, contrast and saturation observations to each selected clip.
- Build and fingerprint one bounded ASC-CDL payload per clip.
- Treat a reference clip as a comparison target, not as a grade to copy blindly.
- Apply every V2 technical correction directly and record the exact CDL identity in evidence.
- Keep existing V1 Colorist records readable and reviewable without silently reinterpreting them.
- Report whether a plan is `PER_CLIP_MEASURED`, `UNIFORM_MANUAL`, or legacy copy behavior.

## Non-goals

- Automatic scene understanding, skin detection, or claims of objective color correctness.
- Reading arbitrary files, moving the Resolve playhead, rendering, or saving a project.
- Applying signature ADV looks; those remain a later, separately approved phase.
- Replacing scopes or a human colorist for the final visual decision.

## Public preparation contract

`prepare_colorist_plan` keeps the existing global `adjustments` input and adds two optional closed
inputs:

- `adjustments_by_clip`: exact map from every selected clip ID to its bounded corrections;
- `observations_by_clip`: exact map from every selected clip ID to technical evidence used to choose
  those corrections.

When `adjustments_by_clip` is supplied it must cover the selected clips exactly. Every entry supports
the existing five controls: `temperature`, `tint`, `exposure_stops`, `contrast`, and `saturation`.
The global `adjustments` must then be empty, preventing two competing sources of truth.

`observations_by_clip` is required for per-clip measured plans and accepts only:

- `source`: `SCOPES` or `REGISTERED_STILL`;
- `sample_frames`: one to three non-negative integer frame numbers;
- optional `neutral_rgb`: three finite normalized values in `[0, 1]`;
- optional `luma_percentiles`: three finite normalized values `p10 < p50 < p90`;
- optional `mean_saturation`: one finite normalized value in `[0, 1]`.

At least one optional measurement is required per clip. The bridge binds these observations to the
fingerprint but does not claim they prove correctness or derive unreviewed adjustments from them.

If `adjustments_by_clip` is absent, the existing global adjustment is expanded to every target and
the plan is labelled `UNIFORM_MANUAL`. This path remains useful for one clip or already homogeneous
material but is never reported as multicamera matching.

## Job compatibility

New records use plan schema `ARPHE_COLORIST_PLAN_V2` and store `adjustments_by_clip`,
`observations_by_clip`, `cdl_by_clip`, and `matching_strategy`. The existing global `adjustments` and
`cdl` fields remain in the persisted model only to decode V1 records.

Legacy records without a plan schema are decoded as `ARPHE_COLORIST_PLAN_V1`. Their original
fingerprints are verified with the original V1 payload. They remain inspectable, previewable and
reviewable. A V1 `PREPARED` or `APPROVED` plan is not upgraded or applied as V2; the operator must
cancel it and prepare a fresh V2 plan. This avoids changing an already approved fingerprint.

## Apply semantics

For V2, the adapter creates every local version first, then calls `SetCDL` with that clip's exact
payload. Optional allowlisted DRX is applied independently after the technical CDL on each selected
clip. `CopyGrades` is not used by V2. Read-back still verifies the active version for every target.

Each apply-evidence record includes `matching_strategy`, `cdl_sha256`, and
`cdl_applied_directly=true`. Evidence must cover the selected clips exactly and its CDL digest must
match the fingerprint-bound payload for that clip.

V1 apply behavior remains only for already persisted V1 records and is not exposed as successful
V2 matching.

## Review

The existing before/after version toggle and mandatory restore remain unchanged. Inspection returns
the strategy, per-clip adjustments, observations, and CDL digests so the reviewer can compare each
camera against the named reference. Acceptance still requires every preview to be restored.

## Safety and verification

- `CAP_COLORIST=false` remains the default and no test connects to Resolve.
- All new values are finite, bounded, closed-schema data.
- Clip-map keys must exactly equal `clip_ids`; unknown, missing, duplicate or malformed evidence
  fails before persistence or Resolve access.
- Tests prove V1 decoding/fingerprint preservation, V2 per-clip fingerprinting, direct per-clip
  application, no `CopyGrades`, rollback, stale-context rejection and human-review invariants.
- Native validation remains a later consented gate on a disposable project.
