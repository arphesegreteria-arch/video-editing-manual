# Artifact Hygiene and Seven-Day Quarantine Design

Date: 2026-10-08

Status: approved in conversation; implementation plan pending review of this document.

## Purpose

Prevent bridge-owned technical files from accumulating on either workstation without scanning or
cleaning arbitrary user folders. The first release covers only file artefacts that the bridge can
identify and own. It does not delete Resolve projects or timelines and does not manage project
backups.

Success means that diagnostics, technical previews, terminal render staging, temporary reports and
rotated logs have an explicit lifecycle, a recoverable seven-day quarantine and an auditable purge,
while source media, editorial work, delivery files and unknown existing files remain protected.

## Decisions already made

- The first release is intentionally limited to bridge-owned files.
- Quarantine lasts seven complete days.
- Expired registered technical artefacts may be purged automatically.
- Resolve projects and timelines always require separate human approval and are out of scope here.
- The bridge must never scan Desktop, Documents or other generic user folders for cleanup.
- `PC_PERSONALE` and `PC_SEGRETERIA` use the same code and policy version but keep independent
  registries, quarantine locations, runs and evidence.
- Unknown legacy files are reported as `UNCLASSIFIED`; they are never moved or deleted
  automatically.
- A future Resolve-backup extension will retain at least the latest three verified `.drp` files per
  project and every verified `.drp` from the last 30 days before applying the seven-day quarantine.

## Scope and protection classes

Every known artefact has one of three protection classes:

1. `PROTECTED`: never eligible for automatic quarantine or purge.
2. `DISPOSABLE`: eligible according to its category and recorded lifecycle state.
3. `UNCLASSIFIED`: visible in inspection reports but never changed automatically.

The essential release recognises these `DISPOSABLE` categories:

| Category | Active retention before quarantine | Eligibility condition |
| --- | ---: | --- |
| `DIAGNOSTIC_CAPTURE` | 24 hours | Capture call completed successfully |
| `TEMP_REPORT` | 24 hours | Producing operation reached a terminal state |
| `TECHNICAL_PREVIEW` | 7 days | Explicitly registered as technical/non-publishable |
| `RENDER_STAGING` | 24 hours | Batch is `VERIFIED`, `CANCELLED` or `FAILED_PREPARE` |
| `FAILED_RENDER_STAGING` | 7 days | Batch is `FAILED_RENDER` or `FAILED_VERIFY` |
| `ROTATED_LOG` | 7 days | File is not the active log and rotation completed |

Render batches in `DRAFT`, `CONFIRMED`, `PREPARED`, `APPROVED`, `RENDERING` or `VERIFYING` are
protected regardless of age. A retry does not make the previous failed staging disposable until
its diagnostic retention has elapsed.

The following are always `PROTECTED` in this release:

- source media and audio;
- graphic-kit assets and other approved assets;
- repositories and worktrees;
- runtime configuration, secrets, state, audit ledgers and the active log;
- editorial review renders, masters and every file under a `publishable` delivery class;
- any file not created or adopted through the artefact registry;
- Resolve projects, timelines, databases and project backups.

Names alone do not prove ownership. An `ARPHE_` prefix or location inside an allowed root is
insufficient to make a file disposable.

## Architecture

### 1. Versioned retention policy

A versioned policy file in the Creative bridge defines the recognised categories, active-retention
duration, quarantine duration and allowed terminal states. Policy entries may only narrow the
essential scope. They cannot make a protected delivery class disposable or add arbitrary filesystem
roots.

The policy is common source code. The runtime records the policy version used for every decision so
that later changes do not rewrite history.

### 2. Per-workstation artefact registry

Each workstation profile owns a registry stored beside its Creative state, written atomically. A
record contains:

- schema and policy version;
- opaque `artifact_id`;
- `workstation_id` and producer action;
- category and protection class;
- canonical path and managed-root identifier;
- size and SHA-256 digest when the file exists;
- creation time, eligibility time and last state change;
- optional non-sensitive `workflow_id` and render `batch_id`;
- lifecycle state: `ACTIVE`, `ELIGIBLE`, `QUARANTINED`, `RESTORED`, `PURGED` or `ERROR`;
- quarantine time, purge deadline and original path when applicable;
- last error code without file contents, review text or secrets.

Registry updates use temporary-file plus atomic replace. A corrupt registry disables all maintenance,
preserves files and exposes a degraded health/report state; it is never silently recreated as empty.

### 3. Managed roots

The implementation accepts only explicit roots from the active workstation profile:

- the Creative render root for diagnostics, previews and staging;
- the profile-owned runtime/log root for temporary reports and rotated logs.

Each managed root has its own hidden bridge quarantine directory on the same volume. Keeping the
quarantine on the same volume makes a normal quarantine operation an atomic move rather than a
copy-and-delete. Resolved paths must remain beneath their declared root. Symlinks, junction escapes,
reparse-point escapes and a quarantine directory nested inside another candidate are rejected.

The generic Desktop, Documents, Downloads, OneDrive and user-profile roots are not managed roots.

### 4. Inventory and legacy discovery

Inventory combines registry records with a shallow, allowlisted inspection of the exact producer
directories (`diagnostics`, `staging`, configured preview output and rotated-log patterns). It does
not recursively traverse unrelated content under the render root.

Registered files are evaluated against policy. Files found in producer directories but absent from
the registry are returned as `UNCLASSIFIED`, with path redacted to a managed-root-relative value,
size and modification age. They require a future explicit adoption decision; the essential release
cannot adopt or delete them.

### 5. Quarantine, restore and purge

Quarantine revalidates the record immediately before mutation:

