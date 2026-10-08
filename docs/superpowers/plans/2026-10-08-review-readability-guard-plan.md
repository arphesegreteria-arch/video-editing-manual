# Review Readability Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make ARPHÈ review reels and Story/Reel templates refuse unreadable, unsafe or incorrectly-fonted content before Resolve is mutated.

**Architecture:** `arphe-graphic-kit` publishes one canonical JSON policy and verifies its own templates. `video-editing-manual` pins that policy, evaluates content in a pure preflight, stores only fingerprint-based approvals, and exposes thin guarded MCP workflows; workstation font and rollout evidence remain separate.

**Tech Stack:** Python 3 standard library and `unittest`, Windows GDI through `ctypes`, JSON, HTML/CSS/SVG, DaVinci Resolve/Fusion scripting, PowerShell installers.

**Spec:** `docs/superpowers/specs/2026-10-08-review-readability-guard-design.md`

## Global Constraints

- `arphe-graphic-kit` is canonical; the bridge runtime consumes a pinned copy and does not require the kit checkout.
- Use complete, genuine, anonymised and editorially approved reviews; never rewrite or automatically excerpt them.
- One card per review is the default; split only at an approved sentence boundary and preserve every character in order.
- Reading duration is `max(3, ceil(word_count / 4) + 1)` seconds at the confirmed project frame rate.
- Standard duration is at most 12 seconds; longer content is `NEEDS_REVIEW`, not silently capped.
- Portrait body tiers are exactly `0.052`, `0.047`, `0.042`; no smaller size is allowed and the maximum is seven lines.
- The 1080x1920 essential safe rectangle is horizontal 8%-84% and vertical 10%-82% (`x=86..907`, `y=192..1574` approximately).
- Typography is Noto Serif Display 300 for headings and Satoshi 400/500/700 for body, labels and buttons; Satoshi Black is not allowed.
- Missing effective fonts, contract mismatch or unresolved review status produces zero Resolve writes.
- Stable reason codes are exactly `TOO_LONG_FOR_STANDARD`, `TEXT_OVERFLOW`, `FONT_UNAVAILABLE`, `UNSAFE_LAYOUT`, `STALE_APPROVAL` and `CONTRACT_MISMATCH`.
- Public Git history, fixtures, audit logs and approval records contain no real review text.
- `PC_PERSONALE` and `PC_SEGRETERIA` share source code but never runtime configuration, state, font evidence or validation claims.
- `CAP_READABILITY_GUARD=false` blocks review writes; it never restores the legacy unguarded path.

## Review Focus

- A single unbroken token wider than the text frame must become `TEXT_OVERFLOW`, never loop, truncate or shrink below `0.042`; Task 5 pins this.
- A registered font family with a missing required weight must become `FONT_UNAVAILABLE`; Task 4 pins family-and-weight matching separately.
- A vertical timeline whose project, timeline or playback rate is not exactly 30 fps must be blocked before review writes; Task 7 pins this.
- Reordering reviews, changing punctuation or changing a split boundary after approval must produce `STALE_APPROVAL`; Task 6 pins all three.
- A missing, malformed or digest-mismatched bundled contract must keep read-only inspection diagnostic but block all review writes; Tasks 3 and 7 pin this.

---

### Task 1: Publish the canonical Graphic Kit readability policy

**Repository:** `arphe-graphic-kit`

**Files:**
- Create: `tokens/video-readability.json`
- Modify: `scripts/verify_kit.py`
- Modify: `tests/test_verify_kit.py`

**Interfaces:**
- Consumes: existing Graphic Kit root and template inventory.
- Produces: `load_video_readability_policy(path: Path) -> dict`, `canonical_policy_digest(policy: dict) -> str`, and policy version `ARPHE_VIDEO_READABILITY_V1` for Task 3.

- [ ] **Step 1: Write failing policy-schema and digest tests**

Add tests asserting the exact version, reading formula values, safe rectangle, size tiers, seven-line limit and typography roles. Assert that unknown keys, booleans in numeric fields, unordered size tiers and out-of-range safe coordinates fail.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `py -3 -m unittest tests.test_verify_kit -v`

Expected: FAIL because `tokens/video-readability.json` and loader functions do not exist.

- [ ] **Step 3: Add the canonical JSON policy**

Use these exact values:

