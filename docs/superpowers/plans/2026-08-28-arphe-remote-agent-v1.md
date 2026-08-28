# ARPHE Remote Agent V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a manually launched Windows desktop agent that polls a private GitHub job queue only while visibly open, safely accesses configured media folders, controls local DaVinci Resolve Studio through approved handlers, and writes structured results back to GitHub.

**Architecture:** Separate the agent into strict models/configuration, lifecycle/UI, GitHub queue, local file broker, Resolve manager, and allowlisted handlers. All network activity is outbound HTTPS; jobs are declarative JSON; no arbitrary shell or remote Python is permitted. HOME_DEV is the first target and POLI_01 remains more restricted.

**Tech Stack:** Python 3.11, Tkinter/ttk, requests, pydantic, keyring, psutil, pytest, DaVinci Resolve Studio scripting API.

**Spec:** `docs/superpowers/specs/2026-08-28-arphe-remote-agent-v1-design.md`

## Global Constraints

- The agent polls GitHub only while the visible desktop application is open.
- Closing the application must leave no agent process, service, scheduled task, tray process, or further polling/heartbeat activity.
- No arbitrary shell, PowerShell, command prompt, Python source, executable path, or remote code may be supplied by a job.
- Jobs are strict schema-versioned JSON and actions must exist in the local allowlist.
- Local filesystem operations accept only configured aliases plus relative paths and must reject escapes/reparse-point traversal.
- Raw media and rendered videos stay local; GitHub receives only small JSON results, bounded logs, hashes and alias-relative paths.
- Secrets are stored through Windows Credential Manager and never in config, logs, results or Git.
- Destructive Resolve tests run only against `ARPHE_TEST` or the audit naming convention.
- `SYNC_APPROVED_CODE` is HOME_DEV-only in V1 and must fast-forward to an exact allowed commit from the configured repository.
- Long-form V4.3 work remains independent from this agent implementation.

---

### Task 1: Package skeleton, strict models and configuration

**Files:**
- Create: `scripts/remote_agent/requirements.txt`
- Create: `scripts/remote_agent/models.py`
- Create: `scripts/remote_agent/config.py`
- Create: `scripts/remote_agent/handler_registry.py`
- Create: `tests/remote_agent/test_models.py`
- Create: `tests/remote_agent/test_config.py`

**Interfaces:**
- Produces: `Job`, `JobStatus`, `JobResult`, `MachineHeartbeat`, `AgentConfig`, `FolderConfig`, `ResolveConfig`, `GitHubConfig`, `HandlerRegistry`.

- [ ] **Step 1: Write failing schema tests** covering valid job parsing, unknown-field rejection, invalid `job_id`, timeout outside `5..7200`, machine mismatch helper behavior, and result serialization with no secret fields.
- [ ] **Step 2: Run** `pytest tests/remote_agent/test_models.py -v` and confirm failure because models do not exist.
- [ ] **Step 3: Implement strict Pydantic models** with `extra='forbid'`, exact V1 status enums, `job_id` regex, UTC timestamps, and explicit `schema_version=1`.
- [ ] **Step 4: Write failing config tests** for machine ID, poll interval `10..300`, folder aliases, action allowlist and HOME_DEV/POLI_01 profile behavior.
- [ ] **Step 5: Implement `AgentConfig.load(path)`** with JSON config loading, strict validation and no secret/token field.
- [ ] **Step 6: Implement `HandlerRegistry`** with `register(action, schema, handler, idempotent=False)` and local-profile enforcement.
- [ ] **Step 7: Run** `pytest tests/remote_agent/test_models.py tests/remote_agent/test_config.py -v` and require all tests to pass.
- [ ] **Step 8: Commit** `feat: add remote agent models and config`.

---

### Task 2: Credential storage, logging and secret redaction

**Files:**
- Create: `scripts/remote_agent/credentials.py`
- Create: `scripts/remote_agent/logging_setup.py`
- Create: `tests/remote_agent/test_credentials.py`
- Create: `tests/remote_agent/test_logging.py`

**Interfaces:**
- Consumes: `AgentConfig`.
- Produces: `CredentialStore.get_token()`, `CredentialStore.set_token(token)`, `redact_secrets(text, secrets)`, `configure_logging(machine_id)`.

