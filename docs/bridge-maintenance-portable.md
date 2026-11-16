# Portable bridge maintenance package

The source baseline is the installed bridge, recorded by SHA256 in
`docs/bridge-maintenance-installed-baseline.json` and isolated in commit 8428874.
Functional maintenance commits follow it. Configuration, credentials, registries,
media, backups and project state are excluded from packages.

Build from the bridge source directory with Python 3.12:

```powershell
python scripts/build_portable_release.py --output C:/review-releases/bridge-maintenance
```

The output directory must be new. The deterministic manifest binds the source
revision, every deployed Python module, public contract, installer, and approved
per-file baseline hashes. The ZIP uses fixed timestamps. Keep the reported ZIP and
manifest hashes with the transfer record. No new per-video command is needed.

Use PowerShell 7 and the target workstation's existing `bridge_config.json`.
It supplies its workstation ID, Creative03 entrypoint and creative config path.
The installer verifies target/config ownership, all package hashes and baseline
drift. Dry run changes nothing. Unknown code, missing previously-existing files,
mixed new/old releases and incomplete installation journals fail closed.

```powershell
$package = 'C:/review-releases/bridge-maintenance'
$profile = 'C:/ARPHE/MCP/ARPHE_WINDOWS_BRIDGE_RUNTIME_V1/runtime-configs/PC_PERSONALE/bridge_config.json'
$installer = Join-Path $package 'payload/install_on_segreteria.ps1'
pwsh -NoProfile -File $installer -PackagePath $package -ProfilePath $profile -PackageMode DryRun
```

After independent review, stop the intended workstation's bridge with its existing
runtime scripts and explicit workstation ID. Keep it stopped throughout install
or rollback; this installer does not control runtime processes or capability flags.
Install requires a new backup path outside the bridge destination:

```powershell
pwsh -NoProfile -File $installer -PackagePath $package -ProfilePath $profile -PackageMode Install -BackupPath 'C:/ARPHE/releases/backups/maintenance-unique'
pwsh -NoProfile -File $installer -PackagePath $package -ProfilePath $profile -PackageMode DryRun
```

An identical complete installation reports already installed. Every changed file,
including the prior release manifest, has verified backup evidence. A failed write
leaves `.arphe-install-pending.json` and a receipt requiring rollback; do not start
the runtime with an incomplete transaction.

```powershell
pwsh -NoProfile -File $installer -PackagePath $package -ProfilePath $profile -PackageMode Rollback -BackupPath 'C:/ARPHE/releases/backups/maintenance-unique'
```

Rollback verifies current/new and backup hashes before restoring. Foreign drift
fails closed. Configurations, feature flags, local registries and credentials are
never copied or rewritten. If rollback fails, leave the runtime stopped and retain
the complete backup/receipt for recovery.

For PC_SEGRETERIA, transfer this same verified package and substitute only its own
profile path ending `runtime-configs/PC_SEGRETERIA/bridge_config.json`. Run DryRun
first. If its baseline is unknown, reconcile its source hashes for review; do not
override drift or copy PC_PERSONALE data. No operation on PC_SEGRETERIA was run.

After restart, use ping's additive `build_identity`: `manifest_valid` must be true
and `release_id` must match the package. Source/catalogue fingerprints derive from
actual installed files; effective policy also binds local purge/maintenance flags.
Inspect maintenance blockers and KEEP artifacts without running physical cleanup.

New transcription jobs require a real canonical project UUID. Extracted WAV files
are held until final WAV and completed transcript evidence agree. Only their own
active/failure hold is released; KEEP/dependencies survive. Eligible extraction
retention is 24 hours after observed completion, then 15 days in quarantine.
Original media, transcripts and manifests remain protected. Legacy files without
the new binding are diagnostic-only and are not automatically adopted.

Unknown APPLYING jobs remain recovery-required regardless of age. PREPARED-only
cancellation requires exact fingerprint, revision, permitted role and reason.
Malformed producer stores remain held with diagnostics, retried after one hour.