```json
{
  "schema_version": 1,
  "policy_version": "ARPHE_VIDEO_READABILITY_V1",
  "canvases": {
    "story_reel_1080x1920": {
      "width": 1080,
      "height": 1920,
      "essential_safe_area": {"left": 0.08, "right": 0.84, "top": 0.10, "bottom": 0.82}
    }
  },
  "reading": {"words_per_second": 4.0, "settle_seconds": 1, "minimum_seconds": 3, "standard_maximum_seconds": 12},
  "review_body": {"size_tiers": [0.052, 0.047, 0.042], "maximum_lines": 7},
  "typography": {
    "heading": {"family": "Noto Serif Display", "weight": 300},
    "body": {"family": "Satoshi", "weight": 400},
    "label": {"family": "Satoshi", "weight": 500},
    "button": {"family": "Satoshi", "weight": 700}
  },
  "technical_fallback_is_final": false
}
```

- [ ] **Step 4: Implement strict loading and canonical SHA-256 calculation**

Parse UTF-8 JSON, reject schema drift and hash canonical JSON encoded with sorted keys and compact separators. Do not include the repository commit in the policy digest.

- [ ] **Step 5: Run verifier tests and the portable verifier**

Run: `py -3 -m unittest tests.test_verify_kit -v`

Run: `py -3 scripts/verify_kit.py`

Expected: both PASS.

- [ ] **Step 6: Commit the policy foundation**

```bash
git add tokens/video-readability.json scripts/verify_kit.py tests/test_verify_kit.py
git commit -m "feat: define video readability policy"
```

### Task 2: Make Story/Reel templates enforce safe areas and observable fonts

**Repository:** `arphe-graphic-kit`

**Files:**
- Modify: `templates/social/story-1080x1920.html`
- Modify: `templates/social/story-1080x1920.svg`
- Modify: `templates/shared/brand.css`
- Modify: `scripts/verify_kit.py`
- Modify: `tests/test_verify_kit.py`
- Modify: `VIDEO-EDITING.md`
- Modify: `fonts/SATOSHI.md`

**Interfaces:**
- Consumes: `load_video_readability_policy()` and `story_reel_1080x1920` from Task 1.
- Produces: `verify_story_reel_template_geometry(root: Path, policy: dict) -> list[str]` and templates whose essential nodes are machine-identifiable.

- [ ] **Step 1: Write failing safe-area and font-marker tests**

Assert that essential HTML/SVG nodes are marked, contained inside `x=86..907` and `y=192..1574`, that the current 96-pixel bottom placement fails, and that a missing Satoshi-ready/draft marker fails.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `py -3 -m unittest tests.test_verify_kit -v`

Expected: FAIL on current `.copy { bottom: 96px; }` and absent font status markers.

- [ ] **Step 3: Move essential Story/Reel content into the canonical safe rectangle**

Use `left: 86px`, `right: 173px` and `bottom: 346px` for the essential copy container. Update SVG essential anchors and button bounds to the same rectangle. Decorative page-number and line elements may remain outside only when marked non-essential.

- [ ] **Step 4: Make fallback status visible**

Keep the licensed Fontshare request, await `document.fonts.ready`, test Satoshi 400/500/700 with `document.fonts.check`, and expose a visible `DRAFT — FONT FALLBACK` badge when any required weight is unavailable. Static verification must reject removal of this behaviour.

- [ ] **Step 5: Document final-vs-draft font behaviour**

State that the template may open offline with a fallback but cannot count as final delivery until required font weights load. Do not add Satoshi binaries.

- [ ] **Step 6: Run all Graphic Kit checks**

Run: `py -3 -m unittest discover -s tests -p "test_*.py" -v`

Run: `py -3 scripts/verify_kit.py`

Expected: PASS with zero errors.

- [ ] **Step 7: Commit and record the source commit for pinning**

```bash
git add templates/social/story-1080x1920.html templates/social/story-1080x1920.svg templates/shared/brand.css scripts/verify_kit.py tests/test_verify_kit.py VIDEO-EDITING.md fonts/SATOSHI.md
git commit -m "feat: enforce Story Reel readability"
git rev-parse HEAD
```

The resulting commit is the exact `graphic_kit_commit` used in Task 3.

### Task 3: Pin and verify the Graphic Kit contract in the bridge

**Repository:** `video-editing-manual`

