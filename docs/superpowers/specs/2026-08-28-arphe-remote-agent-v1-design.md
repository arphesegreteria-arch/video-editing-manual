# ARPHE Remote Agent V1 - Design

## Status

Approved direction, written specification for final review before implementation.

## Goal

Build a Windows desktop application that is started and stopped manually and, only while visibly open, receives authorized jobs from a private GitHub repository, accesses configured local media folders, controls a local DaVinci Resolve Studio instance, and writes structured results back to the private repository.

The first deployment targets are:

- `HOME_DEV`: Alessio's personal gaming PC, used for development, capability audits and experimental Resolve tests.
- `POLI_01`: a Windows PC in the poliambulatorio, initially used for controlled tests and later for validated production workflows.

## Core user experience

1. Alessio opens **ARPHE Remote Agent** on the target Windows PC.
2. The window clearly shows:
   - machine identity;
   - agent state (`OFFLINE`, `ONLINE`, `PAUSED`, `RUNNING`, `ERROR`);
   - Resolve state (`NOT RUNNING`, `STARTING`, `CONNECTED`, `ERROR`);
   - allowed local folders;
   - current/last job;
   - recent log messages.
3. When the agent is online, it polls the private GitHub queue every 30 seconds.
4. A matching job is claimed, validated and executed locally.
5. The result and a bounded log are written back to GitHub.
6. Closing the application stops polling and all network activity from the agent. No Windows service, tray-only process or automatic startup is installed in V1.

The app must never appear to be closed while continuing to poll in the background.

## Explicit non-goals for V1

- No arbitrary remote shell, PowerShell or command prompt execution.
- No arbitrary Python source supplied inside a job.
- No direct exposure of Resolve, Python or a local HTTP port to the public Internet.
- No uploading raw source videos or rendered videos to the GitHub job repository.
- No unattended operation when the application is closed, the PC is off, Windows is logged out, or the PC is asleep.
- No access to clinical, administrative or patient-data folders.
- No polished MSI installer in the first build; V1 uses a guided Windows setup script and desktop shortcut. Packaging can follow after the live workflow is validated.

## High-level architecture

```text
Private GitHub job repository
          |
          | outbound HTTPS polling only
          v
ARPHE Remote Agent (visible Windows app)
  - GUI and lifecycle controller
  - GitHub queue client
  - job schema validator
  - action allowlist / handler registry
  - local file broker
  - Resolve process/connection manager
  - result and log writer
          |
          v
DaVinci Resolve Studio + configured ARPHE folders
```

The PC opens outbound HTTPS connections to GitHub. No inbound firewall rule or router port forwarding is required.

## Repository separation

### Public/source repository

`arphesegreteria-arch/video-editing-manual`

Contains:

- agent source code;
- tests;
- setup scripts;
- Resolve handlers;
- documentation;
- validated editing primitives.

### Private/runtime repository

Recommended name: `arphesegreteria-arch/arphe-remote-jobs`

Contains only:

- small JSON job documents;
- small JSON result documents;
- bounded text logs;
- machine heartbeat/status documents.

It must not contain source media, rendered videos, patient information, credentials or Resolve project databases.

## Authentication

V1 uses a fine-grained GitHub personal access token restricted to the private runtime repository and limited to the minimum repository-content permissions needed to read jobs and write claims/results.

The token is:

- entered during first-run setup;
- stored in Windows Credential Manager through the application;
- never written to `config.json`, logs, Git commits or result files;
- redacted from exception messages.

Each machine has a unique configured `machine_id`, such as `HOME_DEV` or `POLI_01`.

## Application lifecycle

### Startup

On launch the application:

1. acquires a single-instance lock for the configured machine;
2. loads non-secret configuration;
3. retrieves the GitHub token from Windows Credential Manager;
4. validates private repository access;
5. checks configured folder roots;
6. checks whether Resolve is running and attempts an API connection;
7. starts polling only after the UI is visible and setup validation succeeds.

### Normal operation

- Poll interval: 30 seconds by default, configurable from 10 to 300 seconds.
- One job is executed at a time per machine.
- The UI remains responsive while work runs on a worker thread.
- `Pause jobs` stops claiming new work but does not hide the app.
- `Stop after current job` completes the active job and goes offline.

