# Review Readability Guard Design

**Date:** 2026-10-08
**Status:** Approved conversational design; implementation not started
**Repositories:** `arphe-graphic-kit`, `video-editing-manual`

## Purpose

Make mobile readability a measurable precondition for ARPHÈ review reels and Story/Reel
templates. A review must not be shortened automatically, silently rendered with a substitute
font, squeezed below the approved type minimum, or written to Resolve when it fails the policy.

The intended editorial outcome is:

- prefer complete, concise, genuine reviews during selection;
- preserve the exact approved and anonymised wording;
- use one card per review by default;
- permit a verbatim split across consecutive cards only after explicit editorial approval;
- block Resolve writes until the entire sequence is safe to create;
- keep workstation state and validation evidence separate between `PC_PERSONALE` and
  `PC_SEGRETERIA`.

## Current evidence

The current implementation has four measurable gaps:

1. `_review_reading_frames` estimates a reading duration but caps it at five seconds. A review of
   70 words therefore receives the same five seconds as a much shorter review.
2. Portrait review text uses three size tiers (`0.052`, `0.047`, `0.042`) selected from character
   count, but there is no line-count or overflow result and no explicit review state.
3. The Story/Reel HTML template places its final copy block 96 pixels from the lower edge. The
   documentation only states that essential content must avoid social-interface overlays; it
   does not encode a testable safe rectangle.
4. HTML templates request Satoshi from Fontshare and Fusion requests Satoshi by name. Neither
   path proves that the intended family and weight were actually loaded. The current review
   intro also requests Satoshi Black although the canonical Graphic Kit typography assigns
   headings to Noto Serif Display 300 and defines Satoshi 400/500/700 for body, labels and
   buttons.

The existing kit verifier checks required files, palette values, asset references, declared
canvas dimensions and basic file validity. It does not currently prove text fit, safe-area
compliance or effective font loading.

## Scope

### In scope

- A canonical, versioned video-readability policy in `arphe-graphic-kit`.
- A pinned runtime contract shipped with the Creative bridge release.
- A pure review-readability preflight with structured results.
- A hard pre-write gate in review-sequence creation.
- Explicit editorial approval for non-standard duration or verbatim splitting.
- Safe-area, typography and font-readiness checks for the Story/Reel and review-reel paths.
- Automated, visual and workstation-specific validation evidence.
- Documentation updates for the Graphic Kit and video manual.

### Out of scope

- Rewriting, summarising or automatically excerpting reviews.
- Storing real review text in Git, fixtures, logs, approval records or diagnostics.
- General-purpose layout inference for every future graphic.
- Editorial extract selection, audio provenance and end-to-end job orchestration. Those belong
  to analysis points 9 and 10.
- Unrelated palette migration. This design consumes the canonical Graphic Kit typography and
  readability rules without expanding into a full redesign of existing colour roles.

## Architecture

### 1. Canonical policy in the Graphic Kit

`arphe-graphic-kit` owns the machine-readable policy at
`tokens/video-readability.json`. Its schema contains:

- schema and policy versions;
- supported canvas identifiers;
- an essential-content safe rectangle for each canvas;
- approved font family, weight and role mappings;
- allowed review-body size tiers;
- minimum body size and maximum line count;
- reading-rate and editorial-duration thresholds;
- a declaration that technical fallbacks are draft-only;
- a stable content digest.

The public repository does not contain Satoshi font binaries. It retains the existing licensing
instructions and treats a missing licensed installation as a delivery blocker rather than
silently accepting a fallback.

The kit verifier validates the policy schema and compares template geometry against the safe
rectangle. It also verifies that templates declare required fonts and that any fallback is
observable as draft output. Final-render font loading is an environment check and is therefore
reported separately from portable static verification.

### 2. Pinned bridge contract

The video repository ships a small, read-only copy at
`scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/review_readability_contract.json` with every
bridge release. It records:

- Graphic Kit repository identity;
- source commit;
- source policy digest;
- copied policy version and values.

The PCs do not require a second repository checkout at runtime. A repository verification tool
compares the pinned contract with a selected Graphic Kit checkout during development and fails
on drift. Runtime startup validates the bundled contract before exposing review writes.