**Files:**
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/review_readability_contract.json`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/readability_contract.py`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_readability_contract.py`
- Create: `scripts/verify_review_readability_contract.py`

**Interfaces:**
- Consumes: Task 2 Graphic Kit commit and `tokens/video-readability.json`.
- Produces: `ReadabilityPolicy`, `load_readability_contract(path: Path) -> ReadabilityPolicy`, `contract_digest(policy: ReadabilityPolicy) -> str`, and CLI `--graphic-kit <path>` drift verification.

- [ ] **Step 1: Write failing contract parser and drift tests**

Test valid load, missing file, malformed schema, modified policy value, wrong source digest, unknown canvas and exact commit/digest comparison against a temporary Graphic Kit fixture.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `.venv\Scripts\python.exe -m unittest scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_readability_contract -v`

Expected: FAIL because the module and contract do not exist.

- [ ] **Step 3: Create the pinned contract**

Copy the Task 2 policy values exactly and add `graphic_kit_repository`, exact `graphic_kit_commit` and canonical `graphic_kit_policy_digest`. Do not hand-edit copied policy values after generating the digest.

- [ ] **Step 4: Implement strict runtime loading and the development drift CLI**

The runtime loader depends only on the bundled JSON. The CLI accepts an explicit checkout path, reads its Git `HEAD` and policy, and exits non-zero on either commit or digest drift.

- [ ] **Step 5: Run focused and cross-repository verification**

Run: `.venv\Scripts\python.exe -m unittest scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_readability_contract -v`

Run: `.venv\Scripts\python.exe scripts/verify_review_readability_contract.py --graphic-kit <absolute-path-to-arphe-graphic-kit>`

Expected: PASS and print the pinned policy version, commit and digest.

- [ ] **Step 6: Commit the pinned contract**

```bash
git add scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/review_readability_contract.json scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/readability_contract.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_readability_contract.py scripts/verify_review_readability_contract.py
git commit -m "feat: pin review readability contract"
```

### Task 4: Add testable Windows font readiness and text measurement

**Files:**
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/font_readiness.py`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_font_readiness.py`

**Interfaces:**
- Consumes: `ReadabilityPolicy.typography` from Task 3.
- Produces: `TextMeasurer` protocol, `WindowsGdiTextMeasurer`, `FontReadiness`, and `check_required_fonts(policy: ReadabilityPolicy, measurer: TextMeasurer) -> FontReadiness` for Task 5.

- [ ] **Step 1: Write failing family, weight and measurement tests**

Use a fake measurer to prove that Satoshi 400/500/700 and Noto Serif Display 300 are checked independently, a missing weight blocks readiness, long Unicode strings return finite widths, and no local font paths appear in serialized results.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `.venv\Scripts\python.exe -m unittest scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_font_readiness -v`

Expected: FAIL because `font_readiness.py` does not exist.

- [ ] **Step 3: Implement the protocol and Windows GDI adapter**

Use `ctypes` with a memory device context, explicit family/weight selection and `GetTextExtentPoint32W`. Always release selected objects and the device context in `finally`. Non-Windows construction returns an unavailable diagnostic rather than guessing.

- [ ] **Step 4: Add a Windows-only integration test**

The test may skip when required fonts are not installed, but when they are installed it must measure the same synthetic string twice with identical finite results and verify every required weight.

- [ ] **Step 5: Run the focused tests**

Expected: PASS; any environment skip is explicit and does not count as workstation validation.

- [ ] **Step 6: Commit**

```bash
git add scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/font_readiness.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_font_readiness.py
git commit -m "feat: inspect creative font readiness"
```

### Task 5: Build the pure review readability preflight

**Files:**
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/review_readability.py`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_review_readability.py`

**Interfaces:**
- Consumes: `ReadabilityPolicy`, `TextMeasurer`, `FontReadiness`.
- Produces: `ReviewAssessment`, `SequenceAssessment`, `assess_review(text: str, canvas_id: str, fps: float, policy: ReadabilityPolicy, measurer: TextMeasurer, fonts: FontReadiness) -> ReviewAssessment`, `assess_sequence(reviews: list[dict], canvas_id: str, fps: float, policy: ReadabilityPolicy, measurer: TextMeasurer, fonts: FontReadiness) -> SequenceAssessment`, and `suggest_sentence_split(text: str, measurer: TextMeasurer, policy: ReadabilityPolicy) -> int | None`.

- [ ] **Step 1: Write failing duration and type-fit tests**

Assert 20/30/40/44/45/70 words produce 6/9/11/12/13/19 seconds; 45 and 70 are `NEEDS_REVIEW`; sizes are tried largest-first; eight lines fail; seven pass; no size below `0.042` is produced.

- [ ] **Step 2: Add failing Review Focus tests**

Cover explicit newlines, repeated spaces, apostrophes, punctuation, empty text, a single over-wide token, Unicode text and a measurer returning NaN. Expected outcomes are deterministic `TEXT_OVERFLOW` or `BLOCKED`, never truncation or an unbounded loop.

- [ ] **Step 3: Run the focused tests and verify RED**

Run: `.venv\Scripts\python.exe -m unittest scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_review_readability -v`

- [ ] **Step 4: Implement duration, measured wrapping and status aggregation**

Preserve the input text. Count on normalised whitespace only for duration. Wrap using measured advances at each approved tier and reject over-wide tokens. Aggregate severity is `BLOCKED` over `NEEDS_REVIEW` over `PASS`.

- [ ] **Step 5: Implement sentence-boundary suggestions**

Choose the valid sentence boundary nearest the measured midpoint. Return only the character offset; caller views are allowed to show both verbatim parts, but logs and stored assessments are not.

- [ ] **Step 6: Add fingerprint tests and implementation**

`SequenceAssessment.fingerprint` hashes workstation-independent content needed for staleness: exact review text and order, stars, split candidates, canvas, fps, policy version and policy digest. It never becomes an audit field unless already hashed.

- [ ] **Step 7: Run focused tests and commit**

```bash
git add scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/review_readability.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_review_readability.py
git commit -m "feat: assess review readability"
```

### Task 6: Bind editorial exceptions to immutable approvals

**Files:**
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/readability_approvals.py`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_readability_approvals.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/registry.py`

**Interfaces:**
- Consumes: `SequenceAssessment.fingerprint` from Task 5.
- Produces: `ReadabilityApproval`, `approve_readability(registry: Registry, workstation_id: str, assessment_fingerprint: str, decisions: list[dict], operator_role: str) -> ReadabilityApproval`, and `require_current_approval(registry: Registry, assessment: SequenceAssessment, approval_token: str | None) -> ReadabilityApproval | None`.

- [ ] **Step 1: Write failing approval lifecycle tests**

Test `PASS` without approval, long-single approval, sentence-split approval, invalid role, invalid decision, split not on the suggested boundary and approval stored without review text.

- [ ] **Step 2: Add stale-approval tests**

Changing punctuation, review order, policy digest, canvas, fps or split boundary must reject the old token with `STALE_APPROVAL`.

- [ ] **Step 3: Run the focused tests and verify RED**

Run: `.venv\Scripts\python.exe -m unittest scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_readability_approvals -v`

- [ ] **Step 4: Add `readability_approvals` to Registry schema version 1 defaults**

Persist only fingerprint, token, workstation, role, decision types, review indices, split offsets and timestamps. Use the existing atomic `_save`; never persist text or text fragments.

- [ ] **Step 5: Implement approval and validation functions**

Allow roles `SEGRETERIA`, `TECNICO`, `ALESSIO`. Long-single and verbatim-split decisions require explicit entries for every `NEEDS_REVIEW` item. Token generation hashes canonical approval metadata.

- [ ] **Step 6: Run tests and commit**

```bash
git add scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/readability_approvals.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/registry.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_readability_approvals.py
git commit -m "feat: bind readability approvals"
```

### Task 7: Guard every public review write before Resolve mutation

**Files:**
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/review_workflow.py`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_review_workflow.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/server.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/tool_catalog.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/creative_tools.py`

**Interfaces:**
- Consumes: Tasks 3-6 contract, measurer, assessment and approval functions.
- Produces: `inspect_sequence_readability(timeline: Any, config: CreativeConfig, reviews: list[dict]) -> SequenceAssessment`, `create_guarded_review_sequence(project: Any, timeline: Any, config: CreativeConfig, registry: Registry, name: str, reviews: list[dict], total_duration_frames: int, style_role: str, cta: dict | None, intro: dict | None, approval_token: str | None) -> dict`, read-only MCP `inspect_review_readability`, write MCP `approve_review_readability`, guarded `create_review_sequence_v2(..., readability_approval_token: str | None = None)`, guarded compatibility wrapper and guarded single-card tool.

- [ ] **Step 1: Write failing zero-write gate tests**

Instrument fake Resolve objects. `FONT_UNAVAILABLE`, `TEXT_OVERFLOW`, non-30 vertical project/timeline/playback fps, contract mismatch, missing capability and stale approval must all leave composition insertion and `AddTool` call counts at zero.

- [ ] **Step 2: Write failing PASS and approved-exception tests**

Verify standard sequences retain automatic windows, approved long-single uses the full 13+ second duration, approved split creates two consecutive cards from one original payload, and split text concatenates exactly to the source.

- [ ] **Step 3: Write failing MCP surface and redaction tests**

Assert the two new tools and parameter names, safe annotations, no review text in audit/error metadata, and that legacy `add_review_card` and `create_review_sequence` cannot bypass the guard.

- [ ] **Step 4: Run focused tests and verify RED**

Run: `.venv\Scripts\python.exe -m unittest scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_review_workflow -v`

- [ ] **Step 5: Implement `review_workflow.py` orchestration**

Load the bundled contract, confirm 1080x1920 and all three 30 fps settings, build font readiness, assess the full sequence, validate approval, then and only then call the existing creative primitive. Return structured statuses and reason codes without logging payload text.

- [ ] **Step 6: Add MCP tools and route all public review writes through the workflow**

`inspect_review_readability` may run while the capability is disabled. Approval records metadata only. Every write requires the capability and current assessment. Keep low-level creative graph construction internal after guard success.

The guarded workflow expands an approved split in memory, reassesses both verbatim parts, and passes the expanded review payload plus one layout decision per resulting card to the creative primitive. No expanded text is persisted.

- [ ] **Step 7: Replace the five-second timing helper**

Remove the old `words / 5.5` and five-second cap. Creative graph windows consume the preflight-selected durations and size tiers; explicit legacy total duration cannot undercut the assessment.

- [ ] **Step 8: Run focused tests and commit**

```bash
git add scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/review_workflow.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/server.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/tool_catalog.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/creative_tools.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_review_workflow.py
git commit -m "feat: guard review writes with readability"
```

### Task 8: Align Fusion typography and geometry with the policy

**Files:**
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/creative_tools.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_fusion_graph.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_project_timeline_tools.py`

