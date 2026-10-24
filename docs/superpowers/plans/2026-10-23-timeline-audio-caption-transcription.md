# Timeline Audio Caption Transcription Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transcribe the exact audio of an allowlisted Resolve timeline and make generic caption creation reject unrelated or stale transcripts.

**Architecture:** A managed job first renders the selected timeline to an audio-only PCM WAV, then launches the existing isolated word-timestamp transcription worker. The transcript is cryptographically bound to the workstation, project, timeline edit fingerprint, rendered audio, duration, and frame rate; caption creation validates that binding before duplicating anything.

**Tech Stack:** Python 3, DaVinci Resolve scripting API, existing `faster-whisper` worker, JSON job manifests, `unittest`.

**Spec:** `docs/superpowers/specs/2026-10-23-timeline-audio-caption-transcription-design.md`

## Global Constraints

- Live verification is PC_PERSONALE only.
- Never save the Resolve project automatically.
- Never transcribe the uncut media source for this caption path.
- Never start or delete render jobs not created by this managed job.
- Fail closed on any source-binding mismatch.
- Keep tools generic and free of project- or timeline-specific names.

## Review Focus

- Existing foreign render jobs: leave them untouched and start only the owned job.
- Timeline changes between render and caption creation: reject the stale transcript before duplication.
- Interrupted render or worker: return resumable state without launching duplicates.
- Missing, malformed, wrong-duration, or replaced WAV: reject and retain auditable job state.
- Resolve context restoration failure: report failure and do not claim the source was preserved.

---

### Task 1: Managed timeline audio render job

**Files:**
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/timeline_transcription.py`
- Test: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_timeline_transcription.py`

**Interfaces:**
- Consumes: `timeline_edit_fingerprint(timeline)`, `safe_call`, `CreativeConfig`, render job APIs.
- Produces: `start_timeline_audio_transcription(project, config, registry, source_timeline, model="small", language="it") -> dict[str, object]` and `get_timeline_audio_transcription_job(project, config, registry, job_id) -> dict[str, object]`.

- [ ] Write failing tests proving audio-only 48 kHz PCM settings, selective job start, exact timeline/frame binding, preservation of foreign jobs, context restoration, and no project save.
- [ ] Run `python -m unittest tests.test_timeline_transcription -v` and confirm the tests fail because the module/API is absent.
- [ ] Implement the smallest managed render state machine and owned cleanup needed to pass.
- [ ] Re-run the focused tests and confirm they pass.
- [ ] Commit the task.

### Task 2: Word-timestamp worker handoff and provenance

**Files:**
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/timeline_transcription.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/transcription_worker.py`
- Test: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_timeline_transcription.py`

**Interfaces:**
- Consumes: completed owned WAV render and existing worker options.
- Produces: `ARPHE_TRANSCRIPT_V1` with `timeline_source` provenance and a public completed-job response containing `transcript_file`.

- [ ] Write failing tests for WAV fingerprint/duration validation, one worker launch, resume behavior, and emitted `timeline_source` fields.
- [ ] Run the focused tests and verify the intended failures.
- [ ] Add generic optional provenance passthrough to the worker and complete the managed job transition.
- [ ] Re-run focused tests and confirm green.
- [ ] Commit the task.

### Task 3: Caption source-binding gate

**Files:**
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/caption_test.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_caption_test.py`

**Interfaces:**
- Consumes: timeline-bound `ARPHE_TRANSCRIPT_V1` and live source timeline.
- Produces: validation before duplication; foreign or stale transcripts raise `ValidationError`.

- [ ] Write failing tests proving `video in 3`-style media transcripts and stale timeline bindings are rejected before `duplicate_timeline`, while a matching timeline transcript succeeds.
- [ ] Run focused tests and verify the mismatch test fails for the current missing gate.
- [ ] Load transcript metadata, compare every required binding field, then expose segments only after validation.
- [ ] Re-run focused tests and confirm green.
- [ ] Commit the task.

### Task 4: MCP exposure and documentation

**Files:**
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/server.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/tool_catalog.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/README.md`
- Test: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_timeline_transcription.py`

**Interfaces:**
- Consumes: Task 1 and Task 2 functions.
- Produces: generic MCP tools `start_timeline_audio_transcription` and `get_timeline_audio_transcription_job`.

- [ ] Write failing catalog/server tests for exact signatures and read-back fields.
- [ ] Run focused tests and verify red.
- [ ] Add server wrappers, catalog entries, and PC_PERSONALE-to-PC_SEGRETERIA rollout notes without deploying the latter.
- [ ] Run focused tests, then `python -m unittest discover -s tests -v` and confirm the full suite passes.
- [ ] Commit the task.

### Task 5: PC_PERSONALE deployment and live non-saving verification

**Files:**
- Modify only the PC_PERSONALE installed bridge files through the existing deployment procedure.

**Interfaces:**
- Consumes: merged worktree implementation and existing runtime deployment scripts.
- Produces: a transcript bound to `advbeppe / Timeline 1`, followed by a new unsaved caption test timeline.

- [ ] Verify branch status and deploy only to PC_PERSONALE.
- [ ] Restart the dedicated personal bridge and confirm its workstation identity.
- [ ] Start timeline-audio transcription for `advbeppe / Timeline 1`; poll to completion and read back the transcript binding and text.
- [ ] Create a fresh caption test timeline with the established graphic-kit style and CTA cutoff; capture representative frames and inspect text/safe zone.
- [ ] Report `saved: false`, do not call `save_project`, and leave PC_SEGRETERIA unchanged.
- [ ] Commit documentation/read-back evidence and update the existing PR.