### Closing

If no job is running, closing the window immediately stops polling and exits.

If a job is running, the app asks:

- **Finish current job, then close**; or
- **Abort job and close**.

An aborted job is reported as `ABORTED`; the app must not silently leave it in `RUNNING`.

No background process remains after application exit.

## Queue model

The private repository uses stable files instead of moving files between folders.

```text
jobs/<job_id>.json
results/<job_id>.json
logs/<job_id>.log
machines/<machine_id>.json
```

### Job state transitions

```text
PENDING -> CLAIMED -> RUNNING -> SUCCEEDED
                              -> FAILED
                              -> ABORTED
```

A job is claimed by updating the existing job document with its current GitHub blob SHA. The GitHub Contents API SHA requirement acts as compare-and-swap: a second agent attempting to claim the same version receives a conflict and must not execute it.

Each claim includes:

- `claimed_by`;
- `claimed_at`;
- `lease_expires_at`;
- `attempt`.

A stale lease can be retried only when the job explicitly has `retryable: true` and the handler declares the operation idempotent or performs its own cleanup.

## Job schema

Every job must conform to schema version `1`.

```json
{
  "schema_version": 1,
  "job_id": "audit-home-001",
  "target_machine": "HOME_DEV",
  "action": "RUN_CAPABILITY_AUDIT",
  "created_at": "2026-08-28T00:00:00Z",
  "requested_by": "arphe",
  "retryable": false,
  "timeout_seconds": 900,
  "parameters": {
    "project_name": "ARPHE_TEST"
  }
}
```

Validation rules:

- `job_id` matches `^[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}$` and matches the filename.
- `target_machine` must equal the local configured machine ID.
- `action` must exist in the local handler registry and be enabled in the local profile.
- `timeout_seconds` is between 5 and 7200 seconds.
- unknown top-level fields are rejected in schema V1.
- handler parameters are validated against the handler-specific schema before the job is claimed.

## V1 action allowlist

### Agent and environment

- `PING`: returns agent, OS, Python, application and configuration metadata without secrets.
- `GET_STATUS`: returns Resolve state, active project/timeline names and allowed folder aliases.
- `RUN_CAPABILITY_AUDIT`: executes the safe Resolve Studio capability audit against `ARPHE_TEST`.

### Local media

- `LIST_MEDIA`: lists supported media files below an allowed folder alias and relative subdirectory.
- `FIND_MEDIA`: searches filenames and selected metadata below an allowed folder alias.
- `HASH_MEDIA`: computes size and SHA-256 for selected files.
- `COPY_TO_WORKSPACE`: copies selected media from one allowed alias to the configured workspace alias.
- `IMPORT_MEDIA`: imports selected allowed media into the configured Resolve test project/bin.

### Resolve tests

- `RUN_TRACKING_PROBE`: runs the controlled tracking probe on selected test media.
- `RUN_RENDER_PROBE`: creates and executes a short disposable render to the configured exports alias.

### Controlled code synchronization

- `SYNC_APPROVED_CODE`: available only on machines whose local profile explicitly enables it, initially `HOME_DEV` only.

This action may fast-forward the local checkout of `arphesegreteria-arch/video-editing-manual` to an exact commit SHA on an allowed branch. It may not fetch code from another repository, run a supplied command or switch to an uncommitted working tree. The agent verifies:

- repository identity;
- clean working tree;
- requested commit exists in the configured remote;
- update is fast-forward from the current revision;
- requested commit SHA exactly matches the job;
- agent restart is required before new code is used.

`SYNC_APPROVED_CODE` is disabled on `POLI_01` until the update mechanism itself is validated.

## Local folder broker

Configuration maps friendly aliases to absolute Windows paths:

```json
{
  "folders": {
    "incoming": "D:\\ARPHE\\Incoming",
    "test_media": "D:\\ARPHE\\TestMedia",
    "workspace": "D:\\ARPHE\\Workspace",
    "exports": "D:\\ARPHE\\Exports"
  }
}
```

Jobs may reference only an alias plus a relative path. They may not submit an absolute path.

Before every operation the file broker:

