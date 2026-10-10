# Astra review remediation design

## Purpose

Close the defects found in the independent review of `ce76b19` before any
Control Plane rollout. The result must keep the four specialized workflow
registries authoritative while making their common envelope safe under
concurrent MCP requests, interruption, target replacement and multi-step
Vertical Social execution.

## Scope and constraints

- Work only in an isolated branch. Do not install, enable, or invoke Resolve
  on `PC_SEGRETERIA`.
- `CAP_WORKFLOW_CONTROL_PLANE` remains `false` in shipped profiles.
- The common delivery action remains `not_available` until a native workflow
  supplies verified delivery evidence.
- Existing jobs must remain readable; no migration or deletion is allowed.
- All changes use deterministic local storage and existing typed native
  executors. There is no natural-language executor.

## Design

### Local transactions and interrupted work

`WorkflowJobStore` gains a path-scoped re-entrant lock shared by all store
instances in the bridge process. Each create, binding lookup/create, read /
revision check / save transition is executed under that lock. This matches the
single runtime process enforced by the workstation supervisor and prevents
parallel MCP worker threads from losing registry records.

Before a typed native call, the envelope persists `EXECUTING` with the exact
operation key in its evidence. A later advance that finds `EXECUTING` does not
blindly rerun it: it marks the envelope `FAILED_RECOVERABLE` and exposes
`RESUME`. The subsequent resume uses the native workflow's existing
idempotent/recovery proof. This handles a process stop before or after a
native write without pretending the envelope can know whether a killed process
completed its last operation.

### Provenance and approval binding

The native digest represents the actual executable batch. For branded
longform, it hashes the proposal fingerprint together with the native approval
payload (`approved_ids` and `modified`) and source/profile/timeline bindings.
Changing a decision therefore makes the common approval stale.

The common target receives normalized native provenance at preparation:
project name, timeline name, timeline identity when available, and source or
timeline fingerprint when exposed by the native record. Native binding checks
every populated field. Immediately before a Resolve write the server reads
project/timeline identity and validates it against the stored target. Vertical
Social additionally recomputes its source-timeline fingerprint before CUT.
A matching name alone never authorizes replacement media.

### Vertical Social adapter

The adapter reads both the native plan and its workflow metadata, so its card
knows approval, picture lock and the next pending action. One shared
`provisional_timeline_name(plan_id)` function is used by CUT creation and all
later effects; it has a deterministic full-ID form. A `BLOCKED` Podcast or
Carabellese job goes through its guarded native resume path when the card says
`RESUME`.

### Resolve serialization and installation

Every public operation which selects a project/timeline or mutates Resolve
holds `RESOLVE_ACCESS_LOCK` across runtime acquisition, selection and native
call. This prevents an older primitive from changing current context between
Control Plane validation and execution.

The Creative installer copies `branded_longform_contract.json` and provisions
the control-plane registry path for an existing or fresh profile while
preserving feature flag values. Its clean-install test verifies all contracts
the bridge imports are present.

### Validation

Tests first reproduce each review finding: threaded registry races,
interrupted `EXECUTING`, altered branded approval, same-name replacement
target, generated Vertical plan CUT-to-effect, adapter cards, blocked resume,
legacy timeline switch serialization, and clean installer assets. Unit tests
run with the personal venv, Windows tests with Python 3.12. A personal native
gate follows only after all suites are green; it uses the disposable target,
temporary flags and restores context. `PC_SEGRETERIA` remains pending.