### 3. Pure preflight component

Readability logic lives in a focused module rather than further enlarging `creative_tools.py`.
The module has no Resolve dependency and performs no filesystem or state mutation. Given the
review payload, canvas identifier, policy and font-readiness result, it returns a structured
assessment for every review and an aggregate sequence decision.

The assessment contains counts, selected size tier, estimated line count, duration, status and
reason codes. It never returns or persists the original review text in logs or approval records.
Callers already holding the payload may associate the in-memory assessment with it.

### 4. Thin Resolve integration

`create_review_sequence` calls the aggregate preflight before creating a composition or timeline
item. The complete sequence must be `PASS`, or every exception must have a valid editorial
approval, before the first Resolve write.

If preflight fails, the call returns the full structured assessment and performs zero Resolve
writes. Existing rollback remains a defence for downstream Resolve failures, not a substitute
for preflight.

## Readability rules

### Reading time

The automatic duration for one review is:

```text
seconds = max(3, ceil(word_count / 4) + 1)
frames = seconds * project_fps
```

The four-words-per-second rate is a brisk social-video target. The extra second provides entry
and settling time. The implementation uses the confirmed project frame rate; the ARPHÈ vertical
social workflow remains 30 fps.

Examples:

| Words | Duration | Standard result before layout checks |
|---:|---:|---|
| 20 | 6 s | `PASS` |
| 30 | 9 s | `PASS` |
| 40 | 11 s | `PASS` |
| 44 | 12 s | `PASS` |
| 45 | 13 s | `NEEDS_REVIEW` |
| 70 | 19 s | `NEEDS_REVIEW` |

The automatic path has no five-second cap. Twelve seconds is an editorial standard threshold,
not an absolute technical maximum.

### Type fit

For portrait review-body text, preflight tries the approved tiers in order:

1. `0.052`;
2. `0.047`;
3. `0.042`.

It selects the largest tier that fits the approved text frame in no more than seven lines. It
never interpolates a smaller size and never reduces the frame outside the safe rectangle. A
review that does not fit at `0.042` is `NEEDS_REVIEW` with reason `TEXT_OVERFLOW`.

Measurement must handle explicit newlines, repeated whitespace, apostrophes, punctuation and
long unbroken tokens deterministically. Normalisation used for counting must not change the
rendered text.

### Safe area

For the 1080 by 1920 Story/Reel canvas, essential content is constrained to:

- horizontal range: 8% through 84%;
- vertical range: 10% through 82%.

The corresponding approximate pixel rectangle is `x=86..907`, `y=192..1574`. Text, stars,
headings, logos used for identification and calls to action are essential. Backgrounds, masks,
shadows and decorative marks may extend beyond the rectangle.

This replaces the current implicit lower placement. The Graphic Kit template and the Fusion
review layout consume the same canonical values.

### Typography

The runtime and templates follow the Graphic Kit mappings:

- headings: Noto Serif Display 300;
- body copy: Satoshi 400;
- labels: Satoshi 500;
- buttons: Satoshi 700.

Satoshi Black is removed from the review intro because it is not part of the approved mapping.
Noto binaries already licensed for redistribution may remain in the public kit. Satoshi binaries
remain workstation-managed under the Fontshare licence.

An HTML template may open with a technical fallback only when it is clearly marked as a draft.
A final check waits for font loading and blocks delivery if the required family or weight is not
effective. The bridge performs a workstation font preflight before review writes and reports the
missing family or weight without exposing local filesystem details.

## Editorial decisions and approvals

`PASS` means the review fits and its automatic duration is at most twelve seconds.

`NEEDS_REVIEW` permits these decisions:

1. replace the candidate with another complete, shorter review;
2. approve one longer card while preserving the complete text;
3. approve a verbatim split across consecutive cards.

One card remains the default. Split suggestions occur only at sentence boundaries. The system
must display both proposed parts and obtain explicit approval; it never applies the split merely
because it fits better. All characters and punctuation from the approved review remain present
and in order.

An exception approval binds:

- workstation identity;
- policy version and digest;
- canvas and project frame rate;
- a digest of the exact review text, not the text itself;
- decision type;
- split boundary when applicable.

