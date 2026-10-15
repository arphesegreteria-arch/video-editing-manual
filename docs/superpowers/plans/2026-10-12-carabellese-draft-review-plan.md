# Carabellese Draft Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a safe, private, fingerprint-bound phone-review preview of batch-approved Carabellese pause cuts.

**Architecture:** Add a workstation-local draft-review job alongside the existing cleanup job, reuse its pinned candidates and checkpoint primitives, and operate only on an owned duplicated timeline. Generate a verified preview and source-to-draft review map, then transfer only those verified artifacts to private Library storage.

**Tech Stack:** Python 3.12, DaVinci Resolve scripting API, existing ARPHE bridge state/checkpoint/render helpers, ChatGPT Library file upload.

**Spec:** `docs/superpowers/specs/2026-10-12-carabellese-draft-review-design.md`

## Global Constraints

- `PC_PERSONALE` only; never read or modify `PC_SEGRETERIA`, tunnels, credentials, tasks, or MCP schema.
- Do not change the existing final-cleanup semantics or source timeline.
- Draft cuts may use only explicit batch-approved `PAUSE_*` candidates and must retain existing silence handles.
- The current ten pause candidates may be batch-approved for a draft only; no final master or publication is authorized.
- Every write requires matching source, transcript, contract, proposal, timeline, decision, and draft fingerprints.
- Private Library transfer occurs only after local output/hash verification; no share or publish action exists.

## Review Focus

- A stale source timeline after duplication must block draft cuts and preserve the source.
- A zero-length transcript token adjacent to a candidate must never reach the draft splice adapter.
- A successful-looking MP4 with wrong audio codec/rate or hash must not be uploaded.
- A retry after a partially-created draft must reuse or recover the owned object, never make another duplicate.
- Phone approval for a preview superseded by a changed map/preview must be rejected.

---

### Task 1: Draft state and exact decision binding

**Files:**
- Create: `bridge/carabellese_draft_review.py`
- Modify: `bridge/carabellese_jobs.py`
- Modify: `bridge/server.py`
- Test: `tests/test_carabellese_draft_review.py`

**Interfaces:**
- Consumes: `CarabelleseJob`, its proposal fingerprint and existing batch decisions.
- Produces: `DraftReviewJob`, `create_draft_review(...)`, `draft_review_fingerprint(...)` and a read-only inspection card.

- [ ] Write failing tests for batch-only pauses, stale source/proposal/decision fingerprints, and idempotent retry.
- [ ] Run `python -m unittest scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_carabellese_draft_review` and verify RED.
- [ ] Implement the isolated state record and `prepare_carabellese_draft_review(carabellese_job_id, pause_decision)` wrapper; reject individual-candidate shortcuts and non-pause candidates.
- [ ] Run the focused tests and verify GREEN.
- [ ] Commit `feat: bind Carabellese draft review state`.

### Task 2: Duplicate timeline, checkpoint and conservative draft splice

**Files:**
- Create: `bridge/carabellese_draft_apply.py`
- Modify: `bridge/carabellese_checkpoint.py`
- Modify: `bridge/server.py`
- Test: `tests/test_carabellese_draft_apply.py`

**Interfaces:**
- Consumes: a `PREPARED` `DraftReviewJob` and verified source cleanup candidates.
- Produces: `apply_carabellese_draft_review(...) -> DraftReviewJob` with draft timeline/checkpoint/operation evidence.

- [ ] Write failing fake-Resolve tests proving one owned duplicate, source byte/identity invariance, checkpoint-before-cut, descending cuts, handles, zero-token protection, and recoverable partial failure.
- [ ] Run the focused test and verify RED.
- [ ] Implement duplicate ownership validation and the draft-only splice adapter; persist original and draft frame/time values for each verified operation.
- [ ] Run the focused tests and verify GREEN.
- [ ] Commit `feat: create isolated Carabellese draft timeline`.

### Task 3: Review map, markers and temporary preview indicators

**Files:**
- Create: `bridge/carabellese_draft_preview.py`
- Modify: `bridge/carabellese_markers.py`
- Modify: `bridge/render_tools.py`
- Test: `tests/test_carabellese_draft_preview.py`

**Interfaces:**
- Consumes: verified draft operations and a 30 fps resolved format.
- Produces: `write_draft_review_map(...) -> Path`, `render_draft_preview(...) -> DraftPreviewEvidence`.

- [ ] Write failing tests for chronological mapping, source/draft timecode calculation, exact marker parity, temporary-only overlays, H.264/AAC 48 kHz verification, and failed-render no-upload behavior.
- [ ] Run the focused test and verify RED.
- [ ] Implement a canonical JSON map/hash plus owned marker and preview-overlay lifecycle; delete/restore overlays after rendering and verify the preview separately from the draft timeline.
- [ ] Run the focused tests and verify GREEN.
- [ ] Commit `feat: render marked Carabellese draft preview`.

### Task 4: Private Library delivery and phone-review finality gate

**Files:**
- Create: `bridge/carabellese_draft_delivery.py`
- Modify: `bridge/carabellese_draft_review.py`
- Modify: `bridge/server.py`
- Test: `tests/test_carabellese_draft_delivery.py`

**Interfaces:**
- Consumes: `DraftPreviewEvidence` with verified preview/map hashes.
- Produces: `deliver_carabellese_draft_private(...)`, `submit_carabellese_draft_phone_review(...)`.

- [ ] Write failing tests for upload only after verification, saved artifact identities, upload failure recovery, reject/accept responses, and stale preview/map fingerprint rejection.
- [ ] Run the focused test and verify RED.
- [ ] Implement private delivery through the existing Library file-transfer boundary and persist returned identities in the local draft job; expose no share or publication path.
- [ ] Run the focused tests and verify GREEN.
- [ ] Commit `feat: deliver fingerprinted Carabellese draft review`.

### Task 5: End-to-end personal gate and regression verification

**Files:**
- Modify: `tests/test_carabellese_tools.py`
- Modify: `validation/carabellese-draft-review-ledger.json`
- Modify: `CURRENT_STATE.md`

**Interfaces:**
- Consumes: Tasks 1-4 and the existing `MARKED` job.
- Produces: a private `REVIEW_READY` draft evidence record; no final-cleanup invocation.

- [ ] Add RED tests for an existing ten-pause batch decision, exact ten-map/marker correspondence, source timeline invariance, and stale post-view approval.
- [ ] Run the draft-review suite plus existing Carabellese analysis/apply tests and verify RED before the final missing integration is added.
- [ ] Execute the approved `PC_PERSONALE` gate: inspect, duplicate, checkpoint, apply conservative draft cuts, render/verify preview, private-deliver, and inspect `REVIEW_READY`; do not submit final approval or call the final apply endpoint.
- [ ] Run the full Creative bridge suite, record the actual command/result, and update the ledger only on green evidence.
- [ ] Commit `test: validate private Carabellese draft review gate`.

## Self-review

- Coverage: Tasks 1-5 cover separate state, source preservation, splice safety, visual/map review, private delivery, stale phone approval, and the personal gate.
- Type consistency: every later task consumes the exact `DraftReviewJob`, `DraftPreviewEvidence`, and state names introduced earlier.
- Proportion: no implementation bodies are embedded; the plan defers API mechanics to tests and existing Resolve wrappers.
- New decisions versus the approved cleanup design: temporary duplicate timeline, temporary in-preview indicators, private Library artifacts, and a distinct phone-review finality gate. All other provenance, pause, checkpoint, and final-apply rules are reused unchanged.
