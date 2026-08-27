# ARPHE Video Automation - Training Roadmap

## Final objective

Build a reliable workflow where a user can provide source media and a high-level editing request, and the system can produce a publishable DaVinci Resolve timeline with minimal human intervention.

Target example: short-form filler ad with a secretary hook, generative lip-inflation/explosion shot, doctor explanation, selected B-roll, music, captions, CTA, and final export.

## Working rule

A capability enters the ARPHE editing engine only after it passes a repeatable validation test. Long-form development continues in parallel while the short-form primitives are trained.

## Training sequence

### 0. DaVinci Resolve Studio capability audit

**Goal:** determine exactly what can be controlled reliably from external Python/Resolve scripting before investing in more workarounds.

Test matrix:
- connect to a running Resolve Studio instance;
- inspect projects, timelines, tracks, clips and Media Pool;
- create/modify timelines;
- import and place media;
- apply cuts and clip transforms;
- create/read Fusion compositions;
- test face/object tracking paths and whether tracking can be started programmatically;
- test captions/subtitle workflow;
- test audio controls useful for music/ducking;
- test render queue and export;
- test external script execution, logs and error reporting.

**PASS:** repository contains a capability matrix with `SUPPORTED`, `PARTIAL`, or `MANUAL` for every required operation, plus a minimal external script that connects to Resolve and performs a harmless timeline operation.

---

### 1. Cut Engine

**Goal:** raw talking-head footage becomes a natural rough cut.

Train/test:
- pauses;
- false starts;
- repetitions;
- mistakes;
- filler words;
- breathing and phrase endings;
- waveform-aware cut placement.

Continue validating the current long-form V4.3 work here.

**PASS:** 10 consecutive representative videos require only minor manual corrections and do not systematically cut words or phrase tails.

---

### 2. Punch-in / Reframe Engine

**Goal:** deterministic, reusable camera movement primitives.

Primitives:
- static punch-in;
- smooth punch-in;
- fast punch-in;
- punch-out;
- yoyo;
- reframe.

Then add rule-based automatic punch-in timing.

**PASS:** the same instruction produces visually consistent results across representative clips without manual keyframe repair.

---

### 3. Tracking Engine

**Goal:** keep a chosen face/object framed while applying tracked edits.

Targets:
- `TRACK_FACE`;
- `TRACK_OBJECT` where reliable;
- `TRACKED_PUNCH_IN`.

Resolve Studio features should be tested before preserving any current manual workaround.

**PASS:** 20/20 normal talking-head clips complete face tracking without requiring the operator to press Track Forward or repair the path.

---

### 4. Caption Engine

**Goal:** transcription to ARPHE-styled captions with no manual formatting.

Train/test:
- timing;
- line splitting;
- safe-area placement;
- typography preset;
- keyword emphasis;
- optional animation/highlight.

**PASS:** captions are readable, correctly timed and visually consistent on representative short-form videos with no per-caption manual styling.

---

### 5. B-roll Engine

**Goal:** automatically place human-selected B-roll over the doctor's audio.

V1 deliberately keeps asset selection human-controlled. The engine decides placement, duration, pacing and return to A-roll.

Train/test:
- single B-roll insert;
- image insert;
- B-roll sequence;
- fast/normal pacing;
- maintaining continuous doctor audio.

**PASS:** given A-roll plus 5-10 selected assets, the engine creates a coherent B-roll sequence with only minor editorial corrections.

---

### 6. Music + Sound Design

**Goal:** predictable audio finishing without opening Fairlight for routine reels.

Primitives:
- add music;
- set target level;
- duck under speech;
- fade in/out;
- place essential impact/whoosh SFX.

**PASS:** speech remains clear and music/SFX levels are consistent across representative reels.

---

### 7. CTA Engine

**Goal:** reusable ARPHE end cards/CTA sequences.

Initial presets can cover filler, Botox and generic consultation/booking CTAs.

**PASS:** one preset call inserts the complete approved CTA package with correct duration, layout and audio behavior.

---

### 8. Boss Fight V1 - Fully assembled reel without generative video

Input:
- secretary hook clip;
- doctor clip;
- 5-10 human-selected B-roll/images;
- chosen CTA preset.

Expected automated output:

`HOOK -> DOCTOR CUT -> PUNCH/REFRAME -> CAPTIONS -> B-ROLL -> MUSIC -> CTA -> EXPORT`

**PASS:** the system returns a publishable first-pass reel that requires only minor creative corrections and no technical reconstruction.

This is the first major product milestone.

---

### 9. Runway / Generative Shot

**Goal:** add selected generative shots without changing the core editing engine.

First target: secretary's lips progressively inflate and burst, then transition to the doctor scene.

**PASS:** the generative result can be requested from a preset, returned, imported and substituted into the Resolve timeline with a controlled failure/fallback path.

---

### 10. Autopilot / Edit Plan

**Goal:** high-level natural-language intent becomes a validated edit plan which the existing primitives execute.

Example final experience:

`"Make a punchy filler reel using this secretary hook, this doctor clip and these B-rolls." -> validated edit plan -> Resolve execution -> review/export`

**PASS:** the model chooses and parameterizes already-validated primitives without issuing arbitrary Resolve operations, and invalid plans are rejected before timeline execution.

## Parallel workstreams

### Long-form

Continue V4.3 validation while the Studio capability audit begins. Long-form remains the main training ground for semantic cuts and waveform-aware joins.

### Short-form

After the Studio audit, prioritize Punch-in/Reframe, Tracking, Captions and B-roll because these are the shortest path to Boss Fight V1.

## Immediate next milestone

**DaVinci Resolve Studio Capability Audit**

Do not build new Studio-specific abstractions until this audit establishes which operations are genuinely reliable through the current Resolve Studio scripting surface.
