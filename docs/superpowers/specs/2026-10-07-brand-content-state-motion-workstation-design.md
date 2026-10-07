# Brand, Content, State, Motion and Workstation Design

Date: 2026-10-07

Status: approved in conversation; implementation plan pending review of this document.

## Purpose

Resolve the first five findings from the architecture review while keeping one shared bridge
codebase. The result must make ARPHE's visual system authoritative, keep real reviews out of
the public repository, make operational status auditable, correct known motion and validation
defects, and isolate deployment state between `PC_PERSONALE` and `PC_SEGRETERIA`.

## Decisions already made

- `arphe-graphic-kit` is the source of truth for colour and typography.
- Real reviews may be used only after human anonymisation and editorial approval.
- Review text must be supplied locally at runtime. It must not be versioned in this public
  repository or written to bridge logs.
- `PC_PERSONALE` and `PC_SEGRETERIA` share the same source branch and release. They must have
  independent runtime configuration, tunnel, credentials, Python executable, logs, backups and
  validation evidence.
- A code test is portable evidence of behaviour; a workstation validation is evidence only for
  the named PC. Both must be recorded.
- This scope ends before render-profile policy, queue behaviour, cleanup or deletion safeguards
  (findings 6 and later).

## Architecture

### 1. Brand contract

The graphic kit remains canonical. The video repository will consume a small, version-pinned
brand contract derived from the kit's `tokens/colors.json` and typography rules. The contract
records the graphic-kit commit/version it was derived from, exposes only the canonical colours
and fonts, and maps them to video roles without adding near-duplicate palette values.

The bridge will use the contract rather than an independently maintained creative palette.
Where video compositions need tonal hierarchy, they may use opacity, borders and shadows made
from canonical colours; they may not introduce new opaque brand colours. The typography mapping
is explicit: Noto Serif Display 300 for headings; Satoshi 400 for body copy; Satoshi 500 for
labels; Satoshi 700 for buttons. Any technical fallback must be observable and documented.

A verifier compares the contract with a checked-out graphic kit and fails on changed colour or
type rules. Runtime deployment does not depend on a second repository being present on either
PC; it consumes the pinned contract stored with the bridge release.

### 2. Review-content boundary

Public documentation will state one policy consistently:

- the bridge does not acquire reviews, publish content, or decide that a review is anonymous;
- a human prepares and approves an anonymised text locally;
- the runtime accepts only the already-approved text needed for the current composition;
- review text, patient names, author identifiers, source URLs, health details and original
  screenshots are not stored by the public repository, examples, test fixtures or bridge logs;
- public plans use placeholders or opaque review IDs, never source text.

The content boundary is a documentation and input-handling rule, not an automated claim that a
string is safe. The tool surface must avoid optional author/source fields and redact review
payloads from diagnostics. This does not prohibit use of genuine approved reviews in Resolve.

### 3. Operational state and validation ledger

Introduce one versioned validation ledger as the authoritative record of claimed tests. Each
entry records at least: date, source revision, bridge/runtime profile, workstation, Resolve and
Python versions where known, gate/test identifier, command or scenario, result, evidence
reference, rollback/recovery reference and limitations.

`CURRENT_STATE.md` becomes an executive view of that ledger. `CHANGELOG.md` records changes to
the product and points to the ledger entry that validates them. Neither document may upgrade a
workstation from code-test evidence alone. Conflicts such as a dedicated tunnel being both
confirmed and pending must be resolved by recording the latest supported evidence or marking the
fact `UNKNOWN`, never by inference.

Existing evidence is migrated conservatively: retain historical results, label their workstation
and confidence, and do not invent a later remote validation that has not been recorded.

### 4. Motion and plan validation

The animation layer has these semantic guarantees:

- entry starts out of position/transparent and finishes at the visible resting state;
- exit starts at the visible resting state and finishes out of position/transparent;
- applying entry and exit to the same element preserves both time ranges and does not replace
  unrelated transform keys;
- `linear` and `ease_out` create observably distinct numeric key sequences;
- generated keys are deterministic for a supplied plan and frame rate.

The longform plan validator rejects any source interval that becomes zero or negative after
frame conversion. It reports the offending segment and conversion rather than allowing Resolve
to receive a degenerate edit.

### 5. Workstation profiles and deployment

This design extends and supersedes the deployment details in
`2026-09-21-workstation-isolation-design.md` where they differ.

There is one codebase and one release line. Every install/update takes an explicit workstation
profile. A profile owns its runtime configuration path, Creative configuration, absolute Python
executable, expected tunnel identity, task name, logs, backup location and feature flags.

The installer has two phases:

1. Read-only preflight: resolve the selected profile, verify identity and absolute interpreter,
   inspect existing configuration, and reject a foreign or legacy configuration.
2. Apply: create or update only profile-owned paths, preserve compatible local secrets, and
   emit an auditable result.

No fallback may silently reuse the legacy shared Creative configuration. Legacy config is either
migrated after identity confirmation or rejected with recovery instructions. Backup, status and
runtime-switch scripts resolve paths through the active profile, never through a generic Python
alias or a shared `%LOCALAPPDATA%` configuration.

An update of Git source never deploys automatically to either PC. After installation, each PC
requires its own READ validation; SAFE WRITE is a separate, deliberately run gate on a test
project.

## Failure handling

- Brand-contract mismatch stops bridge validation before a composition is created.
- Missing/unavailable font is reported as a preflight failure, not silently substituted.
- Invalid or unapproved review input is rejected without echoing its text in logs.
- Invalid frame intervals are rejected before any Resolve write.
- Profile/tunnel/interpreter mismatch makes the installer stop before modification.
- A partial apply preserves the old profile configuration and reports the exact changed paths;
  recovery uses the profile-specific backup.

## Verification strategy

Tests are written before behavioural changes. The automated suite covers:

- graphic-kit contract parsing and mismatch detection;
- no hard-coded noncanonical palette/type configuration in the Creative bridge;
- review payload redaction and absence of public-review fixtures;
- validation-ledger schema and `CURRENT_STATE` references;
- exit direction/timing, entry-plus-exit preservation and distinct easing samples;
- rejection of sub-frame longform intervals;
- profile-specific paths, absolute interpreters, legacy-config rejection and no cross-profile
  writes in dry-run tests.

Manual validation is separate and recorded in the ledger. It checks the actual Resolve image
for the motion gate and each PC's resolved identity, runtime health, tunnel routing, READ and,
only when authorised, SAFE WRITE. Each changelog entry must distinguish automated tests from
the named workstation gate.

## Out of scope

The following remain for finding 6 and later: vertical/render defaults and queue start policy,
cleanup/deletion and restore semantics, responsive phone-safe layout refinement, higher-level
workflow composition and plan-hash binding.