Changing any bound value makes the approval stale. The write path recomputes and compares the
digest immediately before Resolve mutation.

## Status and error contract

Top-level statuses are:

- `PASS`: safe to create;
- `NEEDS_REVIEW`: editorial decision required;
- `BLOCKED`: technical requirement missing or inconsistent.

Stable reason codes are:

- `TOO_LONG_FOR_STANDARD`;
- `TEXT_OVERFLOW`;
- `FONT_UNAVAILABLE`;
- `UNSAFE_LAYOUT`;
- `STALE_APPROVAL`;
- `CONTRACT_MISMATCH`.

Responses include actionable options but do not echo real review text into server logs. A batch
with any unresolved item is all-or-nothing and leaves no partial Resolve objects.

## Capability and rollout safety

A dedicated readability capability protects review-sequence writes during rollout. Disabled or
unready means review writes are blocked; it never means bypassing the new guard and falling back
to the old behaviour.

The rollout order is:

1. update and test `arphe-graphic-kit`;
2. pin the verified policy in `video-editing-manual`;
3. pass automated bridge tests without Resolve;
4. validate an isolated test timeline on `PC_PERSONALE`;
5. record exact personal evidence and limitations;
6. validate separately on `PC_SEGRETERIA` without touching the existing editorial timeline;
7. record exact segreteria evidence before enabling its capability.

Source code is shared. Feature state, installed fonts, approval records, diagnostic artefacts and
validation evidence remain workstation-specific.

Rollback disables the capability or restores the previous bridge release. It does not delete or
rewrite existing timelines. Policy versions remain identifiable so historical evidence is not
reinterpreted under newer rules.

## Verification strategy

Implementation follows test-driven development. Public fixtures use synthetic text only.

### Graphic Kit

- policy schema, version and digest tests;
- HTML and SVG canvas/safe-area geometry tests;
- template font-role tests;
- static detection of silently accepted final fallbacks;
- boundary template renders using short, seven-line and overflowing synthetic copy;
- an environment-dependent final-font check reported separately from portable verification.

### Bridge unit and integration tests

- exact duration boundaries at 20, 30, 40, 44, 45 and 70 words;
- project-frame-rate conversion without an implicit 30 fps fallback;
- size-tier selection and seven-line boundary;
- long tokens, explicit newlines, apostrophes and punctuation;
- safe-area containment for essential Fusion elements;
- missing-family and missing-weight results;
- aggregate all-or-nothing behaviour;
- valid long-card and split approvals;
- stale approval after text, policy, canvas or frame-rate changes;
- no review text in audit and error records;
- zero Resolve calls when preflight is unresolved.

### Visual and workstation validation

Each workstation validation records:

- bridge commit and Graphic Kit source commit;
- workstation identity;
- installed/effective font evidence;
- project, timeline and playback frame rates;
- captures for a short card, the largest standard card, an approved exception and the CTA;
- mobile-sized inspection outcome;
- whether evidence is automatic, `PC_PERSONALE` live or `PC_SEGRETERIA` live.

Tests on one workstation never count as validation of the other.

## Baseline at design time

Before this specification was written, `origin/main` at merge commit `4e280d3` passed:

- Creative bridge: 167 tests, one environment-dependent skip;
- Windows bridge: 49 tests, one environment-dependent skip.

The repository does not currently contain the validation-ledger path referenced by an older
implementation plan, so no ledger validation is claimed for this design baseline. The eventual
implementation plan must either use the evidence mechanism actually present on `main` or add a
new one explicitly and test it; it must not report a nonexistent validator as passing.

## Success criteria

The work is complete only when:

- the Graphic Kit expresses and verifies the canonical readability policy;
- the bridge pins and validates the same policy;
- a 70-word review no longer receives five seconds;
- standard reviews never render below `0.042` or above seven lines;
- unresolved readability or font failures produce zero Resolve writes;
- the Story/Reel template keeps essential content inside the canonical safe rectangle;
- final output cannot silently use an unintended font;
- one-card default and approved-only verbatim splitting are enforced;
- validation documentation states exactly which checks passed on which PC.
