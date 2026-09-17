# T10 native register comparison with bounded relative alignment

## Authority and baseline

The user approved correction of the native numeric and independent-clock analysis blockers with “开始进行修正”. This specification freezes that bounded correction; it does not authorize deployment, new hardware, or remote actions. Accepted base: `6a8da073d8e79595acad21d5f2367c8393ac9597`. Primary owns design, orchestration and acceptance; one Luna/max owner implements product and tests; an independent reviewer reviews the complete diff. There is no primary product implementation exception.

Canonical integration is `D:\codex-tmp\stm32tk-integration`. Work for this slice stays under `D:\codex-tmp\t10n-0917`; retired workspace paths are not recreated. Deployed source remains `ee2152b497e62389a103ea4ff9ce2ebf92aae160` until separately authorized deployment.

## Runnable scenarios and non-goals

1. Compare the authenticated, already captured P3/P4 `GPIOE.ODR` windows using their original native register values and scheduled timestamps. An explicit bounded policy accommodates independent scheduling. The preserved windows must yield 300 valid pairs, zero exclusions, VALID/COMPLETED and changed=true with minimum_valid_pairs=297.
2. Reject invalid requests and exclude invalid numeric samples or ambiguous/unmatched positions without coercion, interpolation, sample reuse, timestamp edits, index-based pairing, or a lower pair threshold.
3. Preserve request/1 exact run-relative semantics and result/1 and result/2 bytes, digests, compatibility, identities and error behavior. Native support is explicitly opt-in through request/2, not a silent reinterpretation of old evidence.
4. On an isolated copy of real evidence, persist the new result, publish its bundle, complete Diagnostic verification, and read the final v3 checkpoint from a fresh process. Persisted readers must authenticate the actual request and recompute the new statistics, rejecting forged but self-consistent result hashes.

Non-goals: changing runtime sampling, backend, firmware, leases, hardware actions, CLI commands, UI, 100ms acceptance thresholds, old evidence or business records; acquiring another physical window; a generic diagnostic framework; packaging, deployment, push, T10/VS10-A acceptance based solely on a copied store.

## Versioned request and result contract

`stm32-monitor-analysis-request/1` retains its existing closed fields, `{type,value}` scalar rules and `alignment="run-relative"` implementation unchanged.

New `stm32-monitor-analysis-request/2` has the same base fields and exactly two additional fields:

- `scalar_policy="native-uint-register/1"`.
- `max_pairing_skew_ns`: exact integer, not bool, from 1 through 5,000,000 inclusive.

For request/2, `alignment="bounded-run-relative"`, `selector_kind="register"`, and both references must be authenticated physical Monitor references. The selector uses the existing exact Watch contract. Existing minimum_valid_pairs range and resource bounds remain. Replay reference input and other policies/extra fields are rejected. The complete canonical request, including both original references and all policy parameters, is covered by request_digest.

Request/2 produces `stm32-monitor-analysis/3`. It retains all current result/statistics/lineage fields and adds exactly `request`, the full canonical request/2 object. Analysis ID covers this field as well as the existing unsigned fields. Result/3 requires matching request_digest, minimum_valid_pairs, both reference-derived lineage identities and selector policy. Result/1 and /2 cannot carry request/2 semantics or the additional field; result/3 cannot embed request/1. Existing lineage/1 (same session) and lineage/2 (explicit continuation) remain unchanged and retain their existing proof and parent requirements. There is no implicit session translation.

The computation schema remains internal /1 because its numeric fields are unchanged and its request_digest binds the explicit new policy. Existing AnalysisRequest constructors remain source-compatible by making the new policy fields absent/default for v1. Serialization of old instances is byte-compatible. Bundles retain their existing schema and embed the versioned request/result; bundle request and embedded result request must agree exactly. Existing VerificationPlan and continuation schemas do not change.

## Native scalar validity

Use the exact existing producer representation from `debug/model.py` and `debug/read.py`, with keys `{bitWidth,expression,rawHex,typeName,value}` and no extras. Only a unique requested Watch sample with status OK is eligible.

- expression equals the request selector exactly; no normalization or substitution.
- bitWidth is an exact integer in {8,16,32}; typeName equals `uint{bitWidth}_register`.
- value is an exact integer, not bool, in [0,2**bitWidth-1].
- rawHex is lower-case `0x` followed by exactly bitWidth/4 hexadecimal digits; its integer equals value.
- A pair must have the same width and type. Unsupported width, float/string/bool values, malformed hex, inconsistent shape, non-OK status and differing type/width are excluded, not coerced.

