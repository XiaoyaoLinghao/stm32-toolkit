# B1: optional Git in evidence, Host/Target and controlled debug

This refines section B of 2026-10-26-gcc-content-identity-slices.md and the accepted GCC delivery contract. Owner/reviewer: primary; implementer: local Claude Code CLI with existing settings. Accepted A base: `f73ce706ac17d7c198153825dd3667f2ac2fc131`, final tested code `9e9cd9efba5e1c2b1acc4ca68b8cdd8b3eb8ed4a`. Branch: `codex/gcc-content-evidence`; no PR or remote authorization. Offline only; no originals, real hardware, installed runtime, release/version or remote writes.

## Identity contract

Keep the existing Git form byte-for-byte on serialization and decoding: full Git SHA and strict bool, no new keys emitted. Add one explicit closed snapshot form: git_commit/git_dirty (or existing camelCase aliases) are null; source_baseline is input-snapshot-v1 and git_evidence is the exact bounded unavailable record already emitted by build. Missing pair, mixed Git/snapshot fields, null-only legacy, numeric booleans and unknown keys fail. Preserve immutable records and canonical hash validation. Update both evidence JSON schema copies with oneOf forms; keep legacy envelope bytes/digests readable. No blanket permissiveness or version churn is needed for this additive explicitly discriminated form.

For the generic authorization field revision, retain the recorded Git SHA for legacy identities. For snapshots use the explicitly namespaced content revision input-snapshot-v1:<inputSnapshotSha256>. This is a source revision identifier, never a Git commit. Do not store it in git_commit/gitHead fields. Bind it to the actual snapshot and pair when validating Target authorization records; both current and prepared forms must match. Reuse a small shared provenance helper if needed, not repeated coercions.

## Producers and consumers

EvidenceIdentity and EvidenceIdentityContext support the two forms and Context.bind preserves them. Host discover/run obtains optional Git evidence using existing collect_build_git_evidence, so missing Git/unborn HEAD is not a failure. Target workflow carries the admitted firmware's snapshot pair to identities, prepare/run/replay and compares both form and content. Preserve the Target v1/v2 wire protocol: host-side source identity is not a change to firmware frames. New snapshot prepared records have a strictly closed field set (require input_snapshot_sha256 and the pair, null git_dirty, namespaced revision); legacy record forms and existing hashes remain readable and unchanged. No missing snapshot fallback to zero digest, False or str(None).

Controlled debug/fault authorization uses the same source revision helper so a valid snapshot binding can prepare authorized halt/read operations through the existing lifecycle. Authorization, target/probe matching, nonce/expiry/one-use, readback, finite timeout and cleanup stay unchanged. Acceptance recovery producers that currently fabricate zero Git SHA on Git failure must instead emit the same explicit snapshot form. Keep fake historical fixtures readable without inventing Git in new records.

## Allowed scope and verification

Evidence model/schema copies; testing_workflows.py; testing/target.py; hardware_workflows.py only source revision projection; acceptance/recovery_workflows.py only optional Git identity production; a small shared provenance helper; focused related tests/new test_content_evidence_workflows.py. Monitor, analysis/diagnostic serialization and continuation consumers are B2, not claimed complete here. Report any necessary extra file before changing it.

Author writes tests with no-Git/unborn Host discovery and run; snapshot Target prepare -> consume -> fake transport result/evidence replay; snapshot controlled debug authorization; legacy canonical evidence/authorization bytes or golden digests unchanged; source/ELF/build/target/probe mismatch, mixed/downgraded pair, stale input and replay tampering rejected before effects. Test missing Git cannot synthesize clean/zero commit. Coordinator freezes code and supplies exact PowerShell verification commands. Primary independently reviews complete diff in a clean exact-head worktree, then executes representative integration/negative tests. Physical hardware and user IDE checks are not claimed.

## Review clarifications before dispatch

The new snapshot form requires a real input snapshot, including recovery producers. If input enumeration fails, report the existing typed input error; do not claim the all-zero placeholder is an input-snapshot-v1 baseline. This does not authorize redesigning pre-build attempt placeholders for build/ELF fields. Unexpected Git collector exceptions must not be silently converted to availability failure. Reuse collect_build_git_evidence's bounded classification.

Existing legacy Target defaults are retained only for decoding the accepted legacy form. Snapshot bindings require all snapshot fields explicitly and may not use the old zero/False defaults. Include both Target wire protocol versions in snapshot tests. Keep transport frames, authorization lifetimes and stop/cleanup rules unchanged.
