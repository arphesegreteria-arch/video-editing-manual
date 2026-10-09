# Studio Carabellese YouTube Cleanup — Design

**Date:** 2026-10-09

**Status:** design approved in conversation; awaiting written-spec review

**Workflow:** `CARABELLESE_YOUTUBE_CLEANUP`

## Intent

Studio Carabellese needs a repeatable assisted workflow for cleaning podcast recordings before
publication on YouTube. The result must retain the natural rhythm of the speakers while removing
excessive pauses, technical setup, trailing off-record material and explicitly spoken editorial
instructions. The operator must work with one visible Resolve timeline, review one compact proposal
and send corrections in one response.

Success means:

- the published conversation still sounds natural rather than aggressively compressed;
- the real editorial start and end are identified;
- spoken instructions such as “questo lo eliminiamo” are found with context and never treated as
  automatic commands;
- the approved edit is applied in place only after a verified `.drt` checkpoint exists;
- recovery, learning and rollout stay isolated from ARPHÈ Podcast Reels and from the other PC;
- the workflow adds no CTA or graphics while Studio Carabellese has no dedicated Graphic Kit.

## Scope and non-goals

The first release covers a single YouTube cleanup timeline: transcription, pause analysis,
boundary proposals, spoken editorial cues, structured review, checkpoint, in-place cuts,
verification and workflow-specific learning.

It does not add CTA, captions, titles, visual branding, reframing, social derivatives, music,
colour work or automatic render delivery. Existing render-batch infrastructure may be used later,
but the cleanup workflow stops after the editor has listened to the edited timeline. It does not
reuse editorial preferences learned from `ARPHE_PODCAST_REELS_CTA`.

## Architectural choice

The implementation will add a dedicated Carabellese workflow on top of shared bridge primitives.
It will reuse workstation identity, feature gates, Resolve locking, fingerprints, marker helpers,
approval patterns, checkpoint verification and append-only learning concepts. It will not make the
podcast-Reels engine generic prematurely, and it will not create a monolithic one-off script.

The new capability is `CAP_CARABELLESE_CLEANUP`. It is `false` by default and has a separate
per-workstation rollout ledger. Enabling it on one workstation neither enables nor validates the
other.

The workflow owns separate versioned resources:

- `carabellese_cleanup_contract.json` for thresholds, marker policy and format constraints;
- `carabellese_preferences.json` for the approved shared baseline;
- workstation-local job, journal, overlay and profile-proposal files;
- a dedicated validator and ledger that cannot infer results from Podcast Reels evidence.

The package registry continues to identify `CARABELLESE_YOUTUBE_CLEANUP`; its current render
contract remains 1920×1080, source frame rate, H.264 High and AAC 48 kHz. During cleanup,
project, timeline and playback rates must agree with the pinned primary source. The read-only
playback setting remains a fail-closed preflight.

## Data flow

1. **Inspect.** Read workstation, project, current timeline, format and capability without writing.
2. **Pin.** Bind the job to project identity, timeline identity, source fingerprint, source frame
   rate and current timeline fingerprint.
3. **Transcribe.** Reuse the checkpointed longform transcription path. The manifest must bind the
   timestamped transcript to the selected source fingerprint. Transcripts remain local and are not
   committed.
4. **Analyse.** Derive ordinary pause candidates from timestamp gaps and local audio silence;
   derive boundary and spoken-cue proposals from the complete transcript. Blade points are refined
   inside silence so the proposal does not cut phonemes.
5. **Validate proposal.** The bridge accepts only typed candidate records whose spans are ordered,
   source-bound, non-overlapping after normalization and inside the source duration.
6. **Mark.** Add concise markers to the current timeline for proposed boundaries and cases needing
   individual review. Ordinary pauses remain in the compact review summary rather than flooding
   the timeline with markers.
7. **Review.** Require a complete structured decision set and a reason. Ordinary pauses can share
   one batch decision and reason; boundaries and each exceptional cue require an individual
   decision.
8. **Checkpoint.** Re-run every read-only preflight, export the current timeline as `.drt`, verify
   that it exists and record its SHA-256 before the first cut.
9. **Apply.** Execute approved removals on the same visible timeline from the latest source time to
   the earliest. Record each operation and verify the resulting timeline.
10. **Listen and close.** The operator listens in Resolve, requests any corrections in one message,
    then closes the job. Only closed outcomes may contribute to a Carabellese learning proposal.

## Candidate model and editorial rules

Every proposed intervention has a stable candidate ID, one of four kinds, source in/out times,
transcript excerpt, context before and after, reason, confidence, original duration, proposed
duration and review requirement.

Candidate kinds are:

- `BOUNDARY`: content before the true opening or after the true closing;
- `PAUSE`: an excessive silence that can be shortened without changing meaning;
- `EDITORIAL_CUE`: an instruction, retake, privacy warning or technical note spoken in the recording;
- `MANUAL`: a range introduced or modified by the editor during review.

Initial pause calibration is deliberately moderate:

- gaps below 0.7 seconds are retained;
- gaps from 0.7 through 1.5 seconds are context-sensitive;
- gaps above 1.5 seconds are normally shortened to 0.6–0.8 seconds;
- breaths, emphasis, turn-taking and emotionally meaningful silence are protected;
- speaker changes force review when shortening could damage conversational rhythm.

These values are contract defaults, not hidden constants. Calibration may adjust them after real
work, but changing the contract invalidates stale proposals and approvals.

