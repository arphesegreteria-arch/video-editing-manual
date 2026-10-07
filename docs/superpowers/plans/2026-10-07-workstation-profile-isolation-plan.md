# Workstation Profile Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Deploy the shared bridge safely to either workstation without shared configuration, Python aliases or silent legacy fallbacks.

**Architecture:** Profiles are validated Python data and own all runtime paths. PowerShell installation performs read-only preflight before mutation, then changes only paths owned by the selected profile. Legacy config is migrated only after identity confirmation; mismatch stops before writes.

**Tech Stack:** PowerShell 5.1+, Python stdlib/pytest, Windows Task Scheduler and existing DPAPI runtime scripts.

**Spec:** docs/superpowers/specs/2026-10-07-brand-content-state-motion-workstation-design.md

## Global Constraints

- Use one main code line and shared release.
- Each profile uses an absolute, version-checked interpreter; no py, python or WindowsApps alias in autostart/switch commands.
- Each profile owns config, Creative config, task, log and backup paths.
- No secret enters Git or cross-workstation configuration.
- Updating source does not deploy automatically.
- A PC is not validated until its named live gate is recorded.

## Review Focus

- Foreign legacy config causes failure before venv/config/task creation.
- Two profiles sharing install_root still resolve different Creative configs.
- Preflight creates no directory, venv, task or config.
- Missing/wrong Python fails before runtime mutation.
- Runtime switch retains the profile’s absolute mcp command, never py -3.

---

## File Structure

