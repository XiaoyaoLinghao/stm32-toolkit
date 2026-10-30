# v1.3.6 tool evidence repair and publication

Date: 2026-10-30. Accepted base: 37f69ca4acc2b879d4227a099384241ec39080f4.
The user approved the diagnosis/plan and explicitly requested implementation,
version 1.3.6, release builds/upload, and integration into master.
Primary Codex owns specification, orchestration, complete-diff review and acceptance.
Local Claude Code CLI uses its existing configured route (previously deepseek-v4.1-flash[1m])
for all implementation/test/document changes and delegated verification.
No provider/model/auth or permission override. No active PR. Authorized remote scope:
non-force integration of this reviewed change into master, new v1.3.6 tag and formal
v1.3.6 Release with verified assets. No old tag/asset deletion/replacement.

## Approved behavior
1. Preserve the existing bounded ARMCC Cortex-M4 FPU2 hard inference, selector checks,
literal ABI precedence and all blockers. Baseline binary ABI remains unverified.
The existing conversion-report floatAbi object is the authority for reported migration
provenance, not proof of binary equivalence. Expose that same object in destination
PLAN/APPLY and include its warning in both warnings lists.
2. Build identities and receipts carry optional floatAbi provenance when available.
Capture only the fixed project-local conversion report, through bounded no-redirect
reading, with its source path and SHA256. Validate structure, declared/inferred
semantics, and selected ABI/FPU against the actual project model. Never manufacture
an inferred origin from a manifest hard value. Missing evidence remains readable;
missing/malformed/mismatched evidence must be honestly unavailable with bounded
warnings rather than presented as verified. No source or compiler flag changes.
Preserve the existing identity hash algorithm: new present provenance participates
normally; old absent optional fields retain their original identity calculation.
Typed identity round-trip and closed schema/record validation must preserve the
new optional evidence and continue rejecting unrelated fields. Evidence is captured
with the build and must not be silently relabelled during incremental reuse.
3. Every newly written build-result includes the executing toolkit version,
for debug/release and success/failure receipts. Older records lacking the optional
field remain readable; existing current-version firmware admission is not relaxed.
No legacy runtime/generatedBy/cross-version identity adaptation is added.
4. Keep debug receipt/log at the historical migration root and release in arm-release.
Both are preset-owned; context continues selecting debug. Ordinary switching in
both directions never requires clean. Invalid canonical evidence still fails closed.
5. Backend programming telemetry is nullable. null means unreported, never zero.
verifiedBytes is exact readback extent, not bytes physically programmed. Preserve
the existing pyOCD 0.46.0 high-level programming call; do not parse human logs, invent
sector counts, introspect private SDK state or change hardware behavior for telemetry.
Test null and real values through the existing backend-to-receipt path.
6. Advance active product/package/version authorities to 1.3.6 and update affected
tests/current documentation. Preserve all historical release claims. Link published
v1.3.5 explicitly; document frozen package wording. New v1.3.6 notes distinguish
software evidence from hardware/user validation and become published only after
the release is observed. Do not expand the historical compatibility allowlists.

## Non-goals and constraints
No user Keil/migration project edits, firmware configuration, new hardware access,
retry/recovery, frequency changes, authorization/lease/identity-contract relaxation,
static launch configuration, debug backend/target inference, installations into any
existing runtime, CI or dispatch framework work. Keep 100 kHz/SYSRESETREQ/fail-stop,
UTF-8 JSON, field-level CLI diagnostics, include guard/header encoding, WFI choices,
debugConfiguration/followUp and Git-optional content identity.

## Evidence
Read current standard procedure/checkpoint/referenced report before verification.
Primary independently reviews the complete accepted-base-to-CodeHead diff in a clean
tree. Claude verify calls use only exact prebound native PowerShell commands after
inventory and harmless smoke. No retries by default; retain failure/pending evidence.
Focused tests cover migration evidence and softfp, both preset receipts, schema-1/2
old/new shape, identity round-trip/hash, context/flash admission, invalid/redirected
report handling and telemetry null/value. Real synthetic GCC preset switching uses
only disposable fixtures. Run applicable offline Toolkit integration and version/
release/Monitor contracts; report measured coverage and retained limits separately.
Historical release-only coverage exceptions do not transfer automatically to 1.3.6.
No hardware PASS is inferred. Existing user v1.3.5 end-to-end success is user evidence,
not a fresh v1.3.6 run.

Freeze source; use existing official offline builder twice in separate clean trees,
compare all 13 asset names/lengths/SHA256 and run official extracted-bundle verification.
Do not alter current installation. Publish only the reviewed frozen source/artifacts,
read back master/tag/release and anonymously verify downloadable bytes. Do not expose
or read credentials; existing normal authenticated transports only. If a genuine
credential boundary or unmet release gate remains, retain the concrete candidate and
report the exact blocker without substitution or silent exception.
