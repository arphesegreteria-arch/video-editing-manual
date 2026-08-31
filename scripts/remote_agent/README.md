# ARPHE Remote Agent (Windows / HOME_DEV)

The ARPHE Remote Agent is a manually launched, visible desktop application for
`HOME_DEV`. It polls the private GitHub job queue only while its window is
open. It creates **no service, no scheduled task, no startup entry, no tray
agent and no background process**. Closing the application stops polling and
heartbeats.

## Install on HOME_DEV

1. Clone the approved private repository onto the Windows workstation. Keep the
   checkout in a stable location; do not run setup from a temporary download.
2. Install Python 3.11 or newer from [python.org](https://www.python.org/) and
   ensure the Python Launcher (`py`) is available.
3. Open PowerShell in the checkout and run:

   ```powershell
   Set-ExecutionPolicy -Scope Process Bypass
   .\scripts\remote_agent\windows\setup_windows.ps1 -CreateDefaultFolders
   ```

   The script creates `scripts\remote_agent\.venv`, installs the pinned runtime
   dependencies, prompts for the machine/repository/folder settings on the
   initial run, and creates one desktop shortcut. Existing `config.json` is
   deliberately preserved on repeat runs.
4. When asked, paste a fine-grained GitHub token into the Python hidden prompt.
   It is stored only in **Windows Credential Manager** as `ARPHE Remote Agent`
   / `<machine_id>:github`; it is never written to `config.json`, the command
   line, Git, or the remote job result.
5. Start the app only through the **ARPHE Remote Agent** desktop shortcut. The
   launcher keeps its console visible if setup or startup fails.

Development/test-only dependencies are in `requirements-dev.txt`; production
setup installs `requirements.txt` only.

## Private GitHub queue

Use a private repository and a fine-grained personal access token restricted to
that repository. Grant only the minimum **Contents: Read and write** permission
needed for queue jobs, results, bounded logs, and heartbeats. Do not use an
owner-wide token and never put a token in a configuration file. `HOME_DEV` is
the only V1 profile permitted to enable the separately configured
`SYNC_APPROVED_CODE` action.

## DaVinci Resolve Studio prerequisites

Install DaVinci Resolve **Studio** at the configured, absolute executable path.
Enable the local Fusion/Resolve scripting access required by the Studio API and
verify that the Python scripting module can connect before using live handlers.
Destructive probes must run only in `ARPHE_TEST` or an `ARPHE_AUDIT_` project.

## Everyday operation

The open window is the lifetime boundary. It shows the machine ID, state,
Resolve status, local aliases, job activity and recent logs. Use **Pause jobs**
to stop claiming work, **Stop after current job** to drain a running job, and
the normal close choices to finish or abort the current job. Once closed, there
is no polling, heartbeat, service, scheduled task, startup entry, tray agent,
or background worker left behind.

## Uninstall

Run this from the trusted checkout:

```powershell
.\scripts\remote_agent\windows\uninstall_agent.ps1
```

It removes only the matching desktop shortcut, the dedicated `.venv`, and the
agent `config.json` after verifying their exact paths. It preserves media,
exports, and local logs by default. It does not delete `D:\ARPHE` folders.

## Troubleshooting

- **Python not found:** install Python 3.11+ and rerun setup from PowerShell.
- **Token missing:** rerun `setup_windows.ps1` and choose token setup; use the
  hidden prompt rather than putting the token in a file.
- **Resolve unavailable:** confirm the absolute `resolve.executable_path`, run
  Resolve Studio once, and verify its scripting configuration.
- **Config rejected:** restore from `config.example.json` and use absolute
  folder and Resolve paths. Do not add secret fields.
- **App stops immediately:** keep the launcher console open and inspect the
  redacted local logs under `%LOCALAPPDATA%\ARPHE\RemoteAgent\logs`.

## Static secret scan

Before a release candidate, run this exact PowerShell command from the
repository root. It looks for accidental token literals, authorization dumps,
and secret-like config keys; matches must be investigated, not blindly
suppressed.

```powershell
Get-ChildItem scripts\remote_agent,tests\remote_agent -Recurse -File |
  Where-Object { $_.FullName -notmatch '\\__pycache__\\' } |
  Select-String -Pattern 'github_pat_[A-Za-z0-9_]+|gh[pousr]_[A-Za-z0-9_]+|Authorization\s*:|"(?:token|secret|password|authorization|credential|api[_-]?key)"\s*:'
```

Expected matches still need review. Synthetic token fixtures in the redaction
tests and the deliberate `Authorization` header construction inside the queue
client are normal; an unexpected match in config, README examples, runtime
results, or non-test literals is not.

## HOME_DEV manual release checklist

Run this on the real HOME_DEV workstation before promoting the branch:

1. Open the visible app from the desktop shortcut and confirm the window stays open.
2. Submit `PING` and confirm a `SUCCEEDED` result with sanitized machine metadata.
3. Submit `LIST_MEDIA` against a configured alias and confirm alias-relative paths only.
4. Connect to Resolve Studio and confirm the UI shows a connected status.
5. Run `RUN_CAPABILITY_AUDIT` only inside `ARPHE_TEST` or an `ARPHE_AUDIT_` project.
6. Run `RUN_RENDER_PROBE` only inside `ARPHE_TEST` or an `ARPHE_AUDIT_` project.
7. Pause jobs, then confirm heartbeats continue while new claims stop.
8. Close the app and confirm no process, polling, or heartbeat remains afterward.

Only after that live checklist passes may the build be tagged in documentation
as `REMOTE_AGENT_V1_HOME_DEV_TESTED`. Until then, this branch is a release
candidate only. `POLI_01` remains intentionally more restricted and is not
production-ready in V1.