- scripts/windows_bridge/profile_config.py: normalized profile model and path derivation.
- scripts/windows_bridge/profiles/*.example.json: secret-free templates.
- scripts/install_workstation_profile.ps1: preflight/apply orchestrator.
- scripts/windows_bridge/common.ps1: active profile resolution and guarded legacy migration.
- scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/install_on_segreteria.ps1: explicit Creative config path.
- scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/switch_runtime_bridge.ps1: active profile command resolution.
- scripts/backup/*: profile-aware backup path.
- scripts/windows_bridge/tests/test_profile_config.py, test_profile_installer.py and test_runtime.py: static/dry-run coverage.

### Task 1: Model profile-owned paths in Python and templates

**Files:**
- Modify: scripts/windows_bridge/profile_config.py
- Modify: scripts/windows_bridge/profiles/pc_personale.example.json
- Modify: scripts/windows_bridge/profiles/pc_segreteria.example.json
- Modify: scripts/windows_bridge/tests/test_profile_config.py

**Interfaces:**
- Produces runtime_paths(profile: dict[str, Any]) -> dict[str, str].
- Returned keys: runtime_config, creative_config, backup_dir, log_dir and venv_python.
- Produces runtime_command(profile: dict[str, Any]) -> str using absolute venv_python.

- [ ] **Step 1: Write failing profile-path tests**

~~~python
def test_profiles_resolve_distinct_creative_and_runtime_configs():
    assert runtime_paths(personal)["creative_config"] != runtime_paths(office)["creative_config"]

def test_runtime_command_uses_absolute_profile_venv_python():
    assert not runtime_command(profile).lower().startswith(("py ", "python "))
~~~

- [ ] **Step 2: Run profile tests to verify model is absent**

Run: py -3 -m pytest scripts/windows_bridge/tests/test_profile_config.py -v

Expected: FAIL because runtime_paths/runtime_command do not exist.

- [ ] **Step 3: Implement normalized profile-owned path derivation**

Use <install_root>/runtime-configs/<workstation_id>/ for runtime and Creative config, plus profile-specific backup/log paths. Validate every derived path stays within declared install_root or log_root.

- [ ] **Step 4: Run profile tests**

Run: py -3 -m pytest scripts/windows_bridge/tests/test_profile_config.py -v

Expected: PASS for both Python versions and distinct paths.

- [ ] **Step 5: Commit**

~~~bash
git add scripts/windows_bridge/profile_config.py scripts/windows_bridge/profiles scripts/windows_bridge/tests/test_profile_config.py
git commit -m "feat: derive isolated workstation runtime paths"
~~~

### Task 2: Enforce preflight before writes and explicit legacy handling

**Files:**
- Modify: scripts/install_workstation_profile.ps1
- Modify: scripts/windows_bridge/common.ps1
- Modify: scripts/windows_bridge/tests/test_profile_installer.py
- Modify: scripts/windows_bridge/tests/test_runtime.py

**Interfaces:**
- Consumes ProfilePath, PreflightOnly, AllowTunnelChange and explicit WorkstationId.
- Produces a no-write preflight report or apply result naming only owned paths.
- Produces Resolve-ArpheProfileDataDir -WorkstationId <id>, which rejects foreign legacy configuration.

- [ ] **Step 1: Write failing installer/common tests**

~~~python
def test_preflight_with_foreign_legacy_config_creates_nothing():
    result = run_preflight(profile="PC_PERSONALE", legacy_owner="PC_SEGRETERIA")
    assert result.returncode != 0
    assert created_paths == []

def test_common_script_never_selects_mismatched_legacy_config():
    assert resolve_data_dir("PC_PERSONALE", legacy_owner="PC_SEGRETERIA") == "ERROR"
~~~

- [ ] **Step 2: Run tests to confirm fallback is unsafe**

Run: py -3 -m pytest scripts/windows_bridge/tests/test_profile_installer.py scripts/windows_bridge/tests/test_runtime.py -v

Expected: FAIL for mismatched legacy behavior, or a documented policy skip with static assertions that fail first.

- [ ] **Step 3: Implement read-only preflight**

Resolve profile, interpreter, tunnel and all existing configurations before venv/pip/Creative installer calls. Preflight returns after report. Matching legacy config needs explicit identity-confirmed migration; foreign/unreadable legacy config is rejected.

- [ ] **Step 4: Run dry-run and static PowerShell tests**

Run: py -3 -m pytest scripts/windows_bridge/tests/test_profile_installer.py scripts/windows_bridge/tests/test_runtime.py -v

Expected: PASS, or explicitly documented Windows-policy skip with independent static assertions passing.

- [ ] **Step 5: Commit**

~~~bash
git add scripts/install_workstation_profile.ps1 scripts/windows_bridge/common.ps1 scripts/windows_bridge/tests/test_profile_installer.py scripts/windows_bridge/tests/test_runtime.py
git commit -m "fix: block cross-workstation legacy runtime reuse"
~~~

### Task 3: Make Creative install, switch and backup profile-aware

**Files:**
- Modify: scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/install_on_segreteria.ps1
- Modify: scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/switch_runtime_bridge.ps1
- Modify: scripts/backup/* or the discovered backup entry point
- Modify: scripts/windows_bridge/tests/test_profile_installer.py
- Create: scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_runtime_switch_paths.py

**Interfaces:**
- Consumes profile-derived CreativeConfigPath, active runtime config and explicit WorkstationId.
- Produces profile-owned Creative config, a switch preserving the configured absolute mcp_command, and a profile-specific backup archive path.

- [ ] **Step 1: Write failing path-isolation tests**

~~~python
def test_creative_install_writes_only_selected_profile_config():
    assert install_creative("PC_PERSONALE").config_path == personal_paths["creative_config"]

def test_switch_uses_runtime_mcp_command_not_py_alias_default():
    assert "py -3" not in switched_runtime_command
~~~

- [ ] **Step 2: Run focused tests to prove current paths fail**

Run: py -3 -m pytest scripts/windows_bridge/tests/test_profile_installer.py scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_runtime_switch_paths.py -v

Expected: FAIL because Creative config is shared and switch defaults to py -3.

- [ ] **Step 3: Thread profile-derived paths through scripts**

Keep a compatibility wrapper only if it cannot select a generic config. Switch reads the validated absolute command from active runtime config. Backup resolves current profile, not a hard-coded local-app-data file.

- [ ] **Step 4: Run workstation suite**

Run: py -3 -m pytest scripts/windows_bridge/tests scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03/tests/test_runtime_switch_paths.py -v

Expected: PASS; profiles demonstrate disjoint config and backup paths.

- [ ] **Step 5: Commit**

~~~bash
git add scripts/experiments/ARPHE_MCP_BRIDGE_CREATIVE_03 scripts/backup scripts/windows_bridge/tests
git commit -m "fix: isolate Creative runtime operations by profile"
~~~

### Task 4: Document deploy and pending PC gates

**Files:**
- Modify: docs/10_WINDOWS_BRIDGE_AUTOSTART_AND_WORKSTATIONS.md
- Modify: docs/14_PERSONAL_PC_BRIDGE_INSTALLATION.md
- Modify: docs/15_MULTI_WORKSTATION_ISOLATION_AND_2026-09-21_INCIDENT.md
- Modify: validation/validation-ledger.json
- Modify: CHANGELOG.md

**Interfaces:**
- Consumes preflight/apply commands and profile paths.
- Produces PC-specific READ/SAFE WRITE checklist records with evidence fields; never fabricated results.

- [ ] **Step 1: Document preflight, apply and rollback**

Provide one command path per PC, expected identity report, profile-specific backup location and rule that only the current PC task may restart.

- [ ] **Step 2: Add PENDING validation records**

Create one record per PC rollout gate with fields for future live output and Resolve evidence. Do not mark PASS from automated tests.

- [ ] **Step 3: Validate ledger/documentation references**

Run: py -3 scripts/validate_validation_ledger.py --ledger validation/validation-ledger.json --current-state CURRENT_STATE.md

Expected: PASS; no test result is implied.

- [ ] **Step 4: Commit**

~~~bash
git add docs/10_WINDOWS_BRIDGE_AUTOSTART_AND_WORKSTATIONS.md docs/14_PERSONAL_PC_BRIDGE_INSTALLATION.md docs/15_MULTI_WORKSTATION_ISOLATION_AND_2026-09-21_INCIDENT.md validation/validation-ledger.json CHANGELOG.md
git commit -m "docs: require workstation-specific deployment gates"
~~~

