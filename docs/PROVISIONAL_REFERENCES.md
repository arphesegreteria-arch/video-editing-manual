# Provisional Resolve / Fusion References

> **STATUS: NON-AUTHORITATIVE / PROVISIONAL**
>
> Nothing in this file is an ARPHE gold standard merely because it is listed here. External documentation, code, techniques, API assumptions and workflows MUST be tested against our actual DaVinci Resolve Studio environment before they are adopted.

## Purpose

This file is a scouting registry for external Resolve/Fusion knowledge that may reduce experimentation time while building ARPHE Video Automation.

The repository's own validated documentation and validated scripts remain the source of truth for ARPHE behavior.

## Promotion rule

Every candidate technique moves through these states:

- `UNVERIFIED` - discovered externally; useful lead only. Do not depend on it in production.
- `TESTED` - executed in our environment and observed to work in at least one controlled test, but robustness is not established.
- `VALIDATED` - passed the repeatable ARPHE validation criteria for the relevant primitive/environment. It may then be documented in the appropriate definitive ARPHE document and/or implemented as an approved primitive.
- `REJECTED` - tested and found unsuitable, unreliable, obsolete, incompatible, or strategically wrong for ARPHE.

**Important:** promotion to `VALIDATED` should happen in the definitive ARPHE documentation, not by silently treating this registry as authoritative. Keep the external source attached as provenance.

## Source priority during testing

When external sources disagree, use this order for deciding what to test first:

1. The Developer/Scripting documentation shipped with the exact installed Resolve Studio version.
2. A behavior we reproduce successfully in our own controlled test.
3. Recent third-party material that explicitly states the Resolve version/environment tested.
4. Older docs, examples, gists and community techniques as hypotheses only.

A third-party claim never overrides an ARPHE execution result without investigation.

---

## Candidate references

### 1. Local DaVinci Resolve Developer/Scripting README

**Type:** vendor documentation shipped with Resolve  
**Status:** `UNVERIFIED` until checked against the installed Studio build  
**Priority:** CRITICAL

Resolve ships its own Scripting API documentation and representative examples. This should be our first reference during the Studio capability audit because it corresponds most closely to the installed build.

Useful for:
- external Python connection;
- Project Manager / Project / Media Pool / Timeline APIs;
- media import and timeline construction;
- clip properties;
- captions API surface;
- render queue/export;
- version-specific additions and limitations.

**ARPHE action:** during Phase 0, record the exact Resolve version and snapshot/inspect the local Developer README before relying on online copies.

---

### 2. `velvaiss/auto-subs-davinci-resolve` - Resolve/Fusion skill and reference bundle

URL: https://github.com/velvaiss/auto-subs-davinci-resolve  
Interesting path: `Resolve-Integration/davinci-resolve-fusion/SKILL.md`  
**Status:** `UNVERIFIED`  
**Priority:** HIGH

Why it is interesting:
- explicitly organizes Resolve automation knowledge for agent use;
- bundles a Resolve API snapshot plus Fusion references;
- covers timelines, Media Pool and rendering;
- covers Fusion object model and `.setting` macros;
- covers BezierSpline/keyframe animation;
- includes Windows/macOS script helpers and API update helpers.

Potential ARPHE value:
- Punch-in / Reframe Engine;
- Fusion animation primitives;
- external execution setup;
- reducing repeated Fusion object-model discovery.

**Caution:** this is a fork and its bundled references are snapshots. Individual techniques must be reproduced before adoption.

---

### 3. `mvarge/davinci-scripts`

URL: https://github.com/mvarge/davinci-scripts  
Interesting files: `RESOLVE_API_REFERENCE.md`, `RESOLVE_SCRIPTING_GUIDE.md`  
**Status:** `UNVERIFIED`  
**Priority:** HIGH

Why it is interesting:
- recent Python-oriented Resolve automation project;
- describes itself as agent-friendly;
- combines API reference material with reported live experimentation;
- contains practical notes around external scripting and troubleshooting;
- contains recent observations about subtitle/caption behavior and Resolve 21 features.

Potential ARPHE value:
- Studio capability audit;
- external Python bridge;
- Caption Engine;
- identifying API dead ends before spending test cycles on them.

**Caution:** claims labelled as live-verified by the author are still `UNVERIFIED` for ARPHE until we reproduce them on our machine/build.

---

### 4. `tmoroney/auto-subs`

URL: https://github.com/tmoroney/auto-subs  
**Status:** `UNVERIFIED`  
**Priority:** HIGH for captions, MEDIUM overall

