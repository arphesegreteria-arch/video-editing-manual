# Workflow Control Plane for the Creative Bridge

Date: 2026-10-10
Status: design approved in conversation; implementation plan pending review of this document

## Purpose

Make the existing editorial workflows usable as complete, resumable jobs instead of requiring
ChatGPT and the operator to reconstruct a sequence of low-level bridge calls. ChatGPT remains the
conversation interface. The bridge remains the deterministic executor and never interprets free
text or chooses editorial meaning.

The intended secretary experience is deliberately small:

1. state the desired result;
2. approve the proposed content or plan;
3. review the provisional result;
4. approve delivery when a workflow actually has a validated delivery stage.

The system must know the active workstation, exact Resolve target and next safe action without
asking the operator to remember tool names, plan IDs or recovery procedures.

## Decisions already made

- This is a coordination layer, not a replacement for working specialized workflows.
- It covers the existing `ARPHE_PODCAST_REELS_CTA`, `ARPHE_VERTICAL_SOCIAL`,
  `CARABELLESE_YOUTUBE_CLEANUP` and branded-longform workflows through adapters.
- `PC_PERSONALE` and `PC_SEGRETERIA` retain completely separate local state, flags, journals and
  validation evidence. Installing shared code does not activate it on either workstation.
- A job may perform no Resolve write until its exact approved-plan fingerprint is supplied.
- All Resolve writes acquire one common access lock and revalidate the explicit target immediately
  before mutation.
- A workflow without a currently validated render/delivery implementation stops at verified review;
  this feature must not invent a generic auto-render or auto-publish action.
- The public surface is compact and card-oriented. Primitive tools remain for development and
  technical recovery, not normal secretary interaction.

## Current gap

The repository already has strong local foundations:

- podcast selection jobs bind workstation, source, transcript, project/timeline identity, review
  fingerprint and resumable output operations;
- Carabellese cleanup adds verified `.drt` checkpoints and recovery;
- vertical-social plans bind target/action state and picture-lock fingerprint;
- branded longform binds source, profile, proposal and timeline fingerprints.

They differ in names, status vocabulary, inspection shape and how a caller identifies the next
safe operation. `resolve_status`, `get_creative_status` and feature reporting also expose
overlapping but separate fragments of the initial context. This makes ChatGPT coordinate too much
manual context and leaves no uniform provenance between a human-approved plan and a later command.

## Architecture

### 1. Read-only control snapshot

`inspect_workstation_control_plane` returns one compact initial card. It contains:

- bridge runtime/version and `workstation_id`;
- Resolve connection health, version, active project and active timeline;
- timeline resolution, edit FPS and playback FPS when readable;
- implemented/configured/available capability status;
- the known workflow families and their enabled/disabled status;
- active and recoverable control-plane jobs, with one concise next-safe action each.

The snapshot is diagnostic only. It does not create a project, change the current timeline, set
playback FPS, enable a flag or inspect source media. A failure to connect still returns the local
runtime/workstation identity and a precise blocked condition.

### 2. A common envelope around native jobs

Each user-visible run receives an opaque `workflow_job_id`. The envelope contains:

- schema and control-plane workflow version;
- workstation ID;
- workflow family and referenced native job/plan ID;
- immutable target: project name/identity, timeline name/identity and, where available, source and
  timeline fingerprints;
- a plan fingerprint, approval fingerprint and approval revision;
- native-state snapshot, common state and last verified evidence reference;
- only redacted operator-facing summary fields; detailed review text and media paths stay in the
  existing local journals.

The envelope is an adapter record; it never duplicates or migrates the authoritative specialized
job registry. An adapter translates the native state into the common state and delegates actual
work to the existing validated functions.

The registry is profile-local, atomic and workstation-bound. Reusing an ID with different immutable
content fails closed. A control-plane job may reference only an owned native job/plan from the same
workstation.

### 3. Common state model

The normalized states are:

`PROPOSED → AWAITING_APPROVAL → EXECUTING → REVIEW_READY → DELIVERY_AWAITING_APPROVAL → CLOSED`

Supported exceptional states are `BLOCKED`, `STALE` and `FAILED_RECOVERABLE`.

Not every adapter uses every state. For example, podcast selection can be `REVIEW_READY` after
marker creation; vertical social can become `REVIEW_READY` after verified picture-locked actions;
Carabellese can be `REVIEW_READY` after cleanup verification; branded longform can be
`REVIEW_READY` after native verification. A delivery state is legal only when the native workflow
already has an explicit verified delivery/render batch.

Each inspection returns exactly one `next_safe_action` such as `APPROVE_PLAN`,
`SUBMIT_REVIEW`, `RESUME`, `APPROVE_DELIVERY` or `NONE`. A blocked/stale job returns the concrete
missing condition and does not suggest a write.

### 4. Approval binding and target revalidation

Preparing a control-plane job stores a canonical digest over:

- workflow family and schema version;
- immutable target;
- referenced native plan/job ID and its current fingerprint;
- proposed actions or candidate summary;
- workstation identity.

Approval persists that digest as `approved_plan_fingerprint`, with an append-only approval event.
Every write-capable advance requires the same fingerprint. If the native plan, source, project,
timeline, fingerprint or workstation differs, the job becomes `STALE` or `BLOCKED`; it never
silently advances against the current Resolve context.

