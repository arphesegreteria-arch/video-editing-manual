# PC_PERSONALE Resolve 21.2 hardening deployment

- Deployment date: 2026-11-08 (Europe/Rome)
- Source branch: `codex/resolve-21-2-hardening-20261108`
- Source commit: `3667d56`
- Source base: `origin/main` at `15d697d`
- Runtime root: `C:\ARPHE\MCP\ARPHE_MCP_BRIDGE_CREATIVE_03`
- Backup: `C:\ARPHE\MCP\ARPHE_MCP_BRIDGE_CREATIVE_03\deploy-backups\2026-11-08-resolve21-hardening-3667d56`

## Explicit production overlay

| File | Previous SHA-256 | Deployed SHA-256 |
| --- | --- | --- |
| `bridge/format_contract.py` | `08EED5236C8FD67D50E967EAF330E2709109DEC42F34FB5A1097677E11FA35A9` | `55A87060E2E11CCAF27FD0A6AD28C81C86C9B2FFF01D707DE25FA66BCB08CF4C` |
| `bridge/native_transcription21.py` | `3F0325038715EDB498F7CA4EEB8C0044AE82C38FFFA36675BFC54148425C4812` | `21C4909EA707F58CDF9BA17F4F72274B3E45B991A9DA64CF0E98FE5C17F88C4C` |

`bridge/server.py` and `bridge/tool_catalog.py` were deliberately not overwritten: the installed runtime contains later workstation-specific tools. The existing `resolve21_compat.py` and `review_export21.py` already matched the source adapter hashes exactly.

## Verification evidence

- Clean-worktree suite: 661 tests, 4 expected skips, zero failures.
- Staged runtime import: 128 tools; all four Resolve 21 tools present; transcription schema V2.
- Installed-runtime smoke: playback write/read-back returned `30`; schema `ARPHE_RESOLVE_NATIVE_TRANSCRIPTION_V2`; 128 tools loaded.
- Restart log: new supervisor and tunnel started at 2026-11-08 21:06 local time; MCP stdio command relaunched from the installed runtime.
- Live read-only checks: `ping` reports `PC_PERSONALE`; Resolve reports `21.2.0.6`; compatibility state is `READY`; frame export, thumbnail export, native transcription, and native subtitles APIs are present.
- No export, transcription, save, or timeline mutation was invoked during rollout.

## Residual operational note

The repository copy of `status_bridge.ps1`/`common.ps1` still reads a legacy non-workstation state path, while the installed scheduled task uses the per-workstation configuration. This made its PID field stale even though the task, new processes, log, `/readyz`, and MCP calls were healthy. The status-tool realignment is intentionally left for a separate runtime-maintenance change.
