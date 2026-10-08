# Editorial selection and learning for ARPHÈ podcast Reels

Date: 2026-10-08  
Status: design approved in conversation; implementation not started

## Purpose

Reduce the time spent selecting and correcting Reel excerpts from an ARPHÈ podcast longform,
while keeping editorial judgment with the human reviewers. The system must propose only strong,
self-contained excerpts, make their exact boundaries easy to audition in Resolve, accept one
natural-language review message, cut only the accepted excerpts and learn from every explained
decision.

Success means that the reviewers can work primarily by listening in Resolve and replying once in
plain Italian. The useful measures are first-proposal acceptance, boundary corrections, rejection
reasons and elapsed review time. Tool count and animation count are not success measures.

## Scope

This first version applies only to workflow `ARPHE_PODCAST_REELS_CTA`:

- input: an ARPHÈ podcast longform, commonly about one hour;
- output: independent landscape Reel timelines in the source format;
- CTA: the existing standard CTA for this workflow;
- absolute final duration: at most 180 seconds, including the CTA;
- candidate count: quality-driven, not quota-driven. Six is a normal result; fewer or ten or more
  are valid when the source warrants it;
- review surface: paired point markers on the original source timeline before any cut;
- final decision: one natural-language message covering every proposed excerpt.

The change does not apply to vertical reviews/ads, `CARABELLESE_YOUTUBE_CLEANUP` or the future
full longform graphics workflow. It does not add a separate graphical application or a new video
card style.

## Roles and trust boundaries

- ChatGPT analyzes transcript meaning, ranks candidates, explains the review procedure and turns
  the reviewers' natural-language message into structured decisions.
- The bridge never guesses editorial meaning. It validates identities, transcript anchors,
  markers, decisions, duration, audio provenance and Resolve mutations deterministically.
- The secretaries audition marked intervals in Resolve and return one concise review message.
- Alessio, or a person explicitly qualified as technical, may request an audio A/B comparison and
  is the only role allowed to approve updates to the shared learned preference profile.
- `PC_PERSONALE` and `PC_SEGRETERIA` keep separate runtime state, job registries and feature flags.
  Evidence from one workstation never validates the other.

## Architecture

The feature consists of five bounded units:

1. **Selection contract** — versioned schema for candidate evidence, boundaries, CTA allowance,
   review decisions and reasons.
2. **Editorial job registry** — per-workstation state machine and resumable mutation record.
3. **Resolve marker and cut adapter** — owns only the markers and timelines registered to a job.
4. **Audio provenance verifier** — accepts enhanced audio only when its generation manifest binds
   it to the selected source media.
5. **Learning journal and profile compiler** — keeps detailed local decisions and produces a
   redacted shared-profile proposal that requires Alessio's approval.

Natural-language interpretation stays outside these units. Public bridge tools receive structured
payloads and return structured missing/ambiguous evidence for ChatGPT to explain.

## Job lifecycle

Every source selection run has a random `editorial_job_id`, workstation identity, workflow version,
project identity, timeline identity, source-media fingerprint and transcript fingerprint. The
state machine is:

`ANALYZED → MARKED → REVIEWED → CUT → VERIFIED → CLOSED`

Exceptional states are `STALE`, `BLOCKED` and `FAILED_RECOVERABLE`.

- `ANALYZED`: candidate evidence is complete and no Resolve write has occurred.
- `MARKED`: all proposed `IN/OUT` markers exist on the source timeline.
- `REVIEWED`: every candidate has one complete decision and non-empty reason.
- `CUT`: every approved or modified candidate has its registered output timeline.
- `VERIFIED`: boundaries, CTA, duration and any enhanced audio have passed read-back checks.
- `CLOSED`: only this job's markers have been removed.
- `STALE`: source timeline, media, transcript or approved decision fingerprint changed.
- `BLOCKED`: a precondition such as marker collision or ambiguous phrase prevents mutation.
- `FAILED_RECOVERABLE`: a partial execution can resume from its recorded operation index.

Repeating the same operation returns the recorded result. It must not duplicate markers, clips or
timelines. At most one non-closed editorial-selection job may own markers on a source timeline.

## Candidate selection contract

ChatGPT reads the complete transcript, not only isolated chunks, and submits candidates ranked by
editorial strength. Each candidate contains:

- stable candidate ID `R01`, `R02`, ...;
- one-sentence thesis;
- exact first and last transcript anchors;
- indispensable context explanation;
- source start/end times and derived frame boundaries;
- estimated speech duration, CTA duration and final duration;
- uniqueness evidence against the other candidates;
- concise quality rationale using the current editorial preference profile.

