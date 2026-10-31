# v1.3.6 README archive revision plan — 2026-10-31

Primary owns specification/plan/review/acceptance; local Claude owns bounded edits.
This records the run-local plan frozen before implementation. User requested correction
of published README status and explicitly selected revising v1.3.6 attachments and
checksums while preserving the tag. The subsequent single bounded preparation retry
was explicitly approved separately; original failures remain retained.

1. From frozen source b00cbc4edee191712dd6da7e1beb073ff4a74f28, use a clean isolated
   codex/v136-readme-docrev worktree. Claude edits only the two READMEs: published
   state, stable Latest URL, correct receiving guide, explicit revision/identity limits.
2. Primary reviews the complete diff in an independent clean exact-head tree and
   commits the docs source. Compare the new Git archive against the original public
   archive: exactly two changed files, identical member set and all other bytes.
3. Assemble two deterministic revisions using original release assets and existing
   release utility serialization. Preserve all wheels and nine unrelated assets.
   Update only source commit/hash, source ZIP, Windows ZIP and checksums; no schema change.
4. Separately delegate the existing official bundle verifier; Primary examines actual
   native evidence, exact source/wheel closure and synthetic same-version identity behavior.
5. Under explicit user authority replace exactly four Release attachments and annotate
   publication. Read back all13 metadata digests, anonymously download four changed
   assets, and inspect delivered README/manifest. Preserve tag and original evidence.
6. Merge reviewed README blobs into master. Adjust only the existing README test's
   checksum prohibition to apply to commands, then execute that single affected test.
   Record independent acceptance and perform the originally authorized normal master push.

No original projects/firmware, runtime installation, hardware operation, retries beyond
the explicitly approved preparation attempt, version bump, tag move, credentials,
permissions, provider/model changes or identity-contract adaptation are in scope.
