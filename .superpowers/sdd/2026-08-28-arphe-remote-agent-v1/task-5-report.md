# Task 5 report: guarded Resolve Studio manager

## Implementation

- Added `ResolveManager`, consuming `ResolveConfig` and exposing `get_process_state()`, `launch_if_allowed()`, `connect(timeout_seconds)`, `get_status()`, and `require_test_project()`.
- Process detection normalizes Windows paths and recognizes only the exact local configured executable. A different `Resolve.exe` is reported as `wrong_executable`; a job cannot supply an executable path anywhere in the API.
- Launching is disabled unless `ResolveConfig.launch_if_needed` permits it, always uses the local configured path, and declines to launch when a different Resolve executable is already detected.
- Connection waits in 250 ms bounded increments for a configured Resolve process and its scripting API. The Resolve scripting import, process discovery, launcher, clock, and sleeper are injectable, so the tests never access a live process or API.
- Status distinguishes `not_running`, `running_unavailable`, `connected`, and `wrong_executable`; the connected status exposes only active project, active timeline, and Resolve version.
- `require_test_project()` raises unless the current project is exactly `ARPHE_TEST` or begins with configured `ARPHE_AUDIT_`.

## TDD evidence

All test commands used the external remote-agent virtual environment, `PYTHONDONTWRITEBYTECODE=1`, and `-p no:cacheprovider`.

### RED

The initial focused command was:

```powershell
& '..\remote-agent-venv\Scripts\python.exe' -m pytest -p no:cacheprovider tests/remote_agent/test_resolve_manager.py -v
```

It failed during collection as expected with `ModuleNotFoundError: No module named 'scripts.remote_agent.resolve_manager'`.

The later safety test for a wrong existing `Resolve.exe` was added before its implementation. Its focused run failed as expected because `launch_if_allowed()` invoked the injected launcher.

### GREEN

- Focused manager suite: `13 passed in 0.12s`.
- Full remote-agent suite: `123 passed, 1 skipped in 0.53s`.
- `git diff --check` was run without errors.

The skip is the existing privilege-gated real Windows symlink test. No Resolve process, scripting API, or launcher was invoked by any unit test.

## Files changed

- `scripts/remote_agent/resolve_manager.py`
- `tests/remote_agent/test_resolve_manager.py`
- `.superpowers/sdd/2026-08-28-arphe-remote-agent-v1/task-5-report.md`

## Concerns

- The production scripting module is intentionally loaded lazily; validating its installation and Resolve Studio external-scripting preferences belongs to the HOME_DEV live checklist, not this fake-adapter unit suite.

---

## Audit fix round 1 (2026-08-29)

### Findings resolved

1. A synchronous Resolve scripting call could exceed `connect()`'s timeout. It now runs through a bounded, daemonized call adapter that owns no manager state; timed-out and late results are discarded. This prevents a late scripting response from reconnecting a stopped/timed-out lifecycle while avoiding a shutdown-blocking worker.
2. Connection waits now calculate the remaining duration once immediately before sleeping, return if it is non-positive, and only sleep the smaller of the poll interval and that remaining duration.
3. Process discovery now scans all same-named Resolve executables before accepting a configured match. Any simultaneous wrong `Resolve.exe` fails closed. Status and destructive-project checks revalidate the configured process identity and invalidate any cached API object if the process disappears, is replaced, or becomes ambiguous.

### TDD evidence

All commands used the external remote-agent virtual environment, `PYTHONDONTWRITEBYTECODE=1`, and `-p no:cacheprovider`.

RED tests were added before the implementation. The focused failures demonstrated:

- a simultaneous configured and wrong `Resolve.exe` returned `RUNNING`;
- the old clock sampling exhausted the scripted clock before it could protect the sleep boundary;
- a blocking connector left the `connect()` caller alive beyond its timeout;
- a late connector remained active past deadline; and
- a cached connection still authorized project access after process replacement.

After the implementation, the five new checks passed: `5 passed, 13 deselected in 0.27s`.

Focused manager suite: `18 passed in 0.27s`.

Full remote-agent suite: `128 passed, 1 skipped in 0.71s`. The skip is the existing privilege-gated Windows symlink test.

### Remaining concern

Python cannot forcefully terminate arbitrary in-process third-party code. The production adapter deliberately uses a daemon worker that cannot mutate manager state, and it discards results after the timeout; this keeps the agent lifecycle safe. A live HOME_DEV test should still confirm the installed Resolve scripting call returns normally under the expected Studio setup.

---

## Audit fix round 2 (2026-08-29)

### Findings resolved

The manager now preserves the configured Resolve process identity as `(pid, create_time)` from `psutil`. It accepts exactly one matching configured executable, rejects two matching processes as ambiguous, and rejects any same-named executable at a different path. Before returning connected status or permitting destructive project access, it observes the process again and invalidates the cached scripting API if the identity is absent or has changed. A connection result is also accepted only if the same identity remains present after the scripting call.

### TDD evidence

RED: the duplicate-configured-process test observed `RUNNING`; the same-path PID/create-time replacement test kept the old API session `connected`.

GREEN: the two new identity tests passed (`2 passed, 18 deselected in 0.11s`).

Focused manager suite: `20 passed in 0.30s`.

Full remote-agent suite: `130 passed, 1 skipped in 0.66s`. The skip is the existing privilege-gated Windows symlink test.

### Remaining concern

Process metadata must remain available from the local process adapter. The production `psutil` adapter explicitly requests executable path, PID, and creation time; a custom adapter that omits PID/create-time is treated as insufficient to retain a cached live API session.
