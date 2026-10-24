# Natural Dialogue Dereverb Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to execute this plan task-by-task, and `superpowers:test-driven-development` for every behavior change.

**Goal:** Add a generic, non-destructive bridge workflow that renders the exact audio from a Resolve timeline, applies a restrained natural dialogue cleanup, and creates a verified test timeline with one aligned audio copy.

**Architecture:** Extend the existing offline audio worker with a deterministic V5 preset, then add an asynchronous Resolve job that reuses the current timeline-audio render safety pattern. The job binds itself to the workstation, project, source timeline, edit fingerprint, owned render job, WAV fingerprints, and target timeline. It duplicates only after processing succeeds, replaces only duplicated A1, verifies the resulting structure, and never saves the project.

**Tech Stack:** Python 3.12, PyAV/FFmpeg audio filters, DaVinci Resolve scripting API, pytest, existing ARPHE bridge runtime and manifest helpers.

**Spec:** `docs/superpowers/specs/2026-10-24-natural-dialogue-dereverb-design.md`

**Global Constraints:**

- Work only in the isolated `arphe/adv-caption-audio-20261022` worktree and keep the color-test branch untouched.
- Use generic commands and identifiers; never encode `peeling` or a specific timeline name in production code.
- Do not connect to Resolve, install the runtime, restart services, save a project, or render a preview until the user is warned and the code/test phase is complete.
- The source timeline is immutable. Any failure after duplication must fail closed and restore the duplicate's original A1 when possible.
- Preserve foreign Resolve render jobs and restore the current timeline and Deliver settings after the owned audio render is queued.
- Limit rollout to `PC_PERSONALE`; do not update `PC_SEGRETERIA`.
- Keep the bridge work in its own PR. The separate color-test branch, if it contains code or commits, has its own PR and merge.

**Review Focus:**

- Concurrent edits to the source between audio render and application must be detected before any timeline mutation.
- Foreign render jobs and unrelated timelines must never be removed or modified.
- A failed replacement append must not leave two audio copies or damage the source timeline.
- Repeated polling of a completed job must be idempotent and must not create another timeline.
- Invalid WAV format, duration, channel count, or provenance must fail before Resolve writes.

---

## Task 1: Add the natural V5 audio preset

**Files:**

- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/audio_worker.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/audio_tools.py`
- Test: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_audio_pipeline.py`

**Interfaces:**

- Export `DEREVERB_NATURAL_PRESET = "ARPHE_DIALOGUE_DEREVERB_NATURAL_V5"` from `audio_worker.py`.
- Add the preset to the existing allowlist consumed by `start_audio_job`.
- The preset output contract is stereo, 48 kHz, PCM s16 WAV with unchanged sample count and peak at or below -1 dBFS.

### Step 1: Write failing preset contract tests

Add tests that submit the V5 preset through the real audio worker path and assert:

- the preset is accepted;
- output is stereo PCM s16 at 48 kHz;
- output duration/sample count matches input;
- peak does not exceed `0.891` full scale.

Use a generated fixture containing voiced-frequency bursts plus hand-built exponentially decaying room tails. The production mutation caught is a missing or incorrectly routed V5 preset.

**Run:** `python -m pytest tests/test_audio_pipeline.py -k "dereverb_natural_v5" -q`

**Expected:** FAIL because the V5 preset is not defined or allowlisted.

### Step 2: Implement the minimum V5 chain

Centralize the following deterministic chain beside the existing presets:

- `highpass=f=70`
- `afftdn=nr=3:nf=-55:tn=1`
- `equalizer=f=220:t=q:w=0.8:g=-2.5`
- `equalizer=f=430:t=q:w=1.0:g=-2.0`
- `agate=threshold=0.035:ratio=1.8:attack=20:release=220:range=0.35:makeup=1`
- `acompressor=threshold=0.16:ratio=1.5:attack=25:release=250:makeup=1.03`
- `volume=0.5dB`
- `alimiter=limit=0.891:attack=8:release=80:level=false`

Do not add neural denoise, `dynaudnorm`, or a de-esser.

**Run:** `python -m pytest tests/test_audio_pipeline.py -k "dereverb_natural_v5" -q`

**Expected:** PASS.

### Step 3: Add a behavior test for restrained tail reduction

Using the same independent synthetic fixture, assert that quiet inter-burst tail RMS is reduced by at least 20% while active burst RMS remains within `0.55x..1.45x` of the input. The production mutation caught is removal of the expander/EQ or an over-aggressive gate that damages speech.

