# ARPHE Video Automation — Training Roadmap

## Final objective

Build a reliable workflow where the user works **inside ChatGPT** and can provide/select source media, discuss a high-level editing request, approve decisions and have those decisions executed safely in DaVinci Resolve Studio.

Target architecture:

`ChatGPT -> custom MCP app -> Secure MCP Tunnel -> local ARPHE MCP Bridge -> validated editing primitives -> Resolve Studio`

A separate ARPHE desktop GUI is not the intended primary interface.

## Working rule

A capability enters the ARPHE editing engine only after it passes a repeatable validation test. The model may choose and parameterize validated primitives, but the bridge must reject invalid/arbitrary operations.

## 0. DaVinci Resolve Studio capability audit

**Goal:** determine exactly what can be controlled reliably from external Python/Resolve scripting.

### Stato corrente

External READ is **SUPPORTED** on Resolve Studio `21.0.4.5`:
- external Python connects;
- project/timeline/FPS/tracks/items readable;
- test `ARPHE_STUDIO_EXTERNAL_API_TEST_01` exit code 0.

External WRITE is still **PENDING**.

### Test matrix
- external connection/read — SUPPORTED;
- create empty timeline — NEXT;
- import/place media;
- reconstruct/cut timeline;
- clip transforms;
- Fusion compositions;
- tracking paths / programmatic tracking;
- captions/subtitles;
- audio controls;
- render/export;
- logs/error reporting.

**PASS:** `docs/RESOLVE_STUDIO_CAPABILITIES.md` records each required operation as `SUPPORTED`, `PARTIAL` or `MANUAL` based on live tests.

---

## 0.5. ChatGPT / MCP bridge

**Goal:** prove that normal ChatGPT conversation can use safe tools on the local ARPHE PC and ultimately drive Resolve Studio.

Validation sequence:
1. confirm suitable ChatGPT workspace/developer-mode permissions;
2. local MCP server with `ping` + `resolve_status`;
3. test locally with MCP Inspector;
4. connect through Secure MCP Tunnel;
5. ChatGPT invokes `resolve_status` successfully;
6. expose `create_safe_working_timeline` only after external WRITE probe passes;
7. ChatGPT creates one empty test timeline while the original remains untouched.

**PASS:** from a normal ChatGPT chat, a user can ask for Resolve status and then approve a harmless timeline creation that is executed through MCP and verified in Resolve.

**Security:** no arbitrary shell/Python tools; only allowlisted, typed actions; guarded local paths; original timeline protection enforced by code.

---

## 1. Cut Engine

**Goal:** raw talking-head footage becomes a natural rough cut.

Train/test:
- pauses;
- false starts;
- repetitions;
- mistakes;
- filler words;
- breathing and phrase endings;
- speech repair;
- waveform-aware cut placement;
- conceptual cuts as a separate semantic layer;
- sensitive content as FLAG ONLY.

**PASS:** representative videos require only minor manual corrections and do not systematically miss common repair opportunities or cut words/tails.

Benchmark against human references remains mandatory; see `07_EDITORIAL_BENCHMARK.md`.

---

## 2. Punch-in / Reframe Engine

**Goal:** deterministic, reusable camera movement primitives.

Primitives:
- static punch-in;
- smooth punch-in;
- fast punch-in;
- punch-out;
- yoyo;
- reframe.

**PASS:** the same instruction produces visually consistent results across representative clips without manual keyframe repair.

---

## 3. Tracking Engine

**Goal:** keep a chosen face/object framed while applying tracked edits.

Targets:
- `TRACK_FACE`;
- `TRACK_OBJECT` where reliable;
- `TRACKED_PUNCH_IN`.

Resolve Studio features must be tested before preserving old Free/manual workarounds.

**PASS:** representative normal talking-head clips complete tracking without requiring routine manual Track Forward/path repair.

---

## 4. Caption Engine

**Goal:** transcription to ARPHE-styled captions with no manual formatting.

Train/test:
- timing;
- line splitting;
- safe-area placement;
- typography preset;
- keyword emphasis;
- optional animation/highlight.

**PASS:** captions are readable, correctly timed and visually consistent without per-caption manual styling.

---

## 5. B-roll Engine

**Goal:** place human-selected B-roll over continuous speech audio.

V1 can keep asset selection human-controlled while the engine decides placement, duration, pacing and return to A-roll.

**PASS:** given A-roll plus selected assets, the engine creates a coherent B-roll sequence with only minor editorial corrections.

---

## 6. Music + Sound Design

**Goal:** predictable audio finishing without routine manual Fairlight work.

Primitives:
- add music;
- target level;
- duck under speech;
- fade in/out;
- essential impact/whoosh SFX.

---

## 7. CTA Engine

**Goal:** reusable approved ARPHE end cards/CTA sequences.

---

## 8. Boss Fight V1 — assembled reel

Input:
- hook;
- doctor clip;
- selected B-roll/images;
- CTA preset.

Expected:

`HOOK -> CUT -> PUNCH/REFRAME -> CAPTIONS -> B-ROLL -> MUSIC -> CTA -> EXPORT`

**PASS:** ChatGPT can request a validated plan and the bridge returns a publishable first-pass Resolve timeline requiring only minor creative corrections.

---

## 9. Generative Shot

Add selected generative shots as optional assets without changing the deterministic core editing engine.

---

## 10. ChatGPT Autopilot / Edit Plan

**Goal:** high-level natural-language intent in ChatGPT becomes a validated edit plan executed through MCP tools.

Example:

`"Fammi un reel punchy con questo hook, questo medico e questi B-roll" -> discussione/approvazione -> validated edit plan -> MCP tools -> Resolve execution -> review/export`

**PASS:** ChatGPT chooses and parameterizes already-validated primitives, the bridge rejects invalid plans, and Resolve never receives arbitrary model-generated code.

## Parallel workstreams

### Editorial benchmark
Use autonomous podcast excerpts of roughly 8–15 minutes, all starting at `00:00`, freeze the candidate before the human edit and compare quantitatively.

### Studio/MCP infrastructure
Continue the capability audit while validating the MCP path. Do not wait for every advanced Resolve capability before proving the minimal ChatGPT -> MCP -> Resolve read/write loop.

## Immediate next milestone

1. **Run `ARPHE_STUDIO_EXTERNAL_WRITE_TEST_02`.**
2. Build/test a read-only local MCP server (`ping`, `resolve_status`).
3. Configure Secure MCP Tunnel and connect the custom app in ChatGPT.
4. Validate ChatGPT -> MCP -> Resolve READ.
5. If write permissions and Test 02 are both green, validate one harmless MCP WRITE that creates an empty test timeline.
