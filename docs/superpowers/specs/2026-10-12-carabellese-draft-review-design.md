# Studio Carabellese Draft Review - Design

**Date:** 2026-10-12

**Status:** proposed implementation design

**Extends:** `CARABELLESE_YOUTUBE_CLEANUP` v1; it does not replace its final-cleanup flow.

## Intent and confirmed decision

For the current `PC_PERSONALE` job, the explicit user instruction approves the existing **batch**
decision for all ten conservative pause candidates. That is sufficient only to create a private
draft preview: it is not an approval for a final master, publication, or irreversible replacement.
The current job has no boundaries or exceptional cues, so no individual decision is missing.

The draft must make every applied cut easy to find on a phone. It will therefore deliver a light,
private H.264 preview plus a sidecar review map; it will not upload, publish, or overwrite the
source timeline.

## Scope

`DRAFT_REVIEW` is a new, explicitly selected phase after `MARKED` and before final cleanup. It:

- duplicates the source timeline into an owned, isolated draft timeline;
- exports and verifies a `.drt` checkpoint before the first draft cut;
- applies only accepted `PAUSE_*` decisions, descending in source time, while retaining the
  contract's silence handles;
- writes persistent cut markers on the draft and a fingerprint-bound JSON review map containing
  source and draft timecodes for each cut;
- produces a light 1080p H.264/AAC preview with temporary on-picture cut indicators;
- uploads the preview and review map to the user's private Library only after local verification;
- accepts a later phone review only when the job, source, transcript, proposal, draft timeline,
  review map, and preview hashes all match.

It does not change the existing `apply_carabellese_cleanup` endpoint, run a final render,
publish, create social derivatives, alter source media, alter the original timeline, or touch
`PC_SEGRETERIA`.

## State and ownership

The existing source cleanup job remains `MARKED` until a new `DraftReviewJob` has a complete,
fingerprinted batch decision. The draft job is workstation-local and has these states:

`DRAFT -> PREPARED -> RENDERING -> REVIEW_READY -> ACCEPTED | REJECTED | FAILED_RECOVERABLE`.

Its immutable binding includes source job ID, source/transcript/contract/proposal fingerprints,
the exact batch decision, source timeline identity/fingerprint, draft timeline identity/fingerprint,
checkpoint hash, cut-map hash, and preview SHA-256. A mismatch before a write yields zero write;
a mismatch after the checkpoint yields `FAILED_RECOVERABLE` with rollback instructions.

The draft timeline must have an owned prefix such as `ARPHE_CARABELLESE_DRAFT_<job-suffix>` and
an ownership marker. The source timeline is read-only to this phase. Only one open draft may own a
source cleanup job; retries return the same state rather than duplicating a timeline, markers,
cuts, renders, or uploads.

## Cut and review semantics

The batch decision maps `REMOVE` to the existing conservative pause removal and `SHORTEN` or
`MODIFY` to the contract residual range. `KEEP` creates no cut. Candidate spans are revalidated
against the pinned silence window and protected handles after duplicating the timeline. Zero-length
transcript tokens continue to prevent adjacent automatic cuts. Cut operations are ordered latest
to earliest and each operation records original in/out, resulting draft in/out, frame values,
candidate ID, and verification result.

The review map is a compact JSON sidecar, not a new transcript. It lists every cut in chronological
order with `candidate_id`, source/draft SMPTE-like 30 fps timecodes, original duration, removed
duration, residual duration, and matching marker names. The preview overlays a short temporary
banner at each cut, for example `P003 | 00:25:29.290`, so viewing the video alone is sufficient to
locate every edit. Overlay frames are never part of the final timeline or final render.

## Delivery and review

Local output verification checks the expected MP4 exists, is H.264/AAC at 48 kHz, is playable,
and matches the recorded hash. The private Library upload is a delivery copy only; its identity is
stored with the draft job, along with the review-map Library identity. There is no external share
or publication step.

Phone feedback is one complete structured decision: `ACCEPT_DRAFT` or `REJECT_DRAFT`, plus a
reason and optional candidate-level corrections keyed by ID. `ACCEPT_DRAFT` authorizes only the
subsequent, separate final-cleanup action after all fingerprints revalidate. `REJECT_DRAFT` leaves
source and draft intact and records requested corrections; it never silently applies a new cut.

## Existing capability assessment

The repository already has checkpointed Carabellese application, marker ownership, fingerprints,
and generic render-batch state machinery. It does **not** contain a draft-review state model,
duplicate-timeline adapter, preview-indicator renderer, source-to-draft time-map, or a Library
transfer adapter. The connected private Library supports file creation, so the delivery boundary
can use that facility after a verified local file exists; no credential or MCP schema change is
needed.

## Acceptance criteria

1. A batch-approved set of conservative pauses creates one owned draft, never alters the source,
   and emits a verified checkpoint before cuts.
2. Every cut appears in both persistent draft markers and the fingerprinted time map; the preview
   has a temporary indicator for the same candidate ID/timecode.
3. Any stale fingerprint, overlapping/out-of-bounds range, zero-length-adjacent range, failed
   timeline duplication, render verification failure, or upload failure leaves the source intact
   and is recoverable.
4. The Library receives only verified private draft artifacts. No final render, share, or publish
   happens in this phase.
5. Phone approval is bound to the exact delivered preview and cannot approve a changed draft.
