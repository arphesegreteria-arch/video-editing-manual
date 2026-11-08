# Resolve 21.2 Runtime Hardening Implementation Plan

**Goal:** Reconcile the deployed Resolve 21.2 adapters with Git and fix FPS transactionality plus native-transcription state handling on PC_PERSONALE.

**Architecture:** Keep the new APIs in three isolated adapters and thin server wrappers. Harden the existing format contract and native-transcription manifest state machine. Deploy from an isolated, tested worktree with an explicit backup and file list.

**Tech stack:** Python 3.12, DaVinci Resolve 21.2 Scripting API, MCPServer, unittest.

**Spec:** `docs/superpowers/specs/2026-11-08-resolve-21-2-hardening-design.md`

## Task 1: Reconcile focused Resolve 21.2 adapters

**Files:** `bridge/resolve21_compat.py`, `bridge/review_export21.py`, `bridge/native_transcription21.py`, their tests, `bridge/server.py`, and `bridge/tool_catalog.py`.

- [x] Add the existing adapter tests to the clean worktree and confirm they fail because the adapters are absent.
- [x] Port the focused adapters and thin registrations from the PC source, resolving changes against current main.
- [x] Run the focused adapter tests and catalog checks.

## Task 2: Make project-format application transactional

**Files:** `bridge/format_contract.py`, `tests/test_format_contract.py`, and affected workflow tests.

- [x] Add failing tests for explicit 21.2 playback writes, automatic playback alignment, and rollback of playback on setter/read-back failure.
- [x] Implement the four-setting snapshot, conditional playback write, conforming read-back, and complete rollback.
- [x] Run focused format and workflow tests.

## Task 3: Harden native-transcription state

**Files:** `bridge/native_transcription21.py`, `tests/test_native_transcription21.py`.

- [x] Add failing tests for speaker-mode job identity, stale transcript rejection, fresh completion, read-only polling, and timeout.
- [x] Add baseline fingerprints and bounded state derivation without poll-time writes.
- [x] Run the focused transcription tests.

## Task 4: Verify and deploy to PC_PERSONALE

- [x] Run the complete bridge suite in the real dependency environment.
- [x] Review the final diff and record the exact deployment file list.
- [x] Back up the matching runtime files, deploy the explicit list, and rerun the runtime suite.
- [x] Restart or refresh the bridge safely, then run read-only health and Resolve 21.2 compatibility checks.
- [x] Confirm no project or timeline mutation occurred and report residual limitations.