- [ ] **Step 1: Write failing tests** proving tokens are retrieved through an injectable keyring backend and never written into config objects.
- [ ] **Step 2: Implement `CredentialStore`** using service name `ARPHE Remote Agent` and account key `<machine_id>:github`.
- [ ] **Step 3: Write failing redaction tests** for raw token, authorization header and exception-string leakage.
- [ ] **Step 4: Implement centralized redaction and rotating logs** under `%LOCALAPPDATA%/ARPHE/RemoteAgent/logs`, max 5 MiB per file and 5 backups.
- [ ] **Step 5: Run** `pytest tests/remote_agent/test_credentials.py tests/remote_agent/test_logging.py -v`.
- [ ] **Step 6: Commit** `feat: secure remote agent credentials and logs`.

---

### Task 3: Safe local file broker

**Files:**
- Create: `scripts/remote_agent/file_broker.py`
- Create: `tests/remote_agent/test_file_broker.py`

**Interfaces:**
- Consumes: `FolderConfig`.
- Produces: `resolve(alias, relative_path) -> Path`, `list_media(alias, relative_dir)`, `find_media(alias, query)`, `hash_media(alias, relative_path)`, `copy_to_workspace(...)`.

- [ ] **Step 1: Write failing tests** for valid path resolution, `..` escape, absolute path rejection, drive/device-path rejection, case-insensitive Windows containment and fake reparse-point escape.
- [ ] **Step 2: Implement `FileBroker.resolve`** using `Path.resolve(strict=False)` plus Windows-aware normalized containment checks and explicit reparse/symlink rejection.
- [ ] **Step 3: Write failing tests** for media extension allowlist and alias-relative return values.
- [ ] **Step 4: Implement `list_media`, `find_media`, `hash_media` and `copy_to_workspace`** with deterministic sorting and SHA-256 streaming.
- [ ] **Step 5: Run** `pytest tests/remote_agent/test_file_broker.py -v`.
- [ ] **Step 6: Commit** `feat: add guarded local media broker`.

---

### Task 4: GitHub queue, compare-and-swap claim and heartbeat

**Files:**
- Create: `scripts/remote_agent/github_queue.py`
- Create: `tests/remote_agent/test_github_queue.py`

**Interfaces:**
- Consumes: `GitHubConfig`, token, `Job`, `JobResult`, `MachineHeartbeat`.
- Produces: `list_pending(machine_id)`, `claim(job, sha)`, `mark_running(...)`, `write_result(...)`, `write_log(...)`, `write_heartbeat(...)`.

- [ ] **Step 1: Write failing tests with a fake HTTP transport** for listing `jobs/`, parsing matching jobs, ignoring another target machine, and rejecting invalid JSON/schema before claim.
- [ ] **Step 2: Implement a small GitHub Contents API client** with explicit timeouts, redacted errors and no retries on validation failures.
- [ ] **Step 3: Write failing tests** for SHA conflict on claim, lease fields, stale lease behavior and non-retryable job handling.
- [ ] **Step 4: Implement compare-and-swap claim** by updating the job using its fetched blob SHA and treating HTTP 409/422 conflict as `ClaimConflict`.
- [ ] **Step 5: Implement result/log/heartbeat writers** with 256 KiB remote log cap and alias-relative output metadata only.
- [ ] **Step 6: Run** `pytest tests/remote_agent/test_github_queue.py -v`.
- [ ] **Step 7: Commit** `feat: add private GitHub job queue client`.

---

### Task 5: Resolve manager and safe live connection boundary

**Files:**
- Create: `scripts/remote_agent/resolve_manager.py`
- Create: `tests/remote_agent/test_resolve_manager.py`

**Interfaces:**
- Consumes: `ResolveConfig`.
- Produces: `get_process_state()`, `launch_if_allowed()`, `connect(timeout_seconds)`, `get_status()`, `require_test_project()`.

