# Resolve 21.2 Runtime Hardening Design

## Intent

Make the Resolve 21.2 adapters deployed on PC_PERSONALE reproducible from Git and correct the two safety gaps found by the audit, without editing any production timeline.

## Goals

- Port the focused Resolve 21.2 compatibility, review-export, and native-transcription adapters onto the latest `origin/main` base.
- Treat `timelinePlaybackFrameRate` as a writable Resolve 21.2 setting when required, while preserving compatibility with projects where changing `timelineFrameRate` updates playback automatically.
- Snapshot and roll back resolution, project frame rate, and playback frame rate as one transaction.
- Make native-transcription polling distinguish a fresh result from a pre-existing transcript, expose a terminal timeout, keep reads side-effect free, and bind idempotency to the speaker-detection option.
- Deploy exactly the reviewed files to PC_PERSONALE only after focused and full-suite verification.

## Non-goals

- No automatic timeline, subtitle, color, audio, Fusion, or render changes.
- No P1 workflow expansion from the audit.
- No replacement of the existing ARPHE bridge or official MCP integration.
- No cleanup or mutation of the existing dirty `C:\ARPHE\video-editing-manual` checkout.

## Chosen approach

Use an isolated worktree based on the current remote main branch, port only the existing 21.2 adapters and their thin registrations, then harden them test-first. Deployment uses an explicit file allowlist and a timestamped backup. This preserves the running bridge while creating a reviewable provenance chain.

Direct edits in the dirty checkout were rejected because they would mix unrelated work. Mirroring the entire runtime was rejected because the audit found substantial drift and no trustworthy one-to-one source checkout.

## Format transaction

`apply_project_format` snapshots width, height, project FPS, and playback FPS before mutation. It applies width, height, and project FPS first. If playback is already correct, no redundant write is made; otherwise the Resolve 21.2 playback setting is written explicitly. Any rejected setter or non-conforming read-back restores every snapshotted value, including playback, before raising.

## Native-transcription state

Starting a job captures a canonical hash of the current native transcript before calling `TranscribeAudio`. The job identity includes workstation, project, timeline, clip, and speaker-detection mode. Polling reports `COMPLETED` only when the current validated transcript differs from the baseline and contains segments. An unchanged or empty result remains `TRANSCRIBING` until the bounded timeout, then reports `TIMED_OUT`. Polling computes status without rewriting the manifest.

## Verification and rollout

Focused tests cover rollback and transcript freshness/state transitions. The full bridge suite runs in the real PC_PERSONALE dependency environment. Deployment backs up and replaces only changed runtime files, then performs read-only health and compatibility checks. No live export or transcription is launched against user media during rollout.