Immediately inside `RESOLVE_ACCESS_LOCK`, each adapter re-opens/reads the intended project and
timeline and compares their identity/fingerprint to the envelope before calling the native write.
This closes the gap where a user changes Resolve selection between planning and execution.

### 5. Adapters

The first release has four narrow adapters:

| Family | Native authority | Control-plane responsibility |
| --- | --- | --- |
| Podcast Reels | `EditorialJob` | bind proposal/review/cut steps into one recoverable job card |
| Vertical Social | `VerticalSocialPlan` | enforce planned action order and picture-lock provenance |
| Carabellese Cleanup | `CarabelleseJob` | expose checkpoint, apply/resume and recovery coherently |
| Branded Longform | `BrandedLongformJob` | bind profile/proposal/native verification without enabling pending graphic kits |

The adapter does not permit arbitrary tool execution, direct timeline deletion or crossing from
one workflow family into another. A new production line must add an explicit adapter and tests;
it cannot be inferred merely from a string in chat.

### 6. Public bridge surface

The normal operator-facing tools are intentionally few:

- `inspect_workstation_control_plane()` — initial single-card check;
- `prepare_workflow_job(workflow_family, native_reference, target)` — create or rediscover an
  idempotent envelope after the relevant native plan/job exists;
- `inspect_workflow_job(workflow_job_id)` — current state, provenance and one next safe action;
- `approve_workflow_job(workflow_job_id, plan_fingerprint, operator_role)` — bind approval;
- `advance_workflow_job(workflow_job_id, approved_plan_fingerprint)` — run only the adapter's
  next safe native operation or resume it;
- `approve_workflow_delivery(workflow_job_id, approved_delivery_fingerprint, operator_role)` —
  available only where a native verified delivery contract exists.

ChatGPT may make native prepare/review calls internally when converting natural-language requests
to a structured workflow. It always presents the operator a single compact card and never asks
them to copy raw IDs unless a technical person is performing recovery.

### 7. Concurrency and interruption

Control-plane registry changes use a profile-local lock. Resolve mutations use the existing
`RESOLVE_ACCESS_LOCK`; the control-plane lock is not held while an adapter waits for Resolve, to
avoid lock inversion. The adapter claims one job transition atomically, rechecks it under the
Resolve lock and records the native result before releasing its claim.

If an interruption happens after a verified native operation but before the envelope is updated,
inspection reconciles from native evidence. If reconciliation is ambiguous, the envelope becomes
`FAILED_RECOVERABLE` and tells the operator not to retry manually. Repeating a successful advance
returns the recorded result; it must never duplicate markers, cuts, timelines, checkpoints or
render jobs.

## Secretary interaction

The response after preparation is one card, not a menu of bridge functions. Its compact form is:

```text
Lavoro: Reel podcast ARPHÈ · pronto per revisione
Target: Podcast EP12 / MASTER
Prossimo passo: ascolta i marker R01–R06 e rispondi in un messaggio unico.
Stato: nessun taglio o render è ancora partito.
```

After an interruption it instead says, for example:

```text
Lavoro: pulizia YouTube Studio Carabellese · riprendibile
Checkpoint: verificato prima dell'applicazione.
Prossimo passo sicuro: riprendo dal taglio 4; non duplicherò i tagli già verificati.
```

Technical detail, full evidence and raw native IDs are available only on request or in the
technical inspection response. This preserves maximum conversational flexibility while making the
standard path dependable.

## Feature flag and rollout

`CAP_WORKFLOW_CONTROL_PLANE` is new, default `false`. Read-only inspection remains available with
the flag disabled; preparation, approval and advancement are unavailable. The installer preserves
each workstation's explicit flag and local registry path.

Rollout order:

1. unit, contract and fake-Resolve tests;
2. install code on `PC_PERSONALE`, flag still false;
3. enable only the personal flag and complete an isolated native gate using a small owned target;
4. record the exact workflow, project/timeline, fingerprints, checkpoint/recovery and rollback
   evidence in the repository;
5. leave `PC_SEGRETERIA` disabled and `PENDING` until its open work is finished and it can run its
   own isolated gate.

No evidence from the personal machine activates or validates the segreteria machine.

## Testing requirements

Tests must cover:

- snapshot behaviour without Resolve and without any write;
- state mapping and one-next-action logic for all four adapters;
- workstation and native-reference mismatch rejection;
- plan approval digest mismatch and stale target rejection;
- idempotent prepare/advance and duplicate suppression;
- lock ordering and target revalidation using fake Resolve contexts;
- interruption after native success and deterministic reconciliation;
- blocked/recoverable state reporting without exposing sensitive paths or review text;
- disabled-flag behaviour and independent per-workstation registries;
- legacy native workflow tests unchanged.

The personal native gate must prove at least one real job card, approval binding, target mismatch
block, successful advance, deliberate recoverable interruption, safe resume and a read-only final
snapshot. It must restore the previously active Resolve context and leave no unowned work behind.

## Out of scope

- a generic natural-language command executor inside the bridge;
- changing a graphic kit's status or enabling a pending kit;
- automatic rendering/publishing where the specialized workflow has not validated it;
- migration or deletion of existing job registries;
- cross-workstation job recovery;
- activating, installing or validating anything on `PC_SEGRETERIA`.
