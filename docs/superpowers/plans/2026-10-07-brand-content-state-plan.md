# Brand, Content and Validation-State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Make the graphic kit enforceable for video work, keep approved real-review text local, and make validation status auditable per workstation.

**Architecture:** A version-pinned brand contract in video-editing-manual is derived from canonical graphic-kit data and checked when both repositories are available. Public plans contain opaque review IDs only; a validation ledger is the single evidence source for CURRENT_STATE.md and CHANGELOG.md.

**Tech Stack:** Python stdlib JSON and pytest/unittest; Markdown and JSON.

**Spec:** docs/superpowers/specs/2026-10-07-brand-content-state-motion-workstation-design.md

## Global Constraints

- arphe-graphic-kit is canonical for colour and typography.
- Public Git history, examples, fixtures and bridge logs must not contain review text or identifiers.
- Genuine anonymised reviews are local runtime input following human editorial approval.
- A code test must not be presented as workstation validation.
- No render, queue, cleanup or deletion change belongs to this plan.

## Review Focus

- Changed graphic-kit token: verification fails with the differing key named.
- Review-like input in a public plan: scan rejects it without exposing the text.
- Ambiguous historical tunnel state: ledger shows UNKNOWN rather than inferring a PASS.
- Missing evidence reference: validator rejects a claimed workstation PASS.
- Font fallback: preflight reports it; it cannot silently alter a composition.

---

## File Structure

- arphe-graphic-kit/tokens/colors.json and brand-guidelines/typography.md: upstream source data.
- arphe-graphic-kit/brand-guidelines/ISTRUZIONI-PER-AI.md: local-only anonymised review policy.
- scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/brand_contract.json: pinned, video-facing contract.
- scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/brand_contract.py: load and resolve canonical brand roles.
- scripts/verify_brand_contract.py: compare contract and checked-out kit.
- scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/audit.py: redact review inputs.
- plans/ARPHE_E09_REVIEWS_CARTOLINE_V1.json: public-safe placeholder plan.
- docs/17_CONTENT_HANDLING_AND_REVIEW_ANONYMIZATION.md: canonical public policy.
- validation/validation-ledger.json and scripts/validate_validation_ledger.py: evidence source and verifier.
- CURRENT_STATE.md and CHANGELOG.md: concise summaries referencing ledger IDs.

### Task 1: Add pinned brand contract and verifier

**Files:**
- Create: scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/brand_contract.json
- Create: scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/brand_contract.py
- Create: scripts/verify_brand_contract.py
- Create: scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_brand_contract.py
- Modify: scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/creative_config.example.json

**Interfaces:**
- Produces load_brand_contract(path: Path) -> BrandContract.
- Produces verify_contract(contract_path: Path, graphic_kit_root: Path) -> list[str].
- Produces BrandContract.color(role: str, alpha: float = 1.0) -> tuple[float, float, float, float].

- [ ] **Step 1: Write failing contract tests**

~~~python
def test_contract_matches_canonical_graphic_kit():
    assert verify_contract(CONTRACT, GRAPHIC_KIT) == []

def test_contract_reports_a_changed_canonical_colour():
    assert "burgundy" in verify_contract(TAMPERED_CONTRACT, GRAPHIC_KIT)[0]
~~~

- [ ] **Step 2: Run test to verify it fails**

Run: py -3 -m pytest scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_brand_contract.py -v

Expected: FAIL because the contract module/files do not exist.

- [ ] **Step 3: Implement the contract and verifier**

Use exactly cream, brown, burgundy, red and ink; record the graphic-kit revision. Map video semantic roles to these values only. Permit alpha variants but reject undeclared opaque colours and noncanonical typography.

- [ ] **Step 4: Replace independent Creative palette/type data**

The example config references the contract. Existing composition functions obtain colour/type roles through BrandContract.

- [ ] **Step 5: Run focused tests**

Run: py -3 -m pytest scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_brand_contract.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_feature_flags.py -v

Expected: PASS, including unknown-role and font-fallback checks.

- [ ] **Step 6: Commit**

~~~bash
git add scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/brand_contract.json scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/brand_contract.py scripts/verify_brand_contract.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/creative_config.example.json scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_brand_contract.py
git commit -m "feat: enforce graphic kit brand contract"
~~~

### Task 2: Establish local-only anonymised-review boundary

**Files:**
- Modify: plans/ARPHE_E09_REVIEWS_CARTOLINE_V1.json
- Modify: scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/audit.py
- Modify: scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_audit.py
- Create: scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_public_review_boundary.py
- Create: docs/17_CONTENT_HANDLING_AND_REVIEW_ANONYMIZATION.md
- Modify: docs/11_CREATIVE_BRIDGE_AND_E09.md and docs/15_E09_REVIEWS_CARTOLINE.md
- Modify: arphe-graphic-kit/brand-guidelines/ISTRUZIONI-PER-AI.md

