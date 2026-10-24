# Natural dialogue dereverb — design

## Intent

Make the speech in the stabilized `peeling` ADV intelligible while preserving a natural voice.
The room echo must drop clearly, but the result must not sound metallic, telephone-like, gated, or
over-denoised.

## Goals

- Process the exact audio heard on the selected Resolve timeline, not an assumed source file.
- Create a new, explicitly named test timeline and preserve every existing timeline.
- Keep exactly one audible audio copy aligned with the unchanged stabilized video.
- Use a deterministic, reusable bridge command rather than a timeline-specific command.
- Verify duration, placement, source binding, clip counts, and read-back before human listening.
- Keep the project unsaved until the operator approves the A/B result.

## Non-goals and anti-goals

- No automatic editing, transcription, captions, render delivery, or project save.
- No attempt to reconstruct acoustic information that was never captured.
- No aggressive neural denoise that introduces metallic speech or pumping.
- No manual Fairlight/GUI dependency and no workstation other than `PC_PERSONALE`.

## Constraints found in the current bridge

- The existing `CLEAN_V1`, `LEVEL_V2`, `DISTANT_V3`, and `NATURAL_V4` chains do not perform
  dereverberation. `DISTANT_V3` can raise room sound and is unsuitable here.
- The installed PyAV/FFmpeg runtime provides `afftdn`, `agate`, `deesser`, `equalizer`,
  `acompressor`, and `alimiter`; `arnndn` is present but needs an external model and is more prone
  to speech artefacts.
- Resolve scripting does not provide a sufficiently reliable, auditable route to the Studio Voice
  Isolation controls for this workflow.
- The timeline is 732 frames at 30 fps with one V1 and one A1 clip. The stabilized provisional
  timeline must remain intact.

## Approaches considered

### 1. Controlled natural restoration — selected

Render the exact timeline mix to a managed WAV, apply a restrained offline chain, duplicate the
timeline, replace only A1, and verify the result. This is deterministic, testable, and preserves
the natural voice. It reduces perceived echo rather than claiming perfect acoustic dereverb.

### 2. Neural `arnndn`

Potentially stronger suppression, but it needs an external model and can create metallic or watery
speech. Rejected for this ADV because naturalness is a stated requirement.

### 3. Manual Resolve Voice Isolation

Potentially effective, but not reliably scriptable or reproducible through the bridge and would
require GUI intervention. Rejected for the automated test path.

## Proposed generic workflow

Use two generic commands so rendering and audio processing never depend on one long tunnel request:

- `start_timeline_dialogue_cleanup_test` queues the exact timeline-audio render and returns a
  `job_id`;
- `get_timeline_dialogue_cleanup_job` advances the owned job after render completion, runs the
  fixed restoration worker, creates the test timeline, and returns final read-back.

The start command accepts:

- `source_timeline`;
- `target_name`;
- allowlisted preset `ARPHE_DIALOGUE_DEREVERB_NATURAL_V5`.

The owned job will:

1. validate the workstation, allowlisted project/timeline, one-clip A1 structure, fps, and duration;
2. render the exact source-timeline audio to an owned 48 kHz PCM WAV while saving and restoring
   the Deliver state and current timeline;
3. process the complete WAV asynchronously with the fixed V5 chain;
4. duplicate the source timeline using the existing non-destructive timeline machinery;
5. import the processed WAV, delete only the duplicated A1 item, and append exactly one replacement
   at the original record frame;
6. confirm one V1 item, one A1 item, matching 732-frame ranges, unchanged video source, processed
   audio provenance, and no extra audio tracks or clips;
7. leave the test timeline current and return full read-back with `saved: false`.

The manifest binds workstation, project, timeline ID, edit fingerprint, frame range, rendered WAV
fingerprint, target name, preset, and output fingerprint. Resuming the same `job_id` must be
idempotent. Any failure after duplication must fail closed, remove only bridge-owned inserted audio
when safe, and leave the source timeline untouched.

## V5 processing chain

The initial fixed chain will favor clarity without the metallic signature of heavy denoise:

- high-pass at 70 Hz;
- low-intensity `afftdn` (`nr=3`, noise floor `-55 dB`);
- broad low-mid attenuation around 220 Hz and 430 Hz to reduce boxiness and room build-up;
- gentle downward expansion with `agate`, using slow enough attack/release to avoid chopped words;
- no de-esser in the first version; preserving consonants is more important than speculative
  sibilance control;
- compression around 1.5:1 with slow release;
- at most +1 dB makeup and a -1 dB safety limiter.

Exact numeric EQ/gate values must be centralized beside the other presets and covered by tests.
The whole file is processed before any later edits so the acoustic character does not change at cut
boundaries.

## Verification and listening gate

Automated checks cover schema, preset allowlist, exact duration within one frame, PCM format,
single-audio replacement, record range, source preservation, and rollback. A short managed A/B
preview may be produced only after those checks pass. Human listening remains the acceptance gate:
speech must be easier to understand, consonants must remain natural, and room tails must not pump.

The project will not be saved and no delivery render will be started during this test.

## Rollout

Implementation and the first live test are limited to `PC_PERSONALE`. `PC_SEGRETERIA` remains
untouched. A later rollout requires its own backup, workstation-specific install, ping/read-back,
and a disposable test project before use on production work.