**Interfaces:**
- Consumes: selected size tier, safe rectangle and typography roles from `SequenceAssessment`/`ReadabilityPolicy`.
- Produces: `create_review_sequence(..., *, readability_layouts: list[dict[str, Any]]) -> dict` and `add_review_card(..., *, readability_layout: dict[str, Any]) -> dict`, with policy-driven Fusion Text+ and essential-node geometry plus read-back verification. These arguments are mandatory for internal callers, preventing a code-level legacy bypass.

- [ ] **Step 1: Write failing typography tests**

Assert review body uses Satoshi Regular/400, labels use Medium/500, buttons use Bold/700, intro heading uses Noto Serif Display Light/300, and no node requests Satoshi Black.

- [ ] **Step 2: Write failing safe-area tests**

For a vertical timeline, compute each essential Text+/mask bounding box and assert it stays inside normalised `0.08..0.84` and `0.10..0.82`. Include the CTA and seven-line body boundary.

- [ ] **Step 3: Run focused tests and verify RED**

Run: `.venv\Scripts\python.exe -m unittest scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_fusion_graph scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_project_timeline_tools -v`

- [ ] **Step 4: Consume policy values instead of length-based hard-coding**

Pass the selected body size and policy typography/geometry into card, intro and CTA construction. Preserve existing Text+ read-back verification and rollback of newly created nodes.

