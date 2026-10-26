# Monitor replay provenance core acceptance

Date: 2026-10-26. Verdict: **ACCEPTED_WITH_FIXES**, bounded to B2b1 replay contracts and publication. Accepted base: `962549287416a9101ccd9e263afad063e6c06260`. Final CodeHead before this report: `a1d30d328328e2cf1fa20814b2e8ce1cf6c969e9`. Governing [plan](../../../superpowers/plans/2026-10-26-gcc-monitor-replay.md). Primary owns specification, complete-diff review and acceptance; local Claude Code CLI with the existing configured route implemented all code/test changes. No remote, release, installation, original-project mutation or hardware operation occurred.

## Behavior and review

Existing v1/v2 replay bindings and references accept two closed forms: unchanged legacy Git records, or null Git fields with the complete input-snapshot discriminator and bounded unavailable-Git evidence. Projections, stored transcript identities, publication, reference hashes and authenticated readback retain the complete pair. References freeze copied evidence and reject partial/mixed/unknown forms. Legacy serialization omits both new keys, retaining canonical hash inputs. Existing lineage, physical-versus-replay labels, operation authority and publication checks remain in place.

Primary reviewed the complete base-to-final-head diff in a clean detached `gcc-delivery-review` checkout, including all product changes, new tests, old-test corrections and plan. One review defect was corrected: V2 direct construction previously validated only its serialized dictionary, which could hide evidence-only provenance under legacy Git. It now validates the original complete pair before serialization; new direct-construction and dataclass-replacement tests cover the bypass, including immutable evidence. No product implementation fallback was used.

## Evidence

All evidence lives under `D:/codex-tmp/gcc26`; exact argv, source hashes, heads and fresh JUnit are retained by the reviewed run-local runner. Actual edit inventories contained only Read/Edit/Write/Glob/Grep; verify inventories contained only native PowerShell and an actual matched smoke. Native successful PowerShell results omit numeric exits, which remain null; runner subprocess exits are separately recorded.

- `monitor-replay-global-core` (session `d4b04c06-86ae-4855-b92c-7e8cc6d9c6c8`) reached the cumulative turn limit after 36 successful native edits. Partial work and two non-mutating literal Edit errors remain recorded. No scope/permission/absent-tool issue occurred. Candidate `a71756f14b03bb4d9e648c3129635346edbe838b` preserved the work rather than restarting it.
- `monitor-replay-global-constructor` (session `b43ec7f5-b003-4465-8814-2bf1f6cf6b13`) completed the bounded reviewer correction. Product/test candidate: `d2c28a6ecba1eef68c5ca2a5a9504d5017770c1d`.
- `monitor-replay-global-verify` (session `24fce45f-fbaa-4acf-ba42-30ad76af57dd`) executed all four supplied native commands: `rpa` new replay **58 pass**, `rpb` existing replay **112 pass / 2 fail**, `rpc` risk/recovery **11 pass**, `rpd` Toolkit contract **129 pass**. Zero skips. The two failures were an old exact dataclass-field inventory and a legacy test hash computed from dataclass defaults instead of serialized wire fields. Original failures remain retained.
- `monitor-replay-global-fixtures` (session `fe0c6b5b-0b29-44d6-b8f9-9a0ba9fec499`) changed only `test_replay.py`: included the designed dataclass fields, added an independent exact old-wire-key assertion and computed the mutation fixture hash from the legacy wire form. All original positive/negative cases remain.
- Final native verification `monitor-replay-global-final-verify` (session `5dff24d4-9003-410d-83f0-b836360e09e3`), `rpe`: **114 pass**, zero skips, source unchanged at final CodeHead.
- Primary independently ran new replay `rpp` (**58 pass**) at the product candidate, then existing replay `rpq` (**114 pass**) at final CodeHead in the clean review checkout. These overlap author cases, not extra distinct coverage.

Accepted author coverage comprises **312 distinct cases** across the four selected groups. The unchanged-source 58/11/129 groups are explicitly reused from `d2c28a6e`; final changes were only the two old test expectations. This is not a final-head full repository matrix. Tests create synthetic recorded fixtures, including documents shaped as physical publications, but invoke no hardware transport; no result is physical acceptance.

## Remaining gates

B2b2 analysis, diagnostic, source-catalog and continuation consumers and their actual public MCP boundary remain unimplemented/unaccepted. Complete prepared-source guidance, combined independent GCC delivery and normal no-Git managed fake-flash journeys remain integration work. No released version includes these local changes merely because this bounded slice passed.