Do not expand variable/float/64-bit support in this slice. Invalid samples contribute existing exclusions and can produce INSUFFICIENT_VALID_PAIRS; they are not accepted merely because the envelope is authentic.

## Time matching and counts

After existing window and identity authentication, derive each offset from its unchanged scheduled_unix_ns minus the first batch's scheduled_unix_ns. For request/2 timestamps must be strictly increasing; duplicates or reversals reject the malformed window through existing typed analysis validation. Existing captured-time/sequence/ref checks remain mandatory.

An eligible edge joins before/after offsets with absolute difference <= max_pairing_skew_ns (inclusive). Accept a time pair only when each endpoint has exactly one eligible edge to the other side. Ambiguity excludes all affected candidates; do not resolve nearest ties, greedily steal a sample, or pick a best-looking value. Each accepted sample is used once. Process accepted pairs in before-time order. Invalid value samples still participate in time ambiguity detection so value filtering cannot manufacture a unique match.

Let B and A be window lengths and T the number of accepted unique time pairs. aligned_position_count=B+A-T. aligned_pair_count is the number of those pairs with compatible valid native values. excluded_position_count=aligned_position_count-aligned_pair_count. This counts a valid time match as one position and every unpaired endpoint as one position. No edge/ambiguous endpoint is silently dropped. The existing computation rules then apply: below the requested minimum is INVALID/INCONCLUSIVE; sufficient pairs plus any exclusion is DEGRADED; sufficient with zero exclusions is VALID. First/last/min/max/delta/changed preserve their current meaning over valid pairs. No new inference about firmware correctness is added to changed=true.

Bounds remain 1024 batches per window, 10,000 total values and 2048 positions. Matching must be deterministic and bounded. This is a finite offline operation, not a new scheduler. The 5ms ceiling is a small explicit allowance relative to the accepted 100ms schedule; observed maximum corresponding skew is 1.4682ms. These observations justify the policy but do not replace algorithmic matching.

## Dependency direction and persisted trust

Monitor depends on Toolkit. Toolkit must not import Monitor. Introduce at most one small pure module `stm32_toolkit/monitor_analysis_contract.py` for the new native policy validation, pairing and deterministic statistics, consumed by both Monitor and Toolkit readers. It is a narrow calculation contract, not a diagnostic framework or additional tool. Existing authenticated transcript/reference readers remain the evidence authority; the helper does no I/O, hardware or evidence publication. Reuse the existing canonical replay contract and validators.

Monitor authenticates windows with existing readers before calculating. Toolkit persisted consumers authenticate each original transcript, publication/TestRun and continuation proof as before, verify the embedded request against the authenticated references and lineage, then recompute result/3 statistics with the same pure helper and compare the entire computation. Self-consistent rehashing cannot authorize changed statistics, mismatched request/ref/digest, broadened policy, downgraded schema, wrong proof or missing parents. Diagnostic completion, Diagnostic fresh read, and v3 final graph validation all retain this protection; none may merely whitelist /3. Refactor only duplicated new-version validation needed to preserve one source of numeric truth.

Error categories remain existing typed request/analysis/evidence/identity errors at their current public boundaries. Invalid request/policy is request-invalid, invalid authenticated graph is the existing corruption/identity category, and insufficient eligible numeric pairs is the existing recorded inconclusive result. No catch-all success or fallback to legacy decoding.

## Evidence requirements and acceptance boundary

Implementation owner runs focused native validity, alignment boundary/ambiguity/count/ordering, v1 compatibility, new result round-trip and downgrade/request/stat tamper tests. Exercise actual persisted Diagnostic and continuation readers, not only the pure helper. Independent review uses a clean worktree at the returned CodeHead and examines accepted-base-to-CodeHead in full.

Primary/integration owner uses a hash-verified isolated copy of current business evidence for the existing public compare -> bundle -> verification -> final v3 checkpoint chain, then a fresh process reads it. The P3/P4 refs and original identities remain exact. Retain minimum_valid_pairs=297 and 5,000,000ns skew in this explicit request. Original data-root file bytes must remain unchanged; all writes target this slice's isolated copy. The copied chain demonstrates software compatibility with real evidence; it does not complete the actual production acceptance ledger or constitute new hardware evidence.

Reuse prior deployment, Target, Monitor capture, continuation proof, T9, attempt7 and unrelated regression evidence where behavior is unchanged. No full release matrix, rebuild/reflash, resampling, or active runtime switch is required. Follow `docs/testing/standard-test-procedure.md`; update its changed offline entry contract and current checkpoint after independent review. Preserve all prior cleanup holds and minimum useful failure evidence.
