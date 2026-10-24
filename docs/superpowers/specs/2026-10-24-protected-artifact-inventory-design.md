# Protected Artifact Inventory and Offline Maintenance Design

Date: 2026-10-24

Status: approved for offline implementation only; no runtime rollout or filesystem mutation.

## Intent

Extend the existing artifact-hygiene protocol without weakening its central rule: an unknown file is
protected. New audio and Colorist producers register their own closed outputs, manifests and review
dependencies as `PROTECTED`; they do not make those files eligible for retention. The existing
quarantine mechanism remains recoverable, while purge is disabled by policy and code.

## Constraints

- Work only on the offline feature branch; do not install, schedule, push or merge it.
- Do not modify Resolve, its projects/timelines, referenced source media, the Peeling A1, gate
  projects or the existing A/original, V5 and `PIU_NATURALE` WAVs.
- Do not move, quarantine or delete live files during design, tests, inventory or migration work.
- Do not classify legacy files by extension, prefix, age or directory alone.
- `PC_PERSONALE` and `PC_SEGRETERIA` remain isolated.
- Purge is disabled even after the seven-day quarantine deadline.

## Model

`ArtifactRecord` accepts two explicit protection classes. Existing policy categories remain
`DISPOSABLE`. New protected categories are `AUDIO_SOURCE`, `AUDIO_DERIVATIVE`, `AUDIO_MANIFEST`,
`COLORIST_STATE`, `COLORIST_ASSET`, `BACKUP_EVIDENCE` and `RESOLVE_REFERENCE`. A protected record can
carry opaque dependency tokens, review state and hold reasons. Dependencies are hashes or stable
logical identities, never arbitrary file contents.

Registration validates containment in a configured managed root, rejects symlinks/reparse points,
hashes closed files, and serializes mutation with a fail-closed registration lock. A lock left by a
crash is reported and never removed by guessing. Mutable Colorist state is refreshed only through a
protected upsert after its own atomic save.

## Producer integration

- Completed whole-source audio jobs register their output WAV and completed manifest. The WAV
  depends on the source fingerprint and manifest identity.
- Completed timeline-dialogue jobs register source WAV, processed WAV, worker manifest and parent
  manifest. Resolve project/timeline/media fingerprints are opaque dependencies and hold reasons.
- Every Colorist store save registers the Colorist registry as protected. DRX identity, project,
  timeline and review state are dependencies; `PREPARED`, `APPROVED`, `APPLYING` and `APPLIED`
  remain held for human review.
- Producer failure before registration leaves an unknown protected orphan for inspection.

## Inventory and simulation

The root inventory names every configured root and its mode. Only exact bridge-owned producer roots
are scanned. Render diagnostics/technical-preview/staging and rotated logs keep the existing shallow
rules. Audio and audio-job roots are recursively inventoried because they are dedicated bridge
roots, but unregistered entries are `UNCLASSIFIED_PROTECTED`. Profile, media, assets, backups,
Resolve archives and project/timeline references are reference-only and never cleanup-scanned.

`simulate_artifact_maintenance` is pure read-only planning. It reports category/state bytes,
quarantine candidates, purge-blocked records, dependency/review holds, active-job holds and potential
space. It rechecks hashes but performs no move. Registered disposable records may be proposed for
quarantine only when terminal, unchanged, dependency-free and not covered by an active job.
Registered protected records and unknown items are never candidates.

Legacy migration is dry-run only. It validates known audio/Colorist schemas and fingerprints and
returns proposed protected registrations. Missing hashes, symlinks, changed media, unknown schemas
and gate/backup references become manual-review holds. No proposal is committed automatically.

## Periodicity and failure safety

The runtime uses one daemon loop, not an OS task. It wakes periodically and calls the existing
24-hour due check. Laptop sleep/offline time is harmless because the decision uses stored UTC
attempt times and no network. Registration and maintenance locks fail closed. An active producer,
active Resolve render, active Colorist preview/apply or unreadable registry prevents a candidate
decision. A concurrent registration either completes before the scan snapshot or blocks the scan;
it cannot be silently lost.

`purge_enabled` is fixed to `false` in policy. Quarantined records past their deadline are reported
as `PURGE_DISABLED`; no purge function is called. Restore remains collision-safe and digest-bound.

## Verification

Temporary-directory tests cover producer registration and dependencies, active/review holds,
unknown protection, hash drift, symlink rejection, registration-lock crashes, periodic wakeups,
laptop time jumps, purge-disabled behavior and legacy migration dry-run immutability. A read-only
inventory of the live configured roots produces only counts, categories and protected proposals.

