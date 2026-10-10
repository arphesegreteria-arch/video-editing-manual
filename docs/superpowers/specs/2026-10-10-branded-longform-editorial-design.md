# Branded Longform Editorial — Design

**Date:** 2026-10-10  
**Status:** approved in conversation; implementation plan pending review.

## Intent

`BRANDED_LONGFORM_EDITORIAL` is the common assisted longform engine for distinct
brands.  It must support an ARPHE longform whose visual source of truth is the
ARPHE Graphic Kit, and a Studio Carabellese longform whose Graphic Kit will
arrive later.  It is not an ARPHE-only workflow and must not leak one brand's
styling or learned preferences into another brand.

The workflow makes an immediately listenable provisional edit first, then
proposes editorial interventions.  It does not silently make creative choices.

## Profiles and kits

The profiles are:

- `ARPHE_LONGFORM_EDITORIAL`: `kit_status=READY`; may use only the registered
  ARPHE Graphic Kit, approved user-provided B-roll and approved existing assets.
- `CARABELLESE_LONGFORM_EDITORIAL`: `kit_status=PENDING`; may clean up,
  transcribe, create markers and propose interventions, but must not apply
  ARPHE styling or substitute unbranded graphics until its own kit is connected.

Profile selection is inferred only from explicit brief/project/path hints.  If
the result is ambiguous, the bridge returns the compact choice menu rather than
guessing.  Profile preferences and learning are strictly namespaced.

## OBS and audio inputs

The engine accepts either a normal single source or an OBS multicamera package:

- `PROGRAM`: composite reference video and the sole final/master audio;
- `CAM_A`, `CAM_B`, …: isolated camera videos; their duplicated master audio is
  guide audio used only for synchronization;
- optional manifest naming source identities and expected frame rate.

The package validator requires one `PROGRAM`, unique camera labels and a
consistent source frame rate.  It aligns cameras against guide audio when
available, otherwise marks synchronization as review-required; it never
pretends a camera is synchronized.  Camera audio is never selected for final
delivery.  The traditional single-video input remains fully supported.

## Timeline lifecycle

The original timeline is immutable to this workflow:

`ORIGINAL -> <name>_CLEANUP -> <name>_EDITORIAL`.

The cleanup copy is the first listenable output.  The editorial copy is created
only after the operator approves a batch of proposals.  Every write has a
verified checkpoint, job ID, revision, source/timeline fingerprint and
operation journal.  A changed source, contract, selected profile or original
timeline invalidates pending approval.  Rollback restores the owned derived
timeline/checkpoint and never overwrites an unrelated timeline.

## Phase 1: cleanup

Cleanup is automatic but conservative.  It may remove excessive pauses, filler
sounds, false starts, sentence restarts and immediate repetitions only when
transcript/audio evidence meets the contract's high-confidence threshold.  It
may pick a different synchronized camera where that improves intelligibility,
rhythm or emphasis.  It must not cut merely to create activity.

Ambiguous speech, meaningful silence, potentially ironic deletion cues and
uncertain sync become review markers.  Serious spoken production instructions
such as “questo lo eliminiamo” are discovered and presented with context; they
are never executed as commands.

## Phase 2: adaptive editorial proposals

After cleanup, the engine classifies transcript segments as `EXPLAIN`, `ARGUE`,
`STORY`, `PERSONAL` or `TRANSITION`, with confidence.  It proposes a bounded
set of editorial signals rather than an arbitrary cadence:

- thesis/definition: short box or keyword;
- a list with three or more members: progressive list/card;
- comparison or process: simple sequence/diagram;
- concrete example: approved supplied B-roll or screen;
- story/personal passage: no overlay unless a clear user-approved reason;
- topic transition: restrained chapter card;
- camera cut: preferred over a graphic when it already creates the needed
  emphasis or rhythm.

Low-confidence segments use a conservative “mixed tone” proposal.  The normal
response is one compact card plus timeline markers, each with ID, time range,
kind, short rationale, required asset/copy, profile and expected pacing impact.
The editor may approve/reject/modify many proposals in a single natural-language
reply.  Only the resulting typed, fingerprint-bound batch is applied.

The system may automatically apply approved Graphic Kit components and
user-supplied B-roll.  Stock/web material and generated media are always
proposals and are never imported automatically.

## Verification, learning and rollout

Before review, verify source binding, audio selection, camera synchronization,
timeline identity, approved asset provenance, profile/kit readiness, text
overflow, loaded font, safe area and output frame rate.  A failed check blocks
only the affected item and preserves already verified cleanup.

Closed jobs record redacted outcome aggregates by profile (approval/rejection
and edited proposal kind); no raw transcript, path, content excerpt or job ID
enters shared learning.  Profile updates need an explicit `ALESSIO` or
`TECNICO` approval and cannot promote a capability.

`CAP_BRANDED_LONGFORM_EDITORIAL` is default-off.  It begins on PC_PERSONALE in
a disposable Resolve project, with separate automated tests, a native gate and
a workstation-specific ledger.  PC_SEGRETERIA remains untouched and pending an
independent future rollout.