1. resolves the candidate path;
2. rejects `..`, device paths and unsupported URI/path forms;
3. verifies the final path remains inside the configured root using Windows-aware path comparison;
4. rejects symlink/reparse-point escapes from the configured root;
5. applies handler-specific file-extension and size limits;
6. records the touched path as an alias-relative path in the audit log.

The initial allowed media extensions are:

`.mov`, `.mp4`, `.m4v`, `.wav`, `.mp3`, `.aif`, `.aiff`, `.jpg`, `.jpeg`, `.png`, `.tif`, `.tiff`.

The agent configuration and setup guide must instruct that these folders contain only media intended for ARPHE editing/testing and no patient or clinical documents.

## Resolve integration

The agent uses the installed Resolve Studio scripting module and the external scripting interface.

The Resolve manager can:

- detect the configured Resolve executable;
- report whether Resolve is running;
- optionally launch only the exact configured Resolve executable when a Resolve job arrives;
- wait for the scripting API to become available with a bounded timeout;
- connect to the Project Manager/current project;
- refuse destructive test actions unless the configured project is exactly `ARPHE_TEST` or matches the audit-only naming convention;
- report the active project/timeline and Resolve version.

V1 never opens a generic executable path supplied by a remote job.

## Machine profiles

Configuration contains a local action allowlist per machine.

### `HOME_DEV`

May enable all V1 actions, including `SYNC_APPROVED_CODE`, because it is the experimental development node.

### `POLI_01`

Initially enables:

- `PING`;
- `GET_STATUS`;
- `LIST_MEDIA`;
- `FIND_MEDIA`;
- `HASH_MEDIA`;
- `COPY_TO_WORKSPACE`;
- `IMPORT_MEDIA` into `ARPHE_TEST`;
- validated audit/test handlers.

It does not enable `SYNC_APPROVED_CODE` until that path passes its own repeatable validation.

The profile is local configuration and cannot be widened by a remote job.

## Logging and results

### Local logs

The app writes rotating local logs under its application data directory. Logs include:

- timestamp;
- machine ID;
- job ID;
- state transitions;
- handler name;
- allowed alias-relative paths touched;
- Resolve version/project/timeline;
- duration;
- sanitized exception information.

Secrets and full token/header values are never logged.

### GitHub result

Each completed job writes a JSON result with:

- schema version;
- job ID and machine ID;
- final status;
- start/end timestamps and duration;
- action;
- structured output;
- warnings;
- sanitized error type/message when applicable;
- local output paths expressed only as alias-relative paths;
- hashes/sizes for created output files when useful;
- agent version and source commit SHA.

The uploaded text log is capped at 256 KiB. Larger local logs are truncated for GitHub with a clear marker while remaining complete on the PC.

Raw media and rendered video stay local in the configured folders.

## Heartbeat

While online, the app updates `machines/<machine_id>.json` every 60 seconds with:

- online/paused/running state;
- last heartbeat time;
- agent version/commit;
- Resolve connection state and version;
- current job ID, if any;
- free space for configured workspace/exports roots;
- no usernames, tokens or unrelated file paths.

When the app exits cleanly it writes `state: OFFLINE`. A missing/stale heartbeat is treated as offline.

## Failure handling

- GitHub unavailable: remain open, show `OFFLINE - GitHub unavailable`, use exponential backoff capped at 5 minutes, and do not execute unclaimed work.
- Invalid job: do not claim it; write a rejection result only when the agent can do so without altering another agent's valid claim.
- Resolve unavailable: optionally launch configured Resolve, wait up to the handler timeout, then fail with a clear diagnostic.
- Handler timeout: request cooperative cancellation, mark `FAILED_TIMEOUT`, and leave detailed local diagnostics.
- App crash: the lease eventually expires; retry occurs only for explicitly retryable, safe jobs.
- Disk full or output-path error: stop before render/import when preflight detects insufficient capacity.
- Partial Resolve mutation: handlers must use the `ARPHE_TEST` project/timeline and document cleanup/recovery in their result.

## Concurrency

- One application instance per machine profile.
- One active job per machine.
- Jobs targeted at another machine are ignored.
- Claim conflicts are normal and are handled without retrying the same stale document.

## Technology choices