**Interfaces:**
- Consumes approved local text, stars and optional display label only.
- Produces audit records with review payload fields removed and public plan records with opaque review_id plus non-identifying layout metadata.

- [ ] **Step 1: Write failing privacy-boundary tests**

~~~python
def test_audit_never_serializes_review_text_or_source_metadata():
    record = write_then_read_audit({"text": "review body", "doctor": "name"})
    assert "review body" not in record
    assert "doctor" not in record

def test_public_review_plan_contains_no_text_or_source_fields():
    assert scan_public_review_plan(E09_PLAN) == []
~~~

- [ ] **Step 2: Run tests to verify they fail**

Run: py -3 -m pytest scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_audit.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_public_review_boundary.py -v

Expected: FAIL because the current plan includes review bodies and source metadata.

- [ ] **Step 3: Replace public review payloads with IDs/templates**

Retain only non-identifying timing/layout/stars. Remove text, author, doctor, date, service, source URL and retrieval metadata. Document the ignored local input manifest that supplies approved runtime text.

- [ ] **Step 4: Align written policy in both repositories**

Replace the graphic kit’s blanket prohibition with the approved local-only boundary. Update video documents to link the policy and remove contradictory statements.

- [ ] **Step 5: Run privacy tests and tracked-content scan**

Run: py -3 -m pytest scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_audit.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_public_review_boundary.py -v

Expected: PASS; tracked public plan/fixture scan contains no review text or identifiers.

- [ ] **Step 6: Commit separately**

~~~bash
git -C ../arphe-graphic-kit add brand-guidelines/ISTRUZIONI-PER-AI.md
git -C ../arphe-graphic-kit commit -m "docs: define local-only approved review policy"
git add plans/ARPHE_E09_REVIEWS_CARTOLINE_V1.json docs/17_CONTENT_HANDLING_AND_REVIEW_ANONYMIZATION.md docs/11_CREATIVE_BRIDGE_AND_E09.md docs/15_E09_REVIEWS_CARTOLINE.md scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/bridge/audit.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_audit.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_public_review_boundary.py
git commit -m "docs: keep approved reviews local"
~~~

### Task 3: Add validation ledger and repair state summaries

**Files:**
- Create: validation/validation-ledger.json
- Create: validation/schema.md
- Create: scripts/validate_validation_ledger.py
- Create: tests/test_validation_ledger.py
- Modify: CURRENT_STATE.md, CHANGELOG.md and docs/14_PERSONAL_PC_BRIDGE_INSTALLATION.md

**Interfaces:**
- Consumes ledger records with evidence_ref, workstation, scope and result.
- Produces validate_ledger(path: Path) -> list[str]; state summaries reference ledger IDs only.

- [ ] **Step 1: Write failing ledger tests**

~~~python
def test_workstation_pass_requires_evidence_and_named_workstation():
    assert "evidence_ref" in validate_ledger(MISSING_EVIDENCE)

def test_current_state_only_references_existing_ledger_ids():
    assert validate_current_state_refs(CURRENT_STATE, LEDGER) == []
~~~

- [ ] **Step 2: Run tests to verify they fail**

Run: py -3 -m pytest tests/test_validation_ledger.py -v

Expected: FAIL because ledger and validator are absent.

- [ ] **Step 3: Implement ledger and migrate evidenced claims only**

Record date, revision, profile, PC, known versions, gate, scenario, result, evidence reference, recovery reference and limits. Mark conflicting tunnel facts UNKNOWN; do not infer later remote success.

- [ ] **Step 4: Rewrite status/changelog summaries**

CURRENT_STATE becomes an executive view of ledger records. CHANGELOG gains a mandatory per-test format: date, PC, profile/runtime, revision, gate, result, evidence, rollback/limitation.

- [ ] **Step 5: Run verification**

Run: py -3 -m pytest tests/test_validation_ledger.py -v; py -3 scripts/validate_validation_ledger.py --ledger validation/validation-ledger.json --current-state CURRENT_STATE.md

Expected: PASS with no dangling evidence or inferred PC validation.

- [ ] **Step 6: Commit**

~~~bash
git add validation scripts/validate_validation_ledger.py tests/test_validation_ledger.py CURRENT_STATE.md CHANGELOG.md docs/14_PERSONAL_PC_BRIDGE_INSTALLATION.md
git commit -m "docs: make workstation validation evidence authoritative"
~~~