- [ ] **Step 1: Write failing tests with injected process/API adapters** for not-running, running-but-unavailable, connected, wrong executable and wrong project states.
- [ ] **Step 2: Implement process detection** against the exact configured Resolve executable and never a path supplied by a job.
- [ ] **Step 3: Implement optional launch** only from local config, then bounded wait for the Resolve scripting module/API.
- [ ] **Step 4: Implement `require_test_project()`** that refuses destructive handlers unless current project equals `ARPHE_TEST` or the configured audit prefix.
- [ ] **Step 5: Run** `pytest tests/remote_agent/test_resolve_manager.py -v`.
- [ ] **Step 6: Commit** `feat: add guarded Resolve Studio manager`.

---

### Task 6: Allowlisted handlers and end-to-end job runner

**Files:**
- Create: `scripts/remote_agent/job_runner.py`
- Create: `scripts/remote_agent/handlers/__init__.py`
- Create: `scripts/remote_agent/handlers/agent_status.py`
- Create: `scripts/remote_agent/handlers/media.py`
- Create: `scripts/remote_agent/handlers/capability_audit.py`
- Create: `scripts/remote_agent/handlers/tracking_probe.py`
- Create: `scripts/remote_agent/handlers/render_probe.py`
- Create: `scripts/remote_agent/handlers/sync_code.py`
- Create: `tests/remote_agent/test_job_runner.py`
- Create: `tests/remote_agent/test_handlers.py`

**Interfaces:**
- Consumes: registry, queue, file broker, Resolve manager.
- Produces: one-job-at-a-time execution with cooperative cancellation and structured `JobResult`.

- [ ] **Step 1: Write failing tests** for `PING`, `GET_STATUS`, target-machine enforcement and action-profile rejection.
- [ ] **Step 2: Implement status handlers** with sanitized environment/Resolve metadata.
- [ ] **Step 3: Write failing tests** for `LIST_MEDIA`, `FIND_MEDIA`, `HASH_MEDIA`, `COPY_TO_WORKSPACE` and `IMPORT_MEDIA` path/schema enforcement.
- [ ] **Step 4: Implement media handlers** using only `FileBroker` and `ResolveManager` interfaces.
- [ ] **Step 5: Implement `RUN_CAPABILITY_AUDIT`, `RUN_TRACKING_PROBE`, `RUN_RENDER_PROBE` adapters** that call the existing/new audit modules only after `require_test_project()`.
- [ ] **Step 6: Write failing tests for `SYNC_APPROVED_CODE`** covering HOME_DEV-only profile, clean worktree requirement, exact repository identity, exact commit SHA and fast-forward-only update.
- [ ] **Step 7: Implement controlled code sync** without arbitrary command text from the job; command arguments are constructed locally from validated configuration and SHA.
- [ ] **Step 8: Implement `JobRunner.run_once()`** with `CLAIMED -> RUNNING -> SUCCEEDED/FAILED/ABORTED`, timeout and cancellation.
- [ ] **Step 9: Run** `pytest tests/remote_agent/test_job_runner.py tests/remote_agent/test_handlers.py -v`.
- [ ] **Step 10: Commit** `feat: add allowlisted remote agent handlers`.

---

### Task 7: Visible lifecycle, polling loop and Tkinter UI

**Files:**
- Create: `scripts/remote_agent/lifecycle.py`
- Create: `scripts/remote_agent/app.py`
- Create: `scripts/remote_agent/start_agent.py`
- Create: `scripts/remote_agent/ui/__init__.py`
- Create: `scripts/remote_agent/ui/main_window.py`
- Create: `tests/remote_agent/test_ui_lifecycle.py`

**Interfaces:**
- Consumes: queue, runner, Resolve manager, config.
- Produces: visible app with `ONLINE`, `PAUSED`, `RUNNING`, `ERROR`, `OFFLINE`; pause, stop-after-current, close-and-abort/finish semantics.

- [ ] **Step 1: Write failing lifecycle tests using a fake scheduler** proving polling starts only after `start()`, stops after `shutdown()`, and never fires after shutdown.
- [ ] **Step 2: Implement lifecycle controller** with a worker thread, 30-second default polling, one active job and 60-second heartbeat.
- [ ] **Step 3: Write failing close-behavior tests** for idle immediate exit, finish-current-then-close and abort-current-then-close.
- [ ] **Step 4: Implement lifecycle close/pause state machine** and single-instance lock.
- [ ] **Step 5: Implement Tkinter window** showing machine ID, agent state, Resolve state, allowed folder aliases, current/last job and recent logs, with `Pause jobs`, `Stop after current job`, and normal window close actions.
- [ ] **Step 6: Add a testable shutdown hook** and prove the worker thread is joined before process exit.
- [ ] **Step 7: Run** `pytest tests/remote_agent/test_ui_lifecycle.py -v`.
- [ ] **Step 8: Commit** `feat: add visible remote agent lifecycle and UI`.

