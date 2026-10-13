# Music Bed Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a closed-world bridge tool that installs or replaces an owned music bed on an allowed ARPHE timeline.

**Architecture:** Extend the existing Creative 03 asset pathway with an audio-specific validator and an ownership record. The MCP tool receives only an allowlisted local asset reference and bounded playback parameters; it may replace only a bed registered by the bridge, leaving all other media untouched.

**Tech Stack:** Python 3.12, MCP Python SDK, DaVinci Resolve Studio external scripting API, pytest.

**Spec:** `docs/superpowers/specs/2026-10-13-music-bed-automation-design.md`

## Global Constraints

- No URL, shell, generic path, generic track setter, or arbitrary Resolve property input.
- Asset must resolve under the configured allowlist and must have an audio-capable extension.
- Allowed gain: -36 to -12 dB; default -24 dB. Fade duration: 0–60 frames; default 12.
- Only an ARPHE/allowlisted timeline may be targeted.
- Video tracks and non-bridge-owned audio clips must remain unchanged.
- Capability defaults to disabled and requires a disposable Resolve gate before PC_PERSONALE rollout.

## Review Focus

- Reject an audio filename outside the allowed root; cover in Task 1.
- Reject a video-only or image-only asset presented as music; cover in Task 1.
- Do not replace an unowned A2 clip; cover in Task 2.
- Handle a source shorter than the visual timeline without looping silently; cover in Task 2.
- A repeated call with the same asset and settings must be idempotent; cover in Task 3.

---

### Task 1: Audio asset validation

**Files:**
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/safety.py`
- Test: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_music_safety.py`

**Interfaces:**
- Produces: `allowed_music_asset(asset_ref: str, root: Path) -> Path` and `validate_music_settings(gain_db: float, fade_in_frames: int, fade_out_frames: int) -> tuple[float, int, int]`.

- [ ] Write failing tests for allowed local audio, path traversal, unsupported extension, out-of-range gain and fade bounds.
- [ ] Run the targeted test to verify it fails.
- [ ] Implement the two validators using resolved paths, explicit extension sets and existing finite-number validation.
- [ ] Run the targeted tests to verify they pass.
- [ ] Commit: `feat: validate allowlisted music assets`.

### Task 2: Owned music-bed placement

**Files:**
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/registry.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/asset_tools.py`
- Test: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_music_bed.py`

**Interfaces:**
- Consumes: Task 1 validators.
- Produces: `set_music_bed(project, timeline, config, registry, asset_ref, gain_db, fade_in_frames, fade_out_frames) -> dict[str, Any]`.
- Produces: registry record keyed by project and timeline with created item identity, asset digest and applied settings.

- [ ] Write failing unit tests with Resolve doubles for first placement, replacing an owned item, declining an unowned item, source-too-short failure and no V1 mutation.
- [ ] Run the targeted test to verify it fails.
- [ ] Implement audio-track discovery/creation, import/trim to effective video duration, bounded fades/gain and ownership-only replacement under the existing Resolve access lock.
- [ ] Run the targeted tests to verify they pass.
- [ ] Commit: `feat: add owned timeline music bed`.

### Task 3: Closed MCP surface and capability gate

**Files:**
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/config.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/server.py`
- Test: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_music_bed_server.py`

**Interfaces:**
- Consumes: Task 2 `set_music_bed`.
- Produces: `set_timeline_music_bed(music_asset_id, gain_db=-24.0, fade_in_frames=12, fade_out_frames=12) -> dict[str, Any]`.

- [ ] Write failing server tests for capability-off rejection, timeline allowlist enforcement, parameter bounds and repeated-call idempotence.
- [ ] Run the targeted test to verify it fails.
- [ ] Add `CAP_MUSIC_BED` disabled by default, resolve the asset ID through the configured approved asset registry, and expose one idempotent MCP tool with no raw path argument.
- [ ] Run the targeted tests to verify they pass.
- [ ] Commit: `feat: expose gated music bed tool`.

### Task 4: Resolve gate and operating documentation

**Files:**
- Modify: `CURRENT_STATE.md`
- Modify: `EXPERIMENT_LOG.md`
- Modify: `CHANGELOG.md`
- Create: `validation/music-bed-gate.md`

**Interfaces:**
- Consumes: Task 3 MCP tool.
- Produces: documented PASS/FAIL evidence and rollout decision for PC_PERSONALE.

- [ ] Write a disposable-project gate checklist: approved local asset, 28-second timeline, unchanged V1/A1, A2 ownership, duration match, -24 dB and fade read-back.
- [ ] Run the gate on a disposable ARPHE timeline and record measured evidence.
- [ ] If and only if PASS, update the three persistent records with capability status; otherwise leave capability disabled and record the failure.
- [ ] Perform one real non-destructive application of “Dreamy Autumn” on the approved working timeline after the gate and verify it is the owned A2 bed.
- [ ] Commit: `docs: record music bed validation`.
