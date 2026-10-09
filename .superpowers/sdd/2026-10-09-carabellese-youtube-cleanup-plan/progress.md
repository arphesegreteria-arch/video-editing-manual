# SDD ledger — plan: docs/superpowers/plans/2026-10-09-carabellese-youtube-cleanup-plan.md

Setup: isolated worktree `codex/carabellese-cleanup`; baseline bridge 282 PASS / 1 SKIP, Windows 55 PASS / 1 SKIP.

Setup Ruling: Bash-only SDD helper scripts are unavailable on this Windows host — use the identical `.superpowers/sdd/<plan>/` workspace and manually extract/read task briefs — cost if wrong: bookkeeping automation only; TDD, commits and verification remain unchanged.

Pre-flight Task 1→2: contract version and isolated config paths match the job-store inputs.
Pre-flight Task 1+3→4: contract and managed transcript outputs match analysis inputs; transcription retains `ARPHE_TRANSCRIPT_V1`.
Pre-flight Task 2+4→5: job store and validated candidate records provide marker inputs.
Pre-flight Task 2+4+5→6: review consumes persisted jobs, anchored candidates and owned marker evidence.
Pre-flight Task 6→7: canonical review fingerprint gates checkpoint creation.
Pre-flight Task 6+7→8: reviewed job and verified checkpoint match application preconditions.
Pre-flight Task 7+8→9: checkpoint manifest and apply journal provide recovery inputs.
Pre-flight Task 2+6+9→10: only CLOSED jobs with decisions feed workflow-specific learning.
Pre-flight Task 1–10→11: public tools are thin wrappers over the exact produced interfaces.
Pre-flight Task 1+10+11→12: installer preserves the same capability and isolated state paths exposed publicly.
Pre-flight Task 1–12→13: rollout checks the produced capability, tools, installer, validator and ledger.
Pre-flight Task 1–13→14: final review covers the complete branch against spec and Review Focus.

Task 1: complete (commits 693e78a..90690cd, tests: bridge 286 PASS / 1 SKIP; Windows 55 PASS / 1 SKIP)
Task 2: complete (commits 90690cd..ba40154, tests: bridge 296 PASS / 1 SKIP; Windows 55 PASS / 1 SKIP)
Task 3: complete (commits ba40154..436c11e, tests: CLI help PASS; bridge 305 PASS / 1 SKIP; Windows 55 PASS / 1 SKIP)
Task 4: complete (commits 436c11e..256aad3, tests: focused 15 PASS; bridge 313 PASS / 1 SKIP; Windows 55 PASS / 1 SKIP)
Task 5: Ruling: `carabellese_marker_specs(job, contract)` cannot derive Resolve frames from second-based candidates under `frame_rate_mode=source` — keep specs in seconds and convert only inside `mark_carabellese_review` using validated timeline FPS, then persist actual frames — cost if wrong: internal marker-spec records need one schema adjustment; no timeline edit or public workflow default changes.
Task 5: complete (commits 256aad3..46bd3b8, tests: focused 5 PASS; bridge 318 PASS / 1 SKIP; Windows 55 PASS / 1 SKIP)
Task 6: Ruling: the planned review signature has no transcript input but `MODIFY` must revalidate transcript anchors — add required keyword-only `transcript` to `submit_carabellese_review` — cost if wrong: one internal call-site parameter must be removed or supplied differently in Task 11.
Task 6: complete (commits 46bd3b8..b3a3aa3, tests: focused 6 PASS; bridge 324 PASS / 1 SKIP; Windows 55 PASS / 1 SKIP)
Task 7: complete (commits b3a3aa3..6b258a9, tests: focused 6 PASS; bridge 330 PASS / 1 SKIP; Windows 55 PASS / 1 SKIP)
Task 8: complete (commits 6b258a9..68cfeb4, tests: focused 5 PASS including 9-case zero-write matrix; bridge 335 PASS / 1 SKIP; Windows 55 PASS / 1 SKIP)
Task 9: Ruling: a verified DRT restore can assign a new Resolve timeline identity — permit `FAILED_RECOVERABLE→CHECKPOINTED` and identity replacement only when the latest operation binds the previous and restored identities to a verified checkpoint restore — cost if wrong: recovery remains blocked; no ordinary job transition or identity mutation is relaxed.
Task 9: complete (base 68cfeb4, tests: focused apply+recovery 8 PASS; bridge 338 PASS / 1 SKIP; Windows 55 PASS / 1 SKIP; `git diff --check` PASS with line-ending warnings only)
Task 10: Ruling: reuse the append-only Carabellese technical journal with a distinct outcome schema and one-way hashed sample tokens, preserving apply/recovery events while excluding raw job/candidate IDs from learning records — cost if wrong: learning journal storage can be split into a dedicated configured path without changing proposal/overlay schemas.
Task 10: complete (base 0f7fb3c, tests: focused 3 PASS; bridge 341 PASS / 1 SKIP; Windows 55 PASS / 1 SKIP; `git diff --check` PASS)
Task 11: Ruling: the public apply tool owns the REVIEWED→CHECKPOINTED step so no separate checkpoint mutation is exposed to chat; all Resolve wrappers check the default-off gate before runtime access and destructive apply/recovery tools are explicitly annotated — cost if wrong: checkpoint export can be separated later without widening generic Resolve access.
Task 11: complete (base f2f0301, tests: focused tools+safety 37 PASS including fake-runtime prepare/idempotence; bridge 346 PASS / 1 SKIP; Windows 55 PASS / 1 SKIP; `git diff --check` PASS with line-ending warnings only)