The proposed opening is the first complete sentence addressed to the audience, including a natural
greeting or introduction. The proposed ending follows the last complete audience-facing sentence,
including a natural closing. Technical setup, tests, “siamo pronti?”, off-record conversation and
post-closing tails may be proposed for removal. No CTA is synthesized or appended.

Spoken editorial cues include explicit deletion requests, retakes, recording start/stop directions,
private or non-publishable content, stated technical problems and ambiguous or possibly ironic
instructions. They are always reviewed individually. Confidence never authorizes their automatic
removal.

## Review interaction

The secretary receives one short summary with:

- the proposed opening and closing;
- the number of ordinary pauses and estimated time removed;
- the exceptional candidates that require listening;
- exact instructions for a single response.

A representative response format is:

```text
CONFINI OK
PAUSE OK — il ritmo resta naturale
E01 ELIMINA — è una richiesta seria fuori contenuto
E02 CONSERVA — è una battuta nel discorso
E03 MODIFICA 00:18:42.200-00:18:48.900 — conserva la frase conclusiva
```

The exact wording may be simplified during live calibration, but the semantics do not change:
every group or exception needs an explicit outcome and reason, missing decisions keep the job in
review, and no cut occurs from an incomplete response.

## One-timeline rule

The operator sees and edits one Resolve timeline. Proposal markers live on that timeline; the
approved cuts modify it in place. The system does not create a permanent review duplicate.

Safety is provided by the external `.drt` checkpoint. A recovery operation may temporarily import
the checkpoint while verifying it, but it must finish with one canonical visible timeline. It must
not silently adopt an unrelated timeline with the same name.

Cuts are calculated in source time and applied in descending order so earlier coordinates remain
stable. The implementation must protect small silence handles at joins. If a native audio
crossfade cannot be created and read back reliably through the installed Resolve API, the bridge
must report that limitation and preserve safe handles; it must not claim a transition it cannot
verify.

## State, idempotency and concurrency

The job state machine separates proposal, marking, review, checkpoint, application, verification,
recoverable failure and closure. Each persisted update uses optimistic revision checks. Repeating
an already verified operation returns the registered result rather than duplicating cuts or
markers.

The Resolve access lock covers each complete operation, not only individual API calls. The bridge
rejects a second active cleanup job for the same timeline. A changed project, timeline, source,
transcript, contract, plan or approval fingerprint fails before checkpoint or timeline writes.

Legacy or unknown jobs never start automatically. Only the explicit current job ID and approved
plan fingerprint may be executed.

## Failure and recovery

Preflight failures are zero-write and leave persisted state unchanged unless the failure itself is
an owned collision or tamper event that must block the job.

After the checkpoint is verified, an application failure produces `FAILED_RECOVERABLE`, stops all
later cuts and never starts a render. The operation journal records which approved cuts completed.
Recovery is a technical action: verify the checkpoint hash, restore the checkpoint without
overwriting unrelated work, verify the restored timeline fingerprint, leave one canonical timeline
and then permit a new reviewed attempt. The bridge does not rely on a long Resolve undo chain.

The source media, transcript and `.drt` checkpoint are retained under existing artifact policy.
Synthetic validation artifacts are quarantined and later purged through the established hygiene
workflow.

## Learning isolation

Closed Carabellese jobs may append privacy-safe outcome aggregates to the Carabellese local journal.
Raw transcript text, names, paths, job IDs and content excerpts never enter the shared profile or
repository.

The learned dimensions may include preferred residual pause range, approval rates by pause band,
false-positive categories and boundary adjustments. A proposed profile update requires a minimum
sample count, a digest of the previous profile and explicit approval by `ALESSIO` or `TECNICO`.
It is shareable between the two PCs only as an approved redacted profile. Podcast-Reels samples and
preferences are never mixed into it.

## Testing and rollout

Automated coverage must include:

- strict contract/profile parsing and unknown-field rejection;
- source-bound transcript provenance;
- pause bands, protected breaths, speaker turns and silence-safe blade points;
- true opening/closing proposals;
- serious, ambiguous and ironic editorial cues;
- complete review, batch pause decisions, individual exceptions and mandatory reasons;
- stale timeline/transcript/contract/plan/approval rejection before writes;
- verified `.drt` checkpoint before the first cut;
- descending in-place cuts, idempotent retries and no duplicate markers;
- partial failure, recoverable state and checkpoint restoration;
- one-timeline final invariant;
- isolated Carabellese learning and privacy redaction;
- installer preservation, default-off feature flag and workstation mismatch rejection.

Live rollout starts on a disposable `PC_PERSONALE` project with synthetic dialogue containing
ordinary pauses, a speaker change, setup chatter, a serious delete instruction and an ironic
look-alike. The gate verifies proposal, markers, review, checkpoint, in-place edit, failure/recovery,
listening state, cleanup and rollback with the capability returned to `false`. `PC_SEGRETERIA`
remains `PENDING` until an independent gate can run without touching its active work.

## Adjustable during calibration

The following may be simplified without redesigning the safety model:

- exact pause thresholds and residual pause target;
- summary wording and grouping of ordinary pauses;
- marker colours and how many low-confidence cases are shown;
- minimum learning sample count;
- the amount of transcript context shown to the editor.

The following are not calibration shortcuts: source/transcript provenance, explicit complete review,
mandatory reasons, plan fingerprint, verified checkpoint, zero-write preflight, single-workstation
state, default-off capability and independent live gates.