- [ ] **Step 5: Run tests and commit**

```bash
git add scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/creative_tools.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_fusion_graph.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_project_timeline_tools.py
git commit -m "feat: apply canonical review typography"
```

### Task 9: Add the fail-closed capability and preserve workstation isolation

**Files:**
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/config.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/feature_flags.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/creative_config.example.json`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/set_feature_flag.ps1`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/install_on_segreteria.ps1`
- Modify: `scripts/windows_bridge/tests/test_profile_installer.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_feature_flags.py`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_safety.py`

**Interfaces:**
- Consumes: guarded public workflows from Task 7.
- Produces: `CAP_READABILITY_GUARD`, default false, installer migration that preserves explicit existing values, and feature report readiness details.

- [ ] **Step 1: Write failing config, feature-report and installer tests**

Assert the new flag is recognised, defaults false, appears in PowerShell validation, is added false to both workstation configs, survives upgrades when true, and never copies another workstation's state.

- [ ] **Step 2: Write the fail-closed test**

With `CAP_REVIEW=true` and `CAP_READABILITY_GUARD=false`, inspection succeeds but every review write returns a capability error before Resolve calls.

- [ ] **Step 3: Run focused Creative and Windows tests and verify RED**

Run: `.venv\Scripts\python.exe -m unittest scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_feature_flags scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_safety -v`