The bridge validates that anchors occur in the pinned transcript, boundaries are ordered, the
interval is non-empty and final duration including CTA is at most 180 seconds. It rejects duplicate
IDs, overlapping duplicate proposals and candidates whose anchors cannot be resolved uniquely.
Semantic thesis quality remains a ChatGPT proposal subject to human review.

There is no minimum output count and no requirement to fill six positions. Candidates with the
same thesis are consolidated. The technical payload allows at most 20 candidates in one job to
bound marker and API load; a richer source is split into another explicit review job rather than
silently truncating candidates.

## Marker contract on the original timeline

Before any cut, the bridge creates two point markers per candidate on the original source timeline:

- `ARPHE_R01_IN`
- `ARPHE_R01_OUT`

and so on for every candidate. The job registry binds display name, exact frame, marker color,
timeline identity and job ID. The `IN` marker note contains the thesis, expected final duration and
the indispensable-context summary; the `OUT` marker note identifies the close boundary.

The bridge must not cut, move or retime clips, change tracks, change project/timeline settings or
alter any pre-existing marker during this phase. If a required frame already contains a marker and
Resolve cannot represent both, the operation blocks and reports the exact collision; it never
shifts a boundary silently.

Marker creation is all-or-nothing. If one marker write or read-back fails, the bridge removes only
the marker writes completed by that same attempt and leaves the job `BLOCKED`. Existing markers
remain untouched.

## Guided secretary interaction

After successful marking, ChatGPT always reports the exact project, timeline, candidate count and
review steps. The default response is compact:

1. listen from each `ARPHE_Rxx_IN` marker to its matching `ARPHE_Rxx_OUT` marker;
2. do not move or delete markers manually;
3. reply once with `OK`, `MODIFICA` or `RIFIUTA` and a short reason for every `Rxx`.

The response includes a copyable example:

```text
R01 OK — chiaro e diretto
R02 MODIFICA — inizia da "..." e termina dopo "..." — parte lentamente
R03 RIFIUTA — ripete R01
```

Reviewers never need to provide timecodes. ChatGPT converts the message into structured decisions.
If information is missing, it asks only for the missing candidate or reason and repeats the relevant
example. A full explanation remains available, but the normal interaction stays short.

## Review decision contract

Every marked candidate must have exactly one decision:

- `APPROVE`: keep proposed boundaries;
- `MODIFY`: provide new natural-language start/end anchors;
- `REJECT`: create no output timeline.

Every decision, including `APPROVE`, requires a non-empty human reason. The detailed reason remains
in the local job journal. A normalized reason tag may be inferred in addition to, never instead of,
the human explanation.

The bridge resolves modified anchors only against the pinned transcript and within a bounded
neighborhood of the candidate. Zero matches or multiple plausible matches return an ambiguity and
perform no cut. Submission is all-or-nothing: until all candidates are complete and unambiguous,
the job remains `MARKED` and no output timeline is created.

The completed structured review has a fingerprint. All cut operations require that exact current
fingerprint so a later change invalidates stale execution.

## Cutting and verification

After a complete review, the bridge creates one independent timeline for each approved or modified
candidate. Rejected candidates produce no timeline. Output names include job and candidate IDs so
retries can find the exact prior result.

For each output the bridge:

1. resolves source boundaries to exact frames;
2. appends only the approved source interval;
3. adds the existing workflow CTA;
4. preserves the source format explicitly rather than accepting Resolve defaults;
5. checks final duration including CTA is at most 180 seconds;
6. reads back clip boundaries and timeline duration;
7. records the result before proceeding to the next candidate.

If candidate four fails after three successful outputs, the job becomes `FAILED_RECOVERABLE` and
retains all markers. A retry validates the first three registered timelines and resumes at four;
it never recreates successful outputs.

Markers are removed only after every requested timeline passes verification. Removal targets the
exact registered marker names and frames for this job and verifies that pre-existing markers are
unchanged. The local manifest preserves the final boundaries after cleanup.

## Audio provenance

The feature does not add duplicate audio tracks by default. Enhanced audio is optional and remains
part of the established audio pipeline.

Every generated WAV must have an audio-job manifest containing source-media fingerprint, audio-job
ID, preset, output hash, duration and synchronization metadata. The editorial cut accepts the WAV
only when the manifest source fingerprint equals the selected source media and the output hash
matches the current file. Merely residing in an allowed directory is insufficient.

A mismatch blocks before any timeline mutation. Alessio or qualified technical staff may request
an explicit A/B comparison when audio sounds suspicious; this is not part of the secretary review
and does not clutter every Reel timeline.

## Metrics and local learning journal

The local per-workstation journal records, for every candidate:

- proposed, approved and final boundaries;
- `APPROVE`, `MODIFY` or `REJECT`;
- original human reason and normalized reason tags;
- proposed and final durations;
- amount removed or added at each boundary;
- proposal and review timestamps;
- whether the first proposal was accepted unchanged.

Job-level metrics include candidate count, accepted-unchanged rate, modification rate, rejection
rate, boundary-correction count and elapsed time from `MARKED` to complete feedback. Elapsed time is
reported honestly as elapsed review latency, not active labor minutes.

Detailed reasons, transcript anchors, paths and source identifiers remain local. They are never
committed to the public repository or copied between workstations.

## Shared learned preference profile

Each workstation may immediately use its own local history as a ranking overlay. A profile compiler
can produce a redacted proposal containing only aggregate editorial preferences, sample counts and
the source profile version. Examples include preferred duration bands, recurring weak-opening tags,
context reduction tendencies and structures correlated with unchanged approval.

The shared profile contains no transcript text, quotes, paths, media names, reviewer names or job
IDs. It is a readable, versioned JSON file in the repository. Compilation never pushes or edits the
shared profile automatically. Alessio must review and approve every shared-profile change before it
is committed. Both workstations use the latest merged shared version plus their unmerged local
overlay.

Profile updates are monotonic and auditable: the proposal states sample counts and before/after
values. Applying a shared update requires the expected prior profile digest, preventing concurrent
or stale overwrites. Reverting the repository commit restores the prior shared behavior without
deleting local journals.

## Feature flag and workstation rollout

All public marking, review submission, cutting, marker cleanup and learning-profile mutation routes
are gated by a new `CAP_EDITORIAL_SELECTION`, default `false`. Read-only contract, job inspection
and profile inspection remain available while disabled. The installer preserves an explicit local
value and never copies it between workstation profiles.

Rollout order:

1. automated tests and privacy audit;
2. install on `PC_PERSONALE` with the flag false;
3. isolated personal test using synthetic or approved non-sensitive content;
4. marker, natural-feedback, cut, recovery, duration, cleanup and rollback checks;
5. record personal evidence;
6. keep `PC_SEGRETERIA` disabled until its own independent gate can run without touching an open
   editorial job.

## Failure behavior

The system fails closed before mutation for wrong workstation identity, unsupported workflow,
stale media/transcript/timeline, marker collision, incomplete reasons, ambiguous anchors, duration
over 180 seconds, foreign audio provenance, stale review fingerprint or output-name collision.

Every write acquires the existing Resolve access lock and records job state around each operation.
Unexpected exceptions preserve markers and verified outputs, identify the first incomplete
candidate and return recovery instructions. Automatic recovery may resume registered operations;
it may not delete or replace an unregistered timeline.

## Public workflow surface

The implementation should expose a small complete workflow rather than additional primitive tools:

- inspect the editorial-selection contract and learned profile;
- prepare and mark one ARPHÈ podcast candidate job;
- inspect one job and generate the secretary instructions;
- submit a complete structured review;
- apply/resume verified cuts;
- inspect metrics and compile a redacted shared-profile proposal;
- approve/apply a shared-profile proposal as Alessio.

ChatGPT may make several bridge calls internally, but the operator experience remains: choose the
podcast, listen to markers, send one review message, receive verified Reel timelines.

## Testing requirements

Pure tests must cover:

- transcript-anchor uniqueness and frame conversion;
- dynamic candidate counts, duplicate thesis rejection and CTA-inclusive 180-second limit;
- marker namespace, collision handling, all-or-nothing creation and preservation of existing
  markers;
- complete decisions and mandatory reasons for every outcome;
- natural-language decisions after ChatGPT converts them to the structured contract;
- ambiguous or stale anchors causing zero cuts;
- review fingerprint invalidation;
- resumable per-candidate timeline creation without duplicates;
- verified marker cleanup only after all requested outputs pass;
- audio manifest/source/hash matching;
- local journal privacy and shared-profile redaction;
- stale profile digest and Alessio-only shared approval;
- feature flag defaults, installer preservation and cross-workstation rejection.

Integration fakes must assert exact Resolve mutation order and zero writes on every preflight
failure. Live personal validation must inspect the real source marker pairs, audition instructions,
at least one approved, modified and rejected candidate, partial-failure recovery, final timelines,
CTA-inclusive duration and marker cleanup. No segreteria result may be inferred from personal or
automated evidence.

## Completion boundary

The feature is complete when the shared contract and default-off code are merged, automated tests
and privacy checks pass, `PC_PERSONALE` has completed the live marker/review/cut/cleanup/rollback
gate and the repository records the exact evidence. `PC_SEGRETERIA` may remain explicitly pending
and disabled until the machine and its current editorial work are available for an isolated gate.