- Python 3.11 on Windows 10/11.
- Tkinter/ttk for the visible V1 GUI to minimize dependencies and packaging risk.
- `requests` for GitHub HTTPS API calls.
- `pydantic` for strict job/config/result validation.
- `keyring` for Windows Credential Manager integration.
- standard `logging` with rotating file handlers.
- `pytest` for tests.
- `psutil` for Resolve process detection and machine status.
- DaVinci Resolve Studio scripting module loaded from the installed Resolve developer paths.

## Source layout

```text
scripts/remote_agent/
  README.md
  requirements.txt
  start_agent.py
  app.py
  config.py
  credentials.py
  lifecycle.py
  logging_setup.py
  models.py
  github_queue.py
  job_runner.py
  file_broker.py
  resolve_manager.py
  handler_registry.py
  handlers/
    __init__.py
    agent_status.py
    media.py
    capability_audit.py
    tracking_probe.py
    render_probe.py
    sync_code.py
  ui/
    __init__.py
    main_window.py
  windows/
    setup_windows.ps1
    start_agent.bat
    uninstall_agent.ps1

tests/remote_agent/
  test_models.py
  test_file_broker.py
  test_github_queue.py
  test_job_runner.py
  test_config.py
  test_credentials.py
  test_resolve_manager.py
  test_ui_lifecycle.py
```

## Installation experience for the first live test

The V1 repository provides `scripts/remote_agent/windows/setup_windows.ps1`.

The script:

1. confirms Windows and Python 3.11+;
2. creates a dedicated virtual environment;
3. installs pinned dependencies;
4. creates the four default ARPHE folders when requested;
5. launches the first-run configuration UI;
6. stores the GitHub token in Windows Credential Manager;
7. creates a desktop shortcut that runs `start_agent.bat`;
8. does not create a Windows service, scheduled task or startup item.

Uninstallation removes the shortcut and virtual environment but preserves local media, exports and logs unless the user explicitly selects their removal.

## Test strategy

### Unit tests without Resolve or GitHub

- strict schema validation;
- action/profile enforcement;
- safe path resolution and escape rejection;
- token redaction;
- state transitions;
- lease expiry rules;
- timeout/cancellation behavior;
- close/pause lifecycle;
- result/log size caps.

### Integration tests with fakes

- simulated GitHub list/fetch/claim/update conflicts;
- simulated stale lease and retry rules;
- simulated Resolve unavailable/starting/connected states;
- full `PENDING -> SUCCEEDED` and `PENDING -> FAILED` flows;
- no polling after lifecycle shutdown.

### Live tests

1. Install on `HOME_DEV`.
2. Open app and verify visible online/Resolve status.
3. Submit `PING` and inspect result.
4. Submit `LIST_MEDIA` against `test_media`.
5. Start/connect Resolve Studio and run the connectivity/capability probe only against `ARPHE_TEST`.
6. Close the app and prove no heartbeat, polling or process remains.
7. Reopen and run a controlled render probe.
8. Only after HOME_DEV passes, install the same release on `POLI_01` with the restricted profile.

## Acceptance criteria

V1 is accepted when all of the following are demonstrated:

1. The application is visibly open whenever it polls or runs jobs.
2. Closing it leaves no agent process and produces no further GitHub requests/heartbeats.
3. A private-repo `PING` job targeted at `HOME_DEV` is claimed once and produces a valid result.
4. A job targeted at `POLI_01` is ignored by `HOME_DEV`.
5. The agent lists/searches media only inside configured aliases and rejects path escapes.
6. The agent connects to or safely launches the configured Resolve Studio executable.
7. The capability audit runs only against `ARPHE_TEST` and returns structured results.
8. A short render probe writes to the configured exports root and returns path, size and hash without uploading the video.
9. The UI can pause new jobs and safely stop/close during an active job.
10. Credentials are stored outside the repository/config and are absent from logs/results.
11. `HOME_DEV` can optionally fast-forward to an exact approved source commit through the controlled synchronization handler; `POLI_01` cannot enable this remotely.

## Future extensions deliberately deferred

- signed release bundles and automatic production updates;
- encrypted cloud transfer of preview renders;
- direct natural-language job creation from an ARPHE interface;
- multi-job parallel execution;
- remote desktop/screen streaming;
- a packaged MSI installer;
- a managed backend replacing GitHub as the queue.