Why it is interesting:
- mature open-source subtitle/transcription workflow connected to Resolve;
- substantial real-world usage/community history;
- useful implementation reference for transcription -> subtitle styling/insertion workflows;
- useful for understanding installation and cross-platform integration patterns.

Potential ARPHE value:
- Caption Engine architecture;
- reusable caption templates;
- transcription integration;
- Windows/macOS deployment lessons.

**Caution:** ARPHE should not inherit its architecture wholesale. We already have our own transcription/editing pipeline and only want techniques that simplify our validated design.

---

### 5. `Rraz0rR/DaVinci-Resolve-Subtitle-to-TextPlus`

URL: https://github.com/Rraz0rR/DaVinci-Resolve-Subtitle-to-TextPlus  
**Status:** `UNVERIFIED`  
**Priority:** MEDIUM-HIGH

Why it is interesting:
- focused Python script converting subtitle content into Text+ clips;
- potentially useful when native subtitle styling/animation is insufficient;
- Text+ gives access to Fusion styling and animation.

Potential ARPHE value:
- animated short-form captions;
- keyword emphasis;
- ARPHE typography presets.

**Caution:** first test whether Resolve Studio 21 native/AI subtitle features already solve our requirement more simply. Do not build a Text+ workaround for a problem Studio already solves reliably.

---

### 6. `czukowski/fusionscript-stubs`

URL: https://github.com/czukowski/fusionscript-stubs  
**Status:** `UNVERIFIED`  
**Priority:** MEDIUM

Why it is interesting:
- Python type hints for the Resolve/Fusion scripting library;
- current versions are based on recent Resolve scripting documentation;
- may improve development speed, autocomplete and detection of wrong assumptions while building the external bridge.

Potential ARPHE value:
- cleaner external Python development;
- fewer typo/signature mistakes;
- easier maintenance of the future ARPHE Resolve bridge.

**Caution:** type stubs describe an interface; they do not prove that a method behaves reliably in our Resolve environment.

---

### 7. `leoweyr/DaVinci_Resolve_API_Docs`

URL: https://github.com/leoweyr/DaVinci_Resolve_API_Docs  
**Status:** `UNVERIFIED`  
**Priority:** MEDIUM / HISTORICAL

Why it is interesting:
- convenient searchable copies of Resolve scripting API documentation;
- useful for historical comparison and finding older API behavior.

Potential ARPHE value:
- understanding version changes;
- quick searchable reference when investigating an API method.

**Caution:** older version snapshots must never be preferred over the Developer README shipped with our installed Resolve version.

---

### 8. `b3n0y/ResolveDevDoc`

URL: https://github.com/b3n0y/ResolveDevDoc  
**Status:** `UNVERIFIED`  
**Priority:** LOW-MEDIUM / HISTORICAL

Why it is interesting:
- reformats Resolve/Fusion developer documentation into easier-to-navigate docs;
- useful for concept discovery and older Fusion/Resolve scripting references.

Potential ARPHE value:
- background reference when the current Developer README is terse;
- Fusion object-model exploration.

**Caution:** portions are old. Treat as explanatory material, not current API truth.

---

## First validation queue

When Resolve Studio is installed on the development machine, test these external claims/techniques in this order:

1. External Python connection and environment setup.
2. Timeline/Media Pool read-write operations.
3. Fusion composition creation/readback from external Python.
4. Programmatic tracking: configure tracker, trigger tracking, read resulting path.
5. Resolve 21 subtitle creation/styling capabilities before building custom Text+ workarounds.
6. Render queue/export from the external bridge.
7. Only after the above, evaluate helper libraries/type stubs for inclusion in the development environment.

These tests should feed `docs/RESOLVE_STUDIO_CAPABILITIES.md` as planned in the Studio capability audit. A successful one-off test earns `TESTED`, not automatically `VALIDATED`.

## Gold-standard rule

A procedure becomes an approved ARPHE procedure only when all of the following are true:

- it has been executed in our environment;
- its expected result has been checked, not merely its return value;
- it is repeatable on representative material;
- failure behavior is understood;
- it does not introduce a worse operational burden than the method it replaces;
- the relevant PASS criteria in `TRAINING_ROADMAP.md` are satisfied, where applicable;
- the result is copied/rewritten into the appropriate definitive ARPHE documentation or validated script.

Until then, **this file is a map of promising places to look, not a manual of instructions to follow.**

## Maintenance

Add promising sources freely, but always give them a status and a reason for inclusion. When a source technique is tested, record the outcome. When it becomes validated, link to the definitive ARPHE implementation/document. When rejected, preserve the rejection reason so we do not waste time rediscovering the same dead end.
