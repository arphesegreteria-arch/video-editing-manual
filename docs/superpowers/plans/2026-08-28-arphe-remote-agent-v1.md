# ARPHE Remote Agent V1 Implementation Plan — SUPERSEDED

## Status

**SUPERSEDED on 2026-09-01. Do not execute the tasks in the old plan.**

The previous plan targeted:
- a manually opened Tkinter GUI;
- GitHub job polling/heartbeat;
- a private runtime jobs repository;
- local Resolve handlers behind that desktop agent.

The current product decision is different.

## Replacement architecture

`ChatGPT -> custom MCP app -> Secure MCP Tunnel -> local ARPHE MCP Bridge -> DaVinci Resolve Studio API`

Use these documents instead:
- `docs/08_CHATGPT_MCP_RESOLVE_ARCHITECTURE.md` — current architecture and validation gates;
- `docs/RESOLVE_STUDIO_CAPABILITIES.md` — live Studio API capability matrix;
- `docs/TRAINING_ROADMAP.md` — current validation order;
- `EXPERIMENT_LOG.md` — current experiment state.

## What remains reusable

Do not throw away the engineering safety ideas from the old plan. Reuse them where appropriate in the MCP bridge:
- strict typed schemas;
- handler/tool allowlist;
- safe local file broker;
- credential redaction;
- structured logging;
- bounded timeouts;
- original timeline protection;
- unit/integration tests with fakes before destructive live tests.

## New immediate implementation sequence

1. Finish `ARPHE_STUDIO_EXTERNAL_WRITE_TEST_02`.
2. Build the smallest read-only local MCP server: `ping` + `resolve_status`.
3. Test with the official MCP Inspector.
4. Configure Secure MCP Tunnel.
5. Connect a custom ChatGPT app and validate `ChatGPT -> MCP -> Resolve READ`.
6. If full MCP write is available and the external write probe passed, expose only `create_safe_working_timeline`.
7. Validate one harmless `ChatGPT -> MCP -> Resolve WRITE` operation.
8. Expand tool-by-tool: media listing, transcription, edit-plan application, captions, render, etc.

The detailed original task list is preserved in Git history only for historical reference.