Run: `.venv\Scripts\python.exe -m unittest scripts.windows_bridge.tests.test_profile_installer -v`

- [ ] **Step 4: Implement the capability and installer migration**

Technical availability requires a valid bundled contract and the public guarded workflow; installed-font status remains a per-call readiness result. Do not make a missing font disappear from diagnostics by marking the whole bridge unavailable.

- [ ] **Step 5: Run tests and commit**

```bash
git add scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/config.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/feature_flags.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/creative_config.example.json scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/set_feature_flag.ps1 scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/install_on_segreteria.ps1 scripts/windows_bridge/tests/test_profile_installer.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_feature_flags.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_safety.py
git commit -m "feat: gate review readability rollout"
```

### Task 10: Document operation and complete automated verification

**Files:**
- Create: `validation/review-readability-ledger.json`
- Create: `scripts/validate_review_readability_ledger.py`
- Create: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_readability_validation.py`
- Modify: `docs/16_INSTAGRAM_REVIEW_REEL_STANDARD.md`
- Modify: `docs/11_CREATIVE_BRIDGE_AND_E09.md`
- Modify: `CURRENT_STATE.md`
- Modify: `CHANGELOG.md`
- Modify: `INDEX.md`
- Modify: `START_HERE.md`
- Modify: `scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/README.md`

**Interfaces:**
- Consumes: all previous tasks and exact test output.
- Produces: operator flow, rollback, `validate_readability_ledger(path: Path, current_state: Path) -> list[str]`, and separate validation states for automated, `PC_PERSONALE` and `PC_SEGRETERIA` evidence.

- [ ] **Step 1: Write failing validation-ledger tests**

Require schema version, evidence kind (`AUTOMATED`, `PC_PERSONALE_LIVE`, `PC_SEGRETERIA_LIVE`), exact repository commits, policy version/digest, observed timestamp, result, limitations and a `CURRENT_STATE.md` reference. Reject raw review text, missing workstation identity for live evidence and claims that one PC validates the other.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `.venv\Scripts\python.exe -m unittest scripts.experiments.ARPHE_MCP_BRIDGE_CREATIVE_03.tests.test_readability_validation -v`

Expected: FAIL because the ledger and validator do not exist.

- [ ] **Step 3: Implement the ledger and validator**

Start with automated evidence only and explicit pending entries for both PCs. The validator returns every schema, privacy and cross-reference error and exits non-zero when invoked as a CLI with any error.

- [ ] **Step 4: Update operator documentation**

Document inspect -> content approval -> optional readability approval -> guarded creation -> visual preview. Include reason-code actions, 4 words/second, 12-second standard, one-card default, verbatim split exception, font installation requirements and safe area.

- [ ] **Step 5: Run the complete automated suites**

Run: `.venv\Scripts\python.exe -m unittest discover -s scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests -p "test_*.py" -v`

Run: `.venv\Scripts\python.exe -m unittest discover -s scripts/windows_bridge/tests -p "test_*.py" -v`

Run: `.venv\Scripts\python.exe scripts/verify_review_readability_contract.py --graphic-kit <absolute-path-to-arphe-graphic-kit>`

Run: `.venv\Scripts\python.exe scripts/validate_review_readability_ledger.py --ledger validation/review-readability-ledger.json --current-state CURRENT_STATE.md`

Expected: all tests pass; only named environment-dependent skips remain; contract commit and digest match.

- [ ] **Step 6: Audit privacy and bypasses**

Run searches for real review fixtures, raw `text` in audit records, Satoshi binaries, the old five-second cap, Satoshi Black and unguarded public review writes. Any match must be explained or removed before rollout.

- [ ] **Step 7: Update state and changelog with automated evidence only**

Mark live validation pending. Do not infer either workstation result from unit tests.

- [ ] **Step 8: Commit documentation and validation tooling**

```bash
git add validation/review-readability-ledger.json scripts/validate_review_readability_ledger.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_readability_validation.py docs/16_INSTAGRAM_REVIEW_REEL_STANDARD.md docs/11_CREATIVE_BRIDGE_AND_E09.md CURRENT_STATE.md CHANGELOG.md INDEX.md START_HERE.md scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/README.md
git commit -m "docs: add review readability workflow"
```

### Task 11: Review both repositories and validate `PC_PERSONALE`

**Files:**
- Modify after evidence: `CURRENT_STATE.md`
- Modify after evidence: `CHANGELOG.md`
- Modify after evidence: `validation/review-readability-ledger.json`

**Interfaces:**
- Consumes: Graphic Kit branch, video branch and disabled capability.
- Produces: review findings resolved, personal live evidence and a rollback-tested personal rollout.

- [ ] **Step 1: Run a whole-change review in each repository**

Review Graphic Kit from its pre-Task-1 base and video manual from `origin/main`. Focus on policy drift, false font positives, privacy, unguarded writes, stale approvals, Resolve partial mutation and cross-workstation paths. Fix every Critical or Important finding and rerun Task 10 Step 2.

- [ ] **Step 2: Install the video branch on `PC_PERSONALE` with the flag false**

Confirm workstation identity and preserve the existing personal config/state. Restart only the personal bridge. Check readiness, contract version and font status before enabling.

- [ ] **Step 3: Enable only `CAP_READABILITY_GUARD` on `PC_PERSONALE`**

Use the existing feature-flag script. Confirm `PC_SEGRETERIA` config remains byte-for-byte unchanged.

- [ ] **Step 4: Validate on an isolated personal test timeline**

Use synthetic text for boundary tests and locally approved anonymised real reviews only for editorial visual inspection. Capture short, 44-word, approved-long, approved-split, CTA and font evidence. Confirm preview/project/timeline fps are all 30 and no existing editorial timeline changes.

- [ ] **Step 5: Exercise rollback**

Disable the personal capability, confirm inspection still works and writes block, then re-enable only after rollback evidence is recorded. Leave created test timelines untouched; any later retirement must use the existing archive-first workflow as a separate explicit action.

- [ ] **Step 6: Record exact personal evidence and commit**

State `PC_PERSONALE` only, exact commits, test counts, font status, limitations and rollback. Leave `PC_SEGRETERIA` as pending.

### Task 12: Open coordinated PRs, merge safely and stage `PC_SEGRETERIA`

**Files:**
- Modify after segreteria evidence: `CURRENT_STATE.md`
- Modify after segreteria evidence: `CHANGELOG.md`
- Modify after segreteria evidence: `validation/review-readability-ledger.json`.

**Interfaces:**
- Consumes: reviewed Graphic Kit and video branches with personal evidence.
- Produces: merged canonical policy and guarded bridge; segreteria remains disabled until its own live gate.

- [ ] **Step 1: Open the Graphic Kit PR first**

Require portable verifier and unit tests. Merge it first so the video contract points to a reachable canonical commit.

- [ ] **Step 2: Re-pin to the Graphic Kit commit reachable from merged `main`**

Set `graphic_kit_commit` to the exact merged `main` commit that contains the policy, retain the verified policy digest, rerun drift verification and commit the pin update before opening the video PR.

- [ ] **Step 3: Open the video PR and run final branch verification**

Attach both PRs to the task. Require full Creative/Windows suites, cross-repository contract verification, privacy audit and whole-branch review. Merge only when clean.

- [ ] **Step 4: Keep `PC_SEGRETERIA` disabled after merge**

Installation may update common code and add the false flag, but must not enable review writes or touch its open Resolve project/timeline.

- [ ] **Step 5: Perform the separate segreteria live gate when available**

Verify workstation identity, fonts, contract, 1080x1920/30 settings and an isolated new test timeline. Repeat the same visual cases and rollback test. Record only observed evidence.

- [ ] **Step 6: Enable segreteria only after its evidence commit is merged**

If any gate fails, leave the flag false, preserve the open editorial project, document the blocker and keep the personal rollout independent.

## Completion Boundary

Implementation is complete when both repository PRs are merged, automated verification is clean,
`PC_PERSONALE` has passed its live and rollback gates, and the shipped segreteria configuration is
fail-closed. Full `PC_SEGRETERIA` validation and enablement may remain explicitly pending until the
machine is available; it must never be inferred from personal results.
