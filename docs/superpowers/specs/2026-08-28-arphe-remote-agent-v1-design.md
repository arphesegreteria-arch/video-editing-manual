# ARPHE Remote Agent V1 — Design — SUPERSEDED

## Status

**SUPERSEDED on 2026-09-01. DO NOT IMPLEMENT AS CURRENT PRODUCT DIRECTION.**

This document originally specified a visible Windows/Tkinter desktop application that polled a private GitHub job queue and controlled Resolve Studio.

That direction has been replaced.

## Current architecture

The product interface should be **ChatGPT**, with the local Windows component acting only as infrastructure:

`Segreteria -> ChatGPT -> custom MCP app -> Secure MCP Tunnel -> local ARPHE MCP Bridge -> DaVinci Resolve Studio API`

Definitive current document:

`docs/08_CHATGPT_MCP_RESOLVE_ARCHITECTURE.md`

Current capability status:

`docs/RESOLVE_STUDIO_CAPABILITIES.md`

## Why this design was superseded

A separate desktop UI would duplicate the conversational interface that the user actually wants. Current MCP capabilities make it plausible for ChatGPT itself to expose the operational workflow while a guarded local bridge performs deterministic work on the ARPHE PC.

The previous GitHub polling queue is therefore not the preferred ChatGPT-to-PC transport. Secure MCP Tunnel is the target transport for the local/private MCP server.

## Safety principles retained from the old design

These ideas remain useful and must survive in the MCP bridge:
- strict allowlist of actions;
- no arbitrary remote shell or Python execution;
- guarded local media folders and path validation;
- no access to unrelated/clinical folders;
- original Resolve timelines preserved;
- destructive operations isolated to explicit new/test timelines;
- structured local logs and sanitized errors;
- credentials never committed to the repository;
- clear failure/timeout behavior.

## Historical preservation

The detailed original specification remains available in Git history. This file intentionally stays in place as a tombstone so future sessions do not mistake the old `Approved direction` for the current architecture.