---

### Task 8: Windows setup, first-run configuration and uninstall

**Files:**
- Create: `scripts/remote_agent/windows/setup_windows.ps1`
- Create: `scripts/remote_agent/windows/start_agent.bat`
- Create: `scripts/remote_agent/windows/uninstall_agent.ps1`
- Create: `scripts/remote_agent/config.example.json`
- Create: `scripts/remote_agent/README.md`

**Interfaces:**
- Produces: repeatable HOME_DEV installation without service/scheduled task/startup entry.

- [ ] **Step 1: Write `requirements.txt` with pinned compatible versions** for requests, pydantic, keyring, psutil and pytest/dev extras documented separately.
- [ ] **Step 2: Implement `setup_windows.ps1`** to verify Python 3.11+, create `.venv`, install dependencies, optionally create `D:\ARPHE\Incoming`, `TestMedia`, `Workspace`, `Exports`, copy config example, prompt for machine ID/runtime repo, launch first-run token setup, and create a desktop shortcut only.
- [ ] **Step 3: Implement `start_agent.bat`** to activate the dedicated environment and run `start_agent.py` with the local config path.
- [ ] **Step 4: Implement `uninstall_agent.ps1`** to remove shortcut/venv/application config while preserving media/exports/logs by default.
- [ ] **Step 5: Document exact HOME_DEV install steps, private repo requirements, token permissions, Resolve scripting prerequisites and troubleshooting in README.**
- [ ] **Step 6: Verify by code review that no setup path creates a Windows service, scheduled task or startup entry.**
- [ ] **Step 7: Commit** `docs: add Windows setup for ARPHE Remote Agent`.

---

### Task 9: Verification suite and HOME_DEV release gate

**Files:**
- Modify: `scripts/remote_agent/README.md`
- Create: `tests/remote_agent/test_integration_flow.py`
- Modify: `CURRENT_STATE.md`

**Interfaces:**
- Produces: a release candidate ready for manual installation on HOME_DEV.

- [ ] **Step 1: Add fake integration tests** for full `PENDING -> CLAIMED -> RUNNING -> SUCCEEDED`, target mismatch, claim conflict, GitHub outage/backoff, Resolve unavailable, timeout and aborted close flow.
- [ ] **Step 2: Run all automated tests** with `pytest tests/remote_agent -v` and require zero failures.
- [ ] **Step 3: Run a static secret scan** across `scripts/remote_agent` and tests for token-like literals, `Authorization:` dumps and accidental config secrets; document the exact grep/PowerShell command in README.
- [ ] **Step 4: Perform HOME_DEV manual test checklist:** open app, `PING`, `LIST_MEDIA`, Resolve connect, capability audit on `ARPHE_TEST`, render probe, pause, close, and confirm no process/heartbeat remains.
- [ ] **Step 5: Record observed limitations and exact tested versions** in `CURRENT_STATE.md`.
- [ ] **Step 6: Tag the build in documentation as `REMOTE_AGENT_V1_HOME_DEV_TESTED` only after the live checklist passes; do not call POLI_01 production-ready yet.**
- [ ] **Step 7: Commit** `test: verify ARPHE Remote Agent V1 on HOME_DEV`.

## Self-review summary

This plan covers visible-only lifecycle, GitHub private queue, strict allowlist, file fetch/search under configured roots, credential storage, Resolve launch/connect, capability/tracking/render probes, controlled code sync, Windows installation, shutdown/no-background verification and the restricted POLI_01 profile. No task requires arbitrary remote command execution or uploading source/render media to GitHub.

## Execution choice

1. **Subagent-Driven (recommended):** implement one task at a time with a fresh review gate between tasks.
2. **Inline Execution:** execute the plan in this session in batches with checkpoints.