**Run:** `python -m pytest tests/test_audio_pipeline.py -k "dereverb_natural_v5" -q`

**Expected:** First FAIL if the initial values do not meet the observable contract; adjust only the centralized V5 numeric parameters, then PASS.

### Step 4: Verify and commit Task 1

**Run:** `python -m pytest tests/test_audio_pipeline.py -q`

**Expected:** PASS.

**Commit:** `feat: add natural dialogue dereverb preset`

---

## Task 2: Add the asynchronous timeline cleanup job

**Files:**

- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/timeline_dialogue_cleanup.py`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_timeline_dialogue_cleanup.py`
- Reuse: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/timeline_transcription.py`
- Reuse: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/edge_fade_tools.py`
- Reuse: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/audio_cta_tail.py`

**Interfaces:**

```python
def start_timeline_dialogue_cleanup_test(
    project: Any,
    config: CreativeConfig,
    registry: Any,
    source_timeline: str,
    target_name: str,
    preset: str = DEREVERB_NATURAL_PRESET,
) -> dict[str, object]:
    ...

def get_timeline_dialogue_cleanup_job(
    project: Any,
    config: CreativeConfig,
    registry: Any,
    job_id: str,
) -> dict[str, object]:
    ...
```

Job IDs match `^dialogue_cleanup_[0-9a-f]{16}$`. States are `RENDERING`, `PROCESSING`, `APPLYING`, `COMPLETED`, and `INTERRUPTED`.

### Step 1: Write failing start-job safety tests

Cover real orchestration behavior with controlled Resolve fakes:

- accepts only an allowlisted project/timeline with exactly one V1 and one A1 clip and matching record range;
- refuses an existing target name and a concurrent Resolve render;
- stores source project/timeline identity, edit fingerprint, fps, duration, target, preset, owned render job ID, and managed paths;
- queues exactly one owned Audio Only/LPCM 48 kHz render;
- restores the current timeline and Deliver settings;
- leaves foreign render jobs intact.

**Run:** `python -m pytest tests/test_timeline_dialogue_cleanup.py -k "start" -q`

**Expected:** FAIL because the module/API does not exist.

### Step 2: Implement the minimum start path

Reuse or extract the timeline-transcription render helpers instead of duplicating Deliver-state logic. Validate before side effects, generate managed paths and a manifest, queue one owned job, restore state in `finally`, and start only the owned render.

**Run:** `python -m pytest tests/test_timeline_dialogue_cleanup.py -k "start" -q`

**Expected:** PASS.

### Step 3: Write failing render/process transition tests

Cover:

- pending render remains `RENDERING` with no worker launch;
- failed/missing/foreign owned render returns `INTERRUPTED` without timeline mutation;
- completed render is deleted by exact owned ID only;
- WAV must be PCM s16, stereo, 48 kHz, within one frame of expected duration, and fingerprinted;
- a valid render launches one `ARPHE_AUDIO_JOB_V2` worker manifest and advances to `PROCESSING`;
- worker failure or invalid output is `INTERRUPTED` before Resolve writes.

**Run:** `python -m pytest tests/test_timeline_dialogue_cleanup.py -k "render or processing" -q`

**Expected:** FAIL on missing transitions.

### Step 4: Implement render/process transitions

Persist every transition atomically. On a completed render, verify the managed WAV before starting the existing audio worker with the V5 preset. Poll the worker manifest, verify its output fingerprint/format/duration, then advance to `APPLYING`.

**Run:** `python -m pytest tests/test_timeline_dialogue_cleanup.py -k "render or processing" -q`

**Expected:** PASS.

### Step 5: Write failing apply/read-back tests

Cover:

- changed source edit fingerprint refuses application before duplication;
- successful application duplicates once, removes only duplicated A1, appends one processed clip at the original record frame, and preserves V1 media/range;
- read-back proves one V1, one A1, matching ranges, expected duration, managed output provenance, `saved: false`, and the target current;
- append/read-back failure removes bridge-owned inserted audio when present and restores the duplicate's original A1;
- source timeline remains byte-for-byte equivalent in every case;
- repeated polling after `COMPLETED` returns the stored read-back and never duplicates again;
- malformed or foreign job IDs are refused.

**Run:** `python -m pytest tests/test_timeline_dialogue_cleanup.py -k "apply or idempotent or rollback" -q`

**Expected:** FAIL on missing application behavior.

### Step 6: Implement duplicate, replacement, rollback, and idempotence

Before any write, re-read and compare the source fingerprint. Duplicate using existing non-destructive helpers. Preserve the original duplicated audio item's media/source/record range for rollback. Replace A1 with inclusive `endFrame = duration_frames - 1`. Store final read-back in the manifest before returning `COMPLETED`; completed polls only return that stored result.

**Run:** `python -m pytest tests/test_timeline_dialogue_cleanup.py -k "apply or idempotent or rollback" -q`

**Expected:** PASS.

### Step 7: Verify and commit Task 2

**Run:** `python -m pytest tests/test_timeline_dialogue_cleanup.py tests/test_timeline_transcription.py tests/test_audio_pipeline.py -q`

**Expected:** PASS.

**Commit:** `feat: create verified timeline dialogue cleanup tests`

---

## Task 3: Publish generic bridge tools and documentation

**Files:**

- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/server.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/tool_catalog.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/README.md`
- Modify: `docs/04_LONGFORM_WORKFLOW.md`
- Test: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_timeline_dialogue_cleanup.py`

### Step 1: Write failing public-tool tests

Assert consumer-visible behavior:

- both generic commands are present in the tool catalog with generic schemas;
- server wrappers use `RESOLVE_ACCESS_LOCK` and the current bridge context;
- both are classified as write-capable operations because polling may advance state and mutate the duplicate;
- no schema field or description contains a project/timeline-specific name.

**Run:** `python -m pytest tests/test_timeline_dialogue_cleanup.py -k "catalog or server" -q`

**Expected:** FAIL because the tools are not registered.

### Step 2: Register the tools

Add thin server wrappers and catalog entries. Keep all behavior in `timeline_dialogue_cleanup.py`; wrappers only acquire the lock and pass bridge context.

**Run:** `python -m pytest tests/test_timeline_dialogue_cleanup.py -k "catalog or server" -q`

**Expected:** PASS.

### Step 3: Document operator and rollout procedure

Document:

- exact start/poll sequence and read-back fields;
- the human listening gate and the prohibition on project save;
- PC_PERSONALE-only installation/test steps;
- later PC_SEGRETERIA backup/install/ping/disposable-project verification, without performing it;
- separate PR/merge handling for independent color code.

### Step 4: Verify and commit Task 3

**Run:** `python -m pytest tests/test_timeline_dialogue_cleanup.py tests/test_audio_pipeline.py tests/test_timeline_transcription.py -q`

**Expected:** PASS.

**Commit:** `docs: publish timeline dialogue cleanup workflow`

---

## Task 4: Full verification and PC_PERSONALE rollout gate

**Files:**

- Modify only if evidence requires a fix: files owned by Tasks 1–3
- Record evidence in: `docs/04_LONGFORM_WORKFLOW.md` or an existing deployment evidence document selected during implementation

### Step 1: Run bridge verification

Run the repository's documented complete Python and Windows verification suites from the bridge directory. Capture exact pass/fail counts. Any new failure is handled test-first before continuing.

**Expected:** All suites pass; pre-existing skips are named.

### Step 2: Review the complete branch

Generate a review package from the branch merge base through `HEAD`. Review specifically the five `Review Focus` failure classes and all ledger rulings. Any Critical or Important finding gets one TDD fix pass and a fresh full suite.

**Expected:** No unresolved Critical or Important finding.

### Step 3: Stop before Resolve or runtime changes

Report the verified code/test state to the user and state exactly what the next live step would touch. Wait for explicit confirmation that the color-test chat is no longer using Resolve.

**Expected:** No Resolve connection, service restart, install, project mutation, or render occurs before confirmation.

### Step 4: Install and exercise only on PC_PERSONALE after confirmation

After confirmation:

1. back up current runtime/config;
2. install the verified bridge revision and restart the PC_PERSONALE runtime without GUI control;
3. ping and confirm workstation identity `PC_PERSONALE`;
4. inspect the active project/timeline and refuse if it does not match the authorized peeling test context;
5. run the cleanup from the approved stabilized source to a new explicit test timeline;
6. poll to `COMPLETED` and report full structural read-back;
7. leave the project unsaved and do not create a delivery render;
8. stop for human A/B listening.

**Expected:** Source untouched, one V1 and one processed A1 on the duplicate, exact 732-frame alignment at 30 fps, `saved: false`, and no PC_SEGRETERIA changes.

### Step 5: Push/update the audio PR only after verification

Push the audio branch and update its existing PR. Do not merge. Do not include or cherry-pick commits from the separate color branch.

**Expected:** The audio PR contains only the audio/bridge commits from this worktree.
