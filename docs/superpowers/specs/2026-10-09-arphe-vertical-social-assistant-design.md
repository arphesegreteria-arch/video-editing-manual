# ARPHÈ Vertical Social Assistant — Design

Status: approved in conversation; implementation plan pending review of this document.

## Intent and success criteria

`ARPHE_VERTICAL_SOCIAL` is an extensible editing assistant for ARPHÈ vertical shorts and advertising.
An operator can describe an intended edit in natural language; ChatGPT turns that request into an
explicit editorial plan, while the bridge safely validates, applies, verifies and resumes only
known operations. The system must reduce repetitive Resolve work without making unapproved
creative decisions or relying on an assistant rereading repository documentation during ordinary
use.

Success means an operator can review one compact card, approve a precise version of a plan, obtain
a checked provisional timeline, continue from a partial failure, and reach human review with clear
evidence. Capabilities may be added over time without changing this lifecycle.

## Boundaries

The existing workflow registry remains the source of executable workflow contracts. Markdown
documents remain rationale and operational guidance, not the runtime authority.

This design covers ARPHÈ vertical social short/ADV editing. It does not implement longform
podcast editing, a generative-video provider, arbitrary Resolve property access, asset licensing
decisions, or automatic final rendering without the existing approval flow.

The workstations remain isolated: runtime state, learned preferences, evidence and capability
rollout are workstation-specific. A capability validated on one PC does not enable itself on the
other.

## Runtime contract and status

The bridge must expose a machine-readable Vertical Social contract, including:

- workflow ID and contract version;
- current workstation identity, active project/timeline, project and playback FPS;
- available feature capabilities and their `VALIDATED`, `PARTIAL`, `EXPERIMENTAL` or unavailable
  status;
- allowed actions, required phase and required capability;
- workflow rules: explicit format, Graphic Kit authority, CTA policy, safe-area policy and caption
  ordering;
- the active plan, checkpoint and next safe action when one exists.

ChatGPT may infer a likely workflow from natural language, but no Resolve write occurs until the
operator confirms the workflow and the bridge validates the corresponding explicit contract.

## Editorial plan

ChatGPT creates a versioned `editing_plan`; it never sends free-form commands for Resolve to
interpret. A plan contains a stable ID, version, content fingerprint, selected target timeline,
picture-lock state, and ordered actions. Each action contains a stable ID, semantic type, reason,
time range or target, dependencies, requested assets, execution state and verification evidence.

Allowed action types begin with a small vocabulary: `CUT`, `REFRAME`, `B_ROLL`, `GRAPHIC`, `CTA`,
`MUSIC_DUCK`, `CAPTIONS` and `GENERATIVE_SHOT`. The contract may list an action without making it
executable. An unimplemented action is a proposal or a blocked dependency, not an arbitrary
command.

Action state is one of `PROPOSED`, `APPROVED`, `APPLIED`, `VERIFIED`, `READY_FOR_REVIEW`,
`BLOCKED`, `REJECTED` or `SUPERSEDED`. Approval binds to the plan fingerprint. Any substantive
change creates a new version requiring explicit approval.

Learned preferences remain isolated from the plan contract. They can influence a proposal but
cannot enable a capability, bypass approval, or change an operation after approval.

## Operational phases

1. **Analyse**: read source, transcript and timeline metadata; no Resolve write.
2. **Propose**: return one concise review card with the interpreted objective, actions, missing
   inputs and blocked items.
3. **Approved provisional edit**: create or resume a provisional timeline with a checkpoint,
   then apply the approved pre-picture-lock actions.
4. **Autocheck and preview**: run each action's checks and report a compact result. The operator
   may send natural-language revisions; they form a new plan version.
5. **Picture lock**: an explicit operator decision. Until it exists, branded captions cannot be
   applied.
6. **Post-lock caption phase**: generate/read the subtitle timing from the locked edit and apply
   the branded Fusion Text+ caption layer only if the caption capability has been promoted for
   the workstation.
7. **Final review and delivery**: use the existing render prepare/approve/start flow. No final
   render begins only because the edit plan is verified.

The native subtitle track is a timing/diagnostic source. The validated visual workaround uses a
single Fusion composition with Text+ nodes; it must retain its existing readability, safe-area,
font, gap and render checks. Caption application stays terminal because earlier edits invalidate
caption timing.

## Execution and verification

The bridge accepts only schema-valid actions allowed by the active contract. For every action it
records precondition evidence, execution result and action-specific verification. Examples:

- `CUT`: resulting clip ranges and timeline duration;
- `B_ROLL`: explicit source/asset identity, range and absence of an unresolved placeholder;
- `REFRAME`: target range, source linkage and approved geometry;
- `CAPTIONS`: locked-edit fingerprint, font availability, wrapping, safe area, scene/face
  collision policy, gap frames and final-resolution render samples.

The bridge must preserve a checkpoint before write groups and journal successful state transitions.
Operations are idempotent under the same plan/action fingerprint: retries must not duplicate
markers, clips, captions or render jobs.

Failures are local. A missing B-roll, rejected asset or unsupported operation becomes `BLOCKED`
with a readable reason and next action; it does not invalidate verified cuts. Transient failures
may retry a bounded number of times. On restart, the bridge reports the existing plan state and
the next safe action, rather than replaying the whole plan.

## Capability promotion

Each action is introduced behind a dedicated capability and with a semantic bridge surface. A
candidate begins as `EXPERIMENTAL` or `PARTIAL`; it becomes `VALIDATED` only after unit tests,
an isolated Resolve gate, action-specific verification and recorded workstation evidence.

The first Vertical Social implementation slice establishes the plan/action lifecycle and exposes
caption capability status. It does not apply captions automatically. Caption execution is added
only after the existing tested workaround is parameterized, rollback-safe and revalidated against
the promotion criteria already recorded in `docs/16_CAPTION_ENGINE_AND_MOBILE_SUBTITLES.md`.

## Human interaction

The normal operator-facing response is one short card: what was understood, approved actions,
blocked inputs, verification result and the single most useful next decision. Technical operators
may request the full evidence, contract, journal and plan details. If the request is ambiguous or
needs an unavailable capability, the assistant asks one concise question instead of guessing.

## Testing and rollout

Automated tests must cover plan fingerprint binding, phase ordering, rejected/unknown action
types, capability gates, per-action state transitions, idempotent retry and resume after a
partial failure. Resolve-facing features require a separate native validation in a temporary
project, with source/project restoration and workstation-specific ledger evidence.

`PC_PERSONALE` is the first rollout target. `PC_SEGRETERIA` remains unchanged until it receives a
separate installation and its own successful gate. The default for every new capability remains
disabled.

