# Editorial Workflows and Safe Render Batches Design

Date: 2026-10-07

Status: approved in conversation; implementation plan pending review of this document.

## Purpose

Remove implicit Resolve defaults from ARPHE editing and delivery. The bridge must identify an
explicit editorial workflow, collect a confirmed brief, set and read back the project/timeline
format, prepare render jobs without starting them, obtain a batch-specific approval, start only
the approved jobs, verify the resulting media and support a scoped rollback.

The design supports the four current production lines and lets later lines be added through
versioned definitions rather than new copies of the render engine.

## Agreed production lines

### `ARPHE_PODCAST_REELS_CTA`

- Purpose: extract one or more non-vertical reels from an ARPHE podcast and add the standard CTA.
- Resolution and frame rate: derived from the confirmed primary source and frozen in the brief.
- Project, timeline and playback frame rates must equal the source frame rate.
- Delivery: MP4, H.264 High Profile, AAC at 48 kHz, video and audio enabled.
- Automation: assisted. Editorial selection, retained ideas and CTA are confirmed before writes.

### `ARPHE_VERTICAL_SOCIAL`

- Purpose: reviews, shorts and advertising in a vertical social format.
- Project, timeline and render format: 1080x1920 at 30 fps.
- Playback frame rate: 30 fps.
- Delivery master: QuickTime ProRes 422 HQ with audio.
- Social derivative: MP4, H.264 High Profile, AAC at 48 kHz, created as a separate delivery.
- Automation: varies by subtype. Review templates may be highly standardised; advertising remains
  editorially assisted.

### `CARABELLESE_YOUTUBE_CLEANUP`

- Purpose: remove pauses and dead time and perform simple cut-and-join editing for Studio
  Carabellese podcasts.
- Project, timeline and render resolution: 1920x1080.
- Frame rate: preserve the exact supported source frame rate; project, timeline and playback use
  that value.
- Delivery: MP4, H.264 High Profile, AAC at 48 kHz, video and audio enabled.
- Graphics and CTA: disabled unless a later approved workflow version explicitly adds them.
- Automation: assisted. Pause aggressiveness, protected passages and intentional hesitations are
  confirmed in the brief.

### `ARPHE_LONGFORM_EDITORIAL`

- Purpose: full ARPHE long-form editing with editorial structure, graphics and CTA.
- Resolution and frame rate: explicit fields in the confirmed brief; never inherited silently
  from the currently open Resolve project.
- Playback frame rate: equal to the confirmed project frame rate.
- Deliveries: review render, master and publishable file are distinct profiles and approvals.
- Automation: `EDITOR_LED` for the first release.

## Extensible workflow registry

A versioned workflow registry is the source of truth for available production lines. Adding a
fifth or sixth line creates a new registry entry and tests; it does not fork the rendering code.

Each workflow definition contains:

- stable `workflow_id`, version, label and purpose;
- recognition hints used by ChatGPT;
- automation level: `AUTOMATIC`, `ASSISTED` or `EDITOR_LED`;
- common and workflow-specific intake questions;
- timeline contract: fixed or source-derived resolution and frame rate;
- allowed editorial operations, graphics, CTA and caption policies;
- allowed review/master/publishable render profiles;
- required human gates and the roles permitted to answer them;
- recovery guidance.

The registry contains no customer content, source media paths, review text or secrets.

## Workflow recognition and confirmation

ChatGPT may infer a likely workflow from an explicit user request, but the bridge never infers a
workflow. Before the first Resolve write, ChatGPT presents a short plain-language summary and the
operator confirms it. The resulting editorial brief contains an explicit `workflow_id`.

If the request is ambiguous or recognition fails, ChatGPT presents a numbered menu of the
available workflows. A low-confidence guess must not select timeline or render defaults.

All later edit and render operations name the same `workflow_id`. A vertical render profile used
with a Carabellese brief, for example, is rejected before settings or jobs are changed.

## Roles and questions

The operational roles are:

- `SEGRETERIA`: uses validated standard workflows, confirms briefs and may approve and start final
  renders that remain inside those standards;
- `TECNICO`: opens advanced questions, chooses allowed technical variants, handles recovery and
  proposes new profiles;
- `ALESSIO`: technical role with authority to approve new organisational standards.

Role declaration is recorded for audit but is not described as strong identity authentication.
Actual account and workspace access remain external controls.

The common operator brief asks, in plain language:

1. What production line or result is needed?
2. Which source files or timeline are in scope?
3. Is the output a full video, extracts or both?
4. How assertive may the edit be?
5. What content must always be retained?
6. Are CTA, captions or graphics required?
7. Is any supplied text or material subject to approval?
8. Is the requested delivery a review, master or publishable file?
9. Who approves the edit and render?