1. category remains disposable;
2. lifecycle or batch state remains terminal;
3. retention has elapsed;
4. path remains inside the same managed root;
5. file size and digest still match the registered artefact;
6. no active operation holds the artefact or its parent staging directory.

The file or fully owned staging directory is moved to a collision-free quarantine location. The
registry stores both paths, digest, move time and purge deadline. A partial directory is never
quarantined: every contained file must be registered to the same terminal batch or the directory is
reported for manual review.

Restore is allowed until purge. It rechecks the digest and restores to the original path. If the
original path exists, restore stops with `RESTORE_COLLISION`; it does not overwrite, rename or merge
automatically.

Purge runs only after seven complete days in `QUARANTINED`. It revalidates quarantine containment and
digest, deletes that exact item and records a tombstone containing metadata but no sensitive content.
An item with missing or changed quarantine content becomes `ERROR` and is not purged automatically.

### 6. Lazy maintenance

No second Windows Scheduled Task is introduced. After the Creative runtime reaches ready state, it
may run one maintenance cycle if the profile has no successful or attempted cycle in the preceding
24 hours. Concurrent calls share a profile-specific lock, so at most one cycle runs.

Maintenance failure does not prevent normal read/edit/render operations. It sets a visible degraded
maintenance status and keeps all uncertain artefacts untouched. Active render locks and non-terminal
batches prevent staging maintenance.

An explicit maintenance action may request a cycle earlier, subject to the same lock and safety
checks. It does not broaden the managed roots or eligible categories.

### 7. Public tool surface and reporting

The bridge exposes three narrow operations:

- `inspect_artifact_hygiene`: read-only summary and candidate inventory;
- `run_artifact_maintenance`: run the policy-bound cycle now;
- `restore_quarantined_artifact(artifact_id)`: restore one exact item.

There is no generic filesystem list, move or delete tool. There is no path parameter for purge.

Reports group counts and bytes by category and state and show:

- protected, eligible, quarantined, restored, purged, errored and unclassified totals;
- space currently held in quarantine and space purged in the latest cycle;
- next purge time;
- policy version and named workstation;
- warnings for registry degradation, collisions, changed files or active batches.

Chat responses use managed-root-relative names and opaque IDs. They do not disclose review text,
secrets, arbitrary absolute paths or file contents.

## Producer integration

Registration occurs only after a producer has successfully created and closed an artefact:

- diagnostic capture registers each exported JPEG;
- render preparation associates staging with the render batch;
- media verification changes staging eligibility only after the batch transition is persisted;
- technical preview producers must label output as technical/non-publishable explicitly;
- report writers register completed temporary reports;
- log rotation registers the closed rotated file, never the active log.

The existing 64-file diagnostic pruner must stop deleting JPEGs directly. The runtime log handler
must likewise stop discarding its oldest rotated file outside the registry. Both producers hand
closed artefacts to the common lifecycle so quarantine and audit cannot be bypassed.

A producer failure before registration performs its existing scoped rollback. Orphan files left by a
crash are found as `UNCLASSIFIED` and remain untouched.

## Failure handling

- Missing registry: create an empty registry only on first installation, never over an expected
  existing file.
- Corrupt registry or policy: disable maintenance and report the error.
- Changed file after registration: mark `ERROR`; do not quarantine or purge.
- Move failure: leave the original in place and preserve the previous registry state.
- Registry-write failure after a move: use a small write-ahead operation record to reconcile the
  exact source and destination on the next cycle; never guess from filenames.
- Restore collision: preserve both the quarantined item and current destination.
- Purge failure: keep the item quarantined and retry no sooner than the next cycle.
- Clock moving backwards: calculate eligibility from stored UTC timestamps and never shorten an
  already recorded deadline.
- Unsupported workstation/profile: refuse maintenance before filesystem access.

## Verification strategy

Implementation follows test-driven development. Automated tests use temporary directories and fake
time and cover:

- category retention and the full seven-day quarantine boundary;
- automatic protection of publishable/master/source/config/secret/state files;
- terminal versus active render-batch staging;
- unknown legacy files reported but untouched;
- path traversal, symlink/junction escape and quarantine recursion rejection;
- digest or size drift before quarantine, restore and purge;
- atomic registry writes, corrupt-registry fail-closed behaviour and write-ahead reconciliation;
- restore success and destination collision;
- purge of exactly one expired registered item;
- workstation separation and once-per-24-hours maintenance locking;
- reports that omit absolute paths and sensitive content;
- existing diagnostic, render, runtime and Windows suites.

The first live gate runs only on `PC_PERSONALE` using newly created disposable files. It proves
inventory, quarantine, restore and re-quarantine without shortening production retention. The purge
gate remains time-bound until that exact quarantined artefact has spent seven complete days in
quarantine; automated tests with a fake clock prove the boundary immediately. `PC_SEGRETERIA` stays
`PENDING` until its own independent rollout and disposable-file gate.

## Token and scope checkpoint

The intended implementation remains in the previously agreed essential range of approximately
20,000–35,000 model tokens for code, tests, documentation and first-PC validation. If implementation
requires Resolve project/timeline work, a generic disk scanner, a new Windows task or materially new
producer refactors, work stops and the scope/cost is reported before proceeding.

## Out of scope

- deletion, quarantine, archive or restore of Resolve projects and timelines;
- `.drp` export, verification, retention and restore;
- media-inclusive `.dra` archives;
- generic disk cleanup or scanning user folders;
- automatic adoption of legacy/unregistered files;
- deletion of source media, assets, review renders, masters or publishable deliveries;
- cloud storage or cross-workstation quarantine;
- user-selectable arbitrary retention paths or shell/file-manager operations.