Workflow definitions add conditional questions. Technical questions remain hidden unless the
workflow requires a non-standard choice or the operator declares `TECNICO` or `ALESSIO`.

## Editorial brief

The confirmed brief is structured data stored locally with the project registry. At minimum it
records:

- brief ID and workflow ID/version;
- operator role and confirmation time;
- project and source identifiers without embedding media content;
- primary source used for source-derived format decisions;
- requested outputs and editorial constraints;
- resolved width, height and exact frame-rate representation;
- playback frame rate;
- allowed render profiles;
- unresolved questions, which must be empty before the first write.

When multiple sources have different frame rates, the bridge must not pick one silently. The
operator confirms a primary rate or a technical operator approves a conversion policy.

## Format and playback invariant

Before creating the first production timeline, the bridge resolves the workflow contract and
sets the project/timeline format. It then reads back the effective values.

For every workflow:

- project frame rate equals timeline frame rate;
- playback/preview frame rate equals project frame rate;
- the render frame rate equals the approved delivery contract;
- width, height and orientation match the workflow contract;
- an unavailable or rejected Resolve setting stops the workflow before editing.

“Preview” is not used ambiguously:

- `playback_fps` means Resolve playback performance and must match the project;
- `review_render` is a file produced for human review;
- `delivery_render` is a verified final output.

Source-native workflows preserve the exact supported source rate. An unsupported or unreadable
rate requires a technical decision; it is never rounded or converted implicitly.

## Render-profile registry

A separate versioned render-profile registry describes delivery mechanics. A profile defines:

- stable ID and version;
- delivery class: review, master or publishable;
- container and video/audio codecs;
- fixed or brief-derived width, height and frame rate;
- audio requirement and sample rate;
- Resolve preset, when one is useful, plus the explicit settings that must still be applied;
- allowed workflows;
- staging and final path policy;
- post-render verification rules.

Resolve presets are implementation helpers, not sources of truth. The bridge applies explicit
settings and verifies the output even when `LoadRenderPreset` succeeds. The global
`render_format`/`render_codec` pair cannot select a delivery for every workflow.

## Render-batch state machine

Every delivery follows this lifecycle:

`DRAFT -> CONFIRMED -> PREPARED -> APPROVED -> RENDERING -> VERIFYING -> VERIFIED`

Terminal or recovery states are:

- `CANCELLED`: cancelled before rendering;
- `FAILED_PREPARE`: settings or job preparation failed;
- `FAILED_RENDER`: rendering was interrupted or failed;
- `FAILED_VERIFY`: an output exists but does not meet its contract.

State transitions are monotonic. Retrying creates a new batch attempt linked to the previous
attempt rather than rewriting its evidence.

## Preparation and approval

`prepare_render_batch` performs read-only validation first, snapshots the current timeline and
the existing render queue, applies one approved render profile per requested output and creates
new jobs. It never calls `StartRendering`.

The prepared manifest records:

- batch ID, attempt and workstation;
- workflow/brief/profile versions;
- project and timeline identities;
- resolved project, timeline, playback and render formats;
- queue job IDs present before preparation;
- exact job IDs added by this batch;
- expected filenames and staging directory;
- a canonical batch fingerprint;
- limitations and recovery instructions.

The operator sees a plain-language summary covering timeline, duration, dimensions, frame rate,
container, codecs, audio, destination and filenames. `approve_render_batch` produces an approval
token bound to the batch fingerprint.

Any change to the brief, project, timeline, render settings, output names or job list invalidates
approval. This fingerprint protects the render batch only; higher-level binding of every edit
plan operation remains a later feature.

## Queue isolation and start policy

Before starting, the bridge reads the queue again and proves that every approved job still
exists with the expected settings. It starts only the recorded IDs using selective Resolve API
arguments.

- Pre-existing jobs are neither started nor deleted.
- Jobs added after approval make the approval stale and require a new preparation or explicit
  technical recovery.
- If the installed Resolve API cannot identify jobs or start an explicit subset reliably, the
  bridge fails closed and requests manual queue cleanup; it never falls back to “start all”.
- A per-project render lock prevents bridge batches from overlapping.
- Starting is rejected while Resolve reports another active render.

The existing immediate-start behaviour in `render_preview` and the default
`start_render=True` behaviour in publish-package export are removed. Existing entry points may
remain temporarily as compatibility wrappers, but they must use the same prepare/approve/start
state machine.

## Staging, verification and promotion

Every batch renders into a dedicated directory below the profile-owned render root:

`staging/<batch_id>/`

No job writes directly into a delivery directory. Verification checks:

- expected file exists and is non-empty;
- render job completed successfully;
- container and video codec;
- width and height;
- exact or rationally equivalent frame rate;
- duration against the expected timeline duration within one frame;
- required audio stream, codec and 48 kHz sample rate where specified;
- unique final filename and absence of an existing delivery collision.

Only verified files are promoted to the delivery directory. Promotion occurs within the
profile-owned render root and uses an atomic move when the filesystem permits it. A copied file
must be hash-verified before the staging source is retired.

## Rollback and recovery

Rollback is scoped to resources owned by the current batch:

- preparation failure: delete only job IDs created during that attempt, restore the initial
  current timeline and record `FAILED_PREPARE`;
- cancellation after preparation: remove only the prepared batch jobs and record `CANCELLED`;
- partial job cleanup failure: retain the known IDs as orphaned evidence and block batch start;
  never clear the entire Resolve queue;
- render failure: stop the batch when safe, record `FAILED_RENDER` and retain partial files under
  staging with a failure marker;
- verification failure: record `FAILED_VERIFY`, retain the nonconforming output in staging and
  do not promote it;
- promotion failure: keep the verified staging file and its hash so promotion can be retried;
- no rollback operation deletes source media, timelines, project content, previous deliveries
  or jobs not created by the batch.

Because Resolve stop behaviour can be process-wide, cancellation during rendering is permitted
only while the bridge owns the render lock and has verified that no foreign job is active.
Otherwise it reports the condition for technical intervention instead of issuing a broad stop.

## Bridge interfaces

The intended closed tool surface is:

- `list_editorial_workflows`;
- `validate_editorial_brief`;
- `prepare_render_batch`;
- `approve_render_batch`;
- `start_render_batch`;
- `get_render_batch_status`;
- `verify_render_batch`;
- `cancel_render_batch`.

There is no generic tool for arbitrary Resolve render settings, arbitrary queue deletion or
starting all jobs.

## Audit and evidence

Audit records include workflow/profile versions, batch state transitions, operator role, job IDs,
fingerprints, verification results and recovery events. They do not include media content,
review text, secrets or full sensitive paths.

Code-test evidence and real workstation evidence remain separate. A live gate names
`PC_PERSONALE` or `PC_SEGRETERIA`, Resolve/Python versions, workflow/profile, batch ID, result and
limitations. A PASS on one PC is not evidence for the other.

## Verification strategy

Automated tests must demonstrate:

- recognition confirmation produces an explicit workflow ID and ambiguous input produces a menu;
- registry additions do not require render-engine branches;
- project, timeline and playback frame rates match;
- source-native workflows freeze source dimensions/rate rather than using current defaults;
- Carabellese forces 1920x1080 while preserving the supported source rate;
- vertical social forces 1080x1920 at 30 fps;
- preparing a batch never invokes `StartRendering`;
- pre-existing jobs are never started or deleted;
- stale approvals are rejected after any manifest or queue change;
- partial preparation removes only newly created jobs;
- rendering and verification failures remain in staging and are never promoted;
- output verification rejects wrong resolution, rate, duration, codec or missing audio;
- a standard-profile final render may be approved by `SEGRETERIA`;
- profile overrides and recovery paths require `TECNICO` or `ALESSIO`;
- no API path can start the entire queue implicitly.

Manual rollout validates one workflow at a time, first on a test project. The minimum live gate
is: format/playback read-back, prepare with an old harmless job already in the queue, approval,
selective start, media verification and proof that the old job remained untouched.

## Migration order

1. Introduce registries and validation without changing current tools.
2. Add the batch manifest/state machine and fake-Resolve tests.
3. Migrate long-form queue/start, which already separates preparation from start.
4. Migrate publish-package export and remove immediate-start defaults.
5. Migrate vertical preview/master delivery.
6. Add the four workflow definitions and conversational documentation.
7. Run code tests, then separate live gates per workstation; do not deploy automatically from a
   Git update.

## Out of scope

- Automated creative decisions about which podcast passages are editorially best.
- Strong authentication of the human role declared in chat.
- Arbitrary custom render settings for non-technical operators.
- Deleting historical delivery files or foreign Resolve jobs.
- Full plan-hash binding across every editing operation.
- The future graphical long-form vocabulary beyond its workflow/render contract.

## Success criteria

The design is complete when no production line relies on implicit project/render defaults, no
preparation call starts rendering, the secretary can safely approve a validated standard final,
old jobs cannot be started by a new batch, every delivered file passes explicit media checks and
rollback can affect only the current batch.
